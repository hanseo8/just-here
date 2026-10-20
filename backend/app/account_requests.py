"""Authenticated deletion intake; requesting never silently deletes financial records."""
import secrets
from datetime import datetime, timezone


def initialize(store):
    with store._db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS account_deletion_requests (
          id TEXT PRIMARY KEY, uid TEXT NOT NULL UNIQUE,
          status TEXT NOT NULL DEFAULT 'requested', created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
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
            'payouts': scalar('SELECT COUNT(*) FROM payouts WHERE uid=?'),
            'pending_payouts': scalar("SELECT COUNT(*) FROM payouts WHERE uid=? AND status IN ('pending','processing')"),
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
    return {'counts': counts, 'blockers':blockers, 'can_execute':False,
            'reason':'deletion_executor_and_retention_policy_not_ready'}
