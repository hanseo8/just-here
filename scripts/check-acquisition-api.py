"""Local-only API fixture; credentials and all records exist only in a temporary directory."""
import os
import tempfile

with tempfile.TemporaryDirectory() as raw:
    os.environ.update(DATA_DIR=raw, ADMIN_TOKEN="local-acquisition-fixture", ADMIN_REQUIRE_2FA="off",
                      ADMIN_TOTP_SECRET="", KAKAO_REST_API_KEY=" ", GOOGLE_PLACES_PHOTOS="off")
    from fastapi.testclient import TestClient
    from backend.app.main import app
    client = TestClient(app)
    headers = {"X-Admin-Token": "local-acquisition-fixture"}
    r = client.get("/v1/analytics/summary")
    assert r.status_code == 401 and "no-store" in r.headers["cache-control"]
    for event in ("app_open", "recommend_shown", "recommend_shown", "match_done", "handoff_open", "handoff_open"):
        r = client.post("/v1/analytics/event", json={"event": event, "props": {"visit_id": "visit-api-fixture-0001", "utm_source": "threads", "utm_content": "hook"}})
        assert r.status_code == 200
    r = client.post("/v1/analytics/event", json={"event": "app_open", "props": {"visit_id": "visit-test-fixture-01", "traffic_type": "test"}})
    assert r.status_code == 200
    r = client.get("/v1/analytics/summary?days=1", headers=headers)
    assert r.status_code == 200 and "no-store" in r.headers["cache-control"]
    data = r.json()
    assert data["totals"]["app_open"] == 1
    funnel = data["acquisition"]
    assert [funnel[k] for k in ("visits", "recommended", "chosen", "handoff")] == [1, 1, 1, 1]
    assert funnel["by_campaign"][0]["utm_content"] == "hook"
    assert "visit-api-fixture" not in r.text
    assert client.get("/v1/analytics/summary?token=local-acquisition-fixture").status_code == 401
print("PASS acquisition API: private admin/no-store, public event collection, same-visit deduplication, campaign labels and test exclusion; no production data")
