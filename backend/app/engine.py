"""세션 · 랭킹 · 허브/전국 2티어 인벤토리."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

from . import brands, kakao
from .geo import HUB_ID, resolve_tier, tier_copy, tier_label
from .place_meta import enrich_place_fields
from .radius import (
    card_radius_m,
    haversine_m,
    session_radius_m,
    walk_minutes,
)


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
    inventory_source: str = "seed"  # seed | kakao | empty
    pool_radius_m: int = 0  # 인벤토리를 받아 둔 상한 반경
    pack_id: str = ""
    pack_cards: list[dict] = field(default_factory=list)
    undo_stack: list[dict] = field(default_factory=list)
    adjust_needed: bool = False
    adjust_filters: dict = field(default_factory=dict)
    last_radius_m: int = 0


SESSIONS: dict[str, Session] = {}


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
    """방문 재고는 카카오 실상호만 쓴다.

    배달은 프랜차이즈 카탈로그(brands.py)를 쓰므로 좌표 재고가 필요 없다.
    시드·좌표 폴백으로 가상 식당을 만들지 않는다 — 없으면 빈 결과다.
    """
    taste = taste or []
    tier = resolve_tier(lat, lng)
    _ = intent
    pool_r = session_radius_m("visit", weather)  # type: ignore[arg-type]

    matched, nearby = _fetch_kakao_block(lat, lng, pool_r, taste)
    kakao_block = _dedupe_places(matched + nearby)
    for p in kakao_block:
        p["tier"] = tier
    if not kakao_block:
        return [], tier, "empty"
    return kakao_block, tier, "kakao"


def apply_intent(session: Session, intent: str) -> None:
    """모드만 바꿀 때 — 덱 소스가 갈리므로 재조회가 필요 없다.

    방문은 카카오 재고, 배달은 프랜차이즈 카탈로그를 쓴다. 둘 다 이미 손에
    있으므로 토글은 네트워크 없이 즉시 끝난다.
    """
    if intent == session.intent:
        return
    session.intent = intent
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0
    session.force_gold_once = False
    reset_pack(session)


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
        pool_radius_m=session_radius_m("visit", weather),  # type: ignore[arg-type]
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
    session.pool_radius_m = session_radius_m("visit", session.weather)  # type: ignore[arg-type]
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0
    session.perfect_slots_left = 5
    reset_pack(session)
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
    session.pool_radius_m = session_radius_m("visit", session.weather)  # type: ignore[arg-type]
    session.seen_menu_ids.clear()
    session.consecutive_nopes = 0
    reset_pack(session)


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
    """방문 카드 점수 — 가까울수록, 평점·취향이 맞을수록 높다."""
    score = 10.0 - distance_m / 100.0
    score += place.get("rating", 4.0)
    score += _taste_boost(place, session.taste)
    for tag in place.get("tags", []):
        score -= session.nope_tags.get(tag, 0.0)
    score -= session.nope_categories.get(place.get("category", ""), 0.0) * 0.8
    return score


def _brand_score(place: dict, session: Session) -> float:
    """배달 브랜드 점수 — 거리가 없으므로 평점·취향·거부 이력만 본다."""
    score = float(place.get("rating", 4.0))
    score += _taste_boost(place, session.taste)
    for tag in place.get("tags", []):
        score -= session.nope_tags.get(tag, 0.0)
    score -= session.nope_categories.get(place.get("category", ""), 0.0) * 0.8
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
    """이번 식사에서만 약한 감점. 장기 hate에 연결하지 않는다.

    묶음이 비면 True — 호출측이 조정 선택지를 띄운다. 골드 카드는 더 이상 없다.
    """
    session.consecutive_nopes += 1
    session.left_swipe_count += 1
    session.seen_menu_ids.add(place["menu_id"])
    session.card_shown_at = time.time()
    _track_category(session, place)
    for tag in place.get("tags", []):
        session.nope_tags[tag] = session.nope_tags.get(tag, 0.0) + 0.4
    cat = place.get("category") or "other"
    session.nope_categories[cat] = session.nope_categories.get(cat, 0.0) + 0.3
    if session.pack_cards and session.pack_cards[0].get("menu_id") == place["menu_id"]:
        card = session.pack_cards.pop(0)
        session.undo_stack.append(card)
    elif session.pack_cards:
        card = session.pack_cards.pop(0)
        session.undo_stack.append(card)
    if not session.pack_cards:
        session.adjust_needed = True
        return True
    return False


def apply_lets_go(session: Session, place: dict) -> dict:
    session.consecutive_nopes = 0
    session.right_swipe_count += 1
    session.seen_menu_ids.add(place["menu_id"])
    _track_category(session, place)
    if session.perfect_slots_left > 0:
        session.perfect_slots_left -= 1
    return build_handoff(place)


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
    """덱 소스는 모드가 결정한다 — 방문은 주변 실상호, 배달은 프랜차이즈."""
    if session.intent == "delivery":
        return build_brand_cards(session, limit)
    return build_visit_cards(session, limit)


def build_brand_cards(session: Session, limit: int = 20) -> tuple[list[dict], int, bool]:
    """배달 후보 — 자사 주문 페이지가 확인된 프랜차이즈만.

    묶음 구성은 present_feed가 한다. 여기는 후보 풀만 만든다.
    """
    pool = brands.brand_places(session.taste)
    avail = [p for p in pool if p["menu_id"] not in session.seen_menu_ids]
    scored = [(_brand_score(p, session), p) for p in avail]
    taste_first = sorted(
        [x for x in scored if x[1].get("taste_match")], key=lambda x: x[0], reverse=True
    )
    rest = sorted(
        [x for x in scored if not x[1].get("taste_match")], key=lambda x: x[0], reverse=True
    )
    ordered = _diversify_by_category(taste_first) + _diversify_by_category(rest)  # type: ignore[arg-type]

    cards = []
    for sc, p in ordered[:limit]:
        meta = enrich_place_fields(p)
        cards.append(
            {
                "card_id": str(uuid.uuid4()),
                "place_id": p["place_id"],
                "menu_id": p["menu_id"],
                "place_name": p["name"],
                "menu_name": p["menu_name"],
                "image_url": "",
                "has_photo": False,
                "distance_m": None,
                "eta_label": "",
                "category": p["category"],
                "kind": p["kind"],
                "hashtag": (p.get("tags") or [""])[0],
                "is_brand": True,
                "brand_id": p["brand_id"],
                "order_url": p["order_url"],
                "order_channel": p["channel"],
                "delivery_sensitivity": meta["delivery_sensitivity"],
                "sensitivity_level": meta["sensitivity_level"],
                "sensitivity_percent": meta["sensitivity_percent"],
                "sensitivity_tip": meta["sensitivity_tip"],
                "card_radius_m": None,
                "rating": meta["rating"],
                "hours": p["hours"],
                "address": "",
                "price_krw": meta["price_krw"],
                "price_band": meta["price_band"],
                "price_source": "estimated",
                "menu_source": "typical",
                "menu_verified": False,
                "review": meta["review"],
                "is_gold": False,
                "taste_match": bool(p.get("taste_match")),
                "lat": None,
                "lng": None,
                "source": "brand",
                "tier": session.tier,
                "_score": round(sc, 2),
            }
        )

    if cards:
        mark_deck_shown(session)
    return cards, 0, False


def build_visit_cards(session: Session, limit: int = 20) -> tuple[list[dict], int, bool]:
    pool_r = session_radius_m("visit", session.weather)  # type: ignore[arg-type]
    inventory = session.places or []
    kakao_cands: list[tuple[float, dict, float, int]] = []

    for p in inventory:
        # 운영 피드에는 실상호만 — 허브 시드·좌표 폴백은 가짜 식당이다
        if p.get("source") != "kakao":
            continue
        if not p.get("open_now", True):
            continue
        dist = haversine_m(session.lat, session.lng, p["lat"], p["lng"])
        allow_r = card_radius_m(
            "visit",
            session.weather,  # type: ignore[arg-type]
            float(p.get("delivery_sensitivity", 0.5)),
        )
        if dist > pool_r or dist > allow_r:
            continue
        if p["menu_id"] in session.seen_menu_ids:
            continue
        sc = _score(p, dist, session)
        kakao_cands.append((sc, p, dist, allow_r))

    taste_first = [x for x in kakao_cands if x[1].get("taste_match")]
    rest = [x for x in kakao_cands if not x[1].get("taste_match")]
    taste_first.sort(key=lambda x: x[0], reverse=True)
    rest.sort(key=lambda x: x[0], reverse=True)
    candidates = _diversify_by_category(taste_first) + _diversify_by_category(rest)

    cards = []
    for sc, p, dist, allow_r in candidates[:limit]:
        meta = enrich_place_fields(p)
        kind = _visit_kind(p)
        cards.append(
            {
                "card_id": str(uuid.uuid4()),
                "place_id": p["place_id"],
                "menu_id": p["menu_id"],
                "place_name": p["name"],
                "menu_name": kind,
                "image_url": p.get("image_url") or "",
                "has_photo": bool(p.get("has_photo", bool(p.get("image_url")))),
                "distance_m": int(dist),
                "eta_label": f"도보 {walk_minutes(dist)}분",
                "category": p.get("category") or "",
                "kind": kind,
                "hashtag": (p.get("tags") or [""])[0],
                "is_brand": False,
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
                "price_source": "estimated",
                "menu_source": "inferred",
                "menu_verified": False,
                "review": meta["review"],
                "is_gold": False,
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
    return cards, pool_r, False


PACK_SIZE = 3
LOGIC_VERSION = "pack3-v1"

TASTE_KO = {
    "korean": "한식",
    "chinese": "중식",
    "japanese": "일식",
    "western": "양식",
    "snack": "분식",
    "meat": "고기",
    "asian": "아시안",
    "mexican": "멕시칸",
    "spicy": "매콤",
    "mild": "담백",
    "chicken": "치킨",
    "pizza": "피자",
    "burger": "버거",
}

KIND_KO = {
    "korean": "한식",
    "chinese": "중식",
    "japanese": "일식",
    "western": "양식",
    "snack": "분식",
    "meat": "고기",
    "asian": "아시안",
    "mexican": "멕시칸",
    "cafe": "카페",
    "noodle": "면",
}


def _visit_kind(place: dict) -> str:
    cat_name = place.get("kakao_category") or ""
    leaf = cat_name.split(">")[-1].strip() if ">" in cat_name else cat_name.strip()
    if leaf and leaf not in ("음식점", "맛집"):
        return leaf
    return KIND_KO.get(place.get("category") or "", "식당")


def reset_pack(session: Session) -> None:
    session.pack_id = ""
    session.pack_cards = []
    session.adjust_needed = False
    session.adjust_filters = {}
    session.undo_stack = []


def _pack_key(card: dict) -> str:
    return str(card.get("kind") or card.get("category") or "other")


def _pick_diverse_pack(cards: list[dict], n: int = PACK_SIZE) -> list[dict]:
    picked: list[dict] = []
    used: set[str] = set()
    for c in cards:
        k = _pack_key(c)
        if k in used:
            continue
        picked.append(c)
        used.add(k)
        if len(picked) >= n:
            return picked
    ids = {c["menu_id"] for c in picked}
    for c in cards:
        if c["menu_id"] in ids:
            continue
        picked.append(c)
        if len(picked) >= n:
            break
    return picked


def _why(session: Session, card: dict) -> str:
    f = session.adjust_filters or {}
    if f.get("cheaper"):
        return "조금 더 저렴한 쪽으로 다시 골랐어요."
    if f.get("exclude_cats"):
        return "다른 종류로 다시 골랐어요."
    if f.get("closer"):
        return "더 가까운 곳으로 다시 골랐어요."
    cats = [
        TASTE_KO[t]
        for t in (session.taste or [])
        if t in TASTE_KO and t not in ("spicy", "mild")
    ]
    if card.get("taste_match") and cats:
        shown = " · ".join(list(dict.fromkeys(cats))[:3])
        return f"선택한 {shown} 취향을 반영했어요."
    if session.intent == "delivery":
        return "고르면 이 브랜드 주문 화면으로 바로 이어져요."
    return "지금 위치에서 걸어갈 수 있는 곳이에요."


def _apply_adjust_filters(session: Session, cards: list[dict]) -> list[dict]:
    f = session.adjust_filters or {}
    out = list(cards)
    if f.get("exclude_cats"):
        excl = {str(x) for x in f["exclude_cats"] if x}
        filtered = [
            c
            for c in out
            if _pack_key(c) not in excl and (c.get("category") or "") not in excl
        ]
        if filtered:
            out = filtered
    if f.get("cheaper"):
        cap = int(f.get("price_cap") or 15000)
        filtered = [c for c in out if (c.get("price_krw") or 10**9) <= cap]
        if filtered:
            out = filtered
        out = sorted(out, key=lambda c: c.get("price_krw") or 10**9)
    if f.get("closer") and session.intent == "visit":
        cap = int(f.get("distance_cap") or 400)
        filtered = [
            c
            for c in out
            if c.get("distance_m") is not None and int(c["distance_m"]) <= cap
        ]
        if filtered:
            out = filtered
        out = sorted(out, key=lambda c: c.get("distance_m") or 10**9)
    return out


def start_pack(session: Session) -> int:
    had_nopes = session.left_swipe_count > 0
    candidates, radius, _ = build_cards(session, limit=30)
    candidates = _apply_adjust_filters(session, candidates)
    picked = _pick_diverse_pack(candidates, PACK_SIZE)
    session.last_radius_m = radius
    session.pack_id = uuid.uuid4().hex[:12]
    session.pack_cards = []
    for i, c in enumerate(picked):
        c["pack_id"] = session.pack_id
        c["pack_rank"] = i + 1
        c["pack_size"] = len(picked)
        c["logic_version"] = LOGIC_VERSION
        c["why"] = _why(session, c)
        session.pack_cards.append(c)
    session.adjust_needed = False
    if session.pack_cards:
        mark_deck_shown(session)
    elif had_nopes:
        session.adjust_needed = True
    return radius


def present_feed(session: Session) -> tuple[list[dict], int, bool]:
    """클라이언트에 한 장만 내려준다. 묶음이 비면 조정 플래그만 세운다."""
    if session.adjust_needed:
        radius = session.last_radius_m if session.intent == "visit" else 0
        return [], radius, False
    if not session.pack_cards:
        start_pack(session)
        if session.adjust_needed:
            radius = session.last_radius_m if session.intent == "visit" else 0
            return [], radius, False
    radius = session.last_radius_m if session.intent == "visit" else 0
    if session.intent == "delivery":
        radius = 0
    if not session.pack_cards:
        return [], radius, False
    return [session.pack_cards[0]], radius, False


def adjust_options(session: Session) -> list[dict]:
    opts = [
        {"id": "cheaper", "label": "더 저렴하게"},
        {"id": "different", "label": "다른 종류로"},
    ]
    if session.intent == "visit":
        opts.append({"id": "closer", "label": "더 가까운 곳"})
    opts.append({"id": "again", "label": "조건 그대로 다시"})
    return opts


def apply_adjust(session: Session, option: str) -> None:
    last = session.undo_stack[-PACK_SIZE:] or session.undo_stack
    if option == "cheaper":
        prices = [int(c["price_krw"]) for c in last if c.get("price_krw")]
        cap = sorted(prices)[len(prices) // 2] if prices else 15000
        session.adjust_filters = {"cheaper": True, "price_cap": int(cap)}
    elif option == "different":
        cats = []
        for c in last:
            cats.append(_pack_key(c))
            if c.get("category"):
                cats.append(c["category"])
        session.adjust_filters = {"exclude_cats": list(dict.fromkeys(cats))}
    elif option == "closer":
        dists = [int(c["distance_m"]) for c in last if c.get("distance_m") is not None]
        cap = min(int(min(dists) * 0.7), 500) if dists else 400
        session.adjust_filters = {"closer": True, "distance_cap": max(200, cap)}
    else:
        session.adjust_filters = {}
    session.adjust_needed = False
    session.pack_cards = []
    start_pack(session)
    # 자동 리필은 하지 않는다. 사용자가 조정을 고른 뒤에만, 브랜드를 다 봤으면 다시 섞는다.
    if not session.pack_cards and session.intent == "delivery":
        session.seen_menu_ids.clear()
        start_pack(session)


def apply_undo(session: Session) -> bool:
    if not session.undo_stack:
        return False
    card = session.undo_stack.pop()
    session.seen_menu_ids.discard(card["menu_id"])
    session.pack_cards.insert(0, card)
    session.adjust_needed = False
    session.consecutive_nopes = max(0, session.consecutive_nopes - 1)
    session.left_swipe_count = max(0, session.left_swipe_count - 1)
    cat = card.get("category") or "other"
    session.nope_categories[cat] = max(0.0, session.nope_categories.get(cat, 0.0) - 0.3)
    mark_deck_shown(session)
    return True


def pack_meta(session: Session) -> dict:
    current = session.pack_cards[0] if session.pack_cards else None
    return {
        "pack_id": session.pack_id,
        "pack_rank": int(current["pack_rank"]) if current else 0,
        "pack_size": int(current["pack_size"]) if current else PACK_SIZE,
        "adjust_needed": bool(session.adjust_needed),
        "can_undo": bool(session.undo_stack),
        "logic_version": LOGIC_VERSION,
        "adjust_options": adjust_options(session) if session.adjust_needed else [],
    }


def build_handoff(place: dict) -> dict:
    """마지막 한 걸음 — 여기서 흐름이 끊기면 앱을 쓴 의미가 없다.

    방문은 지도, 배달은 브랜드 자사 주문 페이지로 보낸다. 배달앱을 열어 다시
    검색하게 만들지 않는다.
    """
    if place.get("order_url"):
        channel = place.get("channel") or "공식 주문 페이지"
        return {
            "intent": "delivery",
            "provider": "brand_direct",
            "url": place["order_url"],
            "cta": f"{place['name']} 바로 주문",
            "auto_open": False,
            "note": f"{channel}으로 바로 이동해요. 배달앱에서 다시 찾지 않아도 돼요.",
        }

    if place.get("kakao_url"):
        url = place["kakao_url"]
        provider = "kakao_map"
    else:
        name = quote(place["name"])
        url = (
            f"https://map.naver.com/v5/search/{name}"
            f"/place?c={place['lng']},{place['lat']},15,0,0,0,dh"
        )
        provider = "naver_map"

    return {
        "intent": "visit",
        "provider": provider,
        "url": url,
        "cta": "지도에서 보기",
        "auto_open": False,
    }


def find_place(session: Session, menu_id: str) -> dict | None:
    if str(menu_id).startswith("brand:"):
        brand = brands.find_brand_place(menu_id)
        if not brand:
            return None
        # 페르소나 계산이 좌표를 요구한다 — 브랜드는 거리 개념이 없으므로 0으로 둔다
        return {**brand, "lat": session.lat, "lng": session.lng}
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
