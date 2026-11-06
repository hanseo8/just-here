"""Isolated beta budget/progress checks. No production or bank requests."""
import tempfile
import os
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from backend.app import rewards, payouts, beta_campaign as beta
from cryptography.fernet import Fernet
from scripts.receipt_image_fixture import receipt_image

with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ,{'RECEIPT_REWARDS_END_AT':'2026-01-01T00:00:00Z','RECEIPT_REWARDS_MAX_CLAIMS':'0','PAYOUT_ENCRYPTION_KEY':Fernet.generate_key().decode()}):
    store = rewards.RewardStore(Path(raw)/'rewards.sqlite3')
    def select(uid):
        return beta.enroll(store,uid,'test')
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda n:select('kakao_one'),range(8)))
    assert all(r['reserved_max_krw']==17600 for r in rows)
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM beta_members').fetchone()[0]==1
    beta.survey(store,'kakao_one','위치 확인과 추천을 직접 테스트했습니다.')
    assert not beta.progress(store,'kakao_one')['bonus_eligible']
    def submit(n):
        a = store.create_attribution(uid='kakao_one',session_id='beta'+str(n),place_id='p',place_name='Test',menu_id='m',menu_name='Test',intent='visit')
        return store.submit_receipt(uid='kakao_one',attribution_id=a['id'],purchased_at=rewards._iso(),amount_krw=12000,approval_number='betaapproval'+str(n),content_type='image/jpeg',image=receipt_image(n),review_return='no',review_tags=[],review_note='불편한 점이 있어요',photo_reuse_consent=False)
    for n in range(3):
        r=submit(n)
        assert r['reward_points']==300
        store.decide(r['id'],approve=True,reason='valid receipt',admin_id='test')
    p=beta.progress(store,'kakao_one')
    assert not p['bonus_eligible'] and p['bonus_payout_available']
    assert store.list_for_user('kakao_one')['balance']==900
    beta.survey(store,'kakao_one','같은 설문을 다시 제출해도 중복 지급되지 않아요.')
    assert store.list_for_user('kakao_one')['balance']==900
    try:submit(4);raise AssertionError('fourth accepted')
    except ValueError as e:assert str(e)=='daily_limit_reached'
    base=rewards._now()
    for day in range(1,14):
        with patch('backend.app.rewards._now',return_value=base+timedelta(days=day)):
            for offset in range(3):
                receipt=submit(10+day*3+offset)
                store.decide(receipt['id'],approve=True,reason='valid receipt',admin_id='test')
    assert store.list_for_user('kakao_one')['balance']==12600
    with patch('backend.app.rewards._now',return_value=base+timedelta(days=14)):
        assert beta.progress(store,'kakao_one')['bonus_eligible']
        def bonus(n):
            try:return beta.request_bonus(store,'kakao_one','request-'+str(n),'Test','123456789012','Test')
            except ValueError as e:
                assert str(e)=='payout_already_requested';return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            requests=list(pool.map(bonus,range(8)))
        issued=next(r for r in requests if r)
        assert len([r for r in requests if r])==1 and issued['amount_krw']==5000
        assert store.list_for_user('kakao_one')['balance']==12600
        payouts.decide(store,issued['id'],'rejected','','no transfer',True,'test')
        assert store.list_for_user('kakao_one')['balance']==17600
        retried=bonus(10)
        assert store.list_for_user('kakao_one')['balance']==12600
        assert beta.request_bonus(store,'kakao_one','request-10','Test','123456789012','Test')['id']==retried['id']
        payouts.decide(store,retried['id'],'processing','','',False,'test')
        assert payouts.recipient(store,retried['id'],'test')['account']=='123456789012'
        payouts.decide(store,retried['id'],'paid','TEST-ONLY-BANK-REF','',False,'test')
        assert payouts.reconciliation(store)['records_match']
        assert beta.progress(rewards.RewardStore(store.path),'kakao_one')['bonus_krw']==5000
    with patch('backend.app.rewards._now',return_value=base+timedelta(days=15)):
        try:submit(5);raise AssertionError('late accepted')
        except ValueError as e:assert str(e)=='beta_outside_period'
    for n in range(14):select('kakao_member'+str(n))
    try:select('kakao_16');raise AssertionError('over budget')
    except ValueError as e:assert str(e)=='beta_capacity_reached'
    assert beta.progress(rewards.RewardStore(store.path),'kakao_one')['approved_receipts']==42
    with store._db() as db:
        assert db.execute('SELECT COUNT(*) FROM beta_members').fetchone()[0]*17600==264000
print('PASS: 15 seats / 264000 KRW reservation, concurrent enrollment, 14 days, 42 receipts, 300P, survey, 5000 bonus encrypted payout / refund / concurrency, restart')
