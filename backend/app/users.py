"""Guest-First 유저 식별 · 취향/칭호/스와이프 누적 (Firestore 호환 JSON).

웹 MVP: device_id + guest uid (Firebase Anonymous 대체 가능).
카카오 연동 시 익명 데이터를 kakao uid로 병합.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import data_dir
from .radius import KST

USERS_PATH = data_dir() / "users.json"
_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _parse_ts(raw: str) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def compute_taste_signals(
    logs: list[dict[str, Any]] | None,
    *,
    exclude: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """스와이프 기록 → 다음 세션 점수에 넣을 장기 신호.

    한 번의 거절은 장기 hate가 아니다. 서로 다른 날짜에 같은 종류를 거절해야
    감점하고, 선택은 그날부터 약한 가산, 식사 확인은 그보다 세게 본다.
    """
    now = now or datetime.now(timezone.utc)
    nope_days: dict[str, set[str]] = defaultdict(set)
    go_days: dict[str, set[str]] = defaultdict(set)
    go_count: dict[str, int] = defaultdict(int)
    ate_count: dict[str, int] = defaultdict(int)
    recent: set[str] = set()
    has_history = False

    for ev in logs or []:
        action = ev.get("action") or ""
        keys = []
        for raw in (ev.get("category"), ev.get("kind")):
            val = str(raw or "").strip()
            if val and val not in keys and val != "other":
                keys.append(val)
        if not keys:
            continue
        ts = _parse_ts(str(ev.get("at") or ""))
        if ts is None:
            continue
        has_history = True
        day = ts.astimezone(KST).strftime("%Y-%m-%d")
        recent_hit = (now - ts) <= timedelta(hours=36)
        for cat in keys:
            if action == "nope":
                nope_days[cat].add(day)
            elif action == "lets_go":
                go_days[cat].add(day)
                go_count[cat] += 1
                if recent_hit:
                    recent.add(cat)
            elif action == "ate":
                go_days[cat].add(day)
                go_count[cat] += 1
                ate_count[cat] += 1
                if recent_hit:
                    recent.add(cat)

    hate: dict[str, float] = {}
    prefer: dict[str, float] = {}
    frequent: list[str] = []
    for cat in set(nope_days) | set(go_days) | set(ate_count):
        n_days = len(nope_days.get(cat, ()))
        g_days = len(go_days.get(cat, ()))
        if n_days >= 2 and n_days > g_days:
            hate[cat] = round(min(1.6, 0.45 * (n_days - 1)), 2)
        pref = 0.3 * min(go_count.get(cat, 0), 4) + 0.7 * ate_count.get(cat, 0)
        if pref > 0:
            prefer[cat] = round(min(1.8, pref), 2)
        if g_days >= 2:
            frequent.append(cat)
    frequent.sort(key=lambda c: (len(go_days.get(c, ())), go_count.get(c, 0)), reverse=True)

    return {
        "hate_categories": hate,
        "prefer_categories": prefer,
        "recent_repeat_categories": sorted(recent),
        "frequent_categories": frequent[:6],
        "exclude_categories": [str(x) for x in (exclude or []) if x],
        "has_history": has_history,
    }


def _empty_user(uid: str, *, auth_type: str, device_id: str = "") -> dict[str, Any]:
    return {
        "uid": uid,
        "auth_type": auth_type,  # anonymous | kakao
        "device_ids": [device_id] if device_id else [],
        "anonymous_linked_from": None,
        "nickname": "고민제로",
        "earned_titles": [],
        "title_ids": [],
        "unlocks": [],
        "preferences": {
            "hate_tags": {},
            "hate_categories": {},
            "taste": [],
            "preferred_spice_level": 2,
        },
        "swipe_logs": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


class UserStore:
    def __init__(self, path: Path = USERS_PATH) -> None:
        self.path = path
        self._users: dict[str, dict[str, Any]] = {}
        self._device_index: dict[str, str] = {}  # device_id -> uid
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._users = raw.get("users") or {}
            self._device_index = raw.get("device_index") or {}
        except Exception:
            self._users = {}
            self._device_index = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        payload = {"users": self._users, "device_index": self._device_index}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, uid: str) -> dict[str, Any] | None:
        with _LOCK:
            u = self._users.get(uid)
            return deepcopy(u) if u else None

    def ensure_guest(self, device_id: str, firebase_uid: str | None = None) -> dict[str, Any]:
        device_id = (device_id or "").strip() or secrets.token_hex(16)
        with _LOCK:
            existing = self._device_index.get(device_id)
            if existing and existing in self._users:
                u = self._users[existing]
                u["updated_at"] = _now()
                self._save()
                return deepcopy(u)

            uid = firebase_uid or f"anon_{hashlib.sha256(device_id.encode()).hexdigest()[:20]}"
            if uid in self._users:
                u = self._users[uid]
                if device_id and device_id not in u.get("device_ids", []):
                    u.setdefault("device_ids", []).append(device_id)
                self._device_index[device_id] = uid
                u["updated_at"] = _now()
                self._save()
                return deepcopy(u)

            u = _empty_user(uid, auth_type="anonymous", device_id=device_id)
            self._users[uid] = u
            self._device_index[device_id] = uid
            self._save()
            return deepcopy(u)

    def ensure_uid(self, uid: str, *, auth_type: str = "anonymous") -> dict[str, Any]:
        """콜백 시 게스트가 디스크에서 사라진 경우(재배포) 복구."""
        uid = (uid or "").strip()
        if not uid:
            raise KeyError("guest_not_found")
        with _LOCK:
            if uid in self._users:
                return deepcopy(self._users[uid])
            u = _empty_user(uid, auth_type=auth_type)
            self._users[uid] = u
            self._save()
            return deepcopy(u)

    def merge_guest_into(self, guest_uid: str, target_uid: str, *, auth_type: str) -> dict[str, Any]:
        with _LOCK:
            guest = self._users.get(guest_uid)
            if not guest:
                # 재배포로 유실된 게스트 스텁
                guest = _empty_user(guest_uid, auth_type="anonymous")
                self._users[guest_uid] = guest
            target = self._users.get(target_uid)
            if target is None:
                target = _empty_user(target_uid, auth_type=auth_type)
                target["anonymous_linked_from"] = guest_uid
                self._users[target_uid] = target
            else:
                target["auth_type"] = auth_type
                if not target.get("anonymous_linked_from"):
                    target["anonymous_linked_from"] = guest_uid

            # merge lists/maps
            titles = list(dict.fromkeys((target.get("earned_titles") or []) + (guest.get("earned_titles") or [])))
            title_ids = list(dict.fromkeys((target.get("title_ids") or []) + (guest.get("title_ids") or [])))
            target["earned_titles"] = titles
            target["title_ids"] = title_ids
            target["unlocks"] = list(
                dict.fromkeys((target.get("unlocks") or []) + (guest.get("unlocks") or []))
            )

            tp = target.setdefault("preferences", {})
            gp = guest.get("preferences") or {}
            hate = dict(tp.get("hate_tags") or {})
            for k, v in (gp.get("hate_tags") or {}).items():
                hate[k] = float(hate.get(k, 0)) + float(v)
            tp["hate_tags"] = hate
            hc = dict(tp.get("hate_categories") or {})
            for k, v in (gp.get("hate_categories") or {}).items():
                hc[k] = float(hc.get(k, 0)) + float(v)
            tp["hate_categories"] = hc
            taste = list(dict.fromkeys((tp.get("taste") or []) + (gp.get("taste") or [])))
            tp["taste"] = taste[-20:]

            logs = (target.get("swipe_logs") or []) + (guest.get("swipe_logs") or [])
            target["swipe_logs"] = logs[-500:]

            for did in guest.get("device_ids") or []:
                if did not in target.setdefault("device_ids", []):
                    target["device_ids"].append(did)
                self._device_index[did] = target_uid

            target["updated_at"] = _now()
            # keep guest stub pointing to linked account
            guest["linked_to"] = target_uid
            guest["updated_at"] = _now()
            self._save()
            return deepcopy(target)

    def append_swipe(self, uid: str, event: dict[str, Any]) -> dict[str, Any]:
        with _LOCK:
            u = self._users.get(uid)
            if not u:
                raise KeyError("user_not_found")
            logs = u.setdefault("swipe_logs", [])
            logs.append({**event, "at": _now()})
            u["swipe_logs"] = logs[-500:]
            # 거절을 장기 비선호로 바로 누적하지 않는다.
            # 일자별 신호는 2단계에서 swipe_logs를 읽어 계산한다.
            u["updated_at"] = _now()
            self._save()
            return deepcopy(u)

    def set_taste(self, uid: str, taste: list[str]) -> dict[str, Any]:
        with _LOCK:
            u = self._users.get(uid)
            if not u:
                raise KeyError("user_not_found")
            u.setdefault("preferences", {})["taste"] = list(taste or [])[:20]
            u["updated_at"] = _now()
            self._save()
            return deepcopy(u)

    def get_taste(self, uid: str) -> list[str]:
        u = self.get(uid)
        if not u:
            return []
        taste = (u.get("preferences") or {}).get("taste") or []
        return [str(x) for x in taste if x]

    def taste_signals(self, uid: str) -> dict[str, Any]:
        u = self.get(uid)
        if not u:
            return compute_taste_signals([])
        prefs = u.get("preferences") or {}
        return compute_taste_signals(
            u.get("swipe_logs") or [],
            exclude=list(prefs.get("exclude_categories") or []),
        )

    def earn_title(self, uid: str, title: str, title_id: str = "") -> dict[str, Any]:
        with _LOCK:
            u = self._users.get(uid)
            if not u:
                raise KeyError("user_not_found")
            titles = u.setdefault("earned_titles", [])
            if title and title not in titles:
                titles.append(title)
            ids = u.setdefault("title_ids", [])
            if title_id and title_id not in ids:
                ids.append(title_id)
            u["updated_at"] = _now()
            self._save()
            return deepcopy(u)

    def add_unlock(self, uid: str, key: str) -> dict[str, Any]:
        """영수증 테마 등 코스메틱 해금."""
        with _LOCK:
            u = self._users.get(uid)
            if not u:
                raise KeyError("user_not_found")
            unlocks = u.setdefault("unlocks", [])
            if key and key not in unlocks:
                unlocks.append(key)
            u["updated_at"] = _now()
            self._save()
            return deepcopy(u)

    def set_nickname(self, uid: str, nickname: str) -> dict[str, Any]:
        with _LOCK:
            u = self._users.get(uid)
            if not u:
                raise KeyError("user_not_found")
            if nickname:
                u["nickname"] = nickname
            u["updated_at"] = _now()
            self._save()
            return deepcopy(u)

    def public_profile(self, uid: str) -> dict[str, Any] | None:
        u = self.get(uid)
        if not u:
            return None
        return {
            "uid": u["uid"],
            "auth_type": u.get("auth_type"),
            "anonymous_linked_from": u.get("anonymous_linked_from"),
            "nickname": u.get("nickname"),
            "earned_titles": u.get("earned_titles") or [],
            "title_ids": u.get("title_ids") or [],
            "unlocks": u.get("unlocks") or [],
            "preferences": u.get("preferences") or {},
            "swipe_count": len(u.get("swipe_logs") or []),
            "device_bound": bool(u.get("device_ids")),
            "created_at": u.get("created_at"),
            "updated_at": u.get("updated_at"),
        }


STORE = UserStore()


def verify_kakao_access_token(access_token: str) -> dict[str, Any]:
    """카카오 액세스 토큰 → 유저 id/nickname."""
    token = (access_token or "").strip()
    if not token:
        raise ValueError("missing_token")
    with httpx.Client(timeout=6.0) as client:
        res = client.get(
            "https://kapi.kakao.com/v2/user/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code != 200:
            raise ValueError(f"kakao_invalid:{res.status_code}")
        data = res.json()
    kid = str(data.get("id") or "")
    if not kid:
        raise ValueError("kakao_no_id")
    props = data.get("kakao_account", {}).get("profile") or {}
    nick = props.get("nickname") or data.get("properties", {}).get("nickname") or "카카오유저"
    return {"kakao_id": kid, "nickname": nick, "raw": data}


def exchange_kakao_auth_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """인가 코드 → access_token (REST API 키 필요). SDK v2 authorize 플로우."""
    rest_key = (os.getenv("KAKAO_REST_API_KEY") or "").strip()
    if not rest_key:
        raise ValueError("missing_rest_key")
    code = (code or "").strip()
    redirect_uri = (redirect_uri or "").strip().rstrip("/")
    if not code or not redirect_uri:
        raise ValueError("missing_code_or_redirect")

    secret = (os.getenv("KAKAO_CLIENT_SECRET") or "").strip()
    # www / apex, trailing slash 변형 시도
    candidates = []
    for u in (redirect_uri, redirect_uri + "/"):
        if u not in candidates:
            candidates.append(u)
    if "://www." in redirect_uri:
        alt = redirect_uri.replace("://www.", "://", 1)
        candidates.extend([alt, alt + "/"])
    elif "://" in redirect_uri:
        # insert www.
        scheme, rest = redirect_uri.split("://", 1)
        alt = f"{scheme}://www.{rest}"
        candidates.extend([alt, alt + "/"])

    last_err = "token_exchange_failed"
    with httpx.Client(timeout=8.0) as client:
        for uri in candidates:
            payload = {
                "grant_type": "authorization_code",
                "client_id": rest_key,
                "redirect_uri": uri,
                "code": code,
            }
            if secret:
                payload["client_secret"] = secret
            res = client.post(
                "https://kauth.kakao.com/oauth/token",
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
                },
            )
            if res.status_code == 200:
                token_data = res.json()
                access = token_data.get("access_token")
                if not access:
                    raise ValueError("no_access_token")
                profile = verify_kakao_access_token(access)
                return {**profile, "access_token": access}
            body = (res.text or "")[:240]
            last_err = f"token_exchange:{res.status_code}:{body}"
            # 코드는 1회용 — 첫 실패 후 다른 URI도 거의 실패하지만 mismatch면 재시도 의미 있음
            if "KOE303" in body or "redirect" in body.lower() or res.status_code == 400:
                continue
            break

    if "secret" in last_err.lower() or "KOE010" in last_err or "-401" in last_err:
        raise ValueError(
            "client_secret_required:"
            "카카오 REST 키 Client Secret이 ON이면 Render에 KAKAO_CLIENT_SECRET을 넣거나 Secret을 OFF 하세요"
        )
    raise ValueError(last_err)


def new_device_id() -> str:
    return uuid.uuid4().hex
