"""Manual bank settlement: reserving a reward never initiates a bank transfer."""
import json
import os
import re
import secrets
import sqlite3

from cryptography.fernet import Fernet, InvalidToken

from . import rewards


def cipher():
    return Fernet(os.environ.get("PAYOUT_ENCRYPTION_KEY", "").encode())


def status():
    try:
        cipher()
        encryption_ready = True
    except (ValueError, TypeError):
        encryption_ready = False
    return {
        "enabled": rewards.enabled() and rewards._on("REWARD_BANK_PAYOUTS") and encryption_ready,
        "amount_krw": 300,
        "channel": "bank_manual",
    }


def public(row):
    return {k: row[k] for k in (
        "id", "receipt_id", "amount_krw", "account_tail", "status", "reason", "created_at", "updated_at"
    )}


def request(store, *, uid, receipt_id, request_id, bank, account, holder):
    if not uid.startswith("kakao_"):
        raise ValueError("linked_account_required")
    account = re.sub(r"[ -]", "", account)
    if not re.fullmatch(r"[0-9]{8,20}", account) or not bank.strip() or not holder.strip():
        raise ValueError("invalid_bank_details")
    encrypted = cipher().encrypt(json.dumps({
        "bank": bank.strip(), "account": account, "holder": holder.strip(),
    }, ensure_ascii=False).encode()).decode()
    with rewards._LOCK, store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT * FROM payouts WHERE uid=? AND request_id=?", (uid, request_id)).fetchone()
        if existing:
            if existing["receipt_id"] != receipt_id:
                raise ValueError("request_id_conflict")
            return public(existing)
        receipt = db.execute("SELECT * FROM receipts WHERE id=? AND uid=? AND status='approved'", (receipt_id, uid)).fetchone()
        if not receipt:
            raise ValueError("approved_receipt_required")
        balance = db.execute("SELECT COALESCE(SUM(amount),0) FROM reward_ledger WHERE uid=?", (uid,)).fetchone()[0]
        if balance < 300:
            raise ValueError("insufficient_balance")
        ident = "pay_" + secrets.token_urlsafe(12)
        now = rewards._iso()
        try:
            db.execute("""INSERT INTO payouts
                (id,uid,request_id,receipt_id,amount_krw,recipient_encrypted,account_tail,created_at,updated_at)
                VALUES (?,?,?,?,300,?,?,?,?)""", (ident,uid,request_id,receipt_id,encrypted,account[-4:],now,now))
            db.execute("""INSERT INTO reward_ledger (id,uid,receipt_id,amount,kind,memo,created_at)
                VALUES (?,?,?,-300,?,?,?)""", ("led_"+secrets.token_urlsafe(12),uid,receipt_id,"payout_hold:"+ident,ident,now))
        except sqlite3.IntegrityError as exc:
            raise ValueError("payout_already_requested") from exc
        row = db.execute("SELECT * FROM payouts WHERE id=?", (ident,)).fetchone()
        db.execute("COMMIT")
        return public(row)


def listing(store, uid=None):
    with store._db() as db:
        rows = db.execute("SELECT * FROM payouts" + (" WHERE uid=?" if uid else "") + " ORDER BY created_at DESC LIMIT 200", (uid,) if uid else ()).fetchall()
    return [public(row) for row in rows]


def audit(db, actor, action, ident):
    db.execute("INSERT INTO admin_audit (id,admin_id,action,target_id,detail,created_at) VALUES (?,?,?,?,?,?)", (
        "aud_"+secrets.token_urlsafe(12), actor, action, ident, "{}", rewards._iso(),
    ))


def recipient(store, ident, actor):
    with rewards._LOCK, store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM payouts WHERE id=? AND status='processing'", (ident,)).fetchone()
        if not row:
            raise ValueError("claim_payout_first")
        try:
            data = json.loads(cipher().decrypt(row["recipient_encrypted"].encode()))
        except (InvalidToken, ValueError, TypeError) as exc:
            raise ValueError("payout_encryption_key_unavailable") from exc
        audit(db, actor, "payout_recipient_view", ident)
        db.execute("COMMIT")
        return data


def decide(store, ident, action, reference, reason, no_transfer, actor):
    with rewards._LOCK, store._db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM payouts WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("payout_not_found")
        if row["status"] in {"paid", "rejected"}:
            if action == row["status"]:
                return public(row)
            raise ValueError("payout_already_final")
        if action == "processing":
            if row["status"] != "pending":
                raise ValueError("payout_already_processing")
            db.execute("UPDATE payouts SET status='processing',updated_at=? WHERE id=?", (rewards._iso(),ident))
        elif action == "paid":
            if row["status"] != "processing" or not reference.strip():
                raise ValueError("transfer_reference_required")
            try:
                db.execute("UPDATE payouts SET status='paid',reference=?,recipient_encrypted='',updated_at=? WHERE id=?", (reference.strip(),rewards._iso(),ident))
            except sqlite3.IntegrityError as exc:
                raise ValueError("transfer_reference_already_used") from exc
        elif action == "rejected":
            if not no_transfer or not reason.strip():
                raise ValueError("confirm_no_transfer_and_reason")
            db.execute("UPDATE payouts SET status='rejected',reason=?,recipient_encrypted='',updated_at=? WHERE id=?", (reason,rewards._iso(),ident))
            db.execute("""INSERT INTO reward_ledger (id,uid,receipt_id,amount,kind,memo,created_at)
                VALUES (?,?,?,300,?,?,?)""", ("led_"+secrets.token_urlsafe(12),row["uid"],row["receipt_id"],"payout_release:"+ident,ident,rewards._iso()))
        else:
            raise ValueError("invalid_payout_action")
        audit(db, actor, "payout_"+action, ident)
        result = public(db.execute("SELECT * FROM payouts WHERE id=?", (ident,)).fetchone())
        db.execute("COMMIT")
        return result
