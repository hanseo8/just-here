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
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
USERS_PATH = DATA_DIR / "users.json"
_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _empty_user(uid: str, *, auth_type: str, device_id: str = "") -> dict[str, Any]:
    return {
        "uid": uid,
        "auth_type": auth_type,  # anonymous | kakao
        "device_ids": [device_id] if device_id else [],
        "anonymous_linked_from": None,
        "nickname": "고민제로",
        "earned_titles": [],
        "title_ids": [],
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

    def merge_guest_into(self, guest_uid: str, target_uid: str, *, auth_type: str) -> dict[str, Any]:
        with _LOCK:
            guest = self._users.get(guest_uid)
            if not guest:
                raise KeyError("guest_not_found")
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
            prefs = u.setdefault("preferences", {})
            if event.get("action") == "nope":
                for tag in event.get("tags") or []:
                    ht = prefs.setdefault("hate_tags", {})
                    ht[tag] = float(ht.get(tag, 0)) + 1.0
                cat = event.get("category")
                if cat:
                    hc = prefs.setdefault("hate_categories", {})
                    hc[cat] = float(hc.get(cat, 0)) + 0.8
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


def new_device_id() -> str:
    return uuid.uuid4().hex
