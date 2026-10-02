"""영수증 보상 API 인증·업로드·관리자 승인을 통합 검증한다."""
from __future__ import annotations

import os
import tempfile
import runpy
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def check(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)
    print(f"OK  {message}")


with tempfile.TemporaryDirectory() as raw:
    os.environ["DATA_DIR"] = raw
    os.environ["RECEIPT_REWARDS"] = "on"
    os.environ["RECEIPT_REWARDS_ALLOW_VOLATILE"] = "on"
    os.environ["ADMIN_TOKEN"] = "test-admin-token"
    os.environ["GUEST_SIGNING_SECRET"] = "test-signing-secret"

    from fastapi.testclient import TestClient
    from backend.app import rewards
    from backend.app.main import app

    client = TestClient(app)
    auth = client.post("/v1/auth/guest", json={"device_id": "reward-api-device"})
    check(auth.status_code == 200, "게스트 인증")
    identity = auth.json()
    uid = identity["uid"]
    headers = {"X-Guest-Token": identity["guest_token"]}

    att = rewards.get_store().create_attribution(
        uid=uid, session_id="api-session", place_id="api-place",
        place_name="API 테스트 식당", menu_id="api-menu", menu_name="비빔밥", intent="visit",
    )
    upload = client.post(
        "/v1/rewards/receipts",
        headers=headers,
        data={
            "uid": uid,
            "attribution_id": att["id"],
            "purchased_at": datetime.now(timezone.utc).isoformat(),
            "amount_krw": "11000",
            "approval_number": "99887766",
            "review_return": "yes",
            "review_tags": "든든해요",
            "review_note": "다시 갈래요",
            "photo_reuse_consent": "false",
        },
        files={"image": ("receipt.jpg", b"\xff\xd8\xfftest-api-image", "image/jpeg")},
    )
    check(upload.status_code == 200, "인증된 사용자 영수증 업로드")
    receipt_id = upload.json()["receipt"]["id"]

    denied = client.get("/v1/admin/rewards")
    check(denied.status_code == 401, "관리자 목록 무인증 차단")
    admin_headers = {"X-Admin-Token": "test-admin-token"}
    queue = client.get("/v1/admin/rewards", headers=admin_headers)
    check(queue.json()["summary"]["pending_points"] == 300, "pending rewards reserve budget")
    check(queue.status_code == 200 and len(queue.json()["receipts"]) == 1, "관리자 검토 큐")
    image = client.get(f"/v1/admin/rewards/{receipt_id}/image", headers=admin_headers)
    check(image.status_code == 200 and image.headers["cache-control"].startswith("no-store"), "영수증 이미지 보호")
    decision = client.post(
        f"/v1/admin/rewards/{receipt_id}/decision",
        headers=admin_headers,
        json={"approve": True, "reason": "확인"},
    )
    check(decision.status_code == 200, "관리자 300P 승인")
    mine = client.get(f"/v1/rewards/me?uid={uid}", headers=headers)
    check(mine.status_code == 200 and mine.json()["balance"] == 300, "사용자 잔액 300P")

    summary = client.get("/v1/admin/rewards", headers=admin_headers).json()["summary"]
    check(summary["claims_remaining"] == 99 and summary["committed_points"] == 300, "pilot budget summary")
    check(client.get("/v1/admin/rewards/backup").status_code == 401, "backup requires admin authentication")
    os.environ["RECEIPT_REWARDS"] = "off"
    stopped = client.get("/v1/admin/rewards", headers=admin_headers).json()
    check(not stopped["rewards"]["enabled"] and stopped["summary"]["points_issued"] == 300, "stopped pilot retains admin visibility")
    result = client.get("/v1/admin/rewards/backup", headers=admin_headers)
    check(result.status_code == 200 and "no-store" in result.headers["cache-control"], "backup available when pilot stopped")
    archive = Path(raw) / "backup.zip"
    archive.write_bytes(result.content)
    restore = runpy.run_path(str(Path(__file__).with_name("restore-rewards.py")))["restore"]
    target = Path(raw) / "restored"
    restore(archive, target)
    restored = rewards.RewardStore(target / "rewards.sqlite3")
    check(restored.list_for_user(uid)["balance"] == 300, "restored ledger matches balance")
    restored_image, _ = restored.image_path(receipt_id)
    check(restored_image.read_bytes() == image.content, "restored receipt image matches original")
    try:
        restore(archive, target)
        raise AssertionError("existing target was accepted")
    except ValueError:
        check(restored.list_for_user(uid)["balance"] == 300, "restore refuses overwriting existing data")
    corrupt = Path(raw) / "corrupt.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, "w") as out:
        for name in source.namelist():
            content = source.read(name)
            if name == "rewards.sqlite3":
                content += b"changed"
            out.writestr(name, content)
    try:
        restore(corrupt, Path(raw) / "invalid")
        raise AssertionError("tampered backup accepted")
    except ValueError:
        check(not (Path(raw) / "invalid").exists(), "checksum rejects damaged backup before restore")

print("영수증 보상 API 검사 통과")
