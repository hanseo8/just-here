"""게스트 소유권 토큰.

uid만 알면 /v1/me·taste·unlock·swipe를 누구나 만질 수 있었다.
발급은 /v1/auth/guest (또는 카카오 병합)에서만 하고, 이후 요청은
X-Guest-Token이 그 uid와 일치할 때만 통과시킨다.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

from .config import data_dir

TTL_SEC = 90 * 24 * 3600


def _secret() -> bytes:
    env = (os.getenv("GUEST_SIGNING_SECRET") or os.getenv("ADMIN_TOKEN") or "").strip()
    if env:
        return env.encode("utf-8")
    path = data_dir() / ".guest_secret"
    if path.exists():
        return path.read_bytes().strip() or path.read_bytes()
    val = secrets.token_hex(32)
    path.write_text(val, encoding="utf-8")
    return val.encode("utf-8")


def issue(uid: str, device_id: str = "") -> str:
    payload = {
        "uid": (uid or "").strip(),
        "did": (device_id or "")[:80],
        "iat": int(time.time()),
        "exp": int(time.time()) + TTL_SEC,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    return f"{raw.decode('ascii')}.{sig}"


def verify(token: str | None) -> dict[str, Any] | None:
    if not isinstance(token, str) or not token or len(token) > 4096 or token.count(".") != 1:
        return None
    raw, _, sig = token.partition(".")
    if not raw.isascii() or len(sig) != 64 or any(c not in "0123456789abcdef" for c in sig):
        return None
    expect = hmac.new(_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw + pad))
    except Exception:
        return None
    if not isinstance(payload, dict) or type(payload.get("exp")) is not int:
        return None
    if payload["exp"] <= int(time.time()):
        return None
    uid = payload.get("uid")
    if not isinstance(uid, str):
        return None
    uid = uid.strip()
    if not uid:
        return None
    return payload
