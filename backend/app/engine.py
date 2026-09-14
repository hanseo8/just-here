"""세션 · 랭킹 · 허브/전국 2티어 인벤토리."""
from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

from . import kakao
from .geo import HUB_ID, resolve_tier, tier_copy, tier_label
from .place_meta import enrich_place_fields
from .radius import (
    card_radius_m,
    delivery_eta_minutes,
    haversine_m,
    session_radius_m,
    walk_minutes,
)
from .seed import CENTER_LAT, CENTER_LNG, PLACES


@dataclass
class Session:
    id: str
    lat: float
    lng: float
    intent: str
    weather: str
    tier: str = "national_light"
    hub_id: str | None = None
    taste: list[str] = field(default_factory=list)
    nope_tags: dict[str, float] = field(default_factory=dict)
    nope_categories: dict[str, float] = field(default_factory=dict)
    consecutive_nopes: int = 0
    left_swipe_count: int = 0
    right_swipe_count: int = 0
    card_shown_at: float | None = None  # time.time() when top card shown
    category_path: list[str] = field(default_factory=list)
    herbivore_streak: int = 0
    perfect_slots_left: int = 5
    seen_menu_ids: set[str] = field(default_factory=set)
    force_gold_once: bool = False
    places: list[dict] = field(default_factory=list)
    inventory_source: str = "seed"  # seed | kakao | seed_fallback
    pool_radius_m: int = 0  # 인벤토리를 받아 둔 상한 반경


SESSIONS: dict[str, Session] = {}


def _hub_places_absolute() -> list[dict]:
    """송도 고정 좌표 큐레이션 재고."""
    out = []
    for raw in PLACES:
        p = copy.deepcopy(raw)
        p["source"] = "hub_seed"
        p["tier"] = "hub_full"
        out.append(p)
    return out


def _national_fallback_anchored(user_lat: float, user_lng: float) -> list[dict]:
    """카카오 키 없을 때: 상대 오프셋으로 라이트 재고 (빈피드 방지)."""
    out = []
    for raw in PLACES:
        p = copy.deepcopy(raw)
        p["lat"] = user_lat + (raw["lat"] - CENTER_LAT)
        p["lng"] = user_lng + (raw["lng"] - CENTER_LNG)
        p["source"] = "seed_fallback"
        p["tier"] = "national_light"
        p["tags"] = ["#전국_라이트"]
        p["review"] = "라이트 모드 임시 카드 — 카카오 키 연결 시 실제 주변 상호로 교체"
        out.append(p)
    return out


def _places_in_radius(
    places: list[dict], lat: float, lng: float, intent: str, weather: str
) -> list[dict]:
    pool_r = session_radius_m(intent, weather)  # type: ignore[arg-type]
    hit = []
    for p in places:
        if not p.get("open_now", True):
            continue
        if intent == "delivery" and not p.get("delivery_available", True):
            continue
        dist = haversine_m(lat, lng, p["lat"], p["lng"])
        allow_r = card_radius_m(
            intent,  # type: ignore[arg-type]
            weather,  # type: ignore[arg-type]
            float(p.get("delivery_sensitivity", 0.5)),
        )
        if dist <= pool_r and dist <= allow_r:
            hit.append(p)
    return hit


def _fetch_kakao(lat: float, lng: float, radius: int) -> list[dict]:
    if not kakao.kakao_configured():
        return []
    try:
        return kakao.fetch_nearby_places(lat, lng, radius_m=radius, limit=30)
    except Exception:
        return []


def _fetch_kakao_taste(lat: float, lng: float, radius: int, taste: list[str]) -> list[dict]:
    if not kakao.kakao_configured() or not taste:
        return []
    try:
        return kakao.fetch_by_taste(lat, lng, radius_m=radius, taste=taste)
    except Exception:
        return []


def _fetch_kakao_block(
    lat: float, lng: float, radius: int, taste: list[str]
) -> tuple[list[dict], list[dict]]:
    if not kakao.kakao_configured():
        return [], []
    try:
        return kakao.fetch_inventory_block(lat, lng, radius, taste or [])
    except Exception:
        return _fetch_kakao_taste(lat, lng, radius, taste), _fetch_kakao(lat, lng, radius)


def _dedupe_places(places: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out = []
    for p in places:
        key = p.get("place_id") or p.get("name", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def load_inventory(
    lat: float,
    lng: float,
    intent: str,
    weather: str,
    taste: list[str] | None = None,
) -> tuple[list[dict], str, str]:
    """
    덱 구성:
      1) 앞쪽 — 허브 큐레이션(반경 안) 또는 없으면 비움
      2) 뒤쪽 — 카카오 실주변 (취향 카테고리 맞춤 → 일반 근처 순)

    후보 풀은 항상 배달 상한 반경으로 받아 두고, 방문은 build_cards에서 700m 컷.
    → 방문↔배달 토글 시 카카오 재조회 없이 즉시 전환.
    """
    taste = taste or []
    tier = resolve_tier(lat, lng)
    # intent 인자 유지(호환). 풀 반경은 배달 상한 고정.
    _ = intent
    pool_r = session_radius_m("delivery", weather)  # type: ignore[arg-type]

    primary: list[dict] = []
    source = "kakao"

    if tier == "hub_full":
        hub = _hub_places_absolute()
        primary = _places_in_radius(hub, lat, lng, "delivery", weather)
        if primary:
            source = "hub+kakao"
        else:
            source = "kakao"

    # 카카오: 취향 + 일반 주변 병렬
    matched, nearby = _fetch_kakao_block(lat, lng, pool_r, taste)

    # 취향 맞춤을 카카오 블록 앞쪽에, 일반 주변을 그 뒤(전체 리스트의 마지막 쪽)
    kakao_block = _dedupe_places(matched + nearby)
    for p in kakao_block:
        p["tier"] = tier

    if not primary and not kakao_block:
        # 완전 실패 시에만 폴백
        anchored = _national_fallback_anchored(lat, lng)
        for p in anchored:
            p["tier"] = tier
        return anchored, tier, "seed_fallback"

    merged = _dedupe_places(primary + kakao_block)
    if primary and kakao_block:
        source = "hub+kakao" if tier == "hub_full" else "kakao"
    elif kakao_block:
        source = "kakao"
    else:
        source = "hub_seed"

    return merged, tier, source


def apply_intent(session: Session, intent: str) -> None:
    """모드만 바꿀 때 — 카카오 재조회 없이 반경 필터만 바꿈."""
    if intent == session.intent:
        return
    session.intent = intent
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0
    session.force_gold_once = False
    # 예전(좁은) 풀만 가진 세션이 배달로 넓힐 때만 1회 재조회
    need = session_radius_m("delivery", session.weather)  # type: ignore[arg-type]
    if intent == "delivery" and session.pool_radius_m < need:
        refresh_inventory(session)


def create_session(
    lat: float, lng: float, intent: str, weather: str, taste: list[str] | None = None
) -> Session:
    places, tier, source = load_inventory(lat, lng, intent, weather, taste)
    s = Session(
        id=str(uuid.uuid4()),
        lat=lat,
        lng=lng,
        intent=intent,
        weather=weather,
        tier=tier,
        hub_id=HUB_ID if tier == "hub_full" else None,
        taste=taste or [],
        places=places,
        inventory_source=source,
        pool_radius_m=session_radius_m("delivery", weather),  # type: ignore[arg-type]
    )
    SESSIONS[s.id] = s
    return s


def get_session(session_id: str) -> Session | None:
    return SESSIONS.get(session_id)


def reanchor_session(session: Session, lat: float, lng: float) -> bool:
    moved = haversine_m(session.lat, session.lng, lat, lng)
    session.lat = lat
    session.lng = lng
    new_tier = resolve_tier(lat, lng)
    tier_changed = new_tier != session.tier

    if moved < 50 and not tier_changed:
        return False

    places, tier, source = load_inventory(
        lat, lng, session.intent, session.weather, session.taste
    )
    session.tier = tier
    session.hub_id = HUB_ID if tier == "hub_full" else None
    session.places = places
    session.inventory_source = source
    session.pool_radius_m = session_radius_m("delivery", session.weather)  # type: ignore[arg-type]
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0
    session.perfect_slots_left = 5
    return True


def refresh_inventory(session: Session) -> None:
    """날씨·위치 등으로 풀 재조회가 필요할 때."""
    places, tier, source = load_inventory(
        session.lat, session.lng, session.intent, session.weather, session.taste
    )
    session.tier = tier
    session.hub_id = HUB_ID if tier == "hub_full" else None
    session.places = places
    session.inventory_source = source
    session.pool_radius_m = session_radius_m("delivery", session.weather)  # type: ignore[arg-type]
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0


def _taste_boost(place: dict, taste: list[str]) -> float:
    if place.get("taste_match"):
        return 2.0
    if not taste:
        return 0.0
    cat = place.get("category", "")
    boost = 0.0
    mapping = {
        "korean": ("korean",),
        "chinese": ("chinese",),
        "japanese": ("japanese",),
        "western": ("western",),
        "snack": ("korean", "noodle"),
        "mexican": ("western",),
        "meat": ("meat",),
        "asian": ("asian", "japanese", "chinese"),
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
    blob = f"{place.get('menu_name', '')} {place.get('name', '')} {' '.join(place.get('tags') or [])}"
    for t in taste:
        if t == cat:
            boost += 1.6
            continue
        if t == "spicy" and any(x in blob for x in ("매운", "짬뽕", "떡볶", "불닭", "마라")):
            boost += 0.9
            continue
        if t == "mild" and any(x in blob for x in ("국밥", "백반", "설렁", "죽", "담백")):
            boost += 0.7
            continue
        cats = mapping.get(t, ())
        if cat in cats:
            boost += 1.2
    return boost


def _score(place: dict, distance_m: float, session: Session) -> float:
    score = 10.0 - distance_m / 100.0
    score += place.get("rating", 4.0)
    score += _taste_boost(place, session.taste)
    for tag in place.get("tags", []):
        score -= session.nope_tags.get(tag, 0.0)
    score -= session.nope_categories.get(place.get("category", ""), 0.0) * 0.8
    if session.intent == "delivery" and place.get("delivery_sensitivity", 0) >= 0.8:
        score -= distance_m / 200.0
    if place.get("source") == "hub_seed":
        score += 0.5
    return score


def _track_category(session: Session, place: dict) -> None:
    cat = place.get("category") or "other"
    session.category_path.append(str(cat))
    # 초식 연속: 클린 메뉴를 넘기며 쌓고, 아니면 리셋
    blob = f"{place.get('menu_name','')} {place.get('name','')} {' '.join(place.get('tags') or [])}"
    herb_keys = ("샐러드", "포케", "채식", "채소", "salad", "poke", "veggie")
    if any(k.lower() in blob.lower() for k in herb_keys):
        session.herbivore_streak += 1
    else:
        session.herbivore_streak = 0


def apply_nope(session: Session, place: dict) -> bool:
    session.consecutive_nopes += 1
    session.left_swipe_count += 1
    session.seen_menu_ids.add(place["menu_id"])
    session.card_shown_at = time.time()  # 다음 카드 노출 시각
    _track_category(session, place)
    for tag in place.get("tags", []):
        session.nope_tags[tag] = session.nope_tags.get(tag, 0.0) + 1.0
    cat = place.get("category") or "other"
    session.nope_categories[cat] = session.nope_categories.get(cat, 0.0) + 0.8
    if session.consecutive_nopes >= 5:
        session.force_gold_once = True
        session.consecutive_nopes = 0
        return True
    return False


def apply_lets_go(session: Session, place: dict) -> dict:
    session.consecutive_nopes = 0
    session.right_swipe_count += 1
    session.seen_menu_ids.add(place["menu_id"])
    _track_category(session, place)
    if session.perfect_slots_left > 0:
        session.perfect_slots_left -= 1
    return build_handoff(session, place)


def decision_seconds(session: Session) -> float | None:
    if session.card_shown_at is None:
        return None
    return max(0.0, time.time() - session.card_shown_at)


def mark_deck_shown(session: Session) -> None:
    """피드가 클라이언트에 내려갈 때 호출 — 결정 시간 측정 시작."""
    session.card_shown_at = time.time()


def _diversify_by_category(
    items: list[tuple[float, dict, float, int]],
) -> list[tuple[float, dict, float, int]]:
    """같은 카테고리가 연속되지 않게 라운드로빈."""
    from collections import defaultdict

    buckets: dict[str, list] = defaultdict(list)
    for item in items:
        buckets[item[1].get("category") or "other"].append(item)
    out: list[tuple[float, dict, float, int]] = []
    while buckets:
        empty: list[str] = []
        for cat in list(buckets.keys()):
            if not buckets[cat]:
                empty.append(cat)
                continue
            out.append(buckets[cat].pop(0))
        for cat in empty:
            buckets.pop(cat, None)
    return out


def build_cards(session: Session, limit: int = 20) -> tuple[list[dict], int, bool]:
    pool_r = session_radius_m(session.intent, session.weather)  # type: ignore[arg-type]
    show_gold = session.force_gold_once
    inventory = session.places or []
    primary: list[tuple[float, dict, float, int]] = []
    kakao_cands: list[tuple[float, dict, float, int]] = []

    for p in inventory:
        if not p.get("open_now", True):
            continue
        if session.intent == "delivery" and not p.get("delivery_available", True):
            continue
        dist = haversine_m(session.lat, session.lng, p["lat"], p["lng"])
        allow_r = card_radius_m(
            session.intent,  # type: ignore[arg-type]
            session.weather,  # type: ignore[arg-type]
            float(p.get("delivery_sensitivity", 0.5)),
        )
        if dist > pool_r or dist > allow_r:
            continue
        if p["menu_id"] in session.seen_menu_ids and not show_gold:
            continue
        sc = _score(p, dist, session)
        item = (sc, p, dist, allow_r)
        if p.get("source") == "kakao":
            kakao_cands.append(item)
        else:
            primary.append(item)

    # 앞: 큐레이션 / 뒤: 카카오(취향맞춤 우선 + 카테고리 다양화)
    primary.sort(key=lambda x: x[0], reverse=True)
    taste_first = [x for x in kakao_cands if x[1].get("taste_match")]
    rest = [x for x in kakao_cands if not x[1].get("taste_match")]
    taste_first.sort(key=lambda x: x[0], reverse=True)
    rest.sort(key=lambda x: x[0], reverse=True)
    kakao_ordered = _diversify_by_category(taste_first) + _diversify_by_category(rest)
    candidates = primary + kakao_ordered

    if not candidates and session.seen_menu_ids and not show_gold:
        session.seen_menu_ids.clear()
        session.consecutive_nopes = 0
        if session.perfect_slots_left <= 0:
            session.perfect_slots_left = 5
        return build_cards(session, limit)

    if show_gold:
        session.force_gold_once = False
        gold_pool = list(primary) + list(kakao_cands)
        if not gold_pool:
            for p in inventory:
                if not p.get("open_now", True):
                    continue
                if session.intent == "delivery" and not p.get("delivery_available", True):
                    continue
                dist = haversine_m(session.lat, session.lng, p["lat"], p["lng"])
                allow_r = card_radius_m(
                    session.intent,  # type: ignore[arg-type]
                    session.weather,  # type: ignore[arg-type]
                    float(p.get("delivery_sensitivity", 0.5)),
                )
                if dist > pool_r or dist > allow_r:
                    continue
                gold_pool.append((_score(p, dist, session), p, dist, allow_r))
        gold_pool.sort(key=lambda x: x[0], reverse=True)
        candidates = gold_pool[:1] if gold_pool else []

    if not candidates and not show_gold:
        places, tier, source = load_inventory(
            session.lat,
            session.lng,
            session.intent,
            session.weather,
            session.taste,
        )
        session.places = places
        session.tier = tier
        session.inventory_source = source
        if places:
            return build_cards(session, limit)

    cards = []
    for i, (sc, p, dist, allow_r) in enumerate(candidates[:limit]):
        tags = p.get("tags") or ["#그냥여기"]
        meta = enrich_place_fields(p)
        cards.append(
            {
                "card_id": str(uuid.uuid4()),
                "place_id": p["place_id"],
                "menu_id": p["menu_id"],
                "place_name": p["name"],
                "menu_name": p["menu_name"],
                "image_url": p.get("image_url") or "",
                "has_photo": bool(p.get("has_photo", bool(p.get("image_url")))),
                "distance_m": int(dist),
                "eta_label": (
                    f"도보 {walk_minutes(dist)}분"
                    if session.intent == "visit"
                    else f"배달 약 {delivery_eta_minutes(dist)}분"
                ),
                "hashtag": tags[0],
                "delivery_sensitivity": meta["delivery_sensitivity"],
                "sensitivity_level": meta["sensitivity_level"],
                "sensitivity_percent": meta["sensitivity_percent"],
                "sensitivity_tip": meta["sensitivity_tip"],
                "card_radius_m": allow_r,
                "rating": meta["rating"],
                "hours": meta["hours"],
                "address": meta["address"],
                "price_krw": meta["price_krw"],
                "price_band": meta["price_band"],
                "review": meta["review"],
                "is_gold": bool(show_gold and i == 0),
                "taste_match": bool(p.get("taste_match")),
                "lat": p["lat"],
                "lng": p["lng"],
                "source": p.get("source", "unknown"),
                "tier": session.tier,
                "_score": round(sc, 2),
            }
        )
    if cards:
        mark_deck_shown(session)
        return cards, pool_r, show_gold

    # 빈 피드 방어: 반경 무시하고 시드 폴백을 현재 좌표에 붙여 최소 덱 보장
    if not getattr(session, "_empty_rescue", False):
        session._empty_rescue = True  # type: ignore[attr-defined]
        session.seen_menu_ids.clear()
        session.places = _national_fallback_anchored(session.lat, session.lng)
        session.inventory_source = "seed_fallback"
        session.tier = session.tier or "national_light"
        rescued, r2, g2 = build_cards(session, limit)
        session._empty_rescue = False  # type: ignore[attr-defined]
        if rescued:
            return rescued, max(pool_r, r2), g2

    return cards, pool_r, show_gold


def build_handoff(session: Session, place: dict) -> dict:
    """핸드오프 URL.

    배민 딥링크는 아직 보류 — 방문/배달 모두 지도로 안내.
    """
    name = quote(place["name"])
    if place.get("kakao_url"):
        url = place["kakao_url"]
        provider = "kakao_map"
    else:
        url = (
            f"https://map.naver.com/v5/search/{name}"
            f"/place?c={place['lng']},{place['lat']},15,0,0,0,dh"
        )
        provider = "naver_map"

    if session.intent == "visit":
        return {
            "intent": "visit",
            "provider": provider,
            "url": url,
            "cta": "지도에서 보기",
            "auto_open": False,
        }

    # 배달: 배민 연결 전까지 지도만
    return {
        "intent": "delivery",
        "provider": provider,
        "url": url,
        "cta": "지도에서 보기",
        "auto_open": False,
        "baemin_ready": False,
        "note": "배달 앱 연결은 준비 중이에요. 먼저 위치를 확인해 보세요.",
    }


def find_place(session: Session, menu_id: str) -> dict | None:
    for p in session.places:
        if p["menu_id"] == menu_id:
            return p
    return None


def session_meta(session: Session) -> dict:
    return {
        "tier": session.tier,
        "tier_label": tier_label(session.tier),  # type: ignore[arg-type]
        "hub_id": session.hub_id,
        "inventory_source": session.inventory_source,
        "copy": tier_copy(session.tier),  # type: ignore[arg-type]
        "kakao_enabled": kakao.kakao_configured(),
    }
