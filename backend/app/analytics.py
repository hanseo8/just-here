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
    "exclude",
    "handoff_open",
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


def _parse_event_ts(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    n = len(xs)
    mid = n // 2
    if n % 2:
        return round(xs[mid], 1)
    return round((xs[mid - 1] + xs[mid]) / 2, 1)


def _rate(a: int, b: int) -> float:
    return round((a / b) * 100, 1) if b else 0.0


def product_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """기획안 성공 지표. 파일 I/O 없이 이벤트 목록만 받는다.

    외부 앱으로 나간 클릭은 주문 완료가 아니다.
    """
    sessions: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "first_shown_ts": None,
            "first_pack_id": "",
            "exhausted_first": False,
            "chose_first_pack": False,
            "adjust": False,
            "chose_after_adjust": False,
            "match_ts": None,
            "handoff": False,
        }
    )
    ordered = sorted(rows, key=lambda r: r.get("ts") or "")
    for r in ordered:
        ev = r.get("event") or ""
        props = r.get("props") or {}
        sid = str(props.get("session_id") or "")
        ts = r.get("ts") or ""
        if not sid:
            continue
        s = sessions[sid]
        if ev == "recommend_shown":
            # 집계 단위: session_id + pack_id + menu_id(후보). undo 재열람은 이 이벤트가 아니다.
            if not s["first_shown_ts"]:
                s["first_shown_ts"] = ts
                s["first_pack_id"] = str(props.get("pack_id") or "")
        elif ev == "pack_exhausted":
            pack = str(props.get("pack_id") or "")
            if s["first_pack_id"] and pack == s["first_pack_id"] and not s["chose_first_pack"]:
                s["exhausted_first"] = True
        elif ev == "swipe_go":
            pack = str(props.get("pack_id") or "")
            try:
                rank = int(props.get("rank") or 0)
            except (TypeError, ValueError):
                rank = 0
            if pack == s["first_pack_id"] and rank in (1, 2, 3) and not s["exhausted_first"]:
                s["chose_first_pack"] = True
        elif ev == "match_done":
            if not s["match_ts"]:
                s["match_ts"] = ts
            if s["adjust"]:
                s["chose_after_adjust"] = True
        elif ev == "adjust":
            s["adjust"] = True
        elif ev == "handoff_open":
            s["handoff"] = True

    first_rec: dict[str, str] = {}
    opens_by_actor: dict[str, list[str]] = defaultdict(list)
    for r in ordered:
        actor = r.get("device_id") or r.get("uid") or ""
        if not actor:
            continue
        ev = r.get("event") or ""
        ts = r.get("ts") or ""
        if ev == "app_open":
            opens_by_actor[actor].append(ts)
        if ev == "recommend_shown" and actor not in first_rec:
            first_rec[actor] = ts

    open_to_rec: list[float] = []
    for actor, t1 in first_rec.items():
        d1 = _parse_event_ts(t1)
        prev = None
        for t0 in opens_by_actor.get(actor, []):
            d0 = _parse_event_ts(t0)
            if d0 and d1 and d0 <= d1:
                prev = d0
        if prev and d1:
            open_to_rec.append((d1 - prev).total_seconds())

    rec_to_choice: list[float] = []
    for s in sessions.values():
        if not (s["first_shown_ts"] and s["match_ts"]):
            continue
        d0, d1 = _parse_event_ts(s["first_shown_ts"]), _parse_event_ts(s["match_ts"])
        if d0 and d1 and d1 >= d0:
            rec_to_choice.append((d1 - d0).total_seconds())

    shown = [s for s in sessions.values() if s["first_shown_ts"]]
    first_choose = sum(1 for s in shown if s["chose_first_pack"])
    exhausted = sum(1 for s in shown if s["exhausted_first"])
    adjusted = [s for s in shown if s["adjust"]]
    choose_after_adj = sum(1 for s in adjusted if s["chose_after_adjust"])
    matched = [s for s in shown if s["match_ts"]]
    handoff = sum(1 for s in matched if s["handoff"])

    days_by_dev: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r.get("event") != "app_open":
            continue
        actor = r.get("device_id") or r.get("uid") or ""
        if actor:
            days_by_dev[actor].add(_day_key(r.get("ts") or ""))
    n_dev = len(days_by_dev)
    n_revisit = sum(1 for d in days_by_dev.values() if len([x for x in d if x]) >= 2)

    return {
        "median_open_to_first_recommend_s": _median(open_to_rec),
        "median_first_recommend_to_choice_s": _median(rec_to_choice),
        "first_pack_choose_rate": _rate(first_choose, len(shown)),
        "first_pack_no_choice_rate": _rate(len(shown) - first_choose, len(shown)),
        "first_pack_exhaust_rate": _rate(exhausted, len(shown)),
        "choose_after_adjust_rate": _rate(choose_after_adj, len(adjusted)),
        "match_to_handoff_rate": _rate(handoff, len(matched)),
        "revisit_rate": _rate(n_revisit, n_dev),
        "sessions_with_shown": len(shown),
        "sessions_adjusted": len(adjusted),
        "sessions_matched": len(matched),
        "devices_seen": n_dev,
        "devices_revisited": n_revisit,
    }


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
        "handoff_open": 0,
        "exclude": 0,
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

    product = product_metrics(rows)
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
            "pack_exhausted_rate": product["first_pack_exhaust_rate"],
            "match_after_adjust": product["choose_after_adjust_rate"],
            "first_pack_no_choice_rate": product["first_pack_no_choice_rate"],
            "match_to_handoff": product["match_to_handoff_rate"],
            "revisit_rate": product["revisit_rate"],
            "meal_confirm_rate": rate(
                funnel.get("meal_confirm", 0), funnel["match_done"]
            ),
            "locate_ok_rate": rate(
                funnel["locate_ok"],
                funnel["locate_ok"] + funnel["locate_fallback"],
            ),
        },
        "product": product,
        "unique_devices_today": len(devices_today),
        "unique_devices_period": len(devices_all),
        "top_taste": taste_cats.most_common(10),
        "top_match_category": match_cats.most_common(10),
        "intents": dict(intents),
        "daily": days,
        "note": "지도·주문 클릭은 외부 앱 이동이지 주문 완료가 아닙니다. Render Free 디스크는 재배포 시 초기화될 수 있습니다.",
    }


def admin_token_ok(token: str | None) -> bool:
    expected = (os.getenv("ADMIN_TOKEN") or "").strip()
    if not expected:
        return False
    return (token or "").strip() == expected
