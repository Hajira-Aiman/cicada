"""
tests/test_guard_api.py
Automated Verification for Guard Local API (T15):
- GET /api/status: health, version, buffer depth, retention countdown, policy hash, canaries
- GET /api/raw-logs: raw lines WITH secrets visible; local access only
- GET /api/egress: last 50 payloads with exact JSON, sha256, and status
- GET /api/checkpoint: cryptographic checkpoint {guard_id, up_to_seq, root}
- GET & POST /api/reveal-requests: lifecycle, approve with reveal, reject, and local audit
- GET /api/reveal/{pseudonym}: local reverse lookup
"""

import time
import pytest
from starlette.testclient import TestClient

from guard.config import GuardConfig
from guard.thin_slice import GuardThinSlice
from guard.api.server import create_guard_api_app


@pytest.fixture
def test_guard(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_api.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r_api.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev_api.db")
    cfg.SHOP_LOG_PATH = str(tmp_path / "shop_api.log")
    guard = GuardThinSlice(cfg=cfg)
    return guard


def test_guard_api_status(test_guard):
    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.json()
        assert data["guard_id"] == "guard-acme-01"
        assert data["tenant_id"] == "acme"
        assert data["guard_version"] == "0.2.0"
        assert data["status"] == "active"
        assert "buffer_depth" in data
        assert "retention_countdown_seconds" in data
        assert "policy_version" in data
        assert "canaries_planted" in data
        assert "secrets_redacted" in data


def test_guard_api_raw_logs(test_guard):
    # Store raw log line containing sensitive credentials
    test_guard.raw_store.store_raw_log(
        text="Login attempt: user=admin password=SecretPassword123 from 203.0.113.5",
        source="shop-api",
    )

    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        # 1. Localhost query returns raw line WITH secrets visible
        res = client.get("/api/raw-logs?minutes=60")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        raw_texts = [l["raw_text"] for l in data["logs"]]
        assert any("SecretPassword123" in t for t in raw_texts)
        assert any("203.0.113.5" in t for t in raw_texts)


def test_guard_api_egress(test_guard):
    # Record a payload in ledger
    test_guard.ledger.record_payload(
        seq=1,
        payload_id="p-test-egress-01",
        sha256="sha256:1111222233334444",
        prev_hash="GENESIS",
        body='{"seq": 1, "test": "data"}',
        status="pending",
    )
    test_guard.ledger.mark_receipt(
        payload_id="p-test-egress-01",
        sha256="sha256:1111222233334444",
        status="stored",
        receipt_at="2026-11-20T15:30:00Z",
    )

    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        res = client.get("/api/egress")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        p = data["payloads"][0]
        assert p["seq"] == 1
        assert p["payload_id"] == "p-test-egress-01"
        assert p["sha256"] == "sha256:1111222233334444"
        assert p["status"] == "stored"
        assert p["receipt_at"] == "2026-11-20T15:30:00Z"
        assert p["body"] == {"seq": 1, "test": "data"}


def test_guard_api_checkpoint(test_guard):
    test_guard.ledger.record_payload(
        seq=1,
        payload_id="p-chk-01",
        sha256="sha256:aaaabbbbccccdddd",
        prev_hash="GENESIS",
        body='{"seq": 1}',
        status="stored",
    )

    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        res = client.get("/api/checkpoint")
        assert res.status_code == 200
        data = res.json()
        assert data["guard_id"] == "guard-acme-01"
        assert data["up_to_seq"] == 1
        assert data["root"].startswith("sha256:")


def test_guard_api_reveal_requests_lifecycle_and_approval(test_guard):
    # Generate a pseudonym in local reveal table
    real_ip = "198.51.100.99"
    pseudo_ip = test_guard.pseudonym_mgr.get_or_create("src", real_ip)

    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        # 1. Create reveal request
        create_res = client.post(
            "/api/reveal-requests",
            json={"pseudonym": pseudo_ip, "reason": "Brute force attack on Shop A"},
        )
        assert create_res.status_code == 200
        req_data = create_res.json()
        req_id = req_data["id"]
        assert req_data["status"] == "pending"

        # 2. List reveal requests
        list_res = client.get("/api/reveal-requests?status=pending")
        assert list_res.status_code == 200
        assert any(r["id"] == req_id for r in list_res.json()["requests"])

        # 3. Approve reveal request
        app_res = client.post(
            f"/api/reveal-requests/{req_id}/approve",
            json={"decision_reason": "Approved by security team"},
        )
        assert app_res.status_code == 200
        approved_data = app_res.json()
        assert approved_data["status"] == "approved"
        assert approved_data["revealed_value"] == real_ip

        # 4. Reject another request
        req2 = client.post(
            "/api/reveal-requests",
            json={"pseudonym": pseudo_ip, "reason": "Spam test"},
        ).json()["id"]

        rej_res = client.post(
            f"/api/reveal-requests/{req2}/reject",
            json={"decision_reason": "Denied due to lack of cause"},
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"


def test_guard_api_reveal_direct_lookup(test_guard):
    real_user = "alice_merchant"
    pseudo_user = test_guard.pseudonym_mgr.get_or_create("user", real_user)

    app = create_guard_api_app(guard=test_guard)
    with TestClient(app) as client:
        # Successful lookup
        res = client.get(f"/api/reveal/{pseudo_user}")
        assert res.status_code == 200
        data = res.json()
        assert data["pseudonym"] == pseudo_user
        assert data["prefix"] == "user"
        assert data["real_value"] == real_user

        # Unknown pseudonym returns 404
        bad_res = client.get("/api/reveal/src-99999999")
        assert bad_res.status_code == 404
