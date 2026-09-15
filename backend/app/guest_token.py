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
    if not token or "." not in token:
        return None
    raw, _, sig = token.partition(".")
    expect = hmac.new(_secret(), raw.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw + pad))
    except Exception:
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    uid = str(payload.get("uid") or "").strip()
    if not uid:
        return None
    return payload
