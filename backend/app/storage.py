"""저장 위치·영구 디스크 판정. 환경변수만으로 persistent를 켜지 않는다."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import data_dir as configured_data_dir
from .config import _REPO_DATA_DIR

log = logging.getLogger("justhere.storage")

WATCH_FILES = (
    "verified-menus.json",
    "users.json",
    "events.jsonl",
    "deals.json",
    "rewards.sqlite3",
    "receipt_uploads",
    ".guest_secret",
)
BACKUP_FILES = (
    "users.json",
    "events.jsonl",
    "verified-menus.json",
    "deals.json",
)
JSON_CHECK_FILES = (
    "users.json",
    "verified-menus.json",
    "deals.json",
)


def inspect_path(path: Path) -> dict[str, Any]:
    exists = path.exists()
    info: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "is_dir": bool(exists and path.is_dir()),
        "is_file": bool(exists and path.is_file()),
        "is_mount": bool(exists and os.path.ismount(path)),
        "writable": bool(exists and os.access(path, os.W_OK)),
        "dev": None,
        "bytes": None,
        "mtime": None,
    }
    if not exists:
        return info
    try:
        st = path.stat()
        info["dev"] = st.st_dev
        info["bytes"] = st.st_size
        info["mtime"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except OSError as exc:
        info["stat_error"] = str(exc)
    return info


def is_persistent_dir(path: Path | None = None) -> bool:
    """DATA_DIR이 있고 쓰기 가능하다는 이유만으로 True가 되지 않는다."""
    target = Path(path) if path is not None else configured_data_dir()
    if not target.exists() or not target.is_dir():
        return False
    if not os.access(target, os.W_OK):
        return False
    try:
        if target.resolve() == _REPO_DATA_DIR.resolve():
            return False
    except OSError:
        return False
    return os.path.ismount(target)


def env_data_dir() -> str:
    return (os.getenv("DATA_DIR") or "").strip()


def file_inventory(root: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name in WATCH_FILES:
        files[name] = inspect_path(root / name)
    extra = []
    if root.exists() and root.is_dir():
        try:
            extra = sorted(
                p.name
                for p in root.iterdir()
                if p.name not in WATCH_FILES and not p.name.startswith(".")
            )
        except OSError as exc:
            extra = [f"list_error:{exc}"]
    return {"files": files, "other": extra}


def snapshot() -> dict[str, Any]:
    env = env_data_dir()
    used = configured_data_dir()
    mount = Path("/data")
    persistent = is_persistent_dir(used)
    return {
        "data_dir_env": env,
        "data_dir": str(used),
        "repo_data_dir": str(_REPO_DATA_DIR),
        "persistent": persistent,
        "persistent_reason": _reason(used, env, persistent),
        "used": inspect_path(used),
        "mount_candidate": inspect_path(mount),
        "aligned": bool(env) and Path(env) == used and persistent,
        **file_inventory(used),
    }


def _reason(used: Path, env: str, persistent: bool) -> str:
    if persistent:
        return "data_dir_is_mount"
    if not env:
        return "data_dir_env_empty"
    if not used.exists():
        return "data_dir_missing"
    if used.resolve() == _REPO_DATA_DIR.resolve():
        return "repo_data_dir"
    if not os.path.ismount(used):
        return "data_dir_not_a_mount"
    if not os.access(used, os.W_OK):
        return "data_dir_not_writable"
    return "not_persistent"


def memory_counts() -> dict[str, int]:
    from . import duo, engine, share

    return {
        "sessions": len(engine.SESSIONS),
        "receipts": len(share.RECEIPTS),
        "duo_rooms": len(duo.ROOMS),
    }


def public_status() -> dict[str, bool]:
    """공개 헬스용. 경로·파일명·식별자는 넣지 않는다."""
    try:
        used = configured_data_dir()
        writable = used.exists() and used.is_dir() and os.access(used, os.W_OK)
        damaged = False
        for name in JSON_CHECK_FILES:
            path = used / name
            if path.exists() and not validate_json_file(path)["valid"]:
                damaged = True
        return {"ok": bool(writable and not damaged), "persistent": is_persistent_dir(used)}
    except Exception:
        log.exception("public storage status failed")
        return {"ok": False, "persistent": False}


def admin_snapshot() -> dict[str, Any]:
    used = configured_data_dir()
    checks = {name: validate_json_file(used / name) for name in JSON_CHECK_FILES}
    events = inspect_path(used / "events.jsonl")
    events_path = used / "events.jsonl"
    events["lines"] = 0
    if events_path.exists():
        try:
            with events_path.open(encoding="utf-8") as fh:
                events["lines"] = sum(1 for _ in fh)
        except OSError as exc:
            events["read_error"] = str(exc)
    return {
        **snapshot(),
        "memory": memory_counts(),
        "json_checks": checks,
        "events": events,
        "public": public_status(),
        "memory_only": ["receipts", "duo_rooms", "sessions"],
    }


def backup_payload() -> dict[str, Any]:
    used = configured_data_dir()
    files: dict[str, Any] = {}
    missing: list[str] = []
    errors: dict[str, str] = {}
    for name in BACKUP_FILES:
        path = used / name
        if not path.exists():
            missing.append(name)
            continue
        try:
            files[name] = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors[name] = str(exc)
            log.error("backup read failed path=%s error=%s", path, exc)
    return {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": files,
        "missing": missing,
        "errors": errors,
        "excluded": [".guest_secret"],
    }


def validate_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "valid": False, "error": "missing"}
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return {"exists": True, "valid": True, "error": ""}
    except Exception as exc:
        log.error("json file damaged path=%s error=%s", path, exc)
        return {"exists": True, "valid": False, "error": str(exc)}
