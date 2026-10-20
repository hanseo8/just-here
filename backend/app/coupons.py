"""Contract-backed, zero-point promotional coupons. No payment provider calls."""
import os
import secrets
import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta


def enabled():
    return os.environ.get('PARTNER_COUPONS', '').lower() == 'on'


def initialize(store):
    with store._db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS partner_coupons (
          id TEXT PRIMARY KEY, uid TEXT NOT NULL, merchant_id TEXT NOT NULL,
          merchant_name TEXT NOT NULL, benefit TEXT NOT NULL, terms TEXT NOT NULL,
          contract_reference TEXT NOT NULL, expires_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'issued', created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS coupon_audit (
          id TEXT PRIMARY KEY, coupon_id TEXT NOT NULL, action TEXT NOT NULL,
          actor TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS partner_coupons_uid ON partner_coupons(uid);
        CREATE TABLE IF NOT EXISTS coupon_codes (
          coupon_id TEXT PRIMARY KEY, code_hash TEXT NOT NULL UNIQUE,
          expires_at TEXT NOT NULL
        );
        ''')


def now():
    return datetime.now(timezone.utc).isoformat()


def public(row):
    result = {key: row[key] for key in (
        'id', 'merchant_name', 'benefit', 'terms', 'expires_at', 'status', 'updated_at')}
    if result['status'] == 'issued' and result['expires_at'] <= now():
        result['status'] = 'expired'
    return result


def listing(store, uid):
    initialize(store)
    with store._db() as db:
        return [public(row) for row in db.execute(
            'SELECT * FROM partner_coupons WHERE uid=? ORDER BY created_at DESC LIMIT 100',
            (uid,)).fetchall()]


def issue(store, payload, actor):
    initialize(store)
    end = datetime.fromisoformat(payload['expires_at'])
    if end.tzinfo is None or end <= datetime.now(timezone.utc):
        raise ValueError('invalid_coupon_expiry')
    expiry = end.astimezone(timezone.utc).isoformat()
    fields = ('uid', 'merchant_id', 'merchant_name', 'benefit', 'terms', 'contract_reference')
    values = [payload[key].strip() for key in fields]
    if not all(values):
        raise ValueError('coupon_contract_and_terms_required')
    stamp = now()
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('SELECT * FROM partner_coupons WHERE request_id=?',
                              (payload['request_id'],)).fetchone()
        if existing:
            if [existing[k] for k in fields] != values or existing['expires_at'] != expiry:
                raise ValueError('coupon_request_conflict')
            return public(existing)
        ident = 'cp_' + secrets.token_urlsafe(18)
        db.execute('''INSERT INTO partner_coupons
          (id,uid,merchant_id,merchant_name,benefit,terms,contract_reference,
          expires_at,created_at,updated_at,request_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
          (ident, *values, expiry, stamp, stamp, payload['request_id']))
        db.execute('INSERT INTO coupon_audit VALUES (?,?,?,?,?)',
                   ('ca_'+secrets.token_urlsafe(12), ident, 'issued', actor, stamp))
        result = public(db.execute('SELECT * FROM partner_coupons WHERE id=?', (ident,)).fetchone())
        db.execute('COMMIT')
        return result


def transition(store, ident, merchant_id, action, actor):
    if action not in ('used', 'cancelled'):
        raise ValueError('invalid_coupon_action')
    initialize(store)
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM partner_coupons WHERE id=? AND merchant_id=?',
                         (ident, merchant_id)).fetchone()
        if not row:
            raise ValueError('coupon_not_found')
        if row['status'] != 'issued' or row['expires_at'] <= now():
            raise ValueError('coupon_unavailable')
        stamp = now()
        db.execute('UPDATE partner_coupons SET status=?,updated_at=? WHERE id=?',
                   (action, stamp, ident))
        db.execute('INSERT INTO coupon_audit VALUES (?,?,?,?,?)',
                   ('ca_'+secrets.token_urlsafe(12), ident, action, actor, stamp))
        result = public(db.execute('SELECT * FROM partner_coupons WHERE id=?', (ident,)).fetchone())
        db.execute('COMMIT')
        return result


def merchant_identity(token):
    """Dedicated merchant credentials are configured server-side, never admin tokens."""
    if not token or len(token) < 32 or len(token) > 256:
        return None
    try:
        credentials = json.loads(os.environ.get('PARTNER_MERCHANT_KEYS', '{}'))
        if not isinstance(credentials, dict):
            return None
        for merchant_id, key in credentials.items():
            if isinstance(key, str) and len(key) >= 32 and hmac.compare_digest(token, key):
                return merchant_id
    except (ValueError, TypeError):
        pass
    return None


def create_code(store, uid, ident):
    initialize(store)
    code = secrets.token_hex(8).upper()
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM partner_coupons WHERE id=? AND uid=?', (ident, uid)).fetchone()
        if not row or row['status'] != 'issued' or row['expires_at'] <= now():
            raise ValueError('coupon_unavailable')
        db.execute('INSERT OR REPLACE INTO coupon_codes VALUES (?,?,?)',
                   (ident, hashlib.sha256(code.encode()).hexdigest(), expiry))
        db.execute('COMMIT')
    return {'code': code, 'expires_at': expiry}


def check_code(store, merchant_id, code, consume=False):
    initialize(store)
    digest = hashlib.sha256(code.strip().upper().encode()).hexdigest()
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('''SELECT p.*, c.expires_at AS code_expiry FROM partner_coupons p
          JOIN coupon_codes c ON c.coupon_id=p.id WHERE c.code_hash=? AND p.merchant_id=?''',
          (digest, merchant_id)).fetchone()
        if not row or row['status'] != 'issued' or row['expires_at'] <= now() or row['code_expiry'] <= now():
            raise ValueError('coupon_code_unavailable')
        if consume:
            stamp = now()
            db.execute("UPDATE partner_coupons SET status='used',updated_at=? WHERE id=?", (stamp,row['id']))
            db.execute('DELETE FROM coupon_codes WHERE coupon_id=?', (row['id'],))
            db.execute('INSERT INTO coupon_audit VALUES (?,?,?,?,?)',
                       ('ca_'+secrets.token_urlsafe(12), row['id'], 'used', 'merchant:'+merchant_id, stamp))
        result = public(db.execute('SELECT * FROM partner_coupons WHERE id=?', (row['id'],)).fetchone())
        db.execute('COMMIT')
    return result
