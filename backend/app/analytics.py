"""경량 이벤트 수집 · 일일 집계 (소프트런치용).

파일: <DATA_DIR>/events.jsonl. 영구 디스크가 없으면 재배포·재시작·슬립에 휘발한다.
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import data_dir

EVENTS_PATH = data_dir() / "events.jsonl"
_LOCK = threading.Lock()

ALLOWED_EVENTS = {
    "app_open",
    "locate_ok",
    "locate_fallback",
    "taste_done",
    "session_start",
    "swipe_nope",
    "swipe_go",
    "match_done",
    "share",
    "kakao_link",
    "kakao_share",
    "duo_create",
    "install_click",
    "story_unlock",
    "story_image",
    "recommend_shown",
    "pack_exhausted",
    "adjust",
    "undo",
    "meal_confirm",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day_key(iso: str) -> str:
    return (iso or "")[:10]


def append_event(
    name: str,
    *,
    uid: str = "",
    device_id: str = "",
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if name not in ALLOWED_EVENTS:
        raise ValueError(f"unknown_event:{name}")
    row = {
        "ts": _now_iso(),
        "event": name,
        "uid": (uid or "")[:80],
        "device_id": (device_id or "")[:80],
        "props": props or {},
    }
    with _LOCK:
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _iter_events(since_days: int = 14) -> list[dict[str, Any]]:
    if not EVENTS_PATH.exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, since_days))
    cutoff_s = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    out: list[dict[str, Any]] = []
    with _LOCK:
        try:
            lines = EVENTS_PATH.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
    for line in lines[-20000:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if (row.get("ts") or "") >= cutoff_s:
            out.append(row)
    return out


def summarize(since_days: int = 7) -> dict[str, Any]:
    rows = _iter_events(since_days)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_event: Counter[str] = Counter()
    by_day_event: dict[str, Counter[str]] = defaultdict(Counter)
    devices_today: set[str] = set()
    devices_all: set[str] = set()
    taste_cats: Counter[str] = Counter()
    match_cats: Counter[str] = Counter()
    intents: Counter[str] = Counter()
    funnel = {
        "app_open": 0,
        "locate_ok": 0,
        "locate_fallback": 0,
        "taste_done": 0,
        "session_start": 0,
        "match_done": 0,
        "share": 0,
        "kakao_link": 0,
        "recommend_shown": 0,
        "pack_exhausted": 0,
        "adjust": 0,
        "meal_confirm": 0,
    }

    for r in rows:
        ev = r.get("event") or ""
        by_event[ev] += 1
        day = _day_key(r.get("ts") or "")
        by_day_event[day][ev] += 1
        did = r.get("device_id") or ""
        if did:
            devices_all.add(did)
            if day == today:
                devices_today.add(did)
        if ev in funnel:
            funnel[ev] += 1
        props = r.get("props") or {}
        if ev == "taste_done":
            for c in props.get("taste") or []:
                if isinstance(c, str) and c not in ("spicy", "mild"):
                    taste_cats[c] += 1
        if ev == "match_done":
            cat = props.get("category")
            if cat:
                match_cats[str(cat)] += 1
            intent = props.get("intent")
            if intent:
                intents[str(intent)] += 1

    days = []
    for i in range(since_days - 1, -1, -1):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        c = by_day_event.get(d) or Counter()
        days.append(
            {
                "day": d,
                "app_open": c.get("app_open", 0),
                "session_start": c.get("session_start", 0),
                "match_done": c.get("match_done", 0),
                "share": c.get("share", 0),
                "kakao_link": c.get("kakao_link", 0),
                "unique_hint": len(
                    {
                        (r.get("device_id") or r.get("uid") or r.get("ts"))
                        for r in rows
                        if _day_key(r.get("ts") or "") == d
                        and r.get("event") == "app_open"
                    }
                ),
            }
        )

    def rate(a: int, b: int) -> float:
        return round((a / b) * 100, 1) if b else 0.0

    return {
        "ok": True,
        "since_days": since_days,
        "generated_at": _now_iso(),
        "totals": dict(by_event),
        "funnel": funnel,
        "conversion": {
            "open_to_session": rate(funnel["session_start"], funnel["app_open"]),
            "session_to_match": rate(funnel["match_done"], funnel["session_start"]),
            "match_to_share": rate(funnel["share"], funnel["match_done"]),
            "match_to_kakao": rate(funnel["kakao_link"], funnel["match_done"]),
            "pack_exhausted_rate": rate(
                funnel.get("pack_exhausted", 0), funnel["session_start"]
            ),
            "match_after_adjust": rate(
                funnel["match_done"], funnel.get("adjust", 0) + funnel["session_start"]
            ),
            "meal_confirm_rate": rate(
                funnel.get("meal_confirm", 0), funnel["match_done"]
            ),
            "locate_ok_rate": rate(
                funnel["locate_ok"],
                funnel["locate_ok"] + funnel["locate_fallback"],
            ),
        },
        "unique_devices_today": len(devices_today),
        "unique_devices_period": len(devices_all),
        "top_taste": taste_cats.most_common(10),
        "top_match_category": match_cats.most_common(10),
        "intents": dict(intents),
        "daily": days,
        "note": "Render Free 디스크는 재배포 시 초기화될 수 있습니다. 중요하면 외부 DB/GA4 병행.",
    }


def admin_token_ok(token: str | None) -> bool:
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        return False
    return (token or "").strip() == expected
