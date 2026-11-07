"""Authenticated deletion intake; requesting never silently deletes financial records."""
import secrets
import hashlib
import hmac
import time
from datetime import datetime, timezone


def initialize(store):
    with store._db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS account_deletion_requests (
          id TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'requested', created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS account_deletion_receipts (
          request_id TEXT PRIMARY KEY, secret_hash TEXT NOT NULL, expires_at INTEGER NOT NULL
        );
        ''')


def get(store, uid):
    initialize(store)
    with store._db() as db:
        row = db.execute('SELECT id,status,created_at,updated_at FROM account_deletion_requests WHERE uid=?', (uid,)).fetchone()
        return dict(row) if row else None


def submit(store, uid):
    initialize(store)
    stamp = datetime.now(timezone.utc).isoformat()
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO account_deletion_requests (id,uid,created_at,updated_at) VALUES (?,?,?,?)',
                   ('del_'+secrets.token_urlsafe(18),uid,stamp,stamp))
        db.execute("UPDATE account_deletion_requests SET status='requested',updated_at=? WHERE uid=? AND status='withdrawn'", (stamp,uid))
        result = dict(db.execute('SELECT id,status,created_at,updated_at FROM account_deletion_requests WHERE uid=?', (uid,)).fetchone())
        db.execute('COMMIT')
        return result


def queue(store):
    initialize(store)
    with store._db() as db:
        return [dict(row) for row in db.execute('SELECT * FROM account_deletion_requests ORDER BY created_at LIMIT 100')]


def reviewing(store, ident):
    initialize(store)
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM account_deletion_requests WHERE id=?',(ident,)).fetchone()
        if not row:
            raise ValueError('deletion_request_not_found')
        if row['status'] == 'withdrawn':
            raise ValueError('deletion_request_withdrawn')
        if row['status'] not in ('requested','reviewing'):
            raise ValueError('deletion_already_processing')
        # There is deliberately no fake "completed" transition without actual data deletion.
        db.execute("UPDATE account_deletion_requests SET status='reviewing',updated_at=? WHERE id=?",
                   (datetime.now(timezone.utc).isoformat(),ident))
        db.execute('COMMIT')
        return True


def withdraw(store, uid):
    initialize(store)
    with store._db() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM account_deletion_requests WHERE uid=?', (uid,)).fetchone()
        if not row:
            raise ValueError('deletion_request_not_found')
        if row['status'] not in ('requested','reviewing','withdrawn'):
            raise ValueError('deletion_already_processing')
        db.execute("UPDATE account_deletion_requests SET status='withdrawn',updated_at=? WHERE uid=?",
                   (datetime.now(timezone.utc).isoformat(),uid))
        db.execute('COMMIT')
    return get(store, uid)


def preflight(store, ident):
    """A read-only snapshot is not permission to delete or a retained-data policy."""
    initialize(store)
    with store._db() as db:
        db.execute('BEGIN')
        row = db.execute('SELECT uid,status FROM account_deletion_requests WHERE id=?', (ident,)).fetchone()
        if not row:
            raise ValueError('deletion_request_not_found')
        uid = row['uid']
        scalar = lambda query: db.execute(query,(uid,)).fetchone()[0]
        counts = {
            'receipts': scalar('SELECT COUNT(*) FROM receipts WHERE uid=?'),
            'pending_receipts': scalar("SELECT COUNT(*) FROM receipts WHERE uid=? AND status='pending'"),
            'payouts': scalar('SELECT COUNT(*) FROM payouts WHERE uid=?') + scalar('SELECT COUNT(*) FROM beta_payouts WHERE uid=?'),
            'ledger_entries': scalar('SELECT COUNT(*) FROM reward_ledger WHERE uid=?'),
            'pending_payouts': scalar("SELECT COUNT(*) FROM payouts WHERE uid=? AND status IN ('pending','processing')") + scalar("SELECT COUNT(*) FROM beta_payouts WHERE uid=? AND status IN ('pending','processing')"),
            'phone_identity_records': scalar('SELECT COUNT(*) FROM reward_identities WHERE uid=?'),
            'phone_identity_attempts': scalar('SELECT COUNT(*) FROM reward_identity_attempts WHERE uid=?'),
            'beta_memberships': scalar('SELECT COUNT(*) FROM beta_members WHERE uid=?'),
            'beta_surveys': scalar('SELECT COUNT(*) FROM beta_members WHERE uid=? AND survey_at IS NOT NULL'),
            'balance_points': scalar('SELECT COALESCE(SUM(amount),0) FROM reward_ledger WHERE uid=?'),
            'attributions': scalar('SELECT COUNT(*) FROM attributions WHERE uid=?'),
        }
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='partner_coupons' AND type='table'").fetchone()
        counts['active_coupons'] = scalar("SELECT COUNT(*) FROM partner_coupons WHERE uid=? AND status='issued' AND expires_at>strftime('%Y-%m-%dT%H:%M:%f+00:00','now')") if exists else 0
        blockers=[]
        if row['status']=='withdrawn': blockers.append('request_withdrawn')
        if counts['pending_receipts']: blockers.append('receipt_review_pending')
        if counts['pending_payouts']: blockers.append('payout_pending')
        if counts['balance_points'] != 0: blockers.append('balance_requires_resolution')
        if counts['active_coupons']: blockers.append('active_coupons_require_resolution')
        db.execute('COMMIT')
    retention_review=[]
    if counts['receipts'] or counts['payouts'] or counts['ledger_entries']:
        retention_review.append('financial_records_retention_review')
    if counts['phone_identity_records'] or counts['phone_identity_attempts']:
        retention_review.append('identity_records_retention_review')
    if counts['beta_memberships']:
        retention_review.append('beta_participation_review')
    return {'counts': counts, 'blockers':blockers, 'retention_review':retention_review, 'can_execute':False,
            'reason':'deletion_executor_and_retention_policy_not_ready'}


def user_status(store, uid):
    """Owner-facing status only; no other account, raw identity or bank data."""
    row=get(store,uid)
    if not row:
        return None
    report=preflight(store,row['id'])
    labels={
        'receipt_review_pending':'아직 검토 중인 영수증이 있어요.',
        'payout_pending':'지급 대기 또는 송금 확인 중인 신청이 있어요.',
        'balance_requires_resolution':'남아 있는 포인트 처리 방법을 확인해야 해요.',
        'active_coupons_require_resolution':'사용 가능한 쿠폰 처리 방법을 확인해야 해요.',
        'financial_records_retention_review':'영수증·지급 기록의 보존 범위를 확인하고 있어요.',
        'identity_records_retention_review':'본인인증·중복 참여 확인 기록의 처리 범위를 확인하고 있어요.',
        'beta_participation_review':'테스트 참여와 참여비 지급 상태를 확인해야 해요.',
    }
    reasons=[labels[v] for v in report['blockers']+report['retention_review'] if v in labels]
    return {**row,'execution_ready':False,'reasons':reasons,
            'next_action':'고객센터에서 삭제 범위와 처리 결과를 안내합니다. 지금은 삭제 완료 상태가 아니에요.'}


def issue_receipt(store, uid):
    """A scoped, read-only receipt continues to work after the login token is revoked."""
    row=get(store,uid)
    if not row:
        raise ValueError('deletion_request_not_found')
    secret=secrets.token_urlsafe(32)
    expires=int(time.time())+90*86400
    with store._db() as db:
        db.execute('INSERT OR REPLACE INTO account_deletion_receipts VALUES(?,?,?)',
                   (row['id'],hashlib.sha256(secret.encode()).hexdigest(),expires))
    return {'request_id':row['id'],'receipt':secret,'expires_at':expires}


def receipt_status(store, ident, secret):
    with store._db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='account_deletion_receipts'").fetchone():
            raise ValueError('deletion_receipt_invalid')
        row=db.execute('''SELECT r.id,r.status,r.updated_at,t.secret_hash,t.expires_at
          FROM account_deletion_requests r JOIN account_deletion_receipts t ON t.request_id=r.id
          WHERE r.id=?''',(ident,)).fetchone()
    if not row or row['expires_at']<=time.time() or not hmac.compare_digest(row['secret_hash'],hashlib.sha256(secret.encode()).hexdigest()):
        raise ValueError('deletion_receipt_invalid')
    return {k:row[k] for k in ('id','status','updated_at')} | {
        'backup_status':'pending' if row['status']=='active_data_deleted' else 'not_started',
        'full_deletion_complete':False}
