"""300P 영수증 보상 원장과 중복 방지를 검증한다."""
from __future__ import annotations

import tempfile
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

print("영수증 보상 검사 통과")
