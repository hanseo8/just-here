"""Destructive scenarios ONLY in TemporaryDirectory; no live accounts or external calls."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,RECEIPT_REWARDS='off',RECEIPT_REWARDS_ALLOW_VOLATILE='on',
        REWARD_BANK_PAYOUTS='off',GUEST_SIGNING_SECRET='isolated-delete-executor',
        ADMIN_TOKEN='isolated-delete-admin',ADMIN_REQUIRE_2FA='on',
        ADMIN_TOTP_SECRET='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',KAKAO_REST_API_KEY=' ',
        GOOGLE_PLACES_PHOTOS='off',ACCOUNT_DELETION_EXECUTION='off',ACCOUNT_DELETION_SINGLE_INSTANCE='on')
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import account_deletion as executor,account_requests,rewards,users,analytics,guest_token,admin_security,engine,share,duo,native_auth
    client=TestClient(app)
    store=rewards.get_store();root=Path(raw)
    def guest(device):
        # Call the ordinary guest issuer before maintenance begins.
        profile=users.STORE.ensure_guest(device)
        return profile['uid'],{'X-Guest-Token':guest_token.issue(profile['uid'],device)}
    def intake(uid,headers,ip):
        c=TestClient(app,client=(ip,5000))
        result=c.post('/v1/me/deletion',headers=headers,json={'uid':uid,'confirm':True})
        assert result.status_code==200,result.text
        return result.json()
    admin={'X-Admin-Token':'isolated-delete-admin'}
    r=client.post('/v1/admin/auth',headers=admin,json={'otp':admin_security.code(admin_security.key(),int(time.time())//30)})
    assert r.status_code==200,r.text
    admin['X-Admin-Session']=r.json()['session_token']
    uid,headers=guest('executor-original');other,other_headers=guest('executor-other')
    data=intake(uid,headers,'127.0.0.10');ident=data['request']['id'];tracking=data['tracking']
    endpoint='/v1/admin/account-deletions/'+ident+'/execute'
    confirm={'confirm_request_id':ident,'confirm_permanent':True}
    assert client.post(endpoint,json=confirm).status_code==401
    assert client.post(endpoint,headers={'X-Admin-Token':admin['X-Admin-Token']},json=confirm).status_code==401
    assert client.post(endpoint,headers=admin,json=confirm).json()['detail']=='deletion_execution_disabled'
    os.environ['ACCOUNT_DELETION_EXECUTION']='on'
    assert client.post(endpoint,headers=admin,json={**confirm,'confirm_permanent':False}).json()['detail']=='explicit_deletion_confirmation_required'
    assert client.post(endpoint,headers=admin,json=confirm).json()['detail']=='maintenance_and_drain_required'
    att=store.create_attribution(uid=uid,session_id='own-session',place_id='p',place_name='Own',menu_id='m',menu_name='Own',intent='visit')
    store.create_attribution(uid=other,session_id='other-session',place_id='p2',place_name='Other',menu_id='m2',menu_name='Other',intent='visit')
    analytics.append_event('session_start',uid=uid,device_id='executor-original',props={'session_id':'own-session','receipt_id':'own-share','duo_id':'own-duo'})
    analytics.append_event('recommend_shown',props={'session_id':'own-session'})
    analytics.append_event('app_open',uid=other,device_id='executor-other',props={'session_id':'other-session'})
    other_bytes=analytics.EVENTS_PATH.read_bytes().splitlines(keepends=True)[-1]
    engine.SESSIONS['own-session']=object();engine.SESSIONS['other-session']=object()
    share.RECEIPTS['own-share']=object();share.RECEIPTS['other-share']=object()
    duo.ROOMS['own-duo']=object();duo.ROOMS['other-duo']=object()
    native_auth.start(uid,'a'*64,'fake-provider-key')
    native_auth.start(other,'b'*64,'fake-provider-key')
    (root/'.storage-maintenance').write_text('test-only')
    assert client.get('/health').status_code==200
    assert client.post('/v1/auth/guest',json={'device_id':'must-not-enter'}).status_code==503
    # Draining must be verified independently from the presence of the marker.
    try:executor.execute(store,ident,actor='test',drained=False,**confirm);raise AssertionError('undrained execution')
    except ValueError as e:assert str(e)=='maintenance_and_drain_required'
    # A failure after revocation must not manufacture a completed status, and must survive restart.
    with patch.object(executor,'_purge_events',side_effect=OSError('test-only-failure')):
        try:executor.execute(store,ident,actor='test',drained=True,**confirm);raise AssertionError('failure hidden')
        except OSError:pass
    assert users.STORE.get(uid) is None and guest_token.verify(headers['X-Guest-Token']) is None
    assert account_requests.get(store,uid)['status']=='deleting'
    assert account_requests.receipt_status(store,ident,tracking['receipt'])['status']=='deleting'
    assert any(uid in line for line in analytics.EVENTS_PATH.read_text().splitlines())
    probe='''
import json,os
from backend.app import rewards,account_deletion
ident=os.environ['TEST_DELETE_REQUEST']
result=account_deletion.execute(rewards.get_store(),ident,actor='restart-fixture',confirm_request_id=ident,confirm_permanent=True,drained=True)
print(json.dumps(result))
'''
    env={**os.environ,'TEST_DELETE_REQUEST':ident}
    restarted=subprocess.run([sys.executable,'-c',probe],env=env,capture_output=True,text=True,check=True)
    result=json.loads(restarted.stdout)
    assert result=={'status':'active_data_deleted','backup_status':'pending','full_deletion_complete':False}
    # A true service restart also discards the old process's in-memory maps.
    executor._purge_memory({'sessions':['own-session'],'shares':['own-share'],'duos':['own-duo']})
    users.STORE=users.UserStore(users.STORE.path)
    assert guest_token.verify(headers['X-Guest-Token']) is None and guest_token.verify(other_headers['X-Guest-Token'])
    assert users.STORE.get(other) and analytics.EVENTS_PATH.read_bytes()==other_bytes
    assert 'other-session' in engine.SESSIONS and 'other-share' in share.RECEIPTS and 'other-duo' in duo.ROOMS
    with store._db() as db:
        assert not db.execute('SELECT 1 FROM attributions WHERE uid=?',(uid,)).fetchone()
        assert db.execute('SELECT 1 FROM attributions WHERE uid=?',(other,)).fetchone()
        assert db.execute('SELECT payload FROM account_deletion_jobs WHERE request_id=?',(ident,)).fetchone()[0]=='{}'
        assert db.execute('SELECT uid FROM account_deletion_requests WHERE id=?',(ident,)).fetchone()[0].startswith('deleted:')
    with native_auth.database() as db:
        assert not db.execute('SELECT 1 FROM attempts WHERE uid=?',(uid,)).fetchone()
        assert db.execute('SELECT 1 FROM attempts WHERE uid=?',(other,)).fetchone()
    assert client.post(endpoint,headers=admin,json=confirm).json()['status']=='active_data_deleted'
    assert client.post('/v1/admin/account-deletions/'+ident+'/review',headers=admin).status_code==404
    (root/'.storage-maintenance').unlink()
    status_client=TestClient(app,client=('127.0.0.20',5000))
    public=status_client.post('/v1/me/deletion/status',json={'request_id':ident,'receipt':tracking['receipt']})
    assert public.status_code==200 and public.headers['cache-control']=='no-store'
    assert public.json()['request']['status']=='active_data_deleted' and not public.json()['request']['full_deletion_complete']
    assert uid not in public.text and 'executor-original' not in public.text
    assert status_client.post('/v1/me/deletion/status',json={'request_id':ident,'receipt':'x'*43}).status_code==404
    assert client.get('/v1/me/deletion',params={'uid':uid},headers=headers).status_code==401
    fresh=client.post('/v1/auth/guest',json={'device_id':'executor-original'}).json()
    assert fresh['uid']!=uid
    print('PASS admin 2FA/explicit confirmation/maintenance/drain; revocation, failed-job persistence and fresh-process resume, scoped receipt, other-user preservation, no fake backup completion')

    # Financial/identity/unknown records never enter this clean-account executor.
    blocked,blocked_headers=guest('executor-blocked')
    blocked_data=intake(blocked,blocked_headers,'127.0.0.30');bid=blocked_data['request']['id']
    with store._db() as db:
        db.execute("INSERT INTO reward_ledger (id,uid,amount,kind,created_at) VALUES ('financial-fixture',?,0,'retained-fixture',?)",(blocked,rewards._iso()))
    assert 'retained_records_require_resolution' in executor.preview(store,bid)['blockers']
    (root/'.storage-maintenance').write_text('test-only')
    r=client.post('/v1/admin/account-deletions/'+bid+'/execute',headers=admin,json={'confirm_request_id':bid,'confirm_permanent':True})
    assert r.status_code==409 and users.STORE.get(blocked)
    (root/'.storage-maintenance').unlink()
    shared,sh=guest('executor-shared');sid=intake(shared,sh,'127.0.0.40')['request']['id']
    analytics.append_event('app_open',uid=other,device_id='executor-shared')
    before=analytics.EVENTS_PATH.read_bytes();(root/'.storage-maintenance').write_text('test-only')
    try:executor.execute(store,sid,actor='test',drained=True,confirm_request_id=sid,confirm_permanent=True);raise AssertionError('shared record deleted')
    except ValueError as e:assert str(e)=='shared_account_records_require_resolution'
    assert users.STORE.get(shared) and analytics.EVENTS_PATH.read_bytes()==before
    (root/'.storage-maintenance').unlink()
    print('PASS transaction retention and shared-identity/event guards keep original profile and records; all scenarios used temporary data only')

    happy,hh=guest('executor-happy-api');hdata=intake(happy,hh,'127.0.0.50');hid=hdata['request']['id']
    analytics.append_event('app_open',uid=happy,device_id='executor-happy-api')
    (root/'.storage-maintenance').write_text('test-only')
    # Returning without deleting a stream must fail postconditions, not report success.
    with patch.object(executor,'_purge_events',return_value=None):
        response=client.post('/v1/admin/account-deletions/'+hid+'/execute',headers=admin,
                            json={'confirm_request_id':hid,'confirm_permanent':True})
    assert response.status_code==409 and response.json()['detail']=='deletion_postcondition_failed'
    assert account_requests.get(store,happy)['status']=='deleting'
    response=client.post('/v1/admin/account-deletions/'+hid+'/execute',headers=admin,
                        json={'confirm_request_id':hid,'confirm_permanent':True})
    assert response.status_code==200,response.text
    assert response.json()['full_deletion_complete'] is False
    assert not any(happy in line for line in analytics.EVENTS_PATH.read_text().splitlines())
    (root/'.storage-maintenance').unlink()
    assert client.get('/v1/admin/account-deletions/registry').status_code==401
    assert client.get('/v1/admin/account-deletions/registry',headers={'X-Admin-Token':admin['X-Admin-Token']}).status_code==401
    export=client.get('/v1/admin/account-deletions/registry',headers=admin)
    assert export.status_code==200 and export.headers['cache-control']=='no-store'
    exported=export.json()['deletion_registry']
    assert exported['revision']>=1 and happy not in export.text and 'executor-happy-api' not in export.text
    assert exported['device_hashes'] and exported['session_hashes']
    tracking_client=TestClient(app,client=('127.0.0.60',5000))
    assert tracking_client.post('/v1/me/deletion/status',json={'request_id':hid,'receipt':tracking['receipt']}).status_code==404
    with store._db() as db:
        saved=db.execute('SELECT secret_hash FROM account_deletion_receipts WHERE request_id=?',(hid,)).fetchone()[0]
        assert saved!=hdata['tracking']['receipt']
    assert account_requests.receipt_status(store,hid,hdata['tracking']['receipt'])['status']=='active_data_deleted'
    print('PASS API execution postcondition failure/retry, request-bound hashed read-only receipt, real active-data deletion with backup phase explicitly pending')
