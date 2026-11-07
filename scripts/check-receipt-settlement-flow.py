"""Phone-verified beta receipt -> review -> manual settlement, isolated and no transfers."""
import os
import tempfile
import time
from pathlib import Path
from cryptography.fernet import Fernet
from scripts.receipt_image_fixture import receipt_image

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw, RECEIPT_REWARDS='on', RECEIPT_REWARDS_ALLOW_VOLATILE='on',
        REWARD_BANK_PAYOUTS='on', PAYOUT_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        REWARD_IDENTITY_REQUIRED='on', REWARD_IDENTITY_ENABLED='on',
        PORTONE_STORE_ID='store-fixture', PORTONE_CHANNEL_KEY='channel-fixture', PORTONE_API_SECRET='fake-not-live',
        REWARD_IDENTITY_HMAC_KEY='isolated-identity-test-key-32-characters',
        GUEST_SIGNING_SECRET='isolated-flow-test', ADMIN_TOKEN='isolated-admin',
        ADMIN_REQUIRE_2FA='on', ADMIN_TOTP_SECRET='GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ',
        KAKAO_REST_API_KEY=' ', GOOGLE_PLACES_PHOTOS='off')
    from fastapi.testclient import TestClient
    from backend.app import rewards, reward_identity, beta_campaign, payouts, admin_security
    from backend.app.main import app
    client=TestClient(app)
    def guest(device):
        body=client.post('/v1/auth/guest',json={'device_id':device}).json()
        return body['uid'],{'X-Guest-Token':body['guest_token']}
    uid,headers=guest('receipt-full-flow');other,other_headers=guest('receipt-other')
    store=rewards.get_store()
    request=client.post('/v1/rewards/identity/start',headers=headers,json={'uid':uid,'consent':True}).json()
    ident=request['identityVerificationId']
    reward_identity.fetch_verified=lambda value:{'id':value,'status':'VERIFIED','channel':{'key':'channel-fixture','type':'LIVE'},'verifiedCustomer':{'di':'fixture-di-no-real-person'}}
    result=client.post('/v1/rewards/identity/complete',headers=headers,json={'uid':uid,'identity_verification_id':ident})
    assert result.status_code==200,result.text
    headers={'X-Guest-Token':result.json()['guest_token']}
    beta_campaign.enroll(store,uid,'fixture-selection')
    admin={'X-Admin-Token':'isolated-admin'}
    login=client.post('/v1/admin/auth',headers=admin,json={'otp':admin_security.code(admin_security.key(),int(time.time())//30)})
    assert login.status_code==200,login.text
    admin['X-Admin-Session']=login.json()['session_token']
    def me():
        r=client.get('/v1/rewards/me',params={'uid':uid},headers=headers)
        assert r.status_code==200 and r.headers['cache-control']=='no-store',r.text
        return r.json()
    def upload(n):
        a=store.create_attribution(uid=uid,session_id='flow-'+str(n),place_id='p'+str(n),place_name='Fixture Restaurant',menu_id='menu',menu_name='Fixture Meal',intent='visit')
        body={'uid':uid,'attribution_id':a['id'],'purchased_at':rewards._iso(),'amount_krw':'12000','approval_number':'flow-approval-'+str(n),'review_return':'no','review_note':'Not a positive review; still eligible.'}
        image=receipt_image(300+n)
        r=client.post('/v1/rewards/receipts',headers=headers,data=body,files={'image':('receipt.jpg',image,'image/jpeg')})
        assert r.status_code==200,r.text
        repeat=client.post('/v1/rewards/receipts',headers=headers,data=body,files={'image':('receipt.jpg',image,'image/jpeg')})
        assert repeat.status_code==409,repeat.text
        return r.json()['receipt']['id']
    def review(rid,approve,reason=''):
        return client.post('/v1/admin/rewards/'+rid+'/decision',headers=admin,json={'approve':approve,'reason':reason})
    a,b=upload(1),upload(2)
    assert me()['pending_points']==600 and me()['balance']==0
    image_url='/v1/rewards/receipts/'+a+'/image'
    assert client.get(image_url,params={'uid':other},headers=other_headers).status_code==404
    assert review(a,True).status_code==200
    assert review(a,True).status_code==200
    assert review(a,False,'opposite after approval').status_code==409
    assert review(b,False).status_code==400
    assert review(b,False,'Unreadable receipt').status_code==200
    assert review(b,False,'repeat').status_code==200
    assert review(b,True).status_code==409
    data=me();assert data['balance']==300 and data['pending_points']==0
    assert {r['id']:r['status'] for r in data['receipts']}=={a:'approved',b:'rejected'}
    assert next(r for r in data['receipts'] if r['id']==b)['admin_reason']=='Unreadable receipt'
    print('PASS phone-verified beta upload, duplicate rejection, private image, negative review, approval idempotency and final-state conflict')
    body={'uid':uid,'receipt_id':a,'request_id':'flow-settlement-1','bank':'Fixture Bank','account':'123456789012','holder':'Fixture Holder','consent':True}
    pay=client.post('/v1/rewards/payouts',headers=headers,json=body)
    assert pay.status_code==200,pay.text
    pid=pay.json()['payout']['id'];assert pay.json()['payout']['amount_krw']==300
    assert '123456789012' not in pay.text and 'Fixture Holder' not in pay.text
    assert me()['balance']==0 and me()['payouts'][0]['status']=='pending'
    assert client.post('/v1/rewards/payouts',headers=headers,json=body).json()['payout']['id']==pid
    assert client.post('/v1/rewards/payouts',headers=headers,json={**body,'request_id':'flow-duplicate'}).status_code==409
    def decision(ident,action,**kw):
        return client.post('/v1/admin/payouts/'+ident+'/decision',headers=admin,json={'action':action,**kw})
    assert decision(pid,'paid',reference='FIXTURE-NOT-A-TRANSFER').status_code==409
    assert decision(pid,'rejected',reason='Invalid fixture bank').status_code==409
    assert decision(pid,'rejected',reason='Invalid fixture bank',no_transfer=True).status_code==200
    assert decision(pid,'rejected',reason='repeat',no_transfer=True).status_code==200
    assert me()['balance']==300 and me()['payouts'][0]['status']=='rejected'
    retry=client.post('/v1/rewards/payouts',headers=headers,json={**body,'request_id':'flow-retry'})
    assert retry.status_code==200,retry.text
    pid2=retry.json()['payout']['id'];assert pid2!=pid and me()['balance']==0
    assert decision(pid2,'processing').status_code==200
    assert any(p['id']==pid2 and p['status']=='processing' for p in me()['payouts'])
    assert decision(pid2,'paid',reference='FIXTURE-NOT-A-TRANSFER').status_code==200
    assert decision(pid2,'paid',reference='FIXTURE-NOT-A-TRANSFER').status_code==200
    assert decision(pid2,'rejected',reason='late',no_transfer=True).status_code==409
    final=me();assert final['balance']==0 and final['pending_points']==0
    assert sum(p['amount_krw'] for p in final['payouts'] if p['status']=='paid')==300
    with store._db() as db:
        assert db.execute("SELECT COUNT(*) FROM reward_ledger WHERE receipt_id=? AND kind='receipt_approved'",(a,)).fetchone()[0]==1
        assert db.execute("SELECT recipient_encrypted FROM payouts WHERE id=?",(pid2,)).fetchone()[0]==''
    assert payouts.reconciliation(store)['records_match'] and not payouts.reconciliation(store)['bank_verified']
    restarted=rewards.RewardStore(Path(raw)/'rewards.sqlite3')
    assert restarted.list_for_user(uid)['receipts']==final['receipts']
    assert payouts.listing(restarted,uid)==final['payouts']
    print('PASS 300 KRW hold -> rejected/refund once -> retry -> processing -> paid, restart, encrypted recipient erased, ledger reconciled; NO bank transfer executed')
