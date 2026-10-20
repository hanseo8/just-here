"""MY checks use temporary data only and do not contact payment providers."""
import os
import tempfile

with tempfile.TemporaryDirectory() as directory:
    os.environ.update(DATA_DIR=directory, RECEIPT_REWARDS='off',
                      REWARD_BANK_PAYOUTS='off', GUEST_SIGNING_SECRET='wallet-test-secret',
                      KAKAO_REST_API_KEY=' ', GOOGLE_PLACES_PHOTOS='off')
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import rewards
    client = TestClient(app)
    for route in ['/my', '/rewards']:
        response = client.get(route)
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
        assert 'id="reserved"' in response.text
    user = client.post('/v1/auth/guest', json={'device_id':'wallet-device-test'}).json()
    headers = {'X-Guest-Token':user['guest_token']}
    first = client.get('/v1/rewards/me', params={'uid':user['uid']}, headers=headers)
    assert first.status_code == 200 and first.json()['balance'] == 0
    assert first.json()['reward_config']['enabled'] is False
    assert not (rewards.data_dir()/'rewards.sqlite3').exists()
    rewards.get_store()  # Existing ledger must remain readable when recruitment is OFF.
    response = client.get('/v1/rewards/me', params={'uid':user['uid']}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data['balance'] == data['pending_points'] == 0
    assert data['reward_config']['enabled'] is False
    assert data['payout_config']['enabled'] is False
    assert client.get('/v1/rewards/me', params={'uid':user['uid']}).status_code == 401
    assert client.get('/v1/rewards/me', params={'uid':'other-person'}, headers=headers).status_code in [401,403]
    print('PASS: MY/rewards routes, no-store, existing wallet readable while OFF, auth and other-user isolation')
