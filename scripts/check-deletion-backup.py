"""Create/sanitize/restore synthetic snapshots only; never reads or alters production backups."""
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path

with tempfile.TemporaryDirectory() as raw:
    root=Path(raw);live=root/'live';live.mkdir()
    os.environ.update(DATA_DIR=str(live),GUEST_SIGNING_SECRET='offline-backup-fixture',KAKAO_REST_API_KEY=' ',
        GOOGLE_PLACES_PHOTOS='off',RECEIPT_REWARDS='off',RECEIPT_REWARDS_ALLOW_VOLATILE='on',
        ACCOUNT_DELETION_EXECUTION='on',ACCOUNT_DELETION_SINGLE_INSTANCE='on')
    from backend.app import users,rewards,analytics,guest_token,native_auth,account_deletion,account_requests,storage
    from backend.app.deletion_backup import sanitize_snapshot,restore_rewards,load_registry,require_current_registry,fingerprint
    own=users.STORE.ensure_guest('deleted-fixture-device')['uid'];other=users.STORE.ensure_guest('retained-fixture-device')['uid']
    token=guest_token.issue(own,'deleted-fixture-device');store=rewards.get_store()
    for uid,sid in [(own,'old-deleted-session'),(other,'retained-session')]:
        store.create_attribution(uid=uid,session_id=sid,place_id='p',place_name='Fixture',menu_id='m',menu_name='Fixture',intent='visit')
    with store._db() as db:
        db.execute("INSERT INTO reward_ledger (id,uid,amount,kind,created_at) VALUES ('preserved-ledger',?,300,'fixture',?)",(other,rewards._iso()))
    analytics.append_event('session_start',uid=own,device_id='deleted-fixture-device',props={'session_id':'old-deleted-session'})
    analytics.append_event('recommend_shown',props={'session_id':'old-deleted-session'})
    analytics.append_event('app_open',device_id='deleted-fixture-device')
    analytics.append_event('app_open',uid=other,device_id='retained-fixture-device')
    retained_event=analytics.EVENTS_PATH.read_bytes().splitlines(keepends=True)[-1]
    native_auth.start(own,'a'*64,'fixture-key');native_auth.start(other,'b'*64,'fixture-key')
    source=root/'before-deletion';source.mkdir()
    for name in ['users.json','events.jsonl']:shutil.copy2(live/name,source/name)
    (source/'verified-menus.json').write_text('[]')
    for name in ['rewards.sqlite3','native-auth.sqlite3']:
        with closing(sqlite3.connect(live/name)) as src,closing(sqlite3.connect(source/name)) as dst:src.backup(dst)
    manifest={'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in source.iterdir()}}
    (source/'manifest.json').write_text(json.dumps(manifest))
    original={p.name:p.read_bytes() for p in source.iterdir()}
    stage=root/'archive-stage';stage.mkdir();archive=store.backup_archive(stage);archive_before=archive.read_bytes()
    ident=account_requests.submit(store,own)['id'];(live/'.storage-maintenance').touch()
    account_deletion.execute(store,ident,actor='fixture',confirm_request_id=ident,confirm_permanent=True,drained=True)
    (live/'.storage-maintenance').unlink()
    current=root/'independent-current-registry.json';current.write_text(json.dumps(users.STORE.deletion_registry()))
    registry=load_registry(current);assert registry['revision']>0 and own not in current.read_text(encoding='utf-8') and 'deleted-fixture-device' not in current.read_text(encoding='utf-8')
    assert guest_token.verify(token) is None
    target=root/'sanitized';report=sanitize_snapshot(source,target,current)
    assert report['counts']['profiles']==1 and report['counts']['events']==3
    assert report['source_backup_modified'] is False and not report['full_deletion_complete']
    assert (target/'events.jsonl').read_bytes()==retained_event
    before_profiles=json.loads(original['users.json']);after=json.loads((target/'users.json').read_text(encoding='utf-8'))
    assert own not in after['users'] and after['users'][other]==before_profiles['users'][other]
    assert after['device_index']=={'retained-fixture-device':other}
    with closing(sqlite3.connect(target/'rewards.sqlite3')) as db:
        assert not db.execute('SELECT 1 FROM attributions WHERE uid=?',(own,)).fetchone()
        assert db.execute('SELECT SUM(amount) FROM reward_ledger WHERE uid=?',(other,)).fetchone()[0]==300
    with closing(sqlite3.connect(target/'native-auth.sqlite3')) as db:
        assert not db.execute('SELECT 1 FROM attempts WHERE uid=?',(own,)).fetchone()
        assert db.execute('SELECT 1 FROM attempts WHERE uid=?',(other,)).fetchone()
    assert all((source/name).read_bytes()==value for name,value in original.items())
    restored=root/'restored-rewards';restore_rewards(archive,restored,current)
    assert archive.read_bytes()==archive_before
    assert (restored/'.storage-maintenance').exists()
    with closing(sqlite3.connect(restored/'rewards.sqlite3')) as db:
        assert not db.execute('SELECT 1 FROM attributions WHERE uid=?',(own,)).fetchone()
        assert db.execute('SELECT SUM(amount) FROM reward_ledger WHERE uid=?',(other,)).fetchone()[0]==300
    restored_users=users.UserStore(target/'users.json');saved=users.STORE;users.STORE=restored_users
    assert guest_token.verify(token) is None
    new=restored_users.ensure_guest('deleted-fixture-device')['uid'];assert new!=own
    users.STORE=saved
    guard_only=users.UserStore(restored/'users.json');users.STORE=guard_only
    assert guest_token.verify(token) is None
    assert guard_only.deletion_registry()==registry
    users.STORE=saved
    conflicting=root/'conflicting-restore';conflicting.mkdir()
    (conflicting/'users.json').write_bytes(original['users.json'])
    (conflicting/'deletion-registry.json').write_bytes(current.read_bytes())
    conflict_store=users.UserStore(conflicting/'users.json');users.STORE=conflict_store
    assert guest_token.verify(token) is None
    try:conflict_store.ensure_guest('deleted-fixture-device');raise AssertionError('stale profile bypassed registry')
    except ValueError:pass
    assert (conflicting/'users.json').read_bytes()==original['users.json']
    users.STORE=saved
    print('PASS copy-only snapshot/ZIP sanitization, profile/device/anonymous-session/native-auth removal, retained user/event/ledger preservation, old-token refusal after restore, unchanged original backups')

    empty=root/'stale.json';empty.write_text(json.dumps({'version':1,'scope':'deletion_restore_guard','revision':0,'uid_hashes':[],'device_hashes':[],'session_hashes':[]}))
    try:require_current_registry(empty,users.STORE);raise AssertionError('stale live registry accepted')
    except ValueError:pass
    assert require_current_registry(current,users.STORE)==registry
    try:sanitize_snapshot(source,source/'nested-target',current);raise AssertionError('overlap')
    except ValueError:pass
    try:sanitize_snapshot(source,target,current);raise AssertionError('existing output')
    except ValueError:pass
    # Unsupported data and corrupt snapshots never publish a replacement.
    unknown=root/'unknown';shutil.copytree(source,unknown);(unknown/'unclassified-private.json').write_text('{}')
    try:sanitize_snapshot(unknown,root/'must-not-exist',current);raise AssertionError('unknown private file ignored')
    except ValueError:pass
    assert not (root/'must-not-exist').exists()
    damaged=root/'damaged';shutil.copytree(source,damaged);(damaged/'events.jsonl').write_text('corrupt')
    try:sanitize_snapshot(damaged,root/'must-not-exist',current);raise AssertionError('corrupt backup accepted')
    except ValueError:pass
    assert not (root/'must-not-exist').exists()
    legacy=users.UserStore(root/'legacy-users.json');legacy.path.write_text(json.dumps({'users':{},'device_index':{},'deleted_uid_hashes':registry['uid_hashes']}));legacy=users.UserStore(legacy.path)
    try:legacy.deletion_registry();raise AssertionError('incomplete deletion metadata accepted')
    except ValueError:pass
    # A backup containing financial records for the deleted account needs explicit retention handling.
    finance=root/'finance';shutil.copytree(source,finance);(finance/'manifest.json').unlink()
    with closing(sqlite3.connect(finance/'rewards.sqlite3')) as db,db:
        db.execute("INSERT INTO reward_ledger (id,uid,amount,kind,created_at) VALUES ('deleted-old-financial',?,0,'fixture',?)",(own,rewards._iso()))
    try:sanitize_snapshot(finance,root/'must-not-exist',current);raise AssertionError('retained record silently erased')
    except ValueError as e:assert str(e)=='backup_retained_records_require_resolution'
    assert not (root/'must-not-exist').exists()
    # CLI refuses to restore when the independent deletion registry is omitted.
    command=subprocess.run([sys.executable,'scripts/restore-rewards.py',str(archive),str(root/'missing-guard')],capture_output=True)
    assert command.returncode!=0 and not (root/'missing-guard').exists()
    print('PASS mandatory/latest registry checks, unknown/corrupt/legacy metadata refusal, financial retention guard, overlap/existing-target protection')

    spec=importlib.util.spec_from_file_location('deletion_merge_test',Path('scripts/merge-storage.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    old={'users.json':original['users.json'],'events.jsonl':original['events.jsonl']}
    now={'users.json':(live/'users.json').read_bytes(),'events.jsonl':(live/'events.jsonl').read_bytes()}
    merged,_=module.merge(old,now,deletion_registry=current)
    assert own not in json.loads(merged['users.json'])['users'] and [json.loads(line) for line in merged['events.jsonl'].splitlines()]==[json.loads(retained_event)]
    # Cross-process recovery and deletion share a lock; it releases cleanly after failure.
    probe="from pathlib import Path;from backend.app import storage;import os;\ntry:\n with storage.exclusive_operation(Path(os.environ['DATA_DIR'])):print('acquired')\nexcept ValueError:print('blocked')"
    with storage.exclusive_operation(live):
        result=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,check=True)
        assert result.stdout.strip()=='blocked'
    result=subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,check=True)
    assert result.stdout.strip()=='acquired'
    print('PASS old/current merge cannot resurrect deleted profile/events; cross-process delete/recovery lock excludes overlap and releases')
