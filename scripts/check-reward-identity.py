"""Phone identity: trusted provider result, account binding, duplicate recovery and reward gates."""
import os
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from cryptography.fernet import Fernet

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw, RECEIPT_REWARDS='on', RECEIPT_REWARDS_ALLOW_VOLATILE='on',
        REWARD_IDENTITY_REQUIRED='on', REWARD_IDENTITY_ENABLED='on',
        REWARD_IDENTITY_HMAC_KEY='identity-test-secret-not-for-production',
        PORTONE_STORE_ID='store-test', PORTONE_CHANNEL_KEY='channel-test', PORTONE_API_SECRET='fake-secret',
        PAYOUT_ENCRYPTION_KEY=Fernet.generate_key().decode(), GUEST_SIGNING_SECRET='identity-test-signing',
        KAKAO_REST_API_KEY=' ', GOOGLE_PLACES_PHOTOS='off')
    from fastapi.testclient import TestClient
    from backend.app import reward_identity as identity, rewards, beta_campaign, payouts
    from backend.app.main import app
    client=TestClient(app)
    def user(name):
        r=client.post('/v1/auth/guest',json={'device_id':name}).json()
        return r['uid'], {'X-Guest-Token':r['guest_token']}
    a,ha=user('identity-a');b,hb=user('identity-b');store=rewards.get_store()
    def begin(uid,headers):
        r=client.post('/v1/rewards/identity/start',json={'uid':uid,'consent':True},headers=headers)
        assert r.status_code==200,r.text
        return r.json()['identityVerificationId']
    def result(ident,di='private-DI-for-person-one',kind='LIVE'):
        return {'id':ident,'status':'VERIFIED','channel':{'key':'channel-test','type':kind},
                'verifiedCustomer':{'di':di,'phoneNumber':'01012345678','name':'DO NOT STORE'}}
    def finish(uid,headers,ident):
        return client.post('/v1/rewards/identity/complete',headers=headers,
                           json={'uid':uid,'identity_verification_id':ident})
    assert client.post('/v1/rewards/identity/start',json={'uid':a,'consent':True}).status_code==401
    assert client.post('/v1/rewards/identity/start',json={'uid':a,'consent':False},headers=ha).status_code==400
    assert client.post('/v1/rewards/beta/apply',json={'uid':a},headers=ha).status_code==409
    try: payouts.request(store,uid=a,receipt_id='none',request_id='request1',bank='test',account='12345678',holder='test')
    except ValueError as e: assert str(e)=='phone_identity_required'
    else: raise AssertionError('unverified payout permitted')
    att=store.create_attribution(uid=a,session_id='test',place_id='p',place_name='test',menu_id='m',menu_name='m',intent='visit')
    from scripts.receipt_image_fixture import receipt_image
    from datetime import datetime,timezone
    upload=client.post('/v1/rewards/receipts',headers=ha,data={'uid':a,'attribution_id':att['id'],
        'purchased_at':datetime.now(timezone.utc).isoformat(),'amount_krw':'10000','approval_number':'12345678','review_return':'yes'},
        files={'image':('receipt.jpg',receipt_image('identity'),'image/jpeg')})
    assert upload.status_code==400 and upload.json()['detail']=='phone_identity_required',upload.text
    print('PASS unverified signup/receipt/payout blocked, authentication and consent required')
    x=begin(a,ha)
    assert finish(b,hb,x).status_code==409
    identity.fetch_verified=lambda ident:result(ident,kind='TEST')
    assert finish(a,ha,x).status_code==409
    identity.fetch_verified=lambda ident:{**result(ident),'status':'READY'}
    assert finish(a,ha,x).status_code==409
    identity.fetch_verified=lambda ident:result(ident)
    done=finish(a,ha,x);assert done.status_code==200,done.text
    assert done.json()['uid']==a and done.json()['identity']['verified']
    assert finish(a,ha,x).json()['uid']==a
    assert client.post('/v1/rewards/beta/apply',headers=ha,json={'uid':a}).status_code==200
    beta_campaign.enroll(store,a,'test-admin')
    print('PASS wrong account/test channel/unverified result rejected; verified guest can apply without Kakao')
    with store._db() as db:
        db.execute("INSERT INTO reward_ledger VALUES('identity-balance',?,NULL,300,'test-credit','',?)", (a,rewards._iso()))
    y=begin(b,hb)
    recovered=finish(b,hb,y);assert recovered.status_code==200,recovered.text
    assert recovered.json()['uid']==a
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM reward_identities').fetchone()[0]==1
        row=dict(db.execute('SELECT * FROM reward_identities').fetchone())
        assert all('private-DI' not in str(v) and '01012345678' not in str(v) and 'DO NOT STORE' not in str(v) for v in row.values())
    assert beta_campaign.progress(store,a)['enrolled']
    assert store.list_for_user(a)['balance']==300
    print('PASS same person recovers existing UID, cohort and balance preserved; no raw DI/name/phone stored')
    z=begin(a,ha);identity.fetch_verified=lambda ident:result(ident,di='different-person-DI')
    assert finish(a,ha,z).status_code==409
    q=begin(a,ha)
    with store._db() as db:db.execute('UPDATE reward_identity_attempts SET expires_at=? WHERE id=?',(int(time.time())-1,q))
    assert finish(a,ha,q).status_code==409
    assert client.post('/v1/rewards/identity/start',json={'uid':a,'consent':True},headers=ha).status_code==429
    c,hc=user('identity-concurrent-c');d,hd=user('identity-concurrent-d')
    ic=begin(c,hc);id_=begin(d,hd)
    identity.fetch_verified=lambda ident:result(ident,di='concurrent-same-person-DI')
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(finish,*args) for args in [(c,hc,ic),(d,hd,id_)]]
        completed=[j.result() for j in jobs]
    assert all(r.status_code==200 for r in completed),[r.text for r in completed]
    assert len({r.json()['uid'] for r in completed})==1
    print('PASS concurrent same-person verification returns one canonical account')
    e,he=user('identity-quota-expiry')
    first=begin(e,he);second=begin(e,he)
    with store._db() as db:
        db.execute('UPDATE reward_identity_attempts SET created_at=?,expires_at=? WHERE uid=?', (int(time.time())-700,int(time.time())-100,e))
    begin(e,he)
    assert client.post('/v1/rewards/identity/start',json={'uid':e,'consent':True},headers=he).status_code==429
    print('PASS expired attempts cannot reset hourly verification quota')
    os.environ['REWARD_IDENTITY_ENABLED']='off'
    assert client.post('/v1/rewards/identity/start',json={'uid':b,'consent':True},headers=hb).status_code==503
    assert client.get('/v1/rewards/me',params={'uid':a},headers=ha).headers['cache-control']=='no-store'
    # A new process/store instance reads the same verified ownership.
    again=rewards.RewardStore(Path(raw)/'rewards.sqlite3');assert identity.status(again,a)['verified']
    print('PASS account switch, expiry, rate limit, unconfigured fail-closed, private cache and restart persistence')
