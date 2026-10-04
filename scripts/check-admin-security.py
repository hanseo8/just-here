"""Offline RFC vectors, replay persistence, expiry and API access checks."""
import base64
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ.update(DATA_DIR=folder, ADMIN_TOKEN='admin-test', ADMIN_TOTP_SECRET='',
                      ADMIN_REQUIRE_2FA='off', KAKAO_REST_API_KEY=' ', GOOGLE_PLACES_PHOTOS='off')
    from backend.app import admin_security as security
    from backend.app.main import app
    from fastapi.testclient import TestClient
    secret = b'12345678901234567890'
    for timestamp, expected in [(59,'94287082'),(1111111109,'07081804'),
                                (1111111111,'14050471'),(1234567890,'89005924'),
                                (2000000000,'69279037'),(20000000000,'65353130')]:
        assert security.code(secret,timestamp//30,8) == expected
    client = TestClient(app)
    headers = {'X-Admin-Token':'admin-test'}
    assert client.get('/v1/admin/security',headers=headers).status_code == 200
    os.environ['ADMIN_REQUIRE_2FA'] = 'on'
    assert client.get('/v1/admin/security',headers=headers).status_code == 401
    assert client.post('/v1/admin/auth',headers=headers,json={}).status_code == 503
    os.environ['ADMIN_TOTP_SECRET'] = base64.b32encode(secret).decode()
    now = int(time.time())
    otp = security.code(secret,now//30)
    response = client.post('/v1/admin/auth',headers=headers,json={'otp':otp})
    assert response.status_code == 200, response.text
    session = response.json()['session_token']
    assert security.session_valid(session,now=now+601) is False
    authenticated = {**headers,'X-Admin-Session':session}
    assert client.get('/v1/admin/security',headers=authenticated).status_code == 200
    assert client.post('/v1/admin/logout',headers=authenticated).status_code == 200
    assert client.get('/v1/admin/security',headers=authenticated).status_code == 401
    assert client.get('/v1/admin/security').status_code == 401
    security.SESSIONS.clear()
    try:
        security.login(otp,now=now)
        raise AssertionError('replayed OTP accepted after restart')
    except ValueError:
        pass
    security.alert('otp_denied')
    security.alert('not-a-category')
    snapshot = security.snapshot()
    assert snapshot['external_notifications'] is False
    assert any(row['kind']=='otp_denied' for row in snapshot['alerts'])
    assert 'admin-test' not in str(snapshot)
    # Earlier two auth attempts share this test client's limiter.
    client.post('/v1/admin/auth',headers=headers,json={'otp':'000000'})
    client.post('/v1/admin/auth',headers=headers,json={'otp':'000000'})
    client.post('/v1/admin/auth',headers=headers,json={'otp':'000000'})
    limited = client.post('/v1/admin/auth',headers=headers,json={'otp':'000000'})
    assert limited.status_code == 429 and limited.headers['Retry-After'] == '60'
    print('PASS: RFC6238 vectors, optional/fail-closed 2FA, access control, expiry, durable replay protection, private counters')
