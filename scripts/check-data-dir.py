"""DATA_DIR 환경변수가 실제 쓰기 경로를 바꾸는지 확인한다.

사용: python scripts/check-data-dir.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"

PROBE = """
import json
from app import analytics, users
from app.config import data_dir

analytics.append_event("app_open", device_id="probe-device")
users.STORE.ensure_guest("probe-device")

print(json.dumps({
    "data_dir": str(data_dir()),
    "events": str(analytics.EVENTS_PATH),
    "users": str(users.USERS_PATH),
    "events_exists": analytics.EVENTS_PATH.exists(),
    "users_exists": users.USERS_PATH.exists(),
}))
"""


def run(data_dir: str | None) -> dict:
    env = dict(os.environ)
    if data_dir is None:
        env.pop("DATA_DIR", None)
    else:
        env["DATA_DIR"] = data_dir
    out = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        print(out.stderr.strip())
        raise SystemExit(f"probe 실패 (DATA_DIR={data_dir})")
    import json

    return json.loads(out.stdout.strip().splitlines()[-1])


def main() -> int:
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "disk"
        got = run(str(target))
        on_disk = Path(got["data_dir"]) == target
        wrote = got["events_exists"] and got["users_exists"]
        under = Path(got["events"]).parent == target
        ok = on_disk and wrote and under
        failures += 0 if ok else 1
        print(f"{'OK  ' if ok else '실패'} DATA_DIR 지정 시 그 경로에 쓴다: {got['data_dir']}")
        print(f"{'OK  ' if wrote else '실패'} events.jsonl / users.json 생성됨")

    got = run(None)
    repo_data = (BACKEND.parent / "data").resolve()
    fallback_ok = Path(got["data_dir"]).resolve() == repo_data
    failures += 0 if fallback_ok else 1
    print(f"{'OK  ' if fallback_ok else '실패'} 미지정 시 레포 data/ 로 폴백: {got['data_dir']}")

    print("")
    print("통과" if failures == 0 else f"실패 {failures}건")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
