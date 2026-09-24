"""Duo — 둘이서 3+3 취향 교집합 → 근처 1곳."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from . import brands, engine
from .config import public_base_url
from .radius import haversine_m, session_radius_m, walk_minutes

TASTE_CATS: dict[str, tuple[str, ...]] = {
    "jjajang": ("chinese",),
    "jjamppong": ("chinese", "noodle"),
    "sundaeguk": ("korean",),
    "gukbap": ("korean",),
    "bibimbap": ("korean",),
    "tteokbokki": ("korean",),
    "kalguksu": ("noodle", "korean"),
    "naengmyeon": ("noodle", "korean"),
    "ramen": ("japanese", "noodle"),
    "sushi": ("japanese",),
    "donkatsu": ("japanese",),
    "udon": ("japanese", "noodle"),
    "pork": ("meat", "korean"),
    "galbi": ("meat",),
    "chicken": ("meat",),
    "pizza": ("western",),
    "pasta": ("western",),
    "burger": ("western",),
}


@dataclass
class DuoRoom:
    id: str
    lat: float
    lng: float
    intent: str
    weather: str
    host_taste: list[str] = field(default_factory=list)
    guest_taste: list[str] = field(default_factory=list)
    host_name: str = "호스트"
    guest_name: str = ""
    status: str = "waiting"  # waiting | ready | matched
    pick: dict[str, Any] | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


ROOMS: dict[str, DuoRoom] = {}


def _cats(taste: list[str]) -> set[str]:
    out: set[str] = set()
    for t in taste:
        out.update(TASTE_CATS.get(t, ()))
    return out


def create_room(
    *,
    lat: float,
    lng: float,
    intent: str,
    weather: str,
    host_taste: list[str],
    host_name: str = "호스트",
) -> DuoRoom:
    room = DuoRoom(
        id=uuid.uuid4().hex[:8],
        lat=lat,
        lng=lng,
        intent=intent,
        weather=weather,
        host_taste=list(host_taste)[:6],
        host_name=host_name or "호스트",
        status="waiting",
    )
    ROOMS[room.id] = room
    return room


def get_room(duo_id: str) -> DuoRoom | None:
    return ROOMS.get(duo_id)


def join_room(
    duo_id: str,
    *,
    guest_taste: list[str],
    guest_name: str = "게스트",
) -> DuoRoom:
    room = ROOMS.get(duo_id)
    if not room:
        raise KeyError("duo not found")
    if room.status == "matched" and room.pick:
        return room
    room.guest_taste = list(guest_taste)[:6]
    room.guest_name = guest_name or "게스트"
    room.status = "ready"
    room.pick = _resolve_pick(room)
    room.status = "matched" if room.pick else "ready"
    return room


def _resolve_brand_pick(room: DuoRoom) -> dict[str, Any] | None:
    """배달 듀오 — 솔로와 같은 프랜차이즈 카탈로그에서 고른다.

    지도로 보내면 둘 다 배달앱을 다시 켜야 한다. 브랜드 주문 페이지로 보낸다.
    """
    host_c = _cats(room.host_taste)
    guest_c = _cats(room.guest_taste)
    inter = host_c & guest_c
    union = host_c | guest_c
    taste = list(dict.fromkeys(room.host_taste + room.guest_taste))

    scored: list[tuple[float, dict]] = []
    for p in brands.brand_places(taste):
        cat = p.get("category") or ""
        score = float(p.get("rating", 4.0))
        if inter and cat in inter:
            score += 5.0
        elif union and cat in union:
            score += 2.0
        if p.get("taste_match"):
            score += 1.5
        scored.append((score, p))
    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    p = scored[0][1]
    reason = (
        f"둘의 취향 교집합({', '.join(sorted(inter)) or '공통'})으로 "
        f"배달 브랜드 1곳을 골랐어요"
    )
    return {
        "place_id": p["place_id"],
        "place_name": p["name"],
        "menu_name": p["menu_name"],
        "image_url": "",
        "distance_m": None,
        "eta_label": p["channel"],
        "category": p["category"],
        "intersection": sorted(inter),
        "union": sorted(union),
        "match_reason": reason,
        "map_url": p["order_url"],
        "inventory_source": "brand",
        "host_taste": room.host_taste,
        "guest_taste": room.guest_taste,
    }


def _resolve_pick(room: DuoRoom) -> dict[str, Any] | None:
    """초대자 좌표·intent·weather 고정. 취향 교집합 카테고리 우선."""
    if room.intent == "delivery":
        return _resolve_brand_pick(room)

    places, _tier, source = engine.load_inventory(
        room.lat, room.lng, room.intent, room.weather, room.host_taste
    )
    host_c = _cats(room.host_taste)
    guest_c = _cats(room.guest_taste)
    inter = host_c & guest_c
    union = host_c | guest_c
    radius = session_radius_m("visit", room.weather)  # type: ignore[arg-type]

    scored: list[tuple[float, dict, float]] = []
    for p in places:
        if not p.get("open_now", True):
            continue
        dist = haversine_m(room.lat, room.lng, p["lat"], p["lng"])
        if dist > radius:
            continue
        cat = p.get("category") or ""
        score = 10.0 - dist / 100.0 + float(p.get("rating", 4.0))
        if inter and cat in inter:
            score += 5.0
        elif union and cat in union:
            score += 2.0
        if p.get("taste_match"):
            score += 1.5
        scored.append((score, p, dist))

    if not scored:
        # 반경 밖 폴백: 전체 풀에서 최단거리 1곳
        for p in places:
            dist = haversine_m(room.lat, room.lng, p["lat"], p["lng"])
            scored.append((1000 - dist, p, dist))
    if not scored:
        return None

    scored.sort(key=lambda x: x[0], reverse=True)
    _sc, p, dist = scored[0]
    name = quote(p["name"])
    if p.get("kakao_url"):
        map_url = p["kakao_url"]
    else:
        map_url = (
            f"https://map.naver.com/v5/search/{name}"
            f"/place?c={p['lng']},{p['lat']},15,0,0,0,dh"
        )
    reason = (
        f"둘의 취향 교집합({', '.join(sorted(inter)) or '공통'})으로 "
        f"걸어갈 수 있는 1곳을 골랐어요"
    )
    return {
        "place_id": p.get("place_id"),
        "place_name": p["name"],
        "menu_name": p.get("menu_name", ""),
        "image_url": p.get("image_url", ""),
        "distance_m": int(dist),
        "eta_label": f"도보 약 {walk_minutes(dist)}분",
        "category": p.get("category"),
        "intersection": sorted(inter),
        "union": sorted(union),
        "match_reason": reason,
        "map_url": map_url,
        "inventory_source": source,
        "host_taste": room.host_taste,
        "guest_taste": room.guest_taste,
    }


def payload(room: DuoRoom, base_url: str) -> dict[str, Any]:
    base = public_base_url(base_url)
    return {
        "id": room.id,
        "status": room.status,
        "intent": room.intent,
        "weather": room.weather,
        "host_name": room.host_name,
        "guest_name": room.guest_name,
        "host_taste": room.host_taste,
        "guest_taste": room.guest_taste,
        "invite_url": f"{base}/duo/{room.id}",
        "invite_path": f"/duo/{room.id}",
        "pick": room.pick,
        "locked": {
            "lat": room.lat,
            "lng": room.lng,
            "intent": room.intent,
            "weather": room.weather,
            "note": "반경·모드는 초대자 기준 고정",
        },
    }
