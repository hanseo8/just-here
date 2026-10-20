"""Temporary-only deletion intake tests. Never deletes customer records."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATA_DIR=directory, RECEIPT_REWARDS='off', REWARD_BANK_PAYOUTS='off',
                      ADMIN_TOKEN='deletion-test-admin',ADMIN_REQUIRE_2FA='off',ADMIN_TOTP_SECRET='',
                      GUEST_SIGNING_SECRET='deletion-test-secret',KAKAO_REST_API_KEY=' ',GOOGLE_PLACES_PHOTOS='off')
    os.environ.pop('RECEIPT_REWARDS_ALLOW_VOLATILE',None)
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import rewards, account_requests
    client=TestClient(app)
    identity=client.post('/v1/auth/guest',json={'device_id':'deletion-test-device'}).json()
    headers={'X-Guest-Token':identity['guest_token']}
    body={'uid':identity['uid'],'confirm':True}
    assert client.get('/account/delete').status_code==200
    assert client.get('/account/delete').headers['cache-control']=='no-store'
    assert client.post('/v1/me/deletion',json=body).status_code==401
    assert client.post('/v1/me/deletion',json={**body,'uid':'someone-else'},headers=headers).status_code==401
    assert client.post('/v1/me/deletion',json={**body,'confirm':False},headers=headers).status_code==400
    assert client.post('/v1/me/deletion',json=body,headers=headers).status_code==503
    os.environ['RECEIPT_REWARDS_ALLOW_VOLATILE']='on'
    response=client.post('/v1/me/deletion',json=body,headers=headers)
    assert response.status_code==200,response.text
    ident=response.json()['request']['id']
    assert client.post('/v1/me/deletion',json=body,headers=headers).status_code==429
    client=TestClient(app,client=('127.0.0.2',50000))
    assert client.post('/v1/me/deletion',json=body,headers=headers).json()['request']['id']==ident
    assert client.get('/v1/me/deletion',params={'uid':'other'},headers=headers).status_code==401
    assert client.get('/v1/admin/account-deletions').status_code==401
    admin={'X-Admin-Token':'deletion-test-admin'}
    assert len(client.get('/v1/admin/account-deletions',headers=admin).json()['requests'])==1
    assert client.post('/v1/admin/account-deletions/'+ident+'/review',headers=admin).status_code==200
    response=client.get('/v1/me/deletion',params={'uid':identity['uid']},headers=headers)
    assert response.json()['request']['status']=='reviewing'
    assert response.headers['cache-control']=='no-store'
    store=rewards.get_store()
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows=list(pool.map(lambda _:account_requests.submit(store,identity['uid']),range(8)))
    assert {row['id'] for row in rows}=={ident}
    restored=rewards.RewardStore(Path(directory)/'rewards.sqlite3')
    assert account_requests.get(restored,identity['uid'])['status']=='reviewing'
    assert restored.list_for_user(identity['uid'])['balance']==0
    print('PASS: owner-only intake, confirmation, persistent-store gate, duplicate/concurrent requests, admin isolation, review state, no fake completion, restart retention')

    endpoint='/v1/admin/account-deletions/'+ident+'/preflight'
    assert client.get(endpoint).status_code==401
    report=client.get(endpoint,headers=admin).json()
    assert report['blockers']==[] and report['can_execute'] is False
    attribution=restored.create_attribution(uid=identity['uid'],session_id='delete-check-session',place_id='delete-check-place',place_name='Test place',menu_id='test-menu',menu_name='Test menu',intent='visit')
    with restored._db() as db:
        db.execute("""INSERT INTO receipts (id,uid,attribution_id,reward_day,purchased_at,amount_krw,approval_hash,image_path,image_sha256,content_type,review_return,created_at)
          VALUES ('delete-test-receipt',?,?, '2026-10-19','2026-10-19T00:00:00+00:00',3000,'delete-test-approval','test-only.jpg','delete-test-image','image/jpeg','yes','2026-10-19T00:00:00+00:00')""",(identity['uid'],attribution['id']))
        db.execute("INSERT INTO reward_ledger (id,uid,amount,kind,created_at) VALUES ('delete-test-ledger',?,300,'test','2026-10-19T00:00:00+00:00')",(identity['uid'],))
        db.execute("""INSERT INTO payouts (id,uid,request_id,receipt_id,amount_krw,recipient_encrypted,account_tail,created_at,updated_at) VALUES ('delete-test-payout',?,'test-request','delete-test-receipt',300,'test-not-real','0000','2026-10-19T00:00:00+00:00','2026-10-19T00:00:00+00:00')""",(identity['uid'],))
    report=client.get(endpoint,headers=admin).json()
    assert set(report['blockers'])=={'receipt_review_pending','payout_pending','balance_requires_resolution'}
    assert report['counts']['balance_points']==300 and report['can_execute'] is False
    response=client.post('/v1/me/deletion/withdraw',json=body,headers=headers)
    assert response.status_code==200 and response.json()['request']['status']=='withdrawn'
    assert 'request_withdrawn' in client.get(endpoint,headers=admin).json()['blockers']
    assert client.post('/v1/admin/account-deletions/'+ident+'/review',headers=admin).status_code==404
    assert restored.list_for_user(identity['uid'])['balance']==300
    assert client.post('/v1/me/deletion',json=body,headers=headers).json()['request']['status']=='requested'
    print('PASS: authenticated preflight, pending receipt/payout/balance blockers, no deletion execution, withdrawal/re-request, transaction records preserved')
