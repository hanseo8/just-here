"""Offline, copy-only backup sanitization using an independently supplied current registry.

Never replaces/deletes a source backup. Financial/identity or ambiguous records fail closed.
"""
import hashlib
import json
import re
import os
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

HASH = re.compile(r'[0-9a-f]{64}')
REMOVABLE = {'attributions','beta_applications'}


def strict_json(value):
    def pairs(items):
        result={}
        for key,v in items:
            if key in result:raise ValueError('duplicate_json_key')
            result[key]=v
        return result
    def constant(_):raise ValueError('non_finite_json')
    return json.loads(value,object_pairs_hook=pairs,parse_constant=constant)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value,str) and value else ''


def load_registry(path):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>16*1024*1024:
        raise ValueError('invalid_deletion_registry')
    data=strict_json(path.read_text(encoding='utf-8'))
    if isinstance(data,dict) and 'deletion_registry' in data:
        if not set(data)<={'ok','deletion_registry'}:
            raise ValueError('independent_current_registry_required')
        data=data['deletion_registry']
    if not isinstance(data,dict) or type(data.get('version')) is not int or data.get('version')!=1 or data.get('scope')!='deletion_restore_guard' or type(data.get('revision')) is not int or data['revision']<0:
        raise ValueError('invalid_deletion_registry')
    for key in ('uid_hashes','device_hashes','session_hashes'):
        values=data.get(key)
        if not isinstance(values,list) or len(values)>100000 or any(not isinstance(v,str) or not HASH.fullmatch(v) for v in values) or len(values)!=len(set(values)):
            raise ValueError('invalid_deletion_registry')
    if set(data)!={'version','scope','revision','uid_hashes','device_hashes','session_hashes'}:
        raise ValueError('invalid_deletion_registry')
    clean={key:sorted(data[key]) for key in ('uid_hashes','device_hashes','session_hashes')}
    return {'version':1,'scope':'deletion_restore_guard','revision':data['revision'],**clean}


def fingerprint(registry):
    return hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def require_current_registry(path, user_store):
    registry=load_registry(path)
    if fingerprint(registry)!=fingerprint(user_store.deletion_registry()):
        raise ValueError('registry_does_not_match_current_live_storage')
    return registry


def _revoked(uid, registry):
    return digest(uid) in registry['uid_hashes']


def sanitize_users(path, registry):
    data=strict_json(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict) or not isinstance(data.get('users'),dict) or not isinstance(data.get('device_index'),dict):
        raise ValueError('invalid_backup_users')
    profiles=data['users'];removed={uid for uid in profiles if _revoked(uid,registry)}
    for uid,profile in profiles.items():
        if not isinstance(profile,dict) or profile.get('uid')!=uid or not isinstance(profile.get('device_ids',[]),list):
            raise ValueError('invalid_backup_users')
        if uid not in removed:
            if any(_revoked(profile.get(key),registry) for key in ('linked_to','anonymous_linked_from')):
                raise ValueError('backup_linked_identity_requires_resolution')
            if any(digest(v) in registry['device_hashes'] for v in profile.get('device_ids',[])):
                raise ValueError('backup_shared_device_requires_resolution')
    for device,uid in data['device_index'].items():
        if digest(device) in registry['device_hashes'] and not _revoked(uid,registry):
            raise ValueError('backup_shared_device_requires_resolution')
    data['users']={uid:p for uid,p in profiles.items() if uid not in removed}
    data['device_index']={d:uid for d,uid in data['device_index'].items() if not _revoked(uid,registry)}
    # Require the independently provided registry to include every tombstone already in this backup.
    for source,target in [('deleted_uid_hashes','uid_hashes'),('deleted_device_hashes','device_hashes'),('deleted_session_hashes','session_hashes')]:
        existing=data.get(source,[])
        if not isinstance(existing,list) or not set(existing)<=set(registry[target]):
            raise ValueError('deletion_registry_older_than_backup')
        data[source]=registry[target]
    old_revision=data.get('deletion_revision',0)
    if type(old_revision) is not int or old_revision<0:raise ValueError('invalid_backup_users')
    if old_revision>registry['revision']:
        raise ValueError('deletion_registry_older_than_backup')
    data['deletion_revision']=registry['revision'];data['deletion_registry_complete']=True
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(removed)


def sanitize_text_files(files, registry):
    if not set(files)<={'users.json','events.jsonl','verified-menus.json','deals.json'}:
        raise ValueError('unclassified_backup_files')
    with tempfile.TemporaryDirectory(prefix='justhere-text-guard-') as raw:
        root=Path(raw);counts={}
        for name,value in files.items():(root/name).write_bytes(value)
        if 'users.json' in files:counts['profiles']=sanitize_users(root/'users.json',registry)
        if 'events.jsonl' in files:counts['events']=sanitize_events(root/'events.jsonl',registry)
        return {name:(root/name).read_bytes() for name in files},counts


def sanitize_events(path, registry):
    rows=[];sessions=set(registry['session_hashes'])
    for raw in path.read_bytes().splitlines(keepends=True):
        if not raw.strip():
            rows.append((raw,{},False));continue
        try:
            row=strict_json(raw)
            if not isinstance(row,dict) or (row.get('props') is not None and not isinstance(row['props'],dict)):
                raise ValueError()
        except (ValueError,UnicodeError):
            raise ValueError('backup_event_integrity_required') from None
        own=_revoked(row.get('uid'),registry)
        device=digest(row.get('device_id')) in registry['device_hashes']
        if row.get('uid') and not own and device:
            raise ValueError('backup_shared_device_requires_resolution')
        if own or device:
            session=(row.get('props') or {}).get('session_id')
            if session:
                sessions.add(digest(session))
        rows.append((raw,row,own or device))
    kept=[];removed=0
    for raw,row,own in rows:
        session=digest((row.get('props') or {}).get('session_id'))
        if session in sessions and row.get('uid') and not own:
            raise ValueError('backup_shared_session_requires_resolution')
        if own or (not row.get('uid') and not row.get('device_id') and session in sessions):
            removed+=1
        else:
            kept.append(raw)
    path.write_bytes(b''.join(kept));return removed


def sanitize_database(path, registry, *, native=False):
    removed=0
    with closing(sqlite3.connect(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('backup_database_integrity_required')
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA secure_delete=ON')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        plan=[]
        for table in tables:
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',table):
                raise ValueError('unsupported_backup_schema')
            columns={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
            if 'uid' in columns:
                uids=[r[0] for r in db.execute(f'SELECT DISTINCT uid FROM {table}') if _revoked(r[0],registry)]
                if uids and table not in (REMOVABLE|{'account_deletion_requests'} if not native else {'attempts'}):
                    raise ValueError('backup_retained_records_require_resolution')
                plan.extend((table,uid) for uid in uids)
            if 'target_uid' in columns and any(_revoked(r[0],registry) for r in db.execute(f'SELECT DISTINCT target_uid FROM {table}')):
                raise ValueError('backup_identity_records_require_resolution')
            if 'session_id' in columns and 'uid' in columns:
                if any(digest(sid) in registry['session_hashes'] and not _revoked(uid,registry) for sid,uid in db.execute(f'SELECT session_id,uid FROM {table}')):
                    raise ValueError('backup_shared_session_requires_resolution')
        if 'admin_audit' in tables:
            if any(_revoked(row[0],registry) for row in db.execute('SELECT target_id FROM admin_audit')):
                raise ValueError('backup_retained_records_require_resolution')
        with db:
            # All blocked scopes are checked before changing this private copy.
            for table,uid in plan:
                if table=='account_deletion_requests':
                    db.execute("UPDATE account_deletion_requests SET uid=?,status='active_data_deleted' WHERE uid=?",('deleted:'+digest(uid),uid))
                else:
                    removed+=db.execute(f'DELETE FROM {table} WHERE uid=?',(uid,)).rowcount
            if 'account_deletion_jobs' in tables:
                for ident,payload in db.execute('SELECT request_id,payload FROM account_deletion_jobs').fetchall():
                    try:data=strict_json(payload)
                    except ValueError:raise ValueError('backup_journal_integrity_required') from None
                    if not isinstance(data,dict):raise ValueError('backup_journal_integrity_required')
                    if _revoked(data.get('uid'),registry):
                        db.execute("UPDATE account_deletion_jobs SET payload='{}',stage='active_data_deleted' WHERE request_id=?",(ident,))
        if db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('backup_reference_integrity_required')
        db.execute('VACUUM');db.execute('PRAGMA journal_mode=DELETE')
    return removed


def _new_target(source, target, registry_path):
    source,target,registry_path=Path(source),Path(target),Path(registry_path)
    if source.is_symlink() or registry_path.is_symlink():raise ValueError('symlink_not_supported')
    if target.exists() or target.is_symlink():raise ValueError('target_must_not_exist')
    source=source.resolve();target=target.resolve();registry_path=registry_path.resolve()
    if target==source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('overlapping_backup_paths')
    if source.is_dir() and registry_path.is_relative_to(source):
        raise ValueError('independent_current_registry_required')
    from .config import data_dir
    if target==data_dir().resolve() or (source.is_dir() and source==data_dir().resolve()):
        raise ValueError('live_storage_is_not_a_backup_target')
    return source,target,load_registry(registry_path)


def _report(root, registry, counts):
    files={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    report={'version':1,'scope':'sanitized_copy_only','registry_revision':registry['revision'],
            'registry_sha256':fingerprint(registry),'counts':counts,'files':files,
            'source_backup_modified':False,'full_deletion_complete':False,
            'requires_account_restore':not (root/'users.json').exists()}
    (root/'restore-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def _publish(output,target):
    # Reserve without replacement, including a target created concurrently after preflight.
    target.mkdir(mode=0o700,exist_ok=False)
    marker=target/'.restore-incomplete';marker.write_text('Do not use until validation and publishing complete.')
    for child in output.iterdir():child.rename(target/child.name)
    marker.unlink()


def _verify_images(root):
    dbpath=root/'rewards.sqlite3'
    with closing(sqlite3.connect(dbpath)) as db:
        referenced={r[0] for r in db.execute('SELECT image_path FROM receipts') if r[0]!='receipt_uploads/deleted'}
    actual={str(p.relative_to(root)).replace('\\','/') for p in (root/'receipt_uploads').glob('*') if p.is_file()}
    if actual!=referenced:raise ValueError('backup_unclassified_or_missing_images')


def sanitize_snapshot(source, target, registry_path):
    source,target,registry=_new_target(source,target,registry_path)
    allowed={'users.json','events.jsonl','verified-menus.json','deals.json','rewards.sqlite3','native-auth.sqlite3','manifest.json','receipt_uploads','deletion-registry.json','restore-report.json'}
    if not source.is_dir() or not (source/'users.json').is_file():raise ValueError('unsupported_snapshot')
    if any(p.is_symlink() for p in source.rglob('*')):raise ValueError('symlink_not_supported')
    if any(p.name not in allowed for p in source.iterdir()):raise ValueError('unclassified_backup_files')
    if (source/'receipt_uploads').exists() and any(not p.is_file() for p in (source/'receipt_uploads').iterdir()):raise ValueError('unclassified_backup_files')
    if (source/'deletion-registry.json').exists():
        embedded=load_registry(source/'deletion-registry.json')
        if embedded['revision']>registry['revision'] or any(not set(embedded[k])<=set(registry[k]) for k in ('uid_hashes','device_hashes','session_hashes')):
            raise ValueError('deletion_registry_older_than_backup')
    if (source/'restore-report.json').exists():
        report=strict_json((source/'restore-report.json').read_text(encoding='utf-8'))
        if not isinstance(report,dict) or not isinstance(report.get('files'),dict):raise ValueError('unsupported_backup_manifest')
        for name,expected in report['files'].items():
            path=source/name
            if not path.resolve().is_relative_to(source) or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('backup_checksum_mismatch')
    if (source/'manifest.json').exists():
        manifest=strict_json((source/'manifest.json').read_text(encoding='utf-8'))
        files=manifest.get('files') if isinstance(manifest,dict) else None
        if not isinstance(files,dict):raise ValueError('unsupported_backup_manifest')
        for name,meta in files.items():
            if name not in allowed-{'manifest.json','receipt_uploads'}:raise ValueError('unsupported_backup_manifest')
            path=source/name;expected=meta.get('sha256') if isinstance(meta,dict) else meta
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('backup_checksum_mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deletion-copy-',dir=target.parent) as raw:
        output=Path(raw)/'result';shutil.copytree(source,output);counts={}
        if os.name!='nt':
            output.chmod(0o700)
            for p in output.rglob('*'):
                if p.is_file():p.chmod(0o600)
        counts['profiles']=sanitize_users(output/'users.json',registry)
        if (output/'events.jsonl').exists():counts['events']=sanitize_events(output/'events.jsonl',registry)
        if (output/'rewards.sqlite3').exists():
            counts['reward_records']=sanitize_database(output/'rewards.sqlite3',registry);_verify_images(output)
        elif (output/'receipt_uploads').exists():raise ValueError('backup_unclassified_images')
        if (output/'native-auth.sqlite3').exists():counts['native_attempts']=sanitize_database(output/'native-auth.sqlite3',registry,native=True)
        (output/'manifest.json').unlink(missing_ok=True)
        (output/'restore-report.json').unlink(missing_ok=True)
        (output/'deletion-registry.json').write_text(json.dumps(registry),encoding='utf-8')
        report=_report(output,registry,counts);_publish(output,target)
    return report


def restore_rewards(archive, target, registry_path):
    archive,target,registry=_new_target(archive,target,registry_path)
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deletion-restore-',dir=target.parent) as raw:
        output=Path(raw)/'result';output.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as bundle:
            names=bundle.namelist()
            if len(names)!=len(set(names)):raise ValueError('duplicate_archive_entries')
            if len(names)>10000 or bundle.getinfo('manifest.json').file_size>16*1024*1024:raise ValueError('backup_too_large')
            if sum(i.file_size for i in bundle.infolist())>1024**3:raise ValueError('backup_too_large')
            manifest=strict_json(bundle.read('manifest.json'))
            if not isinstance(manifest,dict):raise ValueError('unsupported_backup')
            files=manifest.get('files',{})
            if type(manifest.get('version')) is not int or manifest.get('version')!=1 or not isinstance(files,dict) or 'rewards.sqlite3' not in files or set(names)!=set(files)|{'manifest.json'}:raise ValueError('unsupported_backup')
            for name,expected in files.items():
                path=PurePosixPath(name)
                if name!='rewards.sqlite3' and not (len(path.parts)==2 and path.parts[0]=='receipt_uploads' and path.parts[1] not in ('.','..') and '\\' not in name and ':' not in name):raise ValueError('unsafe_archive_path')
                dest=output/name;dest.parent.mkdir(parents=True,exist_ok=True);digest_value=hashlib.sha256()
                with bundle.open(name) as src,dest.open('xb') as dst:
                    for chunk in iter(lambda:src.read(1024*1024),b''):digest_value.update(chunk);dst.write(chunk)
                if digest_value.hexdigest()!=expected:raise ValueError('backup_checksum_mismatch')
        counts={'reward_records':sanitize_database(output/'rewards.sqlite3',registry)};_verify_images(output)
        (output/'deletion-registry.json').write_text(json.dumps(registry),encoding='utf-8')
        (output/'.storage-maintenance').write_text('Offline reward restore only. Restore accounts with the SAME current registry and signing keys, restart and verify before removing this marker.')
        report=_report(output,registry,counts);_publish(output,target)
    return report
