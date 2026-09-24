"""통제 기록을 남긴 뒤 프로세스 재시작 전후 값을 비교한다.

환경변수가 있다는 이유만으로 persistent=true가 되면 실패한다.
승인 메뉴 파일이 이미 있으면 재기동이 덮어쓰지 않아야 한다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def fail(msg: str) -> None:
    print("FAIL", msg)
    sys.exit(1)


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def wait_up(base: str, retries: int = 40) -> dict:
    last = ""
    for _ in range(retries):
        try:
            return get(f"{base}/health")
        except Exception as exc:
            last = str(exc)
            time.sleep(0.25)
    fail(f"server did not start: {last}")
    return {}


def start(data: Path, port: int) -> subprocess.Popen:
    env = dict(os.environ)
    env["DATA_DIR"] = str(data)
    env["VERIFIED_MENUS_VISIT"] = "on"
    env["PUBLIC_BASE_URL"] = ""
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def main() -> None:
    data = ROOT / "data" / "_persist-probe"
    data.mkdir(parents=True, exist_ok=True)
    port = 8099
    base = f"http://127.0.0.1:{port}"
    probe_id = f"persist-{int(time.time())}"
    device = f"probe-{probe_id}"
    custom_note = f"keep-{probe_id}"

    menus = data / "verified-menus.json"
    menus.write_text(
        json.dumps(
            {
                "experiment_id": "persist_probe",
                "menus": [
                    {
                        "menu_name": "보존국밥",
                        "place_name": "보존식당",
                        "address": "인천 연수구 송도동 1",
                        "source": "official",
                        "source_note": custom_note,
                        "confirmed_at": "2026-09-24",
                        "menu_scope": "branch",
                        "branch_sale_confirmed": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    proc = start(data, port)
    try:
        health1 = wait_up(base)
        stor1 = health1.get("storage") or {}
        if stor1.get("persistent") is True:
            fail("일반 폴더를 persistent=true로 판정했다")
        if stor1.get("persistent_reason") not in {"data_dir_not_a_mount", "repo_data_dir"}:
            print("note persistent_reason", stor1.get("persistent_reason"))

        guest = post(f"{base}/v1/auth/guest", {"device_id": device})
        uid = guest.get("uid") or ""
        if not uid:
            fail("게스트를 만들지 못했다")
        ev = post(
            f"{base}/v1/analytics/event",
            {
                "event": "app_open",
                "device_id": device,
                "props": {"persist_probe_id": probe_id},
            },
        )
        if not ev.get("ts"):
            fail("이벤트를 쓰지 못했다")
        duo = post(
            f"{base}/v1/duo",
            {
                "lat": 37.3925,
                "lng": 126.6450,
                "intent": "visit",
                "weather": "clear",
                "taste": ["chicken"],
                "host_name": probe_id,
            },
        )
        receipt = post(
            f"{base}/v1/share/receipt",
            {
                "title": probe_id,
                "place_name": "보존식당",
                "menu_name": "보존국밥",
                "intent": "visit",
            },
        )
        before = {
            "uid": uid,
            "event_ts": ev.get("ts"),
            "duo_id": duo.get("id") or duo.get("duo_id"),
            "receipt_id": (receipt.get("receipt") or receipt).get("id")
            if isinstance(receipt.get("receipt"), dict)
            else receipt.get("id"),
            "menu_note": json.loads(menus.read_text(encoding="utf-8"))["menus"][0]["source_note"],
            "users_bytes": (data / "users.json").stat().st_size if (data / "users.json").exists() else 0,
            "events_bytes": (data / "events.jsonl").stat().st_size if (data / "events.jsonl").exists() else 0,
        }
        print("before", json.dumps(before, ensure_ascii=False))
        if before["users_bytes"] <= 0 or before["events_bytes"] <= 0:
            fail("재시작 전에 사용자·이벤트 파일이 생기지 않았다")
    finally:
        stop(proc)

    proc2 = start(data, port)
    try:
        health2 = wait_up(base)
        stor2 = health2.get("storage") or {}
        if stor2.get("persistent") is True:
            fail("재시작 뒤에도 일반 폴더를 영구 디스크로 봤다")
        after_note = json.loads(menus.read_text(encoding="utf-8"))["menus"][0]["source_note"]
        if after_note != custom_note:
            fail("재기동이 운영 메뉴 파일을 덮어썼다")
        saved = json.loads((data / "users.json").read_text(encoding="utf-8"))
        if uid not in (saved.get("users") or {}):
            fail(f"재시작 후 사용자가 파일에 없다 {list((saved.get('users') or {}).keys())}")
        events = (data / "events.jsonl").read_text(encoding="utf-8")
        if probe_id not in events:
            fail("재시작 후 이벤트 기록이 없다")
        try:
            get(f"{base}/v1/duo/{before['duo_id']}")
            fail("Duo가 파일에 남은 것처럼 보인다")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                fail(f"Duo 재시작 응답 {exc.code}")
        try:
            rid = before["receipt_id"]
            if rid:
                get(f"{base}/v1/share/receipt/{rid}")
                fail("영수증이 파일에 남은 것처럼 보인다")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                fail(f"영수증 재시작 응답 {exc.code}")
        after = {
            "users_bytes": (data / "users.json").stat().st_size,
            "events_bytes": (data / "events.jsonl").stat().st_size,
            "menu_note": after_note,
            "memory": stor2.get("memory"),
        }
        print("after", json.dumps(after, ensure_ascii=False))
        if after["users_bytes"] != before["users_bytes"]:
            fail("사용자 파일 크기가 재시작 후 달라졌다")
        if after["events_bytes"] < before["events_bytes"]:
            fail("이벤트 파일이 재시작 후 줄었다")
        if (stor2.get("memory") or {}).get("duo_rooms", 1) != 0:
            fail("Duo가 재시작 후에도 메모리에 남아 있다")
        if (stor2.get("memory") or {}).get("receipts", 1) != 0:
            fail("영수증이 재시작 후에도 메모리에 남아 있다")
    finally:
        stop(proc2)

    print("storage persist 통과")
    print("파일 보존: users.json / events.jsonl / verified-menus.json")
    print("메모리 소멸: duo / receipt / session")
    print("persistent=false (마운트 아님)")


if __name__ == "__main__":
    main()
