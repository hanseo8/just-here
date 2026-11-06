"""Server-verified PortOne phone identity. No raw DI/name/phone is retained."""
import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import quote
import httpx
from . import rewards

TTL = 600

def required():
    return os.getenv('REWARD_IDENTITY_REQUIRED', 'on').lower() != 'off'

def configured():
    return (os.getenv('REWARD_IDENTITY_ENABLED', '').lower() == 'on'
            and all(os.getenv(k, '').strip() for k in ('PORTONE_STORE_ID', 'PORTONE_CHANNEL_KEY', 'PORTONE_API_SECRET'))
            and len(os.getenv('REWARD_IDENTITY_HMAC_KEY', '')) >= 32)

def initialize(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS reward_identities (
      di_hash TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
      verified_at TEXT NOT NULL, verification_id TEXT NOT NULL UNIQUE);
    CREATE TABLE IF NOT EXISTS reward_identity_attempts (
      id TEXT PRIMARY KEY, uid TEXT NOT NULL, created_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL, target_uid TEXT);
    CREATE INDEX IF NOT EXISTS reward_identity_attempt_uid ON reward_identity_attempts(uid,created_at);
    """)

def verified_db(db, uid):
    return bool(db.execute('SELECT 1 FROM reward_identities WHERE uid=?', (uid,)).fetchone())

def require_db(db, uid, *, legacy_link=False):
    if required():
        if not verified_db(db, uid):
            raise ValueError('phone_identity_required')
    elif legacy_link and not uid.startswith('kakao_'):
        raise ValueError('linked_account_required')

def status(store, uid):
    with store._db() as db:
        row = db.execute('SELECT verified_at FROM reward_identities WHERE uid=?', (uid,)).fetchone()
    return {'required': required(), 'configured': configured(), 'verified': bool(row),
            'verified_at': row['verified_at'] if row else None, 'provider': 'portone_v2'}

def start(store, uid):
    if not configured():
        raise ValueError('phone_identity_not_configured')
    now = int(time.time())
    ident = 'jh-identity-' + secrets.token_urlsafe(24)
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM reward_identity_attempts WHERE uid=? AND created_at>?', (uid,now-3600)).fetchone()[0] >= 3:
            raise ValueError('phone_identity_rate_limited')
        # Old attempts cannot be completed after a new request from this account.
        db.execute('DELETE FROM reward_identity_attempts WHERE created_at<?', (now-86400,))
        db.execute('UPDATE reward_identity_attempts SET expires_at=? WHERE uid=? AND target_uid IS NULL', (now-1,uid))
        db.execute('INSERT INTO reward_identity_attempts VALUES(?,?,?,?,NULL)', (ident,uid,now,now+TTL))
        db.execute('COMMIT')
    return {'identityVerificationId': ident, 'storeId': os.environ['PORTONE_STORE_ID'],
            'channelKey': os.environ['PORTONE_CHANNEL_KEY'], 'expires_at': now+TTL}

def fetch_verified(ident):
    try:
        response = httpx.get('https://api.portone.io/identity-verifications/'+quote(ident,safe=''),
            params={'storeId':os.environ['PORTONE_STORE_ID']},
            headers={'Authorization':'PortOne '+os.environ['PORTONE_API_SECRET']}, timeout=12, follow_redirects=False)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError):
        raise ValueError('phone_identity_provider_unavailable') from None

def complete(store, uid, ident):
    if not configured():
        raise ValueError('phone_identity_not_configured')
    now = int(time.time())
    with store._db() as db:
        attempt = db.execute('SELECT * FROM reward_identity_attempts WHERE id=? AND uid=?', (ident,uid)).fetchone()
    if not attempt or attempt['expires_at'] < now:
        raise ValueError('phone_identity_expired')
    if attempt['target_uid']:
        return attempt['target_uid']
    result = fetch_verified(ident)
    channel = result.get('channel') or {}
    if (result.get('id') != ident or result.get('status') != 'VERIFIED'
        or channel.get('type') != 'LIVE' or channel.get('key') != os.environ['PORTONE_CHANNEL_KEY']):
        raise ValueError('phone_identity_not_verified')
    di = (result.get('verifiedCustomer') or {}).get('di')
    if not isinstance(di,str) or not 8 <= len(di) <= 512:
        raise ValueError('phone_identity_di_unavailable')
    digest = hmac.new(os.environ['REWARD_IDENTITY_HMAC_KEY'].encode(), ('portone-di:'+di).encode(), hashlib.sha256).hexdigest()
    with rewards._LOCK, store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        attempt = db.execute('SELECT * FROM reward_identity_attempts WHERE id=? AND uid=?', (ident,uid)).fetchone()
        if not attempt or attempt['expires_at'] < int(time.time()):
            raise ValueError('phone_identity_expired')
        if attempt['target_uid']:
            return attempt['target_uid']
        own = db.execute('SELECT di_hash FROM reward_identities WHERE uid=?', (uid,)).fetchone()
        if own and own['di_hash'] != digest:
            raise ValueError('phone_identity_account_conflict')
        owner = db.execute('SELECT uid FROM reward_identities WHERE di_hash=?', (digest,)).fetchone()
        target = owner['uid'] if owner else uid
        if not owner:
            db.execute('INSERT INTO reward_identities VALUES(?,?,?,?)', (digest,uid,rewards._iso(),ident))
        db.execute('UPDATE reward_identity_attempts SET target_uid=? WHERE id=?', (target,ident))
        db.execute('COMMIT')
    return target
