from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from . import duo
from . import engine
from . import kakao
from . import share
from . import titles
from . import weather as weather_api
from .radius import KST, suggest_intent, suggest_intent_reason
from .seed import CENTER_LAT, CENTER_LNG, sample_taste_pairs

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"

app = FastAPI(title="그냥여기 MVP", version="0.3.0")
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SwipeBody(BaseModel):
    session_id: str
    card_id: str
    menu_id: str
    action: Literal["nope", "lets_go"]


class SessionStartBody(BaseModel):
    lat: float
    lng: float
    intent: Literal["visit", "delivery"] = "visit"
    weather: Literal["clear", "rain", "snow", "hot", "cold"] = "clear"
    taste: list[str] = Field(default_factory=list)


def _strip(cards: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]


def _feed_payload(s: engine.Session, cards: list[dict], radius: int, gold: bool = False) -> dict:
    meta = engine.session_meta(s)
    return {
        "session_id": s.id,
        "intent": s.intent,
        "weather": s.weather,
        "effective_radius_m": radius,
        "perfect_slots_left": s.perfect_slots_left,
        "copy": meta["copy"],
        "tier": meta["tier"],
        "tier_label": meta["tier_label"],
        "hub_id": meta["hub_id"],
        "inventory_source": meta["inventory_source"],
        "kakao_enabled": meta["kakao_enabled"],
        "nudge": "gold" if gold else None,
        "cards": _strip(cards),
        "empty": len(cards) == 0,
    }


def _build_persona(s: engine.Session, place: dict) -> dict:
    from .radius import haversine_m, session_radius_m

    dist = haversine_m(s.lat, s.lng, place["lat"], place["lng"])
    # enrich price for flexer/value titles
    if "price_krw" not in place:
        from .place_meta import estimated_price_krw

        place = {**place, "price_krw": estimated_price_krw(place)}
    persona = titles.resolve_persona(
        intent=s.intent,
        weather=s.weather,
        left_swipe_count=s.left_swipe_count,
        right_swipe_count=s.right_swipe_count,
        decision_time_seconds=engine.decision_seconds(s),
        distance_m=dist,
        place=place,
        category_path=list(getattr(s, "category_path", []) or []),
        herbivore_streak=int(getattr(s, "herbivore_streak", 0) or 0),
        taste=list(s.taste or []),
    )
    if persona["id"] == "storm_survivor":
        r = session_radius_m(s.intent, s.weather)  # type: ignore[arg-type]
        persona["match_reason"] = f"오늘 비/눈이라 배달 {r}m 이내로 매칭 완료!"
    return persona


def _receipt_title(s: engine.Session, place: dict) -> str:
    return _build_persona(s, place)["title"]


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "just-here-mvp",
        "kakao_enabled": kakao.kakao_configured(),
    }


@app.get("/v1/meta")
def meta():
    return {
        "brand": "그냥여기",
        "copy": "오늘 점심은 그냥여기 어때?",
        "slogan": '메뉴 고민은 사치, 지금 당장 "그냥여기" 어때?',
        "hub": {
            "id": "hub_songdo",
            "label": "인천 송도",
            "lat": CENTER_LAT,
            "lng": CENTER_LNG,
            "radius_m": 4500,
        },
        "tiers": {
            "hub_full": "송도 풀경험 (큐레이션)",
            "national_light": "전국 라이트 (카카오/폴백)",
        },
        "kakao_enabled": kakao.kakao_configured(),
        "taste_pairs": sample_taste_pairs(4),
        "personas": titles.catalog(),
    }


@app.get("/v1/context")
def context(
    weather: Literal["clear", "rain", "snow", "hot", "cold"] | None = None,
    hour: int | None = Query(default=None, ge=0, le=23),
    lat: float | None = None,
    lng: float | None = None,
):
    """날씨·시각 기반 스마트 토글. lat/lng 있으면 Open-Meteo로 실날씨 패치."""
    now = datetime.now(KST)
    h = now.hour if hour is None else hour
    wx_meta: dict = {"source": "manual", "ok": True}
    flag: Literal["clear", "rain", "snow", "hot", "cold"]
    if weather is not None:
        flag = weather
    elif lat is not None and lng is not None:
        wx_meta = weather_api.fetch_weather(lat, lng)
        flag = wx_meta["weather"]  # type: ignore[assignment]
    else:
        flag = "clear"
        wx_meta = {"source": "default", "ok": True}

    intent = suggest_intent(flag, h)
    return {
        "weather": flag,
        "hour": h,
        "local_time": now.isoformat(),
        "suggested_intent": intent,
        "reason": suggest_intent_reason(flag, h, intent),
        "weather_meta": {
            "source": wx_meta.get("source"),
            "ok": wx_meta.get("ok", True),
            "temp_c": wx_meta.get("temp_c"),
            "wmo_code": wx_meta.get("wmo_code"),
        },
    }


@app.post("/v1/session")
def start_session(body: SessionStartBody):
    s = engine.create_session(body.lat, body.lng, body.intent, body.weather, body.taste)
    cards, radius, gold = engine.build_cards(s)
    return _feed_payload(s, cards, radius, gold)


@app.get("/v1/feed")
def feed(
    session_id: str = Query(...),
    intent: Literal["visit", "delivery"] | None = None,
    weather: Literal["clear", "rain", "snow", "hot", "cold"] | None = None,
    lat: float | None = None,
    lng: float | None = None,
):
    s = engine.get_session(session_id)
    if not s:
        raise HTTPException(404, "session not found")

    moved = False
    if lat is not None and lng is not None:
        moved = engine.reanchor_session(s, lat, lng)

    if intent and intent != s.intent:
        # 방문↔배달: 이미 배달 상한으로 받아 둔 풀을 반경만 다시 컷 (카카오 재조회 X)
        engine.apply_intent(s, intent)
    if weather and weather != s.weather:
        s.weather = weather
        if not moved:
            engine.refresh_inventory(s)

    cards, radius, gold = engine.build_cards(s)
    return _feed_payload(s, cards, radius, gold)


class DuoCreateBody(BaseModel):
    lat: float
    lng: float
    intent: Literal["visit", "delivery"] = "visit"
    weather: Literal["clear", "rain", "snow", "hot", "cold"] = "clear"
    taste: list[str] = Field(default_factory=list)
    host_name: str = "호스트"


class DuoJoinBody(BaseModel):
    taste: list[str] = Field(default_factory=list)
    guest_name: str = "게스트"


@app.post("/v1/duo")
def duo_create(body: DuoCreateBody, request: Request):
    if len(body.taste) < 1:
        raise HTTPException(400, "taste required")
    room = duo.create_room(
        lat=body.lat,
        lng=body.lng,
        intent=body.intent,
        weather=body.weather,
        host_taste=body.taste,
        host_name=body.host_name,
    )
    return duo.payload(room, str(request.base_url))


@app.get("/v1/duo/{duo_id}")
def duo_get(duo_id: str, request: Request):
    room = duo.get_room(duo_id)
    if not room:
        raise HTTPException(404, "duo not found")
    return duo.payload(room, str(request.base_url))


@app.post("/v1/duo/{duo_id}/join")
def duo_join(duo_id: str, body: DuoJoinBody, request: Request):
    if len(body.taste) < 1:
        raise HTTPException(400, "taste required")
    try:
        room = duo.join_room(
            duo_id, guest_taste=body.taste, guest_name=body.guest_name
        )
    except KeyError:
        raise HTTPException(404, "duo not found") from None
    return duo.payload(room, str(request.base_url))


@app.get("/duo/{duo_id}")
def duo_landing(duo_id: str):
    path = WEB_DIR / "duo.html"
    if not path.exists():
        raise HTTPException(404, "duo page missing")
    return FileResponse(path)


class ShareReceiptBody(BaseModel):
    title: str
    place_name: str
    menu_name: str
    intent: Literal["visit", "delivery"] = "visit"
    tier: str = ""
    session_id: str | None = None
    sub_text: str = ""
    theme: str = "bg_basic"
    match_reason: str = ""
    persona_id: str = ""
    sticker: str = "🛋️"
    asset_id: str = "bg_basic"


@app.post("/v1/share/receipt")
def create_share_receipt(body: ShareReceiptBody, request: Request):
    r = share.create_receipt(
        title=body.title,
        place_name=body.place_name,
        menu_name=body.menu_name,
        intent=body.intent,
        tier=body.tier,
        sub_text=body.sub_text,
        theme=body.theme,
        match_reason=body.match_reason,
        persona_id=body.persona_id,
        sticker=body.sticker,
        asset_id=body.asset_id or body.theme,
    )
    return share.share_payload(r, str(request.base_url))


@app.get("/v1/share/receipt/{receipt_id}")
def get_share_receipt(receipt_id: str, request: Request):
    r = share.get_receipt(receipt_id)
    if not r:
        raise HTTPException(404, "receipt not found")
    return share.share_payload(r, str(request.base_url))


@app.get("/r/{receipt_id}")
def receipt_landing(receipt_id: str):
    path = WEB_DIR / "receipt.html"
    if not path.exists():
        raise HTTPException(404, "receipt page missing")
    # id는 프론트에서 pathname으로 읽음
    return FileResponse(path)


@app.post("/v1/swipe")
def swipe(body: SwipeBody, request: Request):
    s = engine.get_session(body.session_id)
    if not s:
        raise HTTPException(404, "session not found")
    place = engine.find_place(s, body.menu_id)
    if not place:
        raise HTTPException(404, "menu not found")

    if body.action == "nope":
        engine.apply_nope(s, place)
        cards, radius, gold = engine.build_cards(s)
        return _feed_payload(s, cards, radius, gold)

    handoff = engine.apply_lets_go(s, place)
    persona = _build_persona(s, place)
    title = persona["title"]
    receipt = share.create_receipt(
        title=title,
        place_name=place["name"],
        menu_name=place["menu_name"],
        intent=s.intent,
        tier=s.tier,
        sub_text=persona["sub_text"],
        theme=persona["theme"],
        match_reason=persona["match_reason"],
        persona_id=persona["id"],
        sticker=persona.get("sticker", "🛋️"),
        asset_id=persona.get("asset_id", persona["theme"]),
    )
    return {
        "ok": True,
        "action": "lets_go",
        "perfect_slots_left": s.perfect_slots_left,
        "tier": s.tier,
        "handoff": handoff,
        "receipt_title": title,
        "persona": persona,
        "place_name": place["name"],
        "menu_name": place["menu_name"],
        "receipt": share.share_payload(receipt, str(request.base_url)),
    }


if WEB_DIR.is_dir():

    @app.get("/manifest.webmanifest")
    def web_manifest():
        path = WEB_DIR / "manifest.webmanifest"
        return FileResponse(path, media_type="application/manifest+json")

    @app.get("/sw.js")
    def service_worker():
        path = WEB_DIR / "sw.js"
        return FileResponse(
            path,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return {"message": "web UI missing", "docs": "/docs"}
    return FileResponse(index_path)
