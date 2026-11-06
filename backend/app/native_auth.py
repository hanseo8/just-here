"""Short-lived, device-bound OAuth handoff. Provider tokens never enter app URLs."""
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlencode

from .config import data_dir

REDIRECT_URI = 'https://justthis.co.kr'
TTL = 600
LOCK = threading.RLock()


class OAuthLogFilter(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and ('code=' in args[2] or 'state=native_' in args[2]):
                args[2] = args[2].split('?',1)[0] + '?[oauth-redacted]'
                record.args = tuple(args)
        return True


logging.getLogger('uvicorn.access').addFilter(OAuthLogFilter())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def database():
    path = data_dir() / 'native-auth.sqlite3'
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS attempts (
      id TEXT PRIMARY KEY, uid TEXT NOT NULL, challenge TEXT NOT NULL,
      state_hash TEXT UNIQUE NOT NULL, expires REAL NOT NULL,
      status TEXT NOT NULL, profile TEXT, ticket_hash TEXT)''')
    path.chmod(0o600)
    try:
        with db:
            yield db
    finally:
        db.close()


def start(uid, challenge, rest_key):
    if not rest_key:
        raise ValueError('native_login_not_configured')
    ident, state = secrets.token_urlsafe(24), 'native_' + secrets.token_urlsafe(32)
    with LOCK, database() as db:
        db.execute('DELETE FROM attempts WHERE expires < ?', (time.time(),))
        # One pending login per guest; a new login replaces stale unfinished attempts.
        db.execute('DELETE FROM attempts WHERE uid=?', (uid,))
        if db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] >= 1000:
            raise ValueError('native_login_busy')
        db.execute('INSERT INTO attempts VALUES(?,?,?,?,?,?,NULL,NULL)',
                   (ident,uid,challenge,digest(state),time.time()+TTL,'pending'))
    return {'attempt_id':ident,'expires_in':TTL,'authorize_url':
            'https://kauth.kakao.com/oauth/authorize?' + urlencode({
                'client_id':rest_key,'redirect_uri':REDIRECT_URI,
                'response_type':'code','state':state})}


def callback(state, code, error, exchange):
    """Claim callback once. A finish ticket is delivered ONLY to the returning device.

    Merely possessing the start/state URL cannot retrieve a linked account by polling.
    The completion requires ticket + installation secret + original guest token.
    """
    with LOCK, database() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM attempts WHERE state_hash=?',(digest(state),)).fetchone()
        if not row or row['expires'] <= time.time() or row['status'] != 'pending':
            raise ValueError('native_login_expired_or_used')
        db.execute("UPDATE attempts SET status='processing' WHERE id=?",(row['id'],))
    try:
        if error or not code:
            raise ValueError('native_login_cancelled')
        profile = exchange(code, REDIRECT_URI)
        # Deliberately exclude provider access/refresh tokens and the raw response.
        public = {'kakao_id':profile['kakao_id'],'nickname':profile.get('nickname','')}
        ticket = secrets.token_urlsafe(32)
        with LOCK, database() as db:
            changed = db.execute("UPDATE attempts SET status='ready',profile=?,ticket_hash=? WHERE id=? AND status='processing' AND expires>?",
                                 (json.dumps(public),digest(ticket),row['id'],time.time())).rowcount
            if changed != 1:
                raise ValueError('native_login_expired_or_used')
        return {'attempt_id':row['id'],'ticket':ticket}
    except Exception:
        with LOCK, database() as db:
            db.execute("UPDATE attempts SET status='failed',profile=NULL,ticket_hash=NULL WHERE id=?",(row['id'],))
        raise ValueError('native_login_failed') from None


def complete(uid, ident, verifier, ticket, finish):
    with LOCK, database() as db:
        row = db.execute('SELECT * FROM attempts WHERE id=?',(ident,)).fetchone()
        if (not row or row['uid'] != uid or row['expires'] <= time.time()
            or row['status'] not in ('ready','completed')
            or not hmac.compare_digest(row['challenge'],digest(verifier))
            or not hmac.compare_digest(row['ticket_hash'] or '',digest(ticket))):
            raise ValueError('native_login_proof_invalid')
        result = finish(json.loads(row['profile']))
        db.execute("UPDATE attempts SET status='completed' WHERE id=?",(ident,))
        return result
