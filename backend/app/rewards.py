"""추천 경유 영수증과 300P 원장.

포인트는 금전성 부채이므로 휘발 저장소에서는 기능을 열지 않는다. 로컬 검증은
RECEIPT_REWARDS_ALLOW_VOLATILE=on으로만 허용한다.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import secrets
import sqlite3
import threading
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from PIL import Image, UnidentifiedImageError

from .config import data_dir
from .storage import is_persistent_dir

_LOCK = threading.RLock()
_STORE: "RewardStore | None" = None
_STORE_PATH: Path | None = None
REWARD_POINTS = 300
KST = ZoneInfo("Asia/Seoul")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000  # common 4032x3024 phone images fit
ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(raw: str) -> datetime:
    text = str(raw or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _on(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "on", "true", "yes"}


def status() -> dict[str, Any]:
    configured = _on("RECEIPT_REWARDS")
    persistent = is_persistent_dir(data_dir())
    volatile_allowed = _on("RECEIPT_REWARDS_ALLOW_VOLATILE")
    enabled = configured and (persistent or volatile_allowed)
    if not configured:
        reason = "disabled"
    elif persistent:
        reason = "persistent_storage"
    elif volatile_allowed:
        reason = "volatile_test_only"
    else:
        reason = "persistent_storage_required"
    return {
        "enabled": enabled,
        "configured": configured,
        "persistent": persistent,
        "reason": reason,
        "reward_points": REWARD_POINTS,
    }


def enabled() -> bool:
    return bool(status()["enabled"])


def claim_limit() -> int:
    return _limit("RECEIPT_REWARDS_MAX_CLAIMS", 100)


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        raise ValueError("invalid_pilot_configuration") from None


def pilot_end():
    raw = os.getenv("RECEIPT_REWARDS_END_AT", "").strip()
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if value.tzinfo is None:
            raise ValueError()
        return value.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("invalid_pilot_configuration") from None


def pilot_terms() -> dict[str, Any]:
    end = pilot_end()
    return {
        "claim_limit": claim_limit(),
        "max_claims_per_user": _limit("RECEIPT_REWARDS_MAX_CLAIMS_PER_USER", 0),
        "ends_at": _iso(end) if end else None,
    }


def _hash(value: str) -> str:
    secret = (os.getenv("GUEST_SIGNING_SECRET") or "just-here-rewards").encode()
    return hashlib.sha256(secret + str(value or "").strip().encode()).hexdigest()


def _valid_image_signature(content_type: str, image: bytes) -> bool:
    expected = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(content_type)
    if not expected:
        return False
    try:
        with Image.open(io.BytesIO(image), formats=[expected]) as decoded:
            if decoded.format != expected or decoded.width * decoded.height > MAX_IMAGE_PIXELS:
                return False
            if getattr(decoded, "n_frames", 1) != 1:
                return False
            decoded.verify()
        # verify() alone does not decode every format's pixel data.
        with Image.open(io.BytesIO(image), formats=[expected]) as decoded:
            decoded.load()
        return True
    except (OSError, ValueError, SyntaxError, UnidentifiedImageError, Image.DecompressionBombError):
        return False


class RewardStore:
    def __init__(self, path: Path, uploads_dir: Path | None = None) -> None:
        self.path = path
        self.uploads_dir = uploads_dir or path.parent / "receipt_uploads"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def _db(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with _LOCK, self._db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS attributions (
                  id TEXT PRIMARY KEY,
                  uid TEXT NOT NULL,
                  session_id TEXT NOT NULL,
                  place_id TEXT NOT NULL DEFAULT '',
                  place_name TEXT NOT NULL,
                  menu_id TEXT NOT NULL DEFAULT '',
                  menu_name TEXT NOT NULL DEFAULT '',
                  intent TEXT NOT NULL,
                  selected_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL,
                  handoff_opened_at TEXT,
                  UNIQUE(uid, session_id)
                );
                CREATE TABLE IF NOT EXISTS receipts (
                  id TEXT PRIMARY KEY,
                  uid TEXT NOT NULL,
                  attribution_id TEXT NOT NULL,
                  reward_day TEXT NOT NULL,
                  purchased_at TEXT NOT NULL,
                  amount_krw INTEGER NOT NULL,
                  approval_hash TEXT NOT NULL,
                  image_path TEXT NOT NULL,
                  image_sha256 TEXT NOT NULL,
                  content_type TEXT NOT NULL,
                  review_return TEXT NOT NULL,
                  review_tags TEXT NOT NULL DEFAULT '[]',
                  review_note TEXT NOT NULL DEFAULT '',
                  photo_reuse_consent INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'pending',
                  reward_points INTEGER NOT NULL DEFAULT 300,
                  admin_reason TEXT NOT NULL DEFAULT '',
                  risk_flags TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL,
                  decided_at TEXT,
                  decided_by TEXT,
                  FOREIGN KEY(attribution_id) REFERENCES attributions(id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS receipt_image_unique
                  ON receipts(image_sha256);
                CREATE UNIQUE INDEX IF NOT EXISTS receipt_approval_unique
                  ON receipts(approval_hash);
                CREATE UNIQUE INDEX IF NOT EXISTS receipt_attribution_active
                  ON receipts(attribution_id) WHERE status IN ('pending','approved');
                CREATE UNIQUE INDEX IF NOT EXISTS receipt_user_day_active
                  ON receipts(uid, reward_day) WHERE status IN ('pending','approved');
                CREATE TABLE IF NOT EXISTS reward_ledger (
                  id TEXT PRIMARY KEY,
                  uid TEXT NOT NULL,
                  receipt_id TEXT,
                  amount INTEGER NOT NULL,
                  kind TEXT NOT NULL,
                  memo TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  UNIQUE(receipt_id, kind)
                );
                CREATE TABLE IF NOT EXISTS admin_audit (
                  id TEXT PRIMARY KEY,
                  admin_id TEXT NOT NULL,
                  action TEXT NOT NULL,
                  target_id TEXT NOT NULL,
                  detail TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS payouts (
                  id TEXT PRIMARY KEY,
                  uid TEXT NOT NULL,
                  request_id TEXT NOT NULL,
                  receipt_id TEXT NOT NULL REFERENCES receipts(id),
                  amount_krw INTEGER NOT NULL CHECK(amount_krw=300),
                  recipient_encrypted TEXT NOT NULL,
                  account_tail TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  reference TEXT UNIQUE,
                  reason TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(uid,request_id)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS payout_receipt_active
                  ON payouts(receipt_id) WHERE status IN ('pending','processing','paid');
                """
            )
        self._purge_expired_images()

    def _purge_expired_images(self) -> None:
        """검토 완료 또는 장기 미처리 원본을 30일 뒤 제거한다."""
        cutoff = _iso(_now() - timedelta(days=30))
        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE receipts SET status='rejected',admin_reason='검토 기한 만료',
                   decided_at=?,decided_by='system'
                   WHERE status='pending' AND created_at<?""",
                (cutoff, cutoff),
            )
            rows = db.execute(
                """SELECT id,image_path FROM receipts
                   WHERE decided_at IS NOT NULL AND decided_at<=?
                     AND image_path!='receipt_uploads/deleted'""",
                (cutoff,),
            ).fetchall()
            for row in rows:
                path = (self.path.parent / row["image_path"]).resolve()
                if self.uploads_dir.resolve() in path.parents:
                    path.unlink(missing_ok=True)
                db.execute(
                    "UPDATE receipts SET image_path='receipt_uploads/deleted' WHERE id=?",
                    (row["id"],),
                )
            db.execute("COMMIT")

    def create_attribution(
        self,
        *,
        uid: str,
        session_id: str,
        place_id: str,
        place_name: str,
        menu_id: str,
        menu_name: str,
        intent: str,
    ) -> dict[str, Any]:
        if not uid or not session_id or not place_name:
            raise ValueError("attribution fields required")
        created = _now()
        attribution_id = f"att_{secrets.token_urlsafe(12)}"
        expires = created + timedelta(days=3)
        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM attributions WHERE uid=? AND session_id=?",
                (uid, session_id),
            ).fetchone()
            if existing:
                db.execute("COMMIT")
                return dict(existing)
            db.execute(
                """INSERT INTO attributions
                (id,uid,session_id,place_id,place_name,menu_id,menu_name,intent,selected_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    attribution_id,
                    uid,
                    session_id,
                    place_id or "",
                    place_name,
                    menu_id or "",
                    menu_name or "",
                    intent,
                    _iso(created),
                    _iso(expires),
                ),
            )
            row = db.execute("SELECT * FROM attributions WHERE id=?", (attribution_id,)).fetchone()
            db.execute("COMMIT")
            return dict(row)

    def mark_handoff(self, attribution_id: str, uid: str) -> dict[str, Any]:
        with _LOCK, self._db() as db:
            cur = db.execute(
                "UPDATE attributions SET handoff_opened_at=COALESCE(handoff_opened_at,?) WHERE id=? AND uid=?",
                (_iso(), attribution_id, uid),
            )
            if not cur.rowcount:
                raise KeyError("attribution_not_found")
            row = db.execute("SELECT * FROM attributions WHERE id=?", (attribution_id,)).fetchone()
            return dict(row)

    def submit_receipt(
        self,
        *,
        uid: str,
        attribution_id: str,
        purchased_at: str,
        amount_krw: int,
        approval_number: str,
        content_type: str,
        image: bytes,
        review_return: str,
        review_tags: list[str],
        review_note: str,
        photo_reuse_consent: bool,
    ) -> dict[str, Any]:
        if content_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("unsupported_image_type")
        if not image or len(image) > MAX_IMAGE_BYTES:
            raise ValueError("invalid_image_size")
        if not _valid_image_signature(content_type, image):
            raise ValueError("invalid_image_content")
        if review_return not in {"yes", "maybe", "no"}:
            raise ValueError("invalid_review_return")
        purchase = _parse_iso(purchased_at)
        if purchase > _now() + timedelta(minutes=10) or purchase < _now() - timedelta(days=3):
            raise ValueError("purchase_time_out_of_range")
        if amount_krw < 1000 or amount_krw > 10_000_000:
            raise ValueError("invalid_amount")
        approval = str(approval_number or "").strip()
        if len(approval) < 6:
            raise ValueError("approval_number_required")

        image_sha = hashlib.sha256(image).hexdigest()
        approval_hash = _hash(approval)
        receipt_id = f"rcp_{secrets.token_urlsafe(12)}"
        reward_day = purchase.astimezone(KST).strftime("%Y-%m-%d")
        suffix = ALLOWED_IMAGE_TYPES[content_type]
        relative_path = f"receipt_uploads/{receipt_id}{suffix}"
        target = self.path.parent / relative_path
        flags: list[str] = []

        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attribution = db.execute(
                "SELECT * FROM attributions WHERE id=? AND uid=?",
                (attribution_id, uid),
            ).fetchone()
            if not attribution:
                db.execute("ROLLBACK")
                raise KeyError("attribution_not_found")
            if attribution["intent"] != "visit" or str(attribution["session_id"]).startswith("design"):
                raise ValueError("ineligible_attribution")
            if _now() > _parse_iso(attribution["expires_at"]):
                raise ValueError("attribution_expired")
            limit = claim_limit()
            reserved = db.execute(
                "SELECT COUNT(*) FROM receipts WHERE status IN ('pending','approved')"
            ).fetchone()[0]
            if reserved >= limit:
                raise ValueError("pilot_capacity_reached")
            ends_at = pilot_end()
            if ends_at is not None and _now() >= ends_at:
                raise ValueError("pilot_ended")
            per_user = _limit("RECEIPT_REWARDS_MAX_CLAIMS_PER_USER", 0)
            if per_user:
                user_reserved = db.execute(
                    "SELECT COUNT(*) FROM receipts WHERE uid=? AND status IN ('pending','approved')", (uid,)
                ).fetchone()[0]
                if user_reserved >= per_user:
                    raise ValueError("pilot_user_limit_reached")
            selected = _parse_iso(attribution["selected_at"])
            expires = _parse_iso(attribution["expires_at"])
            if purchase < selected - timedelta(hours=1) or purchase > expires:
                flags.append("purchase_outside_attribution_window")
            try:
                target.write_bytes(image)
                db.execute(
                    """INSERT INTO receipts
                    (id,uid,attribution_id,reward_day,purchased_at,amount_krw,approval_hash,
                     image_path,image_sha256,content_type,review_return,review_tags,review_note,
                     photo_reuse_consent,status,reward_points,risk_flags,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        receipt_id,
                        uid,
                        attribution_id,
                        reward_day,
                        _iso(purchase),
                        int(amount_krw),
                        approval_hash,
                        relative_path,
                        image_sha,
                        content_type,
                        review_return,
                        json.dumps(list(dict.fromkeys(review_tags))[:8], ensure_ascii=False),
                        str(review_note or "").strip()[:300],
                        1 if photo_reuse_consent else 0,
                        "pending",
                        REWARD_POINTS,
                        json.dumps(flags, ensure_ascii=False),
                        _iso(),
                    ),
                )
                db.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                db.execute("ROLLBACK")
                target.unlink(missing_ok=True)
                raise ValueError("duplicate_or_daily_limit") from exc
            except Exception:
                db.execute("ROLLBACK")
                target.unlink(missing_ok=True)
                raise
        return self.get_receipt(receipt_id, uid=uid)

    def get_receipt(self, receipt_id: str, *, uid: str | None = None) -> dict[str, Any]:
        query = """SELECT r.*, a.place_id, a.place_name, a.menu_id, a.menu_name,
                   a.intent, a.selected_at, a.handoff_opened_at
                   FROM receipts r JOIN attributions a ON a.id=r.attribution_id
                   WHERE r.id=?"""
        params: list[Any] = [receipt_id]
        if uid is not None:
            query += " AND r.uid=?"
            params.append(uid)
        with self._db() as db:
            row = db.execute(query, params).fetchone()
        if not row:
            raise KeyError("receipt_not_found")
        return self._public_receipt(dict(row))

    def _public_receipt(self, row: dict[str, Any]) -> dict[str, Any]:
        row = dict(row)
        row.pop("approval_hash", None)
        row.pop("image_path", None)
        row.pop("image_sha256", None)
        row["review_tags"] = json.loads(row.get("review_tags") or "[]")
        row["risk_flags"] = json.loads(row.get("risk_flags") or "[]")
        row["photo_reuse_consent"] = bool(row.get("photo_reuse_consent"))
        return row

    def list_for_user(self, uid: str, limit: int = 30) -> dict[str, Any]:
        with self._db() as db:
            rows = db.execute(
                """SELECT r.*, a.place_id, a.place_name, a.menu_id, a.menu_name,
                   a.intent, a.selected_at, a.handoff_opened_at
                   FROM receipts r JOIN attributions a ON a.id=r.attribution_id
                   WHERE r.uid=? ORDER BY r.created_at DESC LIMIT ?""",
                (uid, max(1, min(limit, 100))),
            ).fetchall()
            balance = db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM reward_ledger WHERE uid=?", (uid,)
            ).fetchone()[0]
            pending = db.execute(
                "SELECT COALESCE(SUM(reward_points),0) FROM receipts WHERE uid=? AND status='pending'",
                (uid,),
            ).fetchone()[0]
            eligible = db.execute(
                """SELECT a.* FROM attributions a
                   WHERE a.uid=? AND a.expires_at>=?
                     AND NOT EXISTS (
                       SELECT 1 FROM receipts r
                       WHERE r.attribution_id=a.id AND r.status IN ('pending','approved')
                     )
                   ORDER BY a.selected_at DESC LIMIT 10""",
                (uid, _iso()),
            ).fetchall()
        return {
            "balance": int(balance or 0),
            "pending_points": int(pending or 0),
            "receipts": [self._public_receipt(dict(row)) for row in rows],
            "eligible_attributions": [dict(row) for row in eligible],
        }

    def admin_receipts(self, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
        query = """SELECT r.*, a.place_id, a.place_name, a.menu_id, a.menu_name,
                   a.intent, a.selected_at, a.handoff_opened_at
                   FROM receipts r JOIN attributions a ON a.id=r.attribution_id"""
        params: list[Any] = []
        if status in {"pending", "approved", "rejected"}:
            query += " WHERE r.status=?"
            params.append(status)
        query += " ORDER BY r.created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 200)))
        with self._db() as db:
            rows = db.execute(query, params).fetchall()
        return [self._public_receipt(dict(row)) for row in rows]

    def decide(
        self, receipt_id: str, *, approve: bool, reason: str, admin_id: str
    ) -> dict[str, Any]:
        if not approve and not str(reason or "").strip():
            raise ValueError("rejection_reason_required")
        new_status = "approved" if approve else "rejected"
        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)).fetchone()
            if not row:
                db.execute("ROLLBACK")
                raise KeyError("receipt_not_found")
            if row["status"] != "pending":
                db.execute("COMMIT")
                return self.get_receipt(receipt_id)
            db.execute(
                "UPDATE receipts SET status=?,admin_reason=?,decided_at=?,decided_by=? WHERE id=?",
                (new_status, str(reason or "")[:240], _iso(), admin_id[:80], receipt_id),
            )
            if approve:
                db.execute(
                    """INSERT INTO reward_ledger
                    (id,uid,receipt_id,amount,kind,memo,created_at) VALUES (?,?,?,?,?,?,?)""",
                    (
                        f"led_{secrets.token_urlsafe(12)}",
                        row["uid"],
                        receipt_id,
                        int(row["reward_points"]),
                        "receipt_approved",
                        "추천 경유 영수증 승인",
                        _iso(),
                    ),
                )
            db.execute(
                "INSERT INTO admin_audit (id,admin_id,action,target_id,detail,created_at) VALUES (?,?,?,?,?,?)",
                (
                    f"aud_{secrets.token_urlsafe(12)}",
                    admin_id[:80],
                    f"receipt_{new_status}",
                    receipt_id,
                    json.dumps({"reason": str(reason or "")[:240]}, ensure_ascii=False),
                    _iso(),
                ),
            )
            db.execute("COMMIT")
        return self.get_receipt(receipt_id)

    def summary(self) -> dict[str, Any]:
        with self._db() as db:
            counts = {
                row["status"]: row["count"]
                for row in db.execute("SELECT status,COUNT(*) count FROM receipts GROUP BY status")
            }
            points = db.execute("SELECT COALESCE(SUM(amount),0) FROM reward_ledger WHERE kind='receipt_approved'").fetchone()[0]
            users = db.execute("SELECT COUNT(DISTINCT uid) FROM receipts").fetchone()[0]
            pending_points = db.execute(
                "SELECT COALESCE(SUM(reward_points),0) FROM receipts WHERE status='pending'"
            ).fetchone()[0]
        reserved = counts.get("pending", 0) + counts.get("approved", 0)
        return {
            "receipts": counts,
            "points_issued": int(points or 0),
            "submitters": int(users or 0),
            "pending_points": int(pending_points),
            "committed_points": int(points) + int(pending_points),
            "claim_limit": claim_limit(),
            "claims_remaining": max(0, claim_limit() - reserved),
            "max_claims_per_user": _limit("RECEIPT_REWARDS_MAX_CLAIMS_PER_USER", 0),
            "ends_at": _iso(pilot_end()) if pilot_end() else None,
        }

    def backup_archive(self, directory: Path) -> Path:
        """Create a consistent SQLite snapshot and its referenced receipt images.

        The database write lock also coordinates with other application workers.
        The destination must be a private temporary directory, outside DATA_DIR.
        """
        snapshot = directory / "rewards.sqlite3"
        if snapshot.resolve() == self.path.resolve():
            raise ValueError("backup_destination_is_live_database")
        archive = directory / "rewards-backup.zip"
        manifest = {"version": 1, "created_at": _iso(), "files": {}}
        with _LOCK, self._db() as guard:
            guard.execute("BEGIN IMMEDIATE")
            try:
                with self._db() as source:
                    destination = sqlite3.connect(snapshot)
                    try:
                        source.backup(destination)
                    finally:
                        destination.close()
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    paths = [("rewards.sqlite3", snapshot)]
                    for row in guard.execute("SELECT image_path FROM receipts"):
                        name = row["image_path"]
                        if name == "receipt_uploads/deleted":
                            continue
                        path = (self.path.parent / name).resolve()
                        if path.parent != self.uploads_dir.resolve() or not path.is_file():
                            raise ValueError("backup_image_missing_or_invalid")
                        paths.append((name, path))
                    for name, path in paths:
                        digest = hashlib.sha256()
                        with path.open("rb") as file:
                            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                                digest.update(chunk)
                        manifest["files"][name] = digest.hexdigest()
                        bundle.write(path, name)
                    bundle.writestr("manifest.json", json.dumps(manifest))
            finally:
                guard.execute("ROLLBACK")
        return archive

    def image_path(self, receipt_id: str) -> tuple[Path, str]:
        with self._db() as db:
            row = db.execute(
                "SELECT image_path,content_type FROM receipts WHERE id=?", (receipt_id,)
            ).fetchone()
        if not row:
            raise KeyError("receipt_not_found")
        target = (self.path.parent / row["image_path"]).resolve()
        if self.uploads_dir.resolve() not in target.parents:
            raise ValueError("invalid_image_path")
        return target, row["content_type"]

    def merge_uid(self, source_uid: str, target_uid: str) -> None:
        if not source_uid or not target_uid or source_uid == target_uid:
            return
        with _LOCK, self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("UPDATE attributions SET uid=? WHERE uid=?", (target_uid, source_uid))
                db.execute("UPDATE receipts SET uid=? WHERE uid=?", (target_uid, source_uid))
                db.execute("UPDATE reward_ledger SET uid=? WHERE uid=?", (target_uid, source_uid))
                db.execute("UPDATE payouts SET uid=? WHERE uid=?", (target_uid, source_uid))
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise


def get_store() -> RewardStore:
    global _STORE, _STORE_PATH
    path = data_dir() / "rewards.sqlite3"
    if _STORE is None or _STORE_PATH != path:
        _STORE = RewardStore(path)
        _STORE_PATH = path
    else:
        _STORE._purge_expired_images()
    return _STORE
