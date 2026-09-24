"""검증된 판매 메뉴 카탈로그.

추정(카카오 종류·카테고리 가격)과 검증값을 섞지 않는다.
필수 필드가 비면 그 행은 추천에 쓰지 않는다. 엔진 랭킹에는 아직 연결하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .config import data_dir

REQUIRED = ("menu_name", "place_name", "address", "source", "confirmed_at")
SOURCE_TRACE = ("source_url", "source_note")
MEAL_CONTEXTS = {"meal", "late_night", "anju"}
SOURCES = {"visit", "receipt", "official", "owner"}
MENU_SCOPES = {"brand", "branch"}
PRICE_CHANNELS = {"", "dine_in", "takeout", "delivery", "unspecified"}
PRICE_UNITS = {"", "menu", "per_person"}
EVIDENCE_KINDS = {"", "brand_official", "catchtable_page", "store_direct"}
REVIEW_ANCHOR = {
    "lat": 37.3925,
    "lng": 126.6450,
    "label": "송도1동 앵커 (센트럴파크·컨벤시아)",
    "walk_m_per_min": 80,
}


def catalog_path() -> Path:
    return data_dir() / "verified-menus.json"


def _clean(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("example"):
        return None
    missing = [k for k in REQUIRED if not str(row.get(k) or "").strip()]
    if missing:
        return None
    src = str(row.get("source") or "").strip()
    if src not in SOURCES:
        return None
    source_url = str(row.get("source_url") or "").strip()
    source_note = str(row.get("source_note") or "").strip()
    if not source_url and not source_note:
        return None
    ctx = [c for c in (row.get("meal_contexts") or []) if c in MEAL_CONTEXTS]
    price = row.get("price_krw")
    price_ok = isinstance(price, int) and not isinstance(price, bool) and price > 0
    scope = str(row.get("menu_scope") or "").strip()
    if scope not in MENU_SCOPES:
        scope = "brand"
    branch = scope == "branch" and bool(row.get("branch_sale_confirmed"))
    channel = str(row.get("price_channel") or "").strip()
    if channel not in PRICE_CHANNELS:
        channel = ""
    photo_rights = row.get("photo_rights") is True
    store_photo = photo_rights and bool(row.get("photo_is_store_menu"))
    price_at = str(row.get("price_verified_at") or "").strip()
    # 지점 판매가 확인된 가격만 숫자로 남긴다. 브랜드 권장가는 비운다.
    listed = branch and price_ok and bool(price_at)
    unit = str(row.get("price_unit") or "").strip()
    if unit not in PRICE_UNITS:
        unit = "menu" if listed else ""
    evidence = str(row.get("evidence_kind") or "").strip()
    if evidence not in EVIDENCE_KINDS:
        evidence = "catchtable_page" if "catchtable" in source_url else (
            "brand_official" if scope == "brand" else ""
        )
    confirmation = str(row.get("branch_confirmation") or "").strip()
    if branch and not confirmation:
        confirmation = "page_posted" if evidence == "catchtable_page" else "store_direct"
    if not branch:
        confirmation = "unconfirmed"
    tags = [str(t).strip() for t in (row.get("menu_tags") or []) if str(t).strip()]
    portion_ok = bool(row.get("portion_confirmed"))
    per_person = row.get("price_per_person_krw")
    per_ok = isinstance(per_person, int) and not isinstance(per_person, bool) and per_person > 0
    return {
        "menu_id": str(row.get("menu_id") or ""),
        "menu_name": str(row["menu_name"]).strip(),
        "place_name": str(row["place_name"]).strip(),
        "place_id": str(row.get("place_id") or "").strip(),
        "kakao_place_id": str(row.get("kakao_place_id") or "").strip(),
        "address": str(row["address"]).strip(),
        "price_krw": int(price) if listed else None,
        "price_menu_krw": int(price) if listed else None,
        "price_per_person_krw": int(per_person) if per_ok and branch else None,
        "price_verified_at": price_at if listed else "",
        "price_channel": channel if listed else "",
        "price_unit": unit if listed else "",
        "price_label": str(row.get("price_label") or "").strip()
        or ("캐치테이블 표시 가격" if evidence == "catchtable_page" and listed else ""),
        "portion_confirmed": portion_ok,
        "evidence_kind": evidence,
        "branch_confirmation": confirmation,
        "menu_tags": tags,
        "confirmed_at": str(row["confirmed_at"]).strip(),
        "source": src,
        "source_url": source_url,
        "source_note": source_note,
        "confirmed_by": str(row.get("confirmed_by") or "").strip(),
        "meal_contexts": ctx,
        "photo_url": str(row.get("photo_url") or "").strip() if store_photo else "",
        "photo_rights": True if store_photo else None,
        "photo_is_store_menu": store_photo,
        "hours": str(row.get("hours") or "").strip(),
        "hours_verified": bool(row.get("hours_verified")),
        "order_url": str(row.get("order_url") or "").strip(),
        "order_verified": bool(row.get("order_verified")),
        "open_now": row.get("open_now"),
        "delivery_available": row.get("delivery_available"),
        "portion": str(row.get("portion") or "").strip(),
        "menu_scope": scope,
        "branch_sale_confirmed": branch,
        "sale_status": "branch_confirmed" if branch else "need_branch_check",
        "menu_verified": branch,
        "menu_source": "verified" if branch else "brand_official",
        "hub_id": str(row.get("hub_id") or "").strip(),
        "dong_code": str(row.get("dong_code") or "").strip(),
    }


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or catalog_path()
    if not target.exists():
        return {
            "ok": True,
            "path": str(target),
            "count": 0,
            "brand_only": 0,
            "branch_confirmed": 0,
        "ready": False,
        "wired_to_ranking": visit_overlay_enabled(),
        "example_file": False,
        "persistent": bool((os.getenv("DATA_DIR") or "").strip()),
        "menus": [],
        "reason": "catalog_missing",
        }
    raw = json.loads(target.read_text(encoding="utf-8"))
    rows = raw.get("menus") if isinstance(raw, dict) else raw
    menus = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cleaned = _clean(row)
        if cleaned:
            menus.append(cleaned)
    return {
        "ok": True,
        "path": str(target),
        "experiment_id": (raw.get("experiment_id") if isinstance(raw, dict) else "") or "",
        "hub_id": (raw.get("hub_id") if isinstance(raw, dict) else "") or "",
        "dong_code": (raw.get("dong_code") if isinstance(raw, dict) else "") or "",
        "count": len(menus),
        "brand_only": sum(1 for m in menus if not m.get("menu_verified")),
        "branch_confirmed": sum(1 for m in menus if m.get("menu_verified")),
        "ready": False,
        "wired_to_ranking": visit_overlay_enabled(),
        "example_file": "example" in target.name,
        "persistent": bool((os.getenv("DATA_DIR") or "").strip()),
        "menus": menus,
        "reason": "not_wired_to_ranking",
    }


EXPERIMENT_TARGET = 20
PRIORITY_FILE = "verified-menus.songdo.priority.json"


def visit_overlay_enabled() -> bool:
    raw = (os.getenv("VERIFIED_MENUS_VISIT") or "on").strip().lower()
    return raw in {"1", "true", "on", "yes"}


def review_exposed() -> bool:
    raw = (os.getenv("REVIEW_SONGDO") or "").strip().lower()
    if raw in {"1", "true", "on", "yes"}:
        return True
    if raw in {"0", "false", "off", "no"}:
        return False
    return not bool((os.getenv("DATA_DIR") or "").strip())


# 방문 오버레이 스위치. 배달에는 쓰지 않는다.
WIRED_TO_RANKING = visit_overlay_enabled


def _norm(value: str) -> str:
    return " ".join(str(value or "").split()).casefold()


def _kakao_ids(place: dict[str, Any]) -> set[str]:
    raw = [
        place.get("kakao_place_id"),
        place.get("place_id"),
    ]
    ids: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        ids.add(text)
        if text.startswith("kakao_"):
            ids.add(text[6:])
    return {i for i in ids if i}


def match_place(row: dict[str, Any], places: list[dict[str, Any]]) -> dict[str, Any] | None:
    """카카오 실상호에만 붙인다. 이름만 같고 주소가 다르면 매칭하지 않는다."""
    kid = str(row.get("kakao_place_id") or "").strip()
    if kid:
        for place in places:
            if kid in _kakao_ids(place):
                return place
    name = _norm(row.get("place_name") or "")
    addr = _norm(row.get("address") or "")
    if not name:
        return None
    hits = [p for p in places if _norm(p.get("name") or "") == name]
    if addr:
        hits = [
            p
            for p in hits
            if addr in _norm(p.get("address") or "") or _norm(p.get("address") or "") in addr
        ]
    if len(hits) == 1:
        return hits[0]
    return None


def is_branch_confirmed(row: dict[str, Any]) -> bool:
    return bool(row.get("menu_verified") and row.get("branch_sale_confirmed") and row.get("menu_scope") == "branch")


def recommendable_menus(menus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """지점 판매가 확인된 행만 추천 카드에 쓴다."""
    return [m for m in menus if is_branch_confirmed(m)]


def apply_verified(place: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    """지점 확인 행만 덮어쓴다. 좌표는 기존 실상호를 유지한다."""
    out = dict(place)
    if not is_branch_confirmed(row):
        out["sale_status"] = "need_branch_check"
        out["menu_verified"] = False
        return out
    out["menu_name"] = row["menu_name"]
    out["menu_verified"] = True
    out["menu_source"] = "verified"
    out["menu_scope"] = "branch"
    out["branch_sale_confirmed"] = True
    out["branch_confirmation"] = row.get("branch_confirmation") or "page_posted"
    out["evidence_kind"] = row.get("evidence_kind") or ""
    out["sale_status"] = "page_posted" if out["branch_confirmation"] == "page_posted" else "branch_confirmed"
    out["verified_menu_id"] = row.get("menu_id") or ""
    out["meal_contexts"] = list(row.get("meal_contexts") or [])
    out["menu_tags"] = list(row.get("menu_tags") or [])
    out["price_for_delivery"] = bool(row.get("price_channel") == "delivery")
    if (row.get("price_menu_krw") or row.get("price_krw")) and row.get("price_verified_at"):
        amount = row.get("price_menu_krw") or row.get("price_krw")
        unit = row.get("price_unit") or ""
        channel = row.get("price_channel") or ""
        evidence = row.get("evidence_kind") or ""
        portion = bool(row.get("portion_confirmed"))
        per_person = bool(
            unit == "per_person"
            or portion
            or (
                not unit
                and channel in ("dine_in", "takeout", "delivery")
                and evidence != "catchtable_page"
            )
        )
        out["price_menu_krw"] = amount
        out["price_unit"] = unit or ("per_person" if per_person else "menu")
        out["portion_confirmed"] = portion
        out["price_verified_at"] = row.get("price_verified_at") or ""
        out["price_channel"] = channel
        out["price_label"] = row.get("price_label") or ""
        out["price_per_person_krw"] = row.get("price_per_person_krw")
        out["price_for_delivery"] = channel == "delivery"
        if per_person:
            out["price_krw"] = row.get("price_per_person_krw") or amount
            out["price_per_person_krw"] = out["price_krw"]
            out["price_source"] = "listed"
        else:
            out["price_krw"] = None
            out["price_source"] = (
                "catchtable_listed" if evidence == "catchtable_page" else "listed_menu"
            )
            out["price_band"] = ""
    if row.get("photo_url") and row.get("photo_rights") is True and row.get("photo_is_store_menu"):
        out["image_url"] = row["photo_url"]
        out["has_photo"] = True
        out["photo_role"] = "menu"
        out["photo_is_menu"] = True
        out["photo_is_store_menu"] = True
        out["photo_is_example"] = False
    if row.get("hours") and row.get("hours_verified"):
        out["hours"] = row["hours"]
    if row.get("order_url") and row.get("order_verified"):
        out["order_url"] = row["order_url"]
        out["order_verified"] = True
    return out


def _tokens(values: list[str] | None) -> list[str]:
    out = []
    for item in values or []:
        text = _norm(item)
        if text:
            out.append(text)
    return out


def infer_menu_prefer(
    *,
    taste: list[str] | None = None,
    prefer: str | None = None,
    adjust: dict[str, Any] | None = None,
) -> str:
    """기존 취향·조정만 본다. 메뉴 선택을 위한 새 질문은 만들지 않는다."""
    explicit = _norm(prefer or "")
    if explicit:
        return explicit
    toks = set(_tokens(taste))
    if toks & {"share", "platter", "플래터", "나눠", "나눠먹기"}:
        return "share"
    if toks & {"taco", "타코"}:
        return "taco"
    if toks & {"burrito", "브리또"}:
        return "burrito"
    if (adjust or {}).get("cheaper"):
        return "cheaper"
    return ""


def _is_unknown_portion_share(row: dict[str, Any]) -> bool:
    tags = set(_tokens(list(row.get("menu_tags") or [])))
    name = _norm(row.get("menu_name") or "")
    share_like = bool(tags & {"platter", "share", "플래터"}) or "플래터" in name
    unknown = row.get("price_unit") == "menu" and not row.get("portion_confirmed")
    return share_like and unknown


def _can_default_without_share_signal(row: dict[str, Any]) -> bool:
    """인분 미확인 플래터를 혼밥 기본값으로 쓰지 않는다."""
    return not _is_unknown_portion_share(row)


def _hash_pick(rows: list[dict[str, Any]], salt: str) -> dict[str, Any]:
    digest = hashlib.sha1(salt.encode("utf-8")).hexdigest()
    return rows[int(digest, 16) % len(rows)]


def pick_verified_menu(
    extras: list[dict[str, Any]],
    *,
    taste: list[str] | None = None,
    meal_context: str | None = None,
    prefer: str | None = None,
    salt: str | None = None,
    adjust: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """같은 매장 검증 메뉴 중 취향·상황에 맞는 하나를 고른다."""
    if not extras:
        raise ValueError("extras required")
    prefer_tok = infer_menu_prefer(taste=taste, prefer=prefer, adjust=adjust)
    if prefer_tok in {"cheaper", "저렴"}:
        from .place_meta import per_person_budget_krw

        priced = []
        for row in extras:
            budget = per_person_budget_krw({**row, "price_source": "listed", "menu_verified": True})
            if budget is not None:
                priced.append((budget, str(row.get("menu_id") or ""), row))
        if priced:
            priced.sort(key=lambda x: (x[0], x[1]))
            return priced[0][2]
        prefer_tok = ""
    if prefer_tok:
        taste_toks = _tokens(taste)
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for row in extras:
            name = _norm(row.get("menu_name") or "")
            tags = _tokens(list(row.get("menu_tags") or []))
            blob = " ".join([name, *tags])
            score = 0
            if meal_context and meal_context in (row.get("meal_contexts") or []):
                score += 2
            for tok in taste_toks:
                if tok in {"taco", "타코", "burrito", "브리또", "share", "platter", "플래터"}:
                    continue
                if tok in blob or any(tok in tag for tag in tags):
                    score += 1
            if prefer_tok in {"share", "platter", "플래터"} and any(
                k in blob for k in ("플래터", "share", "platter")
            ):
                score += 8
            if prefer_tok in {"taco", "타코"} and "타코" in blob:
                score += 8
            if prefer_tok in {"burrito", "브리또"} and "브리또" in blob:
                score += 8
            if prefer_tok in {"light", "가벼운"} and any(k in tags for k in ("light", "taco")):
                score += 4
            scored.append((score, str(row.get("menu_id") or name), row))
        scored.sort(key=lambda x: (-x[0], x[1]))
        if scored[0][0] > 0:
            return scored[0][2]
    pool = [row for row in extras if _can_default_without_share_signal(row)]
    if not pool:
        pool = list(extras)
    return _hash_pick(pool, salt or "default")


def overlay_inventory(
    places: list[dict[str, Any]],
    menus: list[dict[str, Any]],
    *,
    taste: list[str] | None = None,
    meal_context: str | None = None,
    prefer: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """지점 확인 메뉴만 붙인다. 매장당 후보는 하나다."""
    usable = recommendable_menus(menus)
    out: list[dict[str, Any]] = []
    used: set[int] = set()
    matched = 0
    for place in places:
        extras = []
        for i, row in enumerate(usable):
            if match_place(row, [place]):
                extras.append(row)
                used.add(i)
        if extras:
            matched += 1
            place_key = str(place.get("place_id") or place.get("kakao_place_id") or "")
            chosen = pick_verified_menu(
                extras,
                taste=taste,
                meal_context=meal_context,
                prefer=prefer,
                salt=f"{place_key}:{prefer or 'default'}",
            )
            out.append(apply_verified(place, chosen))
        else:
            out.append(dict(place))
    return out, {
        "places": len(places),
        "menus": len(menus),
        "recommendable": len(usable),
        "matched_places": matched,
        "unmatched_menus": len(usable) - len(used),
        "wired_to_ranking": visit_overlay_enabled(),
    }


def expand_cards(
    places: list[dict[str, Any]], menus: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """매장당 메뉴가 여러 개면 카드를 나누되, 실상호 좌표를 복사한다."""
    usable = recommendable_menus(menus)
    cards: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    for place in places:
        extras = [row for row in usable if match_place(row, [place])]
        if extras:
            matched_ids.add(str(place.get("place_id") or ""))
            for row in extras:
                card = apply_verified(place, row)
                card["lat"] = place.get("lat")
                card["lng"] = place.get("lng")
                cards.append(card)
        else:
            cards.append(dict(place))
    return cards


def pick_first_pack(cards: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
    """첫 묶음은 한 매장으로 채우지 않는다."""
    picked: list[dict[str, Any]] = []
    used_places: set[str] = set()
    for card in cards:
        pid = str(card.get("place_id") or card.get("kakao_place_id") or "")
        if pid and pid in used_places:
            continue
        picked.append(card)
        if pid:
            used_places.add(pid)
        if len(picked) >= n:
            return picked
    return picked


def usable_listed_price(card: dict[str, Any]) -> int | None:
    """1인 예산·가격 순위에만 쓴다. 인분 미확인 메뉴 전체가는 넣지 않는다."""
    from .place_meta import per_person_budget_krw

    if card.get("price_source") not in ("listed", "confirmed"):
        return None
    if card.get("price_channel") == "unspecified" and (
        card.get("intent") == "delivery" or card.get("price_for_delivery") is True
    ):
        return None
    return per_person_budget_krw(card)


def quality_report(catalog: dict[str, Any]) -> dict[str, Any]:
    menus = list(catalog.get("menus") or [])
    places = {m.get("place_name") for m in menus if m.get("place_name")}
    branch = [m for m in menus if is_branch_confirmed(m)]
    priced = [m for m in branch if m.get("price_krw") and m.get("price_verified_at")]
    photos = [m for m in branch if m.get("photo_url") and m.get("photo_is_store_menu")]
    kakao = [m for m in menus if m.get("kakao_place_id")]
    return {
        "count": len(menus),
        "places": len(places),
        "brand_only": sum(1 for m in menus if not m.get("menu_verified")),
        "branch_confirmed": len(branch),
        "with_price": len(priced),
        "with_photo": len(photos),
        "with_kakao_id": len(kakao),
        "experiment_target": EXPERIMENT_TARGET,
        "enough_for_experiment": len(branch) >= EXPERIMENT_TARGET,
        "ready": False,
        "wired_to_ranking": visit_overlay_enabled(),
        "reason": catalog.get("reason") or "not_wired_to_ranking",
    }


def bootstrap_persistent_catalog() -> dict[str, Any]:
    """영구 DATA_DIR에 카탈로그가 없으면 승인된 우선 파일을 복사한다. 기존 파일은 덮지 않는다."""
    dest = catalog_path()
    persistent = bool((os.getenv("DATA_DIR") or "").strip())
    if dest.exists():
        return {"bootstrapped": False, "exists": True, "path": str(dest), "persistent": persistent}
    if not persistent:
        return {
            "bootstrapped": False,
            "exists": False,
            "path": str(dest),
            "persistent": False,
            "reason": "not_persistent",
        }
    src = Path(__file__).resolve().parents[2] / "data" / PRIORITY_FILE
    if not src.exists():
        return {
            "bootstrapped": False,
            "exists": False,
            "path": str(dest),
            "persistent": True,
            "reason": "source_missing",
        }
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "bootstrapped": True,
        "exists": True,
        "path": str(dest),
        "persistent": True,
        "source": str(src),
    }


def overlay_status() -> dict[str, Any]:
    persistent = bool((os.getenv("DATA_DIR") or "").strip())
    exists = catalog_path().exists()
    try:
        cat = load_catalog()
        branch = int(cat.get("branch_confirmed") or 0)
    except Exception:
        branch = 0
        exists = False
    enabled = visit_overlay_enabled()
    return {
        "visit_overlay": enabled,
        "persistent": persistent,
        "catalog_exists": exists,
        "branch_confirmed": branch,
        "operational": bool(enabled and persistent and exists and branch > 0),
    }


def overlay_visit_cards(
    cards: list[dict[str, Any]],
    *,
    intent: str = "visit",
    taste: list[str] | None = None,
    meal_context: str | None = None,
    prefer: str | None = None,
    salt: str = "",
    adjust: dict[str, Any] | None = None,
    places: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """필터를 통과한 방문 카드에만 검증 메뉴를 붙인다. 점수·반경은 바꾸지 않는다."""
    if intent != "visit" or not visit_overlay_enabled() or not cards:
        return cards
    try:
        cat = load_catalog()
        usable = recommendable_menus(cat.get("menus") or [])
    except Exception:
        return cards
    if not usable:
        return cards
    prefer_tok = infer_menu_prefer(taste=taste, prefer=prefer, adjust=adjust)
    out: list[dict[str, Any]] = []
    for card in cards:
        extras = [row for row in usable if match_place(row, [card])]
        if not extras:
            out.append(card)
            continue
        place_key = str(card.get("place_id") or card.get("kakao_place_id") or "")
        chosen = pick_verified_menu(
            extras,
            taste=taste,
            meal_context=meal_context,
            prefer=prefer_tok,
            salt=f"{salt}:{place_key}",
            adjust=adjust,
        )
        overlaid = apply_verified(card, chosen)
        for key in (
            "distance_m",
            "eta_label",
            "lat",
            "lng",
            "card_radius_m",
            "_score",
            "card_id",
            "place_id",
            "menu_id",
            "kind",
            "inferred_kind",
        ):
            if key in card:
                overlaid[key] = card[key]
        overlaid["price_for_delivery"] = False
        overlaid.pop("delivery_available", None)
        overlaid.pop("open_now", None)
        if not chosen.get("hours_verified"):
            overlaid["hours"] = card.get("hours") or overlaid.get("hours") or "카카오맵에서 확인"
            overlaid["hours_verified"] = False
        if meal_context == "late_night" and not overlaid.get("hours_verified"):
            hours = str(overlaid.get("hours") or "").strip()
            if not hours or hours == "카카오맵에서 확인":
                overlaid["hours"] = "영업시간 미확인"
        out.append(overlaid)
        if places:
            for place in places:
                if match_place(chosen, [place]):
                    place["verified_menu_id"] = chosen.get("menu_id") or ""
                    place["menu_verified"] = True
                    place["menu_name"] = chosen.get("menu_name") or place.get("menu_name")
                    place["menu_source"] = "verified"
                    place["price_for_delivery"] = False
    return out


def load_priority(path: Path | None = None) -> dict[str, Any]:
    target = path or (Path(__file__).resolve().parents[2] / "data" / "verified-menus.songdo.priority.json")
    cat = load_catalog(target)
    raw = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    cat["stores"] = list(raw.get("stores") or [])
    return cat


def places_from_stores(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    places = []
    for store in stores:
        kid = str(store.get("kakao_place_id") or "").strip()
        places.append(
            {
                "place_id": f"kakao_{kid}" if kid else store.get("place_name"),
                "kakao_place_id": kid,
                "name": store.get("place_name") or "",
                "place_name": store.get("place_name") or "",
                "address": store.get("address") or "",
                "lat": store.get("lat"),
                "lng": store.get("lng"),
                "menu_name": "",
                "category": "",
                "source": "kakao",
                "has_photo": False,
                "image_url": "",
            }
        )
    return places


def attach_walk(card: dict[str, Any], anchor: dict[str, Any] | None = None) -> dict[str, Any]:
    from .radius import haversine_m, walk_minutes

    point = anchor or REVIEW_ANCHOR
    out = dict(card)
    lat, lng = out.get("lat"), out.get("lng")
    if lat is None or lng is None:
        out["distance_m"] = None
        out["eta_label"] = ""
        return out
    dist = int(round(haversine_m(point["lat"], point["lng"], float(lat), float(lng))))
    out["distance_m"] = dist
    out["eta_label"] = f"도보 약 {walk_minutes(dist)}분"
    out["walk_anchor"] = point
    amount = out.get("price_menu_krw") or out.get("price_krw")
    if amount:
        pretty = f"{int(amount):,}원"
        label = out.get("price_label") or ""
        if out.get("price_source") in ("catchtable_listed", "listed_menu") or (
            out.get("price_unit") == "menu" and not out.get("portion_confirmed")
        ):
            out["price_display"] = f"{label} {pretty}".strip() if label else f"메뉴 가격 {pretty}"
        else:
            out["price_display"] = pretty
    else:
        out["price_display"] = "가격 확인 필요"
    if not out.get("why"):
        bits = ["한 끼 후보."]
        if out.get("evidence_kind") == "catchtable_page":
            bits.append("지점 페이지 게시 메뉴. 매장 직접 확인은 아닙니다.")
            bits.append("이용 채널이 확인되지 않아 배달 가격으로 쓰지 않습니다.")
        if out.get("price_unit") == "menu" and not out.get("portion_confirmed"):
            bits.append("메뉴 전체 가격이며 1인 가격은 아닙니다.")
        bits.append("야식 이용은 확인하지 않았습니다.")
        out["why"] = " ".join(bits)
    return out


def review_payload(
    *,
    taste: list[str] | None = None,
    meal_context: str | None = "meal",
    prefer: str | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """검수 화면용. 지점 판매 확인 메뉴만 구매 후보로 내린다."""
    cat = load_priority(path)
    places = places_from_stores(cat.get("stores") or [])
    overlaid, stats = overlay_inventory(
        places, cat["menus"], taste=taste, meal_context=meal_context, prefer=prefer
    )
    user_cards = []
    for card in overlaid:
        if not is_branch_confirmed(card):
            continue
        user_cards.append(attach_walk(card))
    pack = pick_first_pack(user_cards, 3)
    expanded = [
        attach_walk(c)
        for c in expand_cards(places, cat["menus"])
        if is_branch_confirmed(c)
    ]
    pick_examples = {}
    for key, pref in (("platter", "share"), ("taco", "taco"), ("burrito", "burrito")):
        picked, _ = overlay_inventory(
            places, cat["menus"], taste=["mexican"], meal_context="meal", prefer=pref
        )
        chosen = next((c for c in picked if is_branch_confirmed(c)), None)
        pick_examples[key] = attach_walk(chosen) if chosen else None
    notes = [
        {
            "place_name": s.get("place_name"),
            "sale_status": s.get("sale_status"),
            "note": "이 지점 판매 여부 확인 필요. 구매 가능한 메뉴 후보가 아닙니다.",
        }
        for s in (cat.get("stores") or [])
        if s.get("sale_status") != "branch_confirmed"
    ]
    return {
        "ok": True,
        "wired_to_ranking": visit_overlay_enabled(),
        "anchor": REVIEW_ANCHOR,
        "taste": taste or [],
        "meal_context": meal_context,
        "prefer": prefer or "",
        "stats": stats,
        "user_cards": user_cards,
        "pack": pack,
        "branch_menus": expanded,
        "pick_examples": pick_examples,
        "investigation_notes": notes,
        "brand_only": cat.get("brand_only"),
        "branch_confirmed": cat.get("branch_confirmed"),
    }
