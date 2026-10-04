"""Single-admin TOTP sessions and bounded, private security event counters."""
import base64
import hashlib
import hmac
from contextlib import contextmanager
import os
import re
import secrets
import sqlite3
import struct
import threading
import time
import logging
from .config import data_dir

LOCK = threading.RLock()
SESSIONS = {}
TTL = 600
EVENTS = {'admin_denied', 'otp_denied', 'rate_limited', 'upload_denied', 'upload_timeout'}

def required():
    return bool(os.environ.get('ADMIN_TOTP_SECRET', '').strip()) or os.environ.get('ADMIN_REQUIRE_2FA', '').lower() == 'on'

def key():
    raw = os.environ.get('ADMIN_TOTP_SECRET', '').strip().upper()
    if not re.fullmatch(r'[A-Z2-7]{32,128}', raw):
        raise ValueError('admin second factor is not configured')
    return base64.b32decode(raw + '=' * (-len(raw) % 8))

def code(secret, step, digits=6):
    digest = hmac.new(secret, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = struct.unpack('>I', digest[offset:offset+4])[0] & 0x7fffffff
    return str(number % (10**digits)).zfill(digits)

def fingerprint():
    return hashlib.sha256((os.environ.get('ADMIN_TOKEN','') + ':' + os.environ.get('ADMIN_TOTP_SECRET','')).encode()).hexdigest()

@contextmanager
def connect():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'admin-security.sqlite3'
    db = sqlite3.connect(path, timeout=2)
    db.execute('CREATE TABLE IF NOT EXISTS otp_used (fingerprint TEXT PRIMARY KEY, step INTEGER NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS alerts (kind TEXT PRIMARY KEY, count INTEGER NOT NULL, last_seen INTEGER NOT NULL, last_logged INTEGER NOT NULL)')
    if os.name != 'nt': path.chmod(0o600)
    try:
        with db:
            yield db
    finally:
        db.close()

def alert(kind):
    if kind not in EVENTS: return
    # Never record tokens, OTPs, bodies, query strings, IPs or account data.
    try:
        with LOCK, connect() as db:
            now = int(time.time())
            row = db.execute('SELECT count,last_logged FROM alerts WHERE kind=?', (kind,)).fetchone()
            count, last_logged = (row[0]+1, row[1]) if row else (1, 0)
            if now-last_logged >= 60:
                logging.getLogger('justhere.security').warning('security_event kind=%s count=%s', kind, count)
                last_logged = now
            db.execute('INSERT OR REPLACE INTO alerts VALUES (?,?,?,?)', (kind,count,now,last_logged))
    except (OSError, sqlite3.Error):
        logging.getLogger('justhere.security').error('security_event_storage_unavailable')

def login(otp, now=None):
    now = int(time.time() if now is None else now)
    secret = key()
    if not re.fullmatch(r'[0-9]{6}', otp or ''):
        raise ValueError('invalid second factor')
    step = now // 30
    matched = next((s for s in (step-1,step,step+1) if s >= 0 and hmac.compare_digest(code(secret,s),otp)), None)
    if matched is None: raise ValueError('invalid second factor')
    identity = fingerprint()
    with LOCK, connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT step FROM otp_used WHERE fingerprint=?', (identity,)).fetchone()
        if row and matched <= row[0]: raise ValueError('second factor already used')
        db.execute('DELETE FROM otp_used WHERE fingerprint != ?', (identity,))
        db.execute('INSERT OR REPLACE INTO otp_used VALUES (?,?)', (identity,matched))
        for token in list(SESSIONS):
            if SESSIONS[token][0] <= now: del SESSIONS[token]
        if len(SESSIONS) >= 64: raise ValueError('too many admin sessions')
        db.commit()  # Persist replay protection before issuing a session.
        token = secrets.token_urlsafe(32)
        SESSIONS[hashlib.sha256(token.encode()).hexdigest()] = (now+TTL, identity)
        return token

def session_valid(token, now=None):
    if not token or len(token)>128: return False
    now = int(time.time() if now is None else now)
    with LOCK:
        session = SESSIONS.get(hashlib.sha256(token.encode()).hexdigest())
        return bool(session and session[0]>now and session[1]==fingerprint())

def revoke(token):
    with LOCK: SESSIONS.pop(hashlib.sha256((token or '').encode()).hexdigest(),None)

def snapshot():
    with LOCK, connect() as db:
        rows = db.execute('SELECT kind,count,last_seen FROM alerts').fetchall()
    return {'two_factor_required':required(), 'alerts':[{'kind':r[0],'count':r[1],'last_seen':r[2]} for r in rows],
            'external_notifications':False}
