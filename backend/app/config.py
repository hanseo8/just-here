"""공용 설정."""
from __future__ import annotations

import os
from pathlib import Path

# 레포 안 data/는 Render에서 휘발한다. 영구 디스크를 붙였으면
# DATA_DIR로 마운트 경로(예: /data)를 넘겨 그쪽에 쓴다.
_REPO_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def data_dir() -> Path:
    env = (os.getenv("DATA_DIR") or "").strip()
    path = Path(env) if env else _REPO_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_base_url(request_base: str | None = None) -> str:
    """공유/Duo 링크용 절대 URL. 배포 시 PUBLIC_BASE_URL 우선."""
    env = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    if env:
        return env
    if request_base:
        return request_base.rstrip("/")
    return "http://127.0.0.1:8010"
