"""Offline authentication abuse checks; never sends production requests."""
import base64
import hashlib
import hmac
import json
import os
import tempfile
import time

with tempfile.TemporaryDirectory() as folder:
    os.environ.update(DATA_DIR=folder, ADMIN_TOKEN="security-test-admin",
                      GUEST_SIGNING_SECRET="security-test-secret", RECEIPT_REWARDS="off",
                      KAKAO_REST_API_KEY=" ", GOOGLE_PLACES_PHOTOS="off")
    from fastapi.testclient import TestClient
    from backend.app.main import app
    from backend.app import guest_token, users
    client = TestClient(app)
    owner = client.post("/v1/auth/guest", json={"device_id": "security-owner"}).json()
    attacker = client.post("/v1/auth/guest", json={"device_id": "security-attacker"}).json()
    headers = {"X-Guest-Token": attacker["guest_token"]}
    assert client.get("/v1/me", params={"uid": owner["uid"]}, headers=headers).status_code == 401
    assert client.get("/v1/rewards/me", params={"uid": owner["uid"]}, headers=headers).status_code == 401
    assert client.post("/v1/auth/guest", json={"device_id": "identity-spoof", "firebase_uid": owner["uid"]}).status_code == 400
    assert client.post("/v1/auth/guest", json={"device_id": "fake-linked", "firebase_uid": "kakao_spoof"}).status_code == 400
    assert users.STORE.get("kakao_spoof") is None
    for endpoint in ("/v1/admin/storage", "/v1/admin/rewards", "/v1/admin/payouts", "/v1/analytics/summary"):
        assert client.get(endpoint, params={"token": "security-test-admin"}).status_code == 401
        result = client.get(endpoint, headers={"X-Admin-Token": "security-test-admin"})
        assert result.status_code == 200, endpoint
        assert result.headers["Cache-Control"] == "no-store"
    def signed(payload):
        raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        sig = hmac.new(b"security-test-secret", raw.encode(), hashlib.sha256).hexdigest()
        return raw + "." + sig
    malformed = ["x", "x.y", "é." + "0"*64, "x"*5000+"."+"0"*64,
                 signed([]), signed({"uid": "test", "exp": "invalid"}),
                 signed({"uid": {}, "exp": int(time.time())+100}),
                 signed({"uid": "test", "exp": 0})]
    for token in malformed:
        assert guest_token.verify(token) is None
    assert guest_token.verify(owner["guest_token"])["uid"] == owner["uid"]
    assert client.get("/v1/me", params={"uid": owner["uid"]}, headers={"X-Guest-Token": "invalid.token"}).status_code == 401
    print("PASS: identity spoofing, cross-user access, URL admin credentials, malformed tokens, private cache headers")
