"""확인된 혜택만 추천에 쓴다.

제휴·매장 확인이 없는 동안 카탈로그는 비어 있다. 확인된 행만
`data/deals.json` 또는 테스트 주입으로 넣는다. 만료·미확인 혜택은
카드에 올리지 않고, '할인 우선'도 공개하지 않는다.

금액은 혜택 조건이지 최종 결제액이 아니다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import data_dir
from .radius import KST

SOURCE_LABEL = {
    "brand_notice": "브랜드 공지",
    "store": "매장 확인",
    "partner": "제휴",
}

# 운영에 넣을 확인된 혜택. 없으면 비운다 — 추측 할인을 만들지 않는다.
DEALS: list[dict[str, Any]] = []
PUBLIC_READY_MIN = 3

_OVERRIDE: list[dict[str, Any]] | None = None


def set_catalog(rows: list[dict[str, Any]] | None) -> None:
    """테스트용. None이면 파일·내장 카탈로그로 되돌린다."""
    global _OVERRIDE
    _OVERRIDE = None if rows is None else list(rows)


def _parse_dt(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt
    except ValueError:
        return None


def _load_file() -> list[dict[str, Any]]:
    path = data_dir() / "deals.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    rows = raw.get("deals") if isinstance(raw, dict) else None
    if isinstance(rows, list):
        return [x for x in rows if isinstance(x, dict)]
    return []


def catalog() -> list[dict[str, Any]]:
    if _OVERRIDE is not None:
        return list(_OVERRIDE)
    return list(DEALS) + _load_file()


def is_live(deal: dict[str, Any], now: datetime | None = None) -> bool:
    if not deal.get("verified_at"):
        return False
    if not deal.get("title"):
        return False
    now = now or datetime.now(timezone.utc)
    starts = _parse_dt(str(deal.get("starts_at") or ""))
    ends = _parse_dt(str(deal.get("ends_at") or ""))
    if starts and now < starts:
        return False
    if ends and now >= ends:
        return False
    return True


def live(now: datetime | None = None) -> list[dict[str, Any]]:
    return [d for d in catalog() if is_live(d, now)]


def public_ready(now: datetime | None = None) -> bool:
    return len(live(now)) >= PUBLIC_READY_MIN


def match(place: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    brand_id = str(place.get("brand_id") or "")
    place_id = str(place.get("place_id") or "")
    for deal in live(now):
        if brand_id and str(deal.get("brand_id") or "") == brand_id:
            return deal
        if place_id and str(deal.get("place_id") or "") == place_id:
            return deal
    return None


def public_payload(deal: dict[str, Any] | None) -> dict[str, Any] | None:
    if not deal:
        return None
    src = str(deal.get("source") or "")
    return {
        "id": deal.get("id") or "",
        "title": deal.get("title") or "",
        "condition": deal.get("condition") or "",
        "source": src,
        "source_label": SOURCE_LABEL.get(src, "확인된 혜택"),
        "min_order_krw": deal.get("min_order_krw"),
        "delivery_fee_included": bool(deal.get("delivery_fee_included")),
        "verified_at": deal.get("verified_at") or "",
        "ends_at": deal.get("ends_at") or "",
    }


def score_boost(deal: dict[str, Any] | None) -> float:
    return 0.9 if deal else 0.0
