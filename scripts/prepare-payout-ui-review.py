"""Create disposable local data for visual payout-flow review.

This script refuses production-like paths and prints a short-lived test identity.
It never sends money or contacts an external service.
"""
import argparse
import json
from scripts.receipt_image_fixture import receipt_image
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    target = args.directory.resolve()
    if "payout-ui-review" not in target.name or target.exists():
        raise SystemExit("use a new directory whose name contains payout-ui-review")
    target.mkdir(parents=True)
    os.environ.update(
        DATA_DIR=str(target), RECEIPT_REWARDS="on", RECEIPT_REWARDS_ALLOW_VOLATILE="on",
        REWARD_BANK_PAYOUTS="on", PAYOUT_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ADMIN_TOKEN="local-review-only", GUEST_SIGNING_SECRET="local-review-signing-secret",
    )
    from backend.app import guest_token, payouts, rewards
    store = rewards.get_store()
    uid = "kakao_local_ui_review"

    def approved(number, place, menu, days_ago=0):
        attribution = store.create_attribution(
            uid=uid, session_id="ui-session-" + str(number), place_id="place-" + str(number),
            place_name=place, menu_id="menu-" + str(number), menu_name=menu, intent="visit",
        )
        receipt = store.submit_receipt(
            uid=uid, attribution_id=attribution["id"],
            purchased_at=rewards._iso(datetime.now(timezone.utc) - timedelta(days=days_ago)), amount_krw=12000,
            approval_number="770000" + str(number), content_type="image/jpeg",
            image=receipt_image(number), review_return="yes",
            review_tags=["맛있어요"], review_note="화면 검수용 가상 영수증", photo_reuse_consent=False,
        )
        store.decide(receipt["id"], approve=True, reason="local ui review", admin_id="fixture")
        return receipt["id"]

    first = approved(1, "검수 식당", "비빔밥")
    approved(2, "두 번째 검수 식당", "파스타", days_ago=1)
    pending = payouts.request(store, uid=uid, receipt_id=first, request_id="ui-review-request",
                              bank="검수은행", account="123456789012", holder="검수사용자")
    print(json.dumps({
        "uid": uid, "guest_token": guest_token.issue(uid, "kakao"), "admin_token": "local-review-only",
        "payout_id": pending["id"], "data_dir": str(target),
        "payout_encryption_key": os.environ["PAYOUT_ENCRYPTION_KEY"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
