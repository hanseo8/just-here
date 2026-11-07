"""Resumable active-data removal for unlinked anonymous accounts without obligations.

Full deletion remains pending until backup/retention handling is completed separately.
The HTTP adapter requires explicit confirmation, maintenance and a drained single instance.
"""
import hashlib
import json
import os
import sqlite3
import re
import threading
from contextlib import closing, ExitStack
from datetime import datetime, timezone

from . import account_requests, analytics, engine, rewards, share, duo, users
from . import storage

LOCK = threading.Lock()
REMOVABLE = {'attributions', 'beta_applications'}
KNOWN_UID_TABLES = REMOVABLE | {'receipts', 'reward_ledger', 'payouts', 'beta_members',
    'beta_receipts', 'beta_awards', 'beta_payouts', 'reward_identities',
    'reward_identity_attempts', 'partner_coupons', 'account_deletion_requests'}


def enabled():
    return os.getenv('ACCOUNT_DELETION_EXECUTION', '').lower() == 'on'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def initialize(store):
    account_requests.initialize(store)
    with store._db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS account_deletion_jobs (
          request_id TEXT PRIMARY KEY, payload TEXT NOT NULL, stage TEXT NOT NULL,
          actor TEXT NOT NULL, updated_at TEXT NOT NULL)''')


def _row(store, ident):
    with store._db() as db:
        row=db.execute('SELECT * FROM account_deletion_requests WHERE id=?',(ident,)).fetchone()
    if not row:
        raise ValueError('deletion_request_not_found')
    return dict(row)


def _profile_blockers(uid):
    if not re.fullmatch(r'anon_[0-9a-f]{20}',uid):
        return ['identity_scope_requires_resolution']
    profile=users.STORE.get(uid)
    if not profile:
        return [] if users.STORE.identity_deleted(uid) else ['profile_missing']
    if profile.get('auth_type')!='anonymous':
        return ['external_identity_resolution_required']
    # delete_profile additionally verifies reverse aliases under the users lock.
    if profile.get('linked_to') or profile.get('anonymous_linked_from'):
        return ['linked_identity_resolution_required']
    with users._LOCK:
        if any(p.get('linked_to')==uid or p.get('anonymous_linked_from')==uid for p in users.STORE._users.values()):
            return ['linked_identity_resolution_required']
    return []


def _record_blockers(store, uid):
    with store._db() as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        blockers=[]
        for table in tables:
            if not table.replace('_','').isalnum():
                raise ValueError('unknown_storage_schema')
            columns={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
            if 'uid' not in columns:
                continue
            count=db.execute(f'SELECT COUNT(*) FROM {table} WHERE uid=?',(uid,)).fetchone()[0]
            if count and table not in KNOWN_UID_TABLES:
                blockers.append('unknown_account_records')
            elif count and table not in REMOVABLE | {'account_deletion_requests'}:
                blockers.append('retained_records_require_resolution')
        if db.execute('SELECT 1 FROM reward_identity_attempts WHERE target_uid=? LIMIT 1',(uid,)).fetchone():
            blockers.append('identity_recovery_requires_resolution')
        if db.execute('SELECT 1 FROM admin_audit WHERE target_id=? LIMIT 1',(uid,)).fetchone():
            blockers.append('retained_records_require_resolution')
    return sorted(set(blockers))


def preview(store, ident):
    row=_row(store,ident)
    blockers=[]
    if row['status'] not in ('requested','reviewing','deleting'):
        blockers.append('request_not_executable')
    blockers+=_profile_blockers(row['uid'])+_record_blockers(store,row['uid'])
    return {'enabled':enabled(),'eligible':not blockers,'blockers':sorted(set(blockers)),
            'scope':'active_data_only','backup_status':'pending',
            'requires_maintenance':True,'full_deletion_complete':False}


def _events(path):
    if not path.exists():
        return []
    rows=[]
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.strip():
            rows.append((line,{}));continue
        try:
            row=json.loads(line)
            if not isinstance(row,dict):
                raise ValueError()
            if row.get('props') is not None and not isinstance(row['props'],dict):
                raise ValueError()
        except (ValueError, UnicodeError):
            raise ValueError('events_integrity_review_required') from None
        rows.append((line,row))
    return rows


def _contains(value, identifiers):
    if isinstance(value,str):
        return value in identifiers
    if isinstance(value,dict):
        return any(_contains(v,identifiers) for v in value.values())
    if isinstance(value,list):
        return any(_contains(v,identifiers) for v in value)
    return False


def _targets(uid):
    profile=users.STORE.get(uid) or {}
    with users._LOCK:
        devices=set(profile.get('device_ids') or []) | {k for k,v in users.STORE._device_index.items() if v==uid}
    ids={uid,*devices}
    targets={'uid':uid,'devices':sorted(devices),'sessions':[],'shares':[],'duos':[]}
    fields={'session_id':'sessions','receipt_id':'shares','duo_id':'duos'}
    for _,row in _events(analytics.EVENTS_PATH):
        if _contains(row,ids):
            props=row.get('props') or {}
            for field,bucket in fields.items():
                value=props.get(field)
                if isinstance(value,str) and value:
                    targets[bucket].append(value)
    for bucket in ('sessions','shares','duos'):
        targets[bucket]=sorted(set(targets[bucket]))
    _check_shared(targets)
    return targets


def _check_shared(payload):
    ids={payload['uid'],*payload['devices']}
    with users._LOCK:
        if any(owner!=payload['uid'] for device,owner in users.STORE._device_index.items() if device in payload['devices']):
            raise ValueError('shared_account_records_require_resolution')
    for _,row in _events(analytics.EVENTS_PATH):
        if row.get('uid') and row['uid']!=payload['uid']:
            props=row.get('props') or {}
            if _contains(row,ids) or any(props.get(field) in payload[bucket] for field,bucket in [('session_id','sessions'),('receipt_id','shares'),('duo_id','duos')]):
                raise ValueError('shared_account_records_require_resolution')


def _matches(row, payload):
    ids={payload['uid'],*payload['devices']}
    if _contains(row,ids):
        return True
    # Anonymous events may be associated with a known session. Never remove another UID's row.
    props=row.get('props') or {}
    return not row.get('uid') and not row.get('device_id') and props.get('session_id') in payload['sessions']


def _purge_events(payload):
    path=analytics.EVENTS_PATH
    with analytics._LOCK:
        _check_shared(payload)
        rows=_events(path)
        kept=b''.join(raw for raw,row in rows if not _matches(row,payload))
        if path.exists():
            tmp=path.with_suffix('.deletion-tmp')
            try:
                with tmp.open('wb') as f:
                    os.chmod(tmp,0o600);f.write(kept);f.flush();os.fsync(f.fileno())
                tmp.replace(path)
            finally:
                tmp.unlink(missing_ok=True)


def _stage(store, ident, stage):
    with store._db() as db:
        db.execute('UPDATE account_deletion_jobs SET stage=?,updated_at=? WHERE request_id=?',(stage,stamp(),ident))


def _native_auth(uid, root):
    path=root/'native-auth.sqlite3'
    if path.exists():
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM attempts WHERE uid=?',(uid,))


def _purge_memory(payload):
    # Maintenance has drained requests. Only objects demonstrably associated with this account.
    for sid in payload['sessions']:
        engine.SESSIONS.pop(sid,None)
        with engine._SESS_LOCKS_MU:
            engine._SESS_LOCKS.pop(sid,None)
    for ident in payload['shares']:
        share.RECEIPTS.pop(ident,None)
    for ident in payload['duos']:
        duo.ROOMS.pop(ident,None)


def execute(store, ident, *, actor, confirm_request_id, confirm_permanent, drained):
    if not enabled():
        raise ValueError('deletion_execution_disabled')
    if os.getenv('ACCOUNT_DELETION_SINGLE_INSTANCE','').lower()!='on':
        raise ValueError('single_instance_required')
    if not confirm_permanent or confirm_request_id!=ident:
        raise ValueError('explicit_deletion_confirmation_required')
    root=store.path.parent.resolve()
    if not (root/'.storage-maintenance').is_file() or not drained:
        raise ValueError('maintenance_and_drain_required')
    if users.STORE.path.parent.resolve()!=root or analytics.EVENTS_PATH.parent.resolve()!=root:
        raise ValueError('deletion_storage_mismatch')
    if not LOCK.acquire(blocking=False):
        raise ValueError('deletion_in_progress')
    stack=ExitStack()
    try:
        stack.enter_context(storage.exclusive_operation(root))
        initialize(store)
        row=_row(store,ident)
        if row['status']=='active_data_deleted':
            return {'status':row['status'],'backup_status':'pending','full_deletion_complete':False}
        report=preview(store,ident)
        if not report['eligible']:
            raise ValueError('deletion_requires_resolution')
        uid=row['uid']
        with store._db() as db:
            job=db.execute('SELECT * FROM account_deletion_jobs WHERE request_id=?',(ident,)).fetchone()
        if job:
            payload=json.loads(job['payload'])
            if not isinstance(payload,dict) or payload.get('uid')!=uid or any(
                not isinstance(payload.get(key),list) or len(payload[key])>20000 or
                any(not isinstance(v,str) or not v or len(v)>512 for v in payload[key])
                for key in ('devices','sessions','shares','duos')
            ):
                raise ValueError('deletion_journal_integrity_required')
        else:
            # Validate the event stream before removing any profile. Persist retry identifiers first.
            payload=_targets(uid)
            with rewards._LOCK, store._db() as db:
                db.execute('BEGIN IMMEDIATE')
                current=db.execute('SELECT status FROM account_deletion_requests WHERE id=?',(ident,)).fetchone()
                if current['status'] not in ('requested','reviewing'):
                    raise ValueError('request_not_executable')
                db.execute("UPDATE account_deletion_requests SET status='deleting',updated_at=? WHERE id=?",(stamp(),ident))
                db.execute('INSERT INTO account_deletion_jobs VALUES(?,?,?,?,?)',(ident,json.dumps(payload), 'prepared',actor[:80],stamp()))
                db.execute('COMMIT')
        # Recheck blockers for every retry. A final state is never manufactured after a partial failure.
        if _profile_blockers(uid) or _record_blockers(store,uid):
            raise ValueError('deletion_requires_resolution')
        users.STORE.delete_profile(uid,session_ids=payload['sessions'])
        _stage(store,ident,'profile_deleted')
        _purge_events(payload)
        _stage(store,ident,'events_deleted')
        _native_auth(uid,root)
        with rewards._LOCK, store._db() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            for table in sorted(REMOVABLE):
                db.execute(f'DELETE FROM {table} WHERE uid=?',(uid,))
            db.execute('COMMIT')
        _purge_memory(payload)
        if users.STORE.get(uid) is not None or not users.STORE.identity_deleted(uid):
            raise ValueError('deletion_postcondition_failed')
        with users._LOCK:
            if uid in users.STORE._device_index.values():
                raise ValueError('deletion_postcondition_failed')
        with analytics._LOCK:
            if any(_matches(row,payload) for _,row in _events(analytics.EVENTS_PATH)):
                raise ValueError('deletion_postcondition_failed')
        with store._db() as db:
            if any(db.execute(f'SELECT 1 FROM {table} WHERE uid=? LIMIT 1',(uid,)).fetchone() for table in REMOVABLE):
                raise ValueError('deletion_postcondition_failed')
        native_path=root/'native-auth.sqlite3'
        if native_path.exists():
            with closing(sqlite3.connect(native_path)) as db:
                if db.execute('SELECT 1 FROM attempts WHERE uid=? LIMIT 1',(uid,)).fetchone():
                    raise ValueError('deletion_postcondition_failed')
        if any(s in engine.SESSIONS for s in payload['sessions']) or any(s in share.RECEIPTS for s in payload['shares']) or any(s in duo.ROOMS for s in payload['duos']):
            raise ValueError('deletion_postcondition_failed')
        # Only the live-data phase is complete. Backup restoration must reapply the revocation registry.
        with store._db() as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE account_deletion_requests SET uid=?,status='active_data_deleted',updated_at=? WHERE id=?",('deleted:'+hashlib.sha256(uid.encode()).hexdigest(),stamp(),ident))
            db.execute("UPDATE account_deletion_jobs SET payload='{}',stage='active_data_deleted',updated_at=? WHERE request_id=?",(stamp(),ident))
            db.execute('COMMIT')
        return {'status':'active_data_deleted','backup_status':'pending','full_deletion_complete':False}
    finally:
        try:
            stack.close()
        finally:
            LOCK.release()
