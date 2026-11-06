"""Twenty-claim pilot boundaries, without production requests or payments."""
import os
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from backend.app import rewards
from scripts.receipt_image_fixture import receipt_image

with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
    'RECEIPT_REWARDS_MAX_CLAIMS':'20', 'RECEIPT_REWARDS_MAX_CLAIMS_PER_USER':'1',
    'RECEIPT_REWARDS_END_AT':rewards._iso(rewards._now()+timedelta(days=7))
}):
    store = rewards.RewardStore(Path(folder)/'rewards.sqlite3')
    def submit(n, owner=None):
        uid = owner or f'pilot_{n}'
        att = store.create_attribution(uid=uid,session_id=f'session{n}',place_id='place',
            place_name='test',menu_id='menu',menu_name='test',intent='visit')
        return store.submit_receipt(uid=uid,attribution_id=att['id'],purchased_at=rewards._iso(),
            amount_krw=10000,approval_number=f'PILOT{n:06}',content_type='image/jpeg',
            image=receipt_image(n),review_return='yes',review_tags=[],review_note='',photo_reuse_consent=False)
    def refused(n, reason, owner=None):
        try:
            submit(n,owner)
            raise AssertionError('limit not enforced')
        except ValueError as e:
            assert str(e)==reason, str(e)
    first=submit(0)
    submit(100,'pilot_0')
    submit(101,'pilot_0')
    refused(105,'daily_limit_reached','pilot_0')
    store.decide(first['id'],approve=True,reason='test',admin_id='test')
    refused(106,'daily_limit_reached','pilot_0')
    with patch.dict(os.environ,{'RECEIPT_REWARDS_END_AT':rewards._iso(rewards._now()-timedelta(seconds=1))}):
        refused(102,'pilot_ended')
    with patch.dict(os.environ,{'RECEIPT_REWARDS_END_AT':'invalid'}):
        refused(103,'invalid_pilot_configuration')
    # The deprecated lifetime environment limit must not block the next KST day.
    with patch('backend.app.rewards._now', return_value=rewards._now()+timedelta(days=1)):
        repeat = submit(104, 'pilot_0')
        assert repeat['reward_points'] == 100
    for n in range(1,17): submit(n)
    refused(20,'pilot_capacity_reached')
    summary=store.summary()
    assert summary['committed_points']==2000 and summary['claims_remaining']==0
    assert len(list((Path(folder)/'receipt_uploads').iterdir()))==20
print('PASS: 20 slots / 2000P, three-per-day cap / fourth blocked, next-day repeat participation, deadline, invalid configuration, no rejected upload files')

# Simultaneous submissions cannot race past the three-per-day reservation cap.
from concurrent.futures import ThreadPoolExecutor
with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
    'RECEIPT_REWARDS_MAX_CLAIMS':'20', 'RECEIPT_REWARDS_END_AT':''
}):
    store = rewards.RewardStore(Path(folder)/'rewards.sqlite3')
    def parallel(n):
        try:
            submit(200+n, 'parallel_owner')
            return True
        except ValueError as exc:
            assert str(exc) == 'daily_limit_reached', str(exc)
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        result = list(pool.map(parallel, range(8)))
    assert sum(result) == 3
    assert store.summary()['committed_points'] == 300
    assert len(list((Path(folder)/'receipt_uploads').iterdir())) == 3
print('PASS: eight simultaneous claims reserve exactly three, rejected uploads leave no files')
