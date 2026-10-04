"""Offline settlement tests: no bank or Npay requests are sent."""
import os
import tempfile
import json
import runpy
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from cryptography.fernet import Fernet


with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw,RECEIPT_REWARDS='on',RECEIPT_REWARDS_ALLOW_VOLATILE='on',
        REWARD_BANK_PAYOUTS='on',PAYOUT_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ADMIN_TOKEN='payout-test-admin',GUEST_SIGNING_SECRET='payout-test-secret')
    from backend.app import rewards, payouts, guest_token
    from backend.app.main import app
    from fastapi.testclient import TestClient
    store = rewards.get_store()
    client = TestClient(app)
    uid = 'kakao_payout_test'
    headers = {'X-Guest-Token':guest_token.issue(uid,'test')}
    admin = {'X-Admin-Token':'payout-test-admin'}
    def receipt(n):
        owner = uid + str(n)
        att = store.create_attribution(uid=owner,session_id='session'+str(n),place_id='place',
            place_name='Test',menu_id='menu',menu_name='Test',intent='visit')
        r = store.submit_receipt(uid=owner,attribution_id=att['id'],purchased_at=rewards._iso(),
            amount_krw=12000,approval_number='111100'+str(n),content_type='image/jpeg',
            image=b'\xff\xd8\xff'+str(n).encode(),review_return='yes',review_tags=[],review_note='',photo_reuse_consent=False)
        store.decide(r['id'],approve=True,reason='test',admin_id='test')
        return owner,r['id']

    owner,rid=receipt(1)
    headers={'X-Guest-Token':guest_token.issue(owner,'test')}
    body=dict(uid=owner,receipt_id=rid,request_id='request-test-1',bank='Test Bank',account='123456789012',holder='Test Holder',consent=True)
    assert client.post('/v1/rewards/payouts',json=body).status_code == 401
    assert client.post('/v1/rewards/payouts',headers=headers,json={**body,'consent':False}).status_code == 400
    wrong={'X-Guest-Token':guest_token.issue('kakao_other','test')}
    assert client.post('/v1/rewards/payouts',headers=wrong,json={**body,'uid':'kakao_other'}).status_code == 409
    response=client.post('/v1/rewards/payouts',headers=headers,json=body)
    assert response.status_code == 200, response.text
    ident=response.json()['payout']['id']
    assert response.json()['payout']['amount_krw']==300
    assert client.post('/v1/rewards/payouts',headers=headers,json=body).json()['payout']['id']==ident
    assert store.list_for_user(owner)['balance']==0
    assert client.post('/v1/rewards/payouts',headers=headers,json={**body,'request_id':'different-request'}).status_code==409
    with store._db() as db:
        encrypted=db.execute('SELECT recipient_encrypted FROM payouts WHERE id=?',(ident,)).fetchone()[0]
        assert body['account'] not in encrypted and body['holder'] not in encrypted
    assert body['account'] not in response.text
    assert client.get('/v1/admin/payouts').status_code==401
    endpoint='/v1/admin/payouts/'+ident
    assert client.post(endpoint+'/recipient',headers=admin).status_code==409
    def act(action,**extra):
        return client.post(endpoint+'/decision',headers=admin,json=dict(action=action,**extra))
    assert act('paid',reference='BANK-1').status_code==409
    assert act('processing').status_code==200
    assert act('processing').status_code==409
    revealed=client.post(endpoint+'/recipient',headers=admin)
    assert revealed.json()['account']==body['account'] and 'no-store' in revealed.headers['cache-control']
    assert act('rejected',reason='not paid').status_code==409
    assert act('paid').status_code==409
    assert act('paid',reference='BANK-1').status_code==200
    assert act('paid',reference='BANK-1').status_code==200
    assert act('rejected',reason='test',no_transfer=True).status_code==409
    assert store.list_for_user(owner)['balance']==0
    with store._db() as db:
        assert db.execute('SELECT recipient_encrypted FROM payouts WHERE id=?',(ident,)).fetchone()[0]==''

    owner2,rid2=receipt(2)
    headers2={'X-Guest-Token':guest_token.issue(owner2,'test')}
    body2={**body,'uid':owner2,'receipt_id':rid2,'request_id':'request-2'}
    p2=client.post('/v1/rewards/payouts',headers=headers2,json=body2).json()['payout']['id']
    endpoint='/v1/admin/payouts/'+p2
    assert act('processing').status_code==200
    assert act('paid',reference='BANK-1').status_code==409
    assert act('rejected',reason='wrong account',no_transfer=True).status_code==200
    assert act('rejected',reason='retry',no_transfer=True).status_code==200
    assert store.list_for_user(owner2)['balance']==300
    assert store.summary()['points_issued']==600
    assert client.post('/v1/rewards/payouts',headers=headers2,json={**body2,'request_id':'retry-request-2'}).status_code==200
    report = client.get('/v1/admin/payouts', headers=admin)
    assert report.headers['cache-control'] == 'no-store'
    totals = report.json()['reconciliation']
    assert totals['records_match'] and not totals['bank_verified']
    assert totals['states']['paid'] == {'count': 1, 'amount_krw': 300}
    assert totals['states']['pending']['amount_krw'] == 300
    assert totals['states']['rejected']['amount_krw'] == 300
    # Simulate a damaged ledger, ensure it is detected without silently repairing it.
    with store._db() as db:
        db.execute("UPDATE reward_ledger SET amount=-299 WHERE kind=?", ('payout_hold:'+ident,))
    assert payouts.reconciliation(store)['mismatch_count'] == 1
    with store._db() as db:
        db.execute("UPDATE reward_ledger SET amount=-300 WHERE kind=?", ('payout_hold:'+ident,))
    owner3, rid3 = receipt(3)
    def simultaneous(n):
        try:
            return payouts.request(store, uid=owner3, receipt_id=rid3, request_id='parallel-'+str(n),
                bank='Test', account='123456789012', holder='Test')['id']
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(simultaneous, range(8)))
    assert sum(value is not None for value in attempts) == 1
    assert store.list_for_user(owner3)['balance'] == 0
    assert payouts.reconciliation(store)['records_match']
    print('PASS: settlement totals, corrupt ledger detection, concurrent requests reserve exactly once')
    # Restore all payout states, then verify in a new process, not the live store.
    pending_id = next(value for value in attempts if value)
    payouts.decide(store, pending_id, 'processing', '', '', False, 'test')
    before = payouts.listing(store)
    before_totals = payouts.reconciliation(store)
    try:
        store.backup_archive(Path(raw))
        raise AssertionError('live database backup destination accepted')
    except ValueError as exc:
        assert str(exc) == 'backup_destination_is_live_database'
    backup_dir = Path(raw) / 'backup-output'
    backup_dir.mkdir()
    archive = store.backup_archive(backup_dir)
    target = Path(raw) / 'payout-restored'
    restore = runpy.run_path(str(Path(__file__).with_name('restore-rewards.py')))['restore']
    restore(archive, target)
    probe = '''
import json, sys
from pathlib import Path
from backend.app import rewards, payouts
store = rewards.RewardStore(Path(sys.argv[1]) / 'rewards.sqlite3')
account = payouts.recipient(store, sys.argv[2], 'restore-test')
print(json.dumps({'rows': payouts.listing(store), 'totals': payouts.reconciliation(store),
 'balance': store.list_for_user(sys.argv[3])['balance'],
 'recipient_matches': account == {'bank':'Test','account':'123456789012','holder':'Test'}}))
'''
    restarted = subprocess.run([sys.executable, '-B', '-c', probe, str(target), pending_id, owner3],
        capture_output=True, text=True, check=True)
    recovered = json.loads(restarted.stdout)
    assert recovered['rows'] == before and recovered['totals'] == before_totals
    assert recovered['balance'] == 0 and recovered['recipient_matches']
    restored = rewards.RewardStore(target / 'rewards.sqlite3')
    original_key = os.environ['PAYOUT_ENCRYPTION_KEY']
    os.environ['PAYOUT_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    try:
        payouts.recipient(restored, pending_id, 'wrong-key-test')
        raise AssertionError('wrong encryption key accepted')
    except ValueError as exc:
        assert str(exc) == 'payout_encryption_key_unavailable'
    finally:
        os.environ['PAYOUT_ENCRYPTION_KEY'] = original_key
    assert payouts.listing(restored) == before
    assert payouts.reconciliation(restored)['records_match']
    print('PASS: payout backup, fresh-process restore, recipient decryption, wrong-key refusal without data changes')
    os.environ['REWARD_BANK_PAYOUTS']='off'
    assert client.post('/v1/rewards/payouts',headers=headers2,json=body2).status_code==503
    assert client.get('/v1/rewards/me?uid='+owner,headers=headers).json()['payouts'][0]['status']=='paid'
    print('PASS: 300 KRW, auth, consent, encrypted recipient, hold, idempotency, transfer reference, refund, feature OFF')
