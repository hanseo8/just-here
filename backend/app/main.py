from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from . import analytics
from . import deals
from . import duo
from . import engine
from . import guest_token
from . import google_places
from . import kakao
from . import share
from . import titles
from . import users
from . import weather as weather_api
from .radius import (
    KST,
    suggest_intent,
    suggest_intent_reason,
    suggest_meal_context,
    suggest_meal_reason,
)
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


@app.middleware("http")
async def hide_internal_review(request: Request, call_next):
    path = request.url.path.lower()
    review = (
        path.startswith("/review-songdo")
        or path.startswith("/v1/review/songdo")
        or path.endswith("/review-songdo.html")
        or path.endswith("/review-songdo.js")
    )
    if not review:
        return await call_next(request)
    from .verified_menus import review_exposed

    token = request.query_params.get("token") or request.headers.get("x-admin-token")
    if review_exposed() or analytics.admin_token_ok(token):
        return await call_next(request)
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.on_event("startup")
def _bootstrap_verified_menus() -> None:
    try:
        from .verified_menus import bootstrap_persistent_catalog

        bootstrap_persistent_catalog()
    except Exception:
        return


class SwipeBody(BaseModel):
    session_id: str
    card_id: str
    menu_id: str
    action: Literal["nope", "lets_go"]
    pack_id: str | None = None
    meal_context: Literal["meal", "late_night", "anju"] | None = None
    action_id: str | None = None
    epoch: int | None = None
    uid: str | None = None


class SessionStartBody(BaseModel):
    lat: float
    lng: float
    intent: Literal["visit", "delivery"] = "visit"
    weather: Literal["clear", "rain", "snow", "hot", "cold"] = "clear"
    taste: list[str] = Field(default_factory=list)
    meal_context: Literal["meal", "late_night", "anju"] = "meal"
    uid: str | None = None


class GuestAuthBody(BaseModel):
    device_id: str
    firebase_uid: str | None = None


class KakaoLinkBody(BaseModel):
    guest_uid: str
    access_token: str


class KakaoCodeBody(BaseModel):
    guest_uid: str
    code: str
    redirect_uri: str


class TasteSyncBody(BaseModel):
    uid: str
    taste: list[str] = Field(default_factory=list)


class MealConfirmBody(BaseModel):
    uid: str
    menu_id: str = ""
    category: str = ""
    kind: str = ""
    place_name: str = ""
    eaten: bool


class UnlockBody(BaseModel):
    uid: str
    key: Literal["story_gold"]


class ExcludeBody(BaseModel):
    uid: str
    session_id: str | None = None
    kind: str = ""
    category: str = ""
    exclude: bool = True


class AnalyticsEventBody(BaseModel):
    event: str
    uid: str | None = None
    device_id: str | None = None
    props: dict = Field(default_factory=dict)


def _guest_header(request: Request) -> str:
    return (request.headers.get("x-guest-token") or request.headers.get("X-Guest-Token") or "").strip()


def _require_uid(request: Request, uid: str) -> str:
    uid = (uid or "").strip()
    if not uid:
        raise HTTPException(401, "guest token required")
    payload = guest_token.verify(_guest_header(request))
    if not payload or payload.get("uid") != uid:
        raise HTTPException(401, "guest token required")
    return uid


def _stale_response(s: engine.Session) -> JSONResponse:
    cards, radius, gold = engine.present_feed(s)
    payload = _feed_payload(s, cards, radius, gold)
    payload["ok"] = False
    payload["stale"] = True
    return JSONResponse(status_code=409, content=payload)


def _optional_uid(request: Request, uid: str | None) -> str | None:
    if not uid:
        return None
    return _require_uid(request, uid)


def _verified_menu_status() -> dict:
    try:
        from .verified_menus import overlay_status

        return overlay_status()
    except Exception:
        return {"visit_overlay": False, "operational": False}


def _storage_status() -> dict:
    try:
        from . import storage

        return {**storage.snapshot(), "memory": storage.memory_counts()}
    except Exception as exc:
        return {"persistent": False, "error": str(exc)}


def _strip(cards: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]


def _feed_payload(s: engine.Session, cards: list[dict], radius: int, gold: bool = False) -> dict:
    meta = engine.session_meta(s)
    pack = engine.pack_meta(s)
    if pack["adjust_needed"]:
        copy = "어떤 쪽으로 다시 골라볼까요?"
    elif s.intent == "delivery" and s.meal_context == "late_night":
        copy = "야식, 고르면 이 브랜드 주문 화면으로 이어져요"
    elif s.intent == "delivery" and s.meal_context == "anju":
        copy = "술안주, 고르면 이 브랜드 주문 화면으로 이어져요"
    elif s.intent == "delivery":
        copy = "고르면 이 브랜드 주문 화면으로 이어져요"
    elif s.meal_context == "late_night":
        copy = "야식, 한 장씩 골라볼게요"
    elif s.meal_context == "anju":
        copy = "술안주로 한 장씩 골라볼게요"
    else:
        copy = "오늘 뭐 먹을지, 한 장씩 골라볼게요"
    return {
        "session_id": s.id,
        "intent": s.intent,
        "meal_context": s.meal_context,
        "weather": s.weather,
        "effective_radius_m": radius,
        "perfect_slots_left": s.perfect_slots_left,
        "copy": copy,
        "tier": meta["tier"],
        "tier_label": meta["tier_label"],
        "hub_id": meta["hub_id"],
        "inventory_source": meta["inventory_source"],
        "kakao_enabled": meta["kakao_enabled"],
        "nudge": None,
        "cards": _strip(cards),
        "empty": len(cards) == 0 and not pack["adjust_needed"],
        **engine.empty_guide(s),
        **pack,
    }


def _build_persona(s: engine.Session, place: dict) -> dict:
    from .radius import haversine_m

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
    return persona


def _receipt_title(s: engine.Session, place: dict) -> str:
    return _build_persona(s, place)["title"]


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "just-here-mvp",
        "kakao_enabled": kakao.kakao_configured(),
        "auth": "guest_first",
        "storage": _storage_status(),
    }


@app.get("/v1/google/place-photo")
def google_place_photo(token: str = Query(..., min_length=20, max_length=1600)):
    """현재 장소 사진을 서버에서 중계한다. 사진 파일은 서버에 저장하지 않는다."""
    result = google_places.fetch_photo(token)
    if not result:
        raise HTTPException(404, "place photo unavailable")
    content, media_type = result
    return Response(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/v1/google/place-photo/meta")
def google_place_photo_meta(token: str = Query(..., min_length=20, max_length=1600)):
    """사진 출처 표기와 Google 지도 연결을 위한 일회성 메타데이터."""
    result = google_places.metadata(token)
    if not result:
        raise HTTPException(404, "place photo unavailable")
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/v1/analytics/event")
def analytics_event(body: AnalyticsEventBody):
    """클라이언트 퍼널 이벤트 수집 (공개, 허용 이벤트만)."""
    try:
        row = analytics.append_event(
            body.event,
            uid=body.uid or "",
            device_id=body.device_id or "",
            props=body.props or {},
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "ts": row["ts"]}


@app.get("/v1/analytics/summary")
def analytics_summary(
    token: str | None = Query(None),
    days: int = Query(7, ge=1, le=30),
):
    """ADMIN_TOKEN 필요. CTO 대시보드용 집계."""
    if not analytics.admin_token_ok(token):
        raise HTTPException(401, "admin token required")
    return analytics.summarize(since_days=days)


@app.get("/v1/review/songdo")
def review_songdo(
    taste: str = "",
    meal_context: str = "meal",
    prefer: str = "",
):
    """검수용. 운영 추천 랭킹에는 연결하지 않는다."""
    from .verified_menus import review_payload

    tastes = [part.strip() for part in taste.split(",") if part.strip()]
    return review_payload(
        taste=tastes or None,
        meal_context=meal_context or "meal",
        prefer=prefer or None,
    )


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
        "kakao_js_key": (os.getenv("KAKAO_JS_KEY") or "").strip() or None,
        "auth": {
            "mode": "guest_first",
            "firebase_ready": bool((os.getenv("FIREBASE_API_KEY") or "").strip()),
            "kakao_link": True,
            "kakao_client_secret_set": bool((os.getenv("KAKAO_CLIENT_SECRET") or "").strip()),
        },
        "taste_pairs": sample_taste_pairs(4),
        "personas": titles.catalog(),
        "logic_version": engine.LOGIC_VERSION,
        "verified_menus": _verified_menu_status(),
        "storage": _storage_status(),
    }


@app.post("/v1/auth/guest")
def auth_guest(body: GuestAuthBody):
    """1단계: 회원가입 없이 기기 기준 익명 uid 발급/재연결."""
    profile = users.STORE.ensure_guest(body.device_id, firebase_uid=body.firebase_uid)
    token = guest_token.issue(profile["uid"], body.device_id)
    return {
        "ok": True,
        "uid": profile["uid"],
        "auth_type": profile.get("auth_type"),
        "guest_token": token,
        "user": users.STORE.public_profile(profile["uid"]),
    }


def _finish_kakao_link(guest_uid: str, kakao_user: dict, device_id: str = "") -> dict:
    kakao_uid = f"kakao_{kakao_user['kakao_id']}"
    try:
        users.STORE.merge_guest_into(guest_uid, kakao_uid, auth_type="kakao")
    except KeyError:
        raise HTTPException(404, "guest user not found") from None
    if kakao_user.get("nickname"):
        try:
            users.STORE.set_nickname(kakao_uid, kakao_user["nickname"])
        except KeyError:
            pass
    return {
        "ok": True,
        "uid": kakao_uid,
        "auth_type": "kakao",
        "linked_from": guest_uid,
        "guest_token": guest_token.issue(kakao_uid, device_id),
        "user": users.STORE.public_profile(kakao_uid),
    }


@app.post("/v1/auth/kakao/link")
def auth_kakao_link(body: KakaoLinkBody, request: Request):
    """2단계: 액세스 토큰으로 익명 데이터 병합 (레거시)."""
    _require_uid(request, body.guest_uid)
    try:
        kakao_user = users.verify_kakao_access_token(body.access_token)
    except ValueError as e:
        raise HTTPException(401, f"kakao auth failed: {e}") from e
    return _finish_kakao_link(body.guest_uid, kakao_user)


@app.post("/v1/auth/kakao/code")
def auth_kakao_code(body: KakaoCodeBody, request: Request):
    """2단계: SDK v2 authorize 인가코드 → 토큰 교환 후 병합."""
    _require_uid(request, body.guest_uid)
    if not users.STORE.get(body.guest_uid):
        raise HTTPException(404, "guest user not found")
    try:
        kakao_user = users.exchange_kakao_auth_code(body.code, body.redirect_uri)
    except ValueError as e:
        raise HTTPException(401, detail={"error": "kakao_code_exchange", "message": str(e)}) from e
    return _finish_kakao_link(body.guest_uid, kakao_user)


@app.get("/v1/me")
def me(request: Request, uid: str = Query(...)):
    _require_uid(request, uid)
    profile = users.STORE.public_profile(uid)
    if not profile:
        raise HTTPException(404, "user not found")
    return {"ok": True, "user": profile}


@app.post("/v1/me/taste")
def me_taste(body: TasteSyncBody, request: Request):
    _require_uid(request, body.uid)
    try:
        users.STORE.set_taste(body.uid, body.taste)
    except KeyError:
        raise HTTPException(404, "user not found") from None
    return {"ok": True, "user": users.STORE.public_profile(body.uid)}


@app.post("/v1/me/meal")
def me_meal(body: MealConfirmBody, request: Request):
    """선택적 식사 확인 — 선택보다 강한 선호 신호. 안 골라도 된다."""
    uid = _require_uid(request, body.uid)
    action = "ate" if body.eaten else "skip_meal"
    try:
        users.STORE.append_swipe(
            uid,
            {
                "action": action,
                "menu_id": body.menu_id,
                "place_name": body.place_name,
                "category": body.category,
                "kind": body.kind,
            },
        )
    except KeyError:
        raise HTTPException(404, "user not found") from None
    return {"ok": True, "action": action}


@app.post("/v1/me/exclude")
def me_exclude(body: ExcludeBody, request: Request):
    """명시적 '안 먹어요'. 거절보다 강한 제외. 매번 묻지 않는다."""
    uid = _require_uid(request, body.uid)
    keys = engine.exclude_keys(body.kind, body.category)
    if not keys:
        raise HTTPException(400, "kind or category required")
    try:
        users.STORE.set_exclude(uid, keys, exclude=body.exclude)
    except KeyError:
        raise HTTPException(404, "user not found") from None
    s = engine.get_session(body.session_id) if body.session_id else None
    if s:
        engine.apply_exclude(s, keys, exclude=body.exclude)
        cards, radius, gold = engine.present_feed(s)
        payload = _feed_payload(s, cards, radius, gold)
        payload["ok"] = True
        payload["exclude_categories"] = sorted(s.exclude_cats)
        return payload
    profile = users.STORE.public_profile(uid) or {}
    prefs = profile.get("preferences") or {}
    return {
        "ok": True,
        "exclude_categories": list(prefs.get("exclude_categories") or []),
    }


@app.post("/v1/me/unlock")
def me_unlock(body: UnlockBody, request: Request):
    """영수증 코스메틱 해금 (스토리 인증 보상 등)."""
    _require_uid(request, body.uid)
    if not users.STORE.get(body.uid):
        raise HTTPException(404, "user not found")
    profile = users.STORE.add_unlock(body.uid, body.key)
    return {"ok": True, "unlocks": profile.get("unlocks") or []}


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
        "suggested_meal_context": suggest_meal_context(h),
        "meal_reason": suggest_meal_reason(h, suggest_meal_context(h)),
        "weather_meta": {
            "source": wx_meta.get("source"),
            "ok": wx_meta.get("ok", True),
            "temp_c": wx_meta.get("temp_c"),
            "wmo_code": wx_meta.get("wmo_code"),
        },
    }


@app.post("/v1/session")
def start_session(body: SessionStartBody, request: Request):
    uid = _optional_uid(request, body.uid)
    taste = list(body.taste or [])
    signals = None
    if uid:
        stored = users.STORE.get_taste(uid)
        if taste:
            try:
                users.STORE.set_taste(uid, taste)
            except KeyError:
                pass
        else:
            taste = stored
        try:
            signals = users.STORE.taste_signals(uid)
        except KeyError:
            signals = None
    s = engine.create_session(
        body.lat,
        body.lng,
        body.intent,
        body.weather,
        taste,
        meal_context=body.meal_context,
    )
    engine.apply_profile(s, signals, stored_taste=taste)
    cards, radius, gold = engine.present_feed(s)
    return _feed_payload(s, cards, radius, gold)


@app.get("/v1/feed")
def feed(
    session_id: str = Query(...),
    intent: Literal["visit", "delivery"] | None = None,
    weather: Literal["clear", "rain", "snow", "hot", "cold"] | None = None,
    meal_context: Literal["meal", "late_night", "anju"] | None = None,
    lat: float | None = None,
    lng: float | None = None,
):
    with engine.lock_session(session_id):
        return _feed_locked(
            session_id,
            intent=intent,
            weather=weather,
            meal_context=meal_context,
            lat=lat,
            lng=lng,
        )


def _feed_locked(
    session_id: str,
    *,
    intent: str | None,
    weather: str | None,
    meal_context: str | None,
    lat: float | None,
    lng: float | None,
):
    s = engine.get_session(session_id)
    if not s:
        raise HTTPException(404, "session not found")

    moved = False
    if lat is not None and lng is not None:
        moved = engine.reanchor_session(s, lat, lng)

    if intent and intent != s.intent:
        # 방문은 카카오 재고, 배달은 프랜차이즈 카탈로그 — 둘 다 이미 있어 재조회 X
        engine.apply_intent(s, intent)
    if meal_context and meal_context != s.meal_context:
        engine.apply_meal_context(s, meal_context)
    if weather and weather != s.weather:
        s.weather = weather
        if not moved:
            engine.refresh_inventory(s)

    cards, radius, gold = engine.present_feed(s)
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
    if engine.is_preview_session_id(body.session_id):
        raise HTTPException(400, "design preview is isolated")
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


def _replay_or_stale(s: engine.Session, replay: dict | None):
    if replay and replay.get("kind") == "lets_go" and replay.get("payload"):
        return replay["payload"]
    cards, radius, gold = engine.present_feed(s)
    payload = _feed_payload(s, cards, radius, gold)
    if replay:
        payload["replayed"] = True
        payload["action_id"] = replay.get("action_id")
    return payload


@app.post("/v1/swipe")
def swipe(body: SwipeBody, request: Request):
    with engine.lock_session(body.session_id):
        return _swipe_locked(body, request)


def _reject_preview(session_id: str | None):
    if engine.is_preview_session_id(session_id):
        raise HTTPException(400, "design preview is isolated")


def _swipe_locked(body: SwipeBody, request: Request):
    _reject_preview(body.session_id)
    s = engine.get_session(body.session_id)
    if not s:
        raise HTTPException(404, "session not found")
    replay = engine.peek_action(s, body.action_id)
    if replay and replay.get("kind") == body.action:
        return _replay_or_stale(s, replay)
    place = engine.find_place(s, body.menu_id)
    if not place:
        raise HTTPException(404, "menu not found")
    if not engine.accept_action(
        s,
        menu_id=body.menu_id,
        pack_id=body.pack_id,
        meal_context=body.meal_context,
        epoch=body.epoch,
        require_card=True,
    ):
        return _stale_response(s)

    uid = _optional_uid(request, body.uid)
    if uid:
        try:
            users.STORE.append_swipe(
                uid,
                {
                    "action": body.action,
                    "action_id": engine.normalize_action_id(body.action_id),
                    "menu_id": body.menu_id,
                    "place_id": place.get("place_id"),
                    "place_name": place.get("name"),
                    "category": place.get("category"),
                    "kind": place.get("kind") or engine._visit_kind(place),
                    "tags": place.get("tags") or [],
                    "intent": s.intent,
                    "meal_context": s.meal_context,
                    "weather": s.weather,
                    "pack_id": s.pack_id,
                    "logic_version": engine.LOGIC_VERSION,
                    "verified_menu_id": place.get("verified_menu_id") or "",
                    "menu_verified": bool(place.get("menu_verified")),
                },
            )
        except KeyError:
            pass

    if body.action == "nope":
        engine.apply_nope(s, place)
        cards, radius, gold = engine.present_feed(s)
        payload = _feed_payload(s, cards, radius, gold)
        engine.store_action(
            s,
            body.action_id,
            {"kind": "nope", "action_id": engine.normalize_action_id(body.action_id), "menu_id": body.menu_id},
        )
        return payload

    handoff = engine.apply_lets_go(s, place)
    persona = _build_persona(s, place)
    title = persona["title"]
    if uid:
        try:
            users.STORE.earn_title(uid, title, persona.get("id") or "")
        except KeyError:
            pass
    display_menu = engine.card_menu_name(place)
    receipt = share.create_receipt(
        title=title,
        place_name=place["name"],
        menu_name=display_menu,
        intent=s.intent,
        tier=s.tier,
        sub_text=persona["sub_text"],
        theme=persona["theme"],
        match_reason=persona["match_reason"],
        persona_id=persona["id"],
        sticker=persona.get("sticker", "🛋️"),
        asset_id=persona.get("asset_id", persona["theme"]),
    )
    payload = {
        "ok": True,
        "action": "lets_go",
        "perfect_slots_left": s.perfect_slots_left,
        "tier": s.tier,
        "handoff": handoff,
        "receipt_title": title,
        "persona": persona,
        "place_name": place["name"],
        "menu_name": display_menu,
        "menu_id": place.get("menu_id") or body.menu_id,
        "category": place.get("category") or "",
        "kind": place.get("kind") or engine._visit_kind(place),
        "menu_verified": bool(place.get("menu_verified")),
        "menu_source": place.get("menu_source")
        or ("typical" if s.intent == "delivery" else "inferred"),
        "verified_menu_id": place.get("verified_menu_id") or "",
        "pack_id": s.pack_id,
        "logic_version": engine.LOGIC_VERSION,
        "receipt": share.share_payload(receipt, str(request.base_url)),
        "replayed": False,
    }
    engine.store_action(
        s,
        body.action_id,
        {"kind": "lets_go", "action_id": engine.normalize_action_id(body.action_id), "payload": payload},
    )
    return payload


class AdjustBody(BaseModel):
    session_id: str
    option: Literal["cheaper", "different", "closer", "again", "deal"]
    pack_id: str | None = None
    meal_context: Literal["meal", "late_night", "anju"] | None = None
    action_id: str | None = None
    epoch: int | None = None


class UndoBody(BaseModel):
    session_id: str
    pack_id: str | None = None
    meal_context: Literal["meal", "late_night", "anju"] | None = None
    action_id: str | None = None
    epoch: int | None = None
    uid: str | None = None


@app.post("/v1/adjust")
def adjust(body: AdjustBody):
    with engine.lock_session(body.session_id):
        _reject_preview(body.session_id)
        s = engine.get_session(body.session_id)
        if not s:
            raise HTTPException(404, "session not found")
        replay = engine.peek_action(s, body.action_id)
        if replay and replay.get("kind") == "adjust":
            return _replay_or_stale(s, replay)
        if not engine.accept_action(
            s, pack_id=body.pack_id, meal_context=body.meal_context, epoch=body.epoch
        ):
            return _stale_response(s)
        if body.option == "closer" and s.intent != "visit":
            raise HTTPException(400, "closer is visit-only")
        if body.option == "deal" and not deals.public_ready(hub_id=s.hub_id, intent=s.intent):
            raise HTTPException(400, "deals not public yet")
        engine.apply_adjust(s, body.option)
        cards, radius, gold = engine.present_feed(s)
        payload = _feed_payload(s, cards, radius, gold)
        payload["adjusted"] = body.option
        engine.store_action(
            s,
            body.action_id,
            {"kind": "adjust", "action_id": engine.normalize_action_id(body.action_id), "option": body.option},
        )
        return payload


@app.post("/v1/undo")
def undo(body: UndoBody, request: Request):
    with engine.lock_session(body.session_id):
        _reject_preview(body.session_id)
        s = engine.get_session(body.session_id)
        if not s:
            raise HTTPException(404, "session not found")
        replay = engine.peek_action(s, body.action_id)
        if replay and replay.get("kind") == "undo":
            return _replay_or_stale(s, replay)
        if not engine.accept_action(
            s, pack_id=body.pack_id, meal_context=body.meal_context, epoch=body.epoch
        ):
            return _stale_response(s)
        if not engine.apply_undo(s):
            raise HTTPException(400, "nothing to undo")
        cards, radius, gold = engine.present_feed(s)
        payload = _feed_payload(s, cards, radius, gold)
        engine.store_action(
            s,
            body.action_id,
            {"kind": "undo", "action_id": engine.normalize_action_id(body.action_id)},
        )
        return payload


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

    @app.get("/privacy")
    def privacy_page():
        path = WEB_DIR / "privacy.html"
        if not path.exists():
            raise HTTPException(404, "privacy page missing")
        return FileResponse(path)

    @app.get("/kakao-scenario")
    def kakao_scenario_page():
        path = WEB_DIR / "kakao-scenario.html"
        if not path.exists():
            raise HTTPException(404, "scenario page missing")
        return FileResponse(path)

    @app.get("/analytics")
    def analytics_page():
        path = WEB_DIR / "analytics.html"
        if not path.exists():
            raise HTTPException(404, "analytics page missing")
        return FileResponse(path)

    @app.get("/review-songdo")
    def review_songdo_page():
        path = WEB_DIR / "review-songdo.html"
        if not path.exists():
            raise HTTPException(404, "review page missing")
        return FileResponse(path)

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return {"message": "web UI missing", "docs": "/docs"}
    return FileResponse(index_path)
