"""공용 설정."""
from __future__ import annotations

import os


def public_base_url(request_base: str | None = None) -> str:
    """공유/Duo 링크용 절대 URL. 배포 시 PUBLIC_BASE_URL 우선."""
    env = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    if env:
        return env
    if request_base:
        return request_base.rstrip("/")
    return "http://127.0.0.1:8010"
