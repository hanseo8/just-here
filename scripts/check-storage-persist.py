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
ADMIN_TOKEN = "persist-probe-admin"
PUBLIC_STORAGE_KEYS = {"ok", "persistent"}


def fail(msg: str) -> None:
    print("FAIL", msg)
    sys.exit(1)


def get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def get_admin(url: str) -> dict:
    return get(url, {"x-admin-token": ADMIN_TOKEN})


def request_raw(url: str, headers: dict | None = None) -> tuple[int, dict[str, str], object]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            body = json.loads(res.read().decode("utf-8"))
            return res.status, {k.lower(): v for k, v in res.headers.items()}, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") if exc.fp else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = raw
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, body


def assert_no_store(headers: dict[str, str], where: str) -> None:
    cache = (headers.get("cache-control") or "").lower()
    if "no-store" not in cache:
        fail(f"{where} Cache-Control에 no-store가 없다 [{cache}]")
    if "private" not in cache and "no-cache" not in cache:
        fail(f"{where} 캐시 금지 헤더가 약하다 [{cache}]")


def assert_public_storage(payload: dict, where: str) -> dict:
    stor = payload.get("storage") or {}
    extra = set(stor) - PUBLIC_STORAGE_KEYS
    if extra:
        fail(f"{where} 공개 응답에 상세 진단이 있다 {sorted(extra)}")
    leaked = json.dumps(payload, ensure_ascii=False)
    for needle in ("data_dir", "users.json", "/data", "persist-probe"):
        if needle in leaked:
            fail(f"{where} 공개 응답에 {needle}가 있다")
    return stor


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
    env["ADMIN_TOKEN"] = ADMIN_TOKEN
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
        stor1 = assert_public_storage(health1, "health")
        if stor1.get("ok") is not True:
            fail(f"쓰기 가능한 폴더인데 storage.ok가 아니다 {stor1}")
        if stor1.get("persistent") is True:
            fail("일반 폴더를 persistent=true로 판정했다")
        meta1 = get(f"{base}/v1/meta")
        if "storage" in meta1:
            fail("공개 meta에 storage 상세가 있다")
        code, headers, _ = request_raw(f"{base}/v1/admin/storage")
        if code != 401:
            fail(f"관리자 저장 진단이 인증 없이 열렸다 {code}")
        assert_no_store(headers, "admin storage 401")
        code, headers, _ = request_raw(f"{base}/v1/admin/storage/backup")
        if code != 401:
            fail(f"관리자 백업이 인증 없이 열렸다 {code}")
        assert_no_store(headers, "admin backup 401")
        code, headers, _ = request_raw(
            f"{base}/v1/admin/storage",
            {"x-admin-token": "wrong-token"},
        )
        if code != 401:
            fail(f"잘못된 토큰으로 관리자 진단이 열렸다 {code}")
        code, headers, admin1 = request_raw(
            f"{base}/v1/admin/storage",
            {"x-admin-token": ADMIN_TOKEN},
        )
        if code != 200 or not isinstance(admin1, dict):
            fail(f"관리자 진단이 실패했다 {code}")
        assert_no_store(headers, "admin storage 200")
        if admin1.get("persistent") is True:
            fail("관리자 진단이 일반 폴더를 영구 디스크로 봤다")
        if admin1.get("persistent_reason") not in {"data_dir_not_a_mount", "repo_data_dir"}:
            print("note persistent_reason", admin1.get("persistent_reason"))
        if "data_dir" not in admin1:
            fail("관리자 진단에 data_dir이 없다")

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
        backup = get_admin(f"{base}/v1/admin/storage/backup")
        if ".guest_secret" in (backup.get("files") or {}):
            fail("백업에 게스트 시크릿이 포함됐다")
        if probe_id not in ((backup.get("files") or {}).get("events.jsonl") or ""):
            fail("백업 이벤트에 통제 기록이 없다")
        if uid not in ((backup.get("files") or {}).get("users.json") or ""):
            fail("백업 사용자에 통제 uid가 없다")
    finally:
        stop(proc)

    proc2 = start(data, port)
    try:
        health2 = wait_up(base)
        stor2 = assert_public_storage(health2, "health-after")
        if stor2.get("persistent") is True:
            fail("재시작 뒤에도 일반 폴더를 영구 디스크로 봤다")
        admin2 = get_admin(f"{base}/v1/admin/storage")
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
            "memory": admin2.get("memory"),
        }
        print("after", json.dumps(after, ensure_ascii=False))
        if after["users_bytes"] != before["users_bytes"]:
            fail("사용자 파일 크기가 재시작 후 달라졌다")
        if after["events_bytes"] < before["events_bytes"]:
            fail("이벤트 파일이 재시작 후 줄었다")
        if (admin2.get("memory") or {}).get("duo_rooms", 1) != 0:
            fail("Duo가 재시작 후에도 메모리에 남아 있다")
        if (admin2.get("memory") or {}).get("receipts", 1) != 0:
            fail("영수증이 재시작 후에도 메모리에 남아 있다")
    finally:
        stop(proc2)

    print("storage persist 통과")
    print("파일 보존: users.json / events.jsonl / verified-menus.json")
    print("메모리 소멸: duo / receipt / session")
    print("persistent=false (마운트 아님)")


if __name__ == "__main__":
    main()
