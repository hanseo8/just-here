"""검증된 판매 메뉴 카탈로그.

추정(카카오 종류·카테고리 가격)과 검증값을 섞지 않는다.
필수 필드가 비면 그 행은 추천에 쓰지 않는다. 엔진 랭킹에는 아직 연결하지 않는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import data_dir

REQUIRED = ("menu_name", "place_name", "address", "source", "confirmed_at")
SOURCE_TRACE = ("source_url", "source_note")
MEAL_CONTEXTS = {"meal", "late_night", "anju"}
SOURCES = {"visit", "receipt", "official", "owner"}


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
    return {
        "menu_id": str(row.get("menu_id") or ""),
        "menu_name": str(row["menu_name"]).strip(),
        "place_name": str(row["place_name"]).strip(),
        "place_id": str(row.get("place_id") or "").strip(),
        "kakao_place_id": str(row.get("kakao_place_id") or "").strip(),
        "address": str(row["address"]).strip(),
        "price_krw": int(price) if price_ok else None,
        "price_verified_at": str(row.get("price_verified_at") or "").strip(),
        "confirmed_at": str(row["confirmed_at"]).strip(),
        "source": src,
        "source_url": source_url,
        "source_note": source_note,
        "confirmed_by": str(row.get("confirmed_by") or "").strip(),
        "meal_contexts": ctx,
        "photo_url": str(row.get("photo_url") or "").strip(),
        "photo_rights": row.get("photo_rights"),
        "hours": str(row.get("hours") or "").strip(),
        "hours_verified": bool(row.get("hours_verified")),
        "order_url": str(row.get("order_url") or "").strip(),
        "order_verified": bool(row.get("order_verified")),
        "open_now": row.get("open_now"),
        "delivery_available": row.get("delivery_available"),
        "portion": str(row.get("portion") or "").strip(),
        "menu_verified": True,
        "menu_source": "verified",
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
        "ready": False,
        "wired_to_ranking": False,
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
        "ready": False,
        "wired_to_ranking": False,
        "example_file": "example" in target.name,
        "persistent": bool((os.getenv("DATA_DIR") or "").strip()),
        "menus": menus,
        "reason": "not_wired_to_ranking",
    }
