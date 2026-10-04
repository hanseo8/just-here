"""300P 영수증 보상 원장과 중복 방지를 검증한다."""
from __future__ import annotations

import tempfile
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.app.rewards import REWARD_POINTS, RewardStore


def check(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)
    print(f"OK  {message}")


with tempfile.TemporaryDirectory() as raw:
    store = RewardStore(Path(raw) / "rewards.sqlite3")
    att = store.create_attribution(
        uid="guest_a",
        session_id="session_a",
        place_id="place_a",
        place_name="테스트 식당",
        menu_id="menu_a",
        menu_name="비빔밥",
        intent="visit",
    )
    check(att["place_name"] == "테스트 식당", "추천 귀속 저장")
    receipt = store.submit_receipt(
        uid="guest_a",
        attribution_id=att["id"],
        purchased_at=datetime.now(timezone.utc).isoformat(),
        amount_krw=12000,
        approval_number="12345678",
        content_type="image/jpeg",
        image=b"\xff\xd8\xff" + b"test-receipt-a",
        review_return="yes",
        review_tags=["맛있어요"],
        review_note="다시 먹고 싶어요",
        photo_reuse_consent=False,
    )
    check(receipt["status"] == "pending", "접수는 검토 중 상태")
    approved = store.decide(receipt["id"], approve=True, reason="확인", admin_id="test")
    check(approved["status"] == "approved", "관리자 승인")
    store.decide(receipt["id"], approve=True, reason="재시도", admin_id="test")
    me = store.list_for_user("guest_a")
    check(me["balance"] == REWARD_POINTS, "재승인에도 300P 한 번만 적립")

    att2 = store.create_attribution(
        uid="guest_b", session_id="session_b", place_id="place_b",
        place_name="두 번째 식당", menu_id="menu_b", menu_name="국밥", intent="visit",
    )
    duplicate_blocked = False
    try:
        store.submit_receipt(
            uid="guest_b", attribution_id=att2["id"],
            purchased_at=datetime.now(timezone.utc).isoformat(), amount_krw=9000,
            approval_number="12345678", content_type="image/jpeg",
            image=b"\xff\xd8\xff" + b"another-image", review_return="maybe",
            review_tags=[], review_note="", photo_reuse_consent=False,
        )
    except ValueError as exc:
        duplicate_blocked = str(exc) == "duplicate_or_daily_limit"
    check(duplicate_blocked, "동일 승인번호 중복 차단")

    os.environ["RECEIPT_REWARDS_MAX_CLAIMS"] = "1"
    try:
        store.submit_receipt(
            uid="guest_b", attribution_id=att2["id"],
            purchased_at=datetime.now(timezone.utc).isoformat(), amount_krw=9000,
            approval_number="87654321", content_type="image/jpeg",
            image=b"\xff\xd8\xffcapacity", review_return="no",
            review_tags=[], review_note="", photo_reuse_consent=False,
        )
        raise AssertionError("capacity was not enforced")
    except ValueError as exc:
        check(str(exc) == "pilot_capacity_reached", "승인·접수 합산 모집 상한")
    finally:
        os.environ.pop("RECEIPT_REWARDS_MAX_CLAIMS", None)
    image_path, _ = store.image_path(receipt["id"])
    with store._db() as db:
        db.execute("UPDATE receipts SET decided_at='2020-01-01T00:00:00Z' WHERE id=?", (receipt["id"],))
    store._purge_expired_images()
    check(not image_path.exists(), "보관기한 경과 원본 삭제")
    check(store.list_for_user("guest_a")["balance"] == 300, "원본 삭제 후 포인트 보존")

    store.merge_uid("guest_a", "kakao_a")
    store.merge_uid("guest_a", "kakao_a")
    check(store.list_for_user("kakao_a")["balance"] == 300, "account merge preserves points exactly once")
    check(store.list_for_user("guest_a")["balance"] == 0, "source balance migrated")
    store.create_attribution(
        uid="collision", session_id="session_a", place_id="place_a",
        place_name="test", menu_id="menu_a", menu_name="test", intent="visit",
    )
    try:
        store.merge_uid("kakao_a", "collision")
        raise AssertionError("collision should block merge")
    except sqlite3.IntegrityError:
        check(store.list_for_user("kakao_a")["balance"] == 300, "failed merge rolls back points")
        check(store.list_for_user("collision")["balance"] == 0, "failed merge leaves target unchanged")

print("영수증 보상 검사 통과")
