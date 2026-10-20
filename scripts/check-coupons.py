"""Offline coupon lifecycle and access checks; no real coupons are issued."""
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATA_DIR=directory, RECEIPT_REWARDS='off',
                      PARTNER_COUPONS='off', REWARD_BANK_PAYOUTS='off',
                      RECEIPT_REWARDS_ALLOW_VOLATILE='on', ADMIN_TOKEN='coupon-test-admin',
                      ADMIN_REQUIRE_2FA='off', ADMIN_TOTP_SECRET='',
                      GUEST_SIGNING_SECRET='coupon-test-secret',
                      KAKAO_REST_API_KEY=' ', GOOGLE_PLACES_PHOTOS='off')
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import coupons, rewards
    client = TestClient(app)
    guest = client.post('/v1/auth/guest', json={'device_id':'coupon-test-device'}).json()
    headers = {'X-Guest-Token':guest['guest_token']}
    admin = {'X-Admin-Token':'coupon-test-admin'}
    body = dict(uid=guest['uid'], merchant_id='test-branch', merchant_name='Test branch',
                benefit='Test benefit', terms='One use at test branch only',
                contract_reference='local-fixture-only',
                expires_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
                request_id='coupon-test-request-01')
    assert client.post('/v1/admin/coupons', json=body).status_code == 401
    assert client.post('/v1/admin/coupons', json=body, headers=admin).status_code == 503
    assert client.get('/v1/rewards/coupons', params={'uid':guest['uid']}).status_code == 401
    os.environ['PARTNER_COUPONS'] = 'on'
    issued = client.post('/v1/admin/coupons', json=body, headers=admin)
    assert issued.status_code == 200, issued.text
    ident = issued.json()['coupon']['id']
    assert client.post('/v1/admin/coupons', json=body, headers=admin).json()['coupon']['id'] == ident
    assert client.post('/v1/admin/coupons', json={**body,'benefit':'changed'}, headers=admin).status_code == 409
    own = client.get('/v1/rewards/coupons', params={'uid':guest['uid']}, headers=headers)
    assert own.status_code == 200 and len(own.json()['coupons']) == 1
    assert 'contract_reference' not in own.json()['coupons'][0]
    assert own.headers['cache-control'] == 'no-store'
    assert client.get('/v1/rewards/coupons', params={'uid':'other'}, headers=headers).status_code in (401,403)
    action = '/v1/admin/coupons/'+ident+'/action'
    assert client.post(action, json={'merchant_id':'wrong','action':'used'}, headers=admin).status_code == 409
    store = rewards.get_store()
    def use(_):
        try:
            coupons.transition(store, ident, 'test-branch', 'used', 'admin')
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(use, range(8))) == 1
    assert client.post(action, json={'merchant_id':'test-branch','action':'cancelled'}, headers=admin).status_code == 409
    cancelled = coupons.issue(store, {**body,'request_id':'coupon-test-cancel'}, 'admin')
    coupons.transition(store,cancelled['id'],'test-branch','cancelled','admin')
    expired = coupons.issue(store, {**body,'request_id':'coupon-test-expiry'}, 'admin')
    with store._db() as db:
        db.execute("UPDATE partner_coupons SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (expired['id'],))
    try:
        coupons.transition(store,expired['id'],'test-branch','used','admin')
        raise AssertionError('Expired coupon used')
    except ValueError:
        pass
    restarted = rewards.RewardStore(Path(directory)/'rewards.sqlite3')
    assert {x['status'] for x in coupons.listing(restarted,guest['uid'])} == {'used','cancelled','expired'}
    assert restarted.list_for_user(guest['uid'])['balance'] == 0
    os.environ['PARTNER_COUPONS']='off'
    assert client.post('/v1/admin/coupons', json=body, headers=admin).status_code == 503
    assert len(client.get('/v1/rewards/coupons', params={'uid':guest['uid']}, headers=headers).json()['coupons']) == 3
    print('PASS: OFF gating, auth, UID isolation, issue idempotency, branch match, concurrent single use, cancel, expiry, restart retention, no point debit')

    import json
    os.environ['PARTNER_COUPONS']='on'
    os.environ['PARTNER_MERCHANT_KEYS']=json.dumps({'test-branch':'merchant-test-key-'+'x'*32,'other-branch':'other-merchant-key-'+'y'*32})
    merchant_headers={'X-Merchant-Key':'merchant-test-key-'+'x'*32}
    other_headers={'X-Merchant-Key':'other-merchant-key-'+'y'*32}
    fresh=coupons.issue(store,{**body,'request_id':'merchant-code-test'},'admin')
    endpoint='/v1/rewards/coupons/'+fresh['id']+'/code'
    assert client.post(endpoint,params={'uid':'other'},headers=headers).status_code in (401,403)
    first=client.post(endpoint,params={'uid':guest['uid']},headers=headers).json()['code']
    second=client.post(endpoint,params={'uid':guest['uid']},headers=headers).json()['code']
    check='/v1/merchant/coupons/check'
    assert client.post(check,json={'code':second}).status_code==401
    assert client.post(check,json={'code':second},headers=admin).status_code==401
    assert client.post(check,json={'code':first},headers=merchant_headers).status_code==409
    assert client.post(check,json={'code':second},headers=other_headers).status_code==409
    response=client.post(check,json={'code':second},headers=merchant_headers)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert 'uid' not in response.json()['coupon']
    assert client.post('/v1/merchant/coupons/use',json={'code':second},headers=merchant_headers).status_code==200
    assert client.post('/v1/merchant/coupons/use',json={'code':second},headers=merchant_headers).status_code==409
    exp=coupons.issue(store,{**body,'request_id':'merchant-code-expiry'},'admin')
    code=coupons.create_code(store,guest['uid'],exp['id'])['code']
    with store._db() as db:
        db.execute("UPDATE coupon_codes SET expires_at='2000-01-01T00:00:00+00:00' WHERE coupon_id=?",(exp['id'],))
    assert client.post(check,json={'code':code},headers=merchant_headers).status_code==409
    os.environ['PARTNER_COUPONS']='off'
    assert client.post(check,json={'code':code},headers=merchant_headers).status_code==503
    print('PASS: merchant-only key, branch scope, customer ownership, code rotation, expiry, single use, OFF gate, no UID leakage')

    from backend.app import account_requests
    destination='kakao_coupon_migration_test'
    account_requests.submit(store,guest['uid'])
    try:
        store.merge_uid(guest['uid'],destination)
        raise AssertionError('Pending privacy request must block account merge')
    except ValueError as exc:
        assert str(exc)=='account_deletion_pending'
    assert len(coupons.listing(store,guest['uid']))==5
    account_requests.withdraw(store,guest['uid'])
    store.merge_uid(guest['uid'],destination)
    assert coupons.listing(store,guest['uid'])==[]
    assert len(coupons.listing(store,destination))==5
    assert account_requests.get(store,destination)['status']=='withdrawn'
    print('PASS: coupon and withdrawn-request ownership migrate; pending deletion blocks merge atomically')
