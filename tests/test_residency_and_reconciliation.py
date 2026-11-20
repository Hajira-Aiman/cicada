"""
tests/test_residency_and_reconciliation.py
Verification of T6, T7, T8:
1. Data residency enforcement: Acme and Contoso only in airlock_in, Globex only in airlock_eu
2. Region pause switch: 503 on paused region, no failover forwarding
3. Out-of-order & late window storage: ordered by window.start, not arrival
4. Replayed and shuffled stream: sent (max seq), received, duplicates, gaps, last_seen
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport

from hq.api.main import app
from hq.db import (
    execute_query,
    init_all_databases,
    register_guard,
    set_region_paused,
    truncate_all_data,
)
from hq.ingest.main import create_ingest_app


@pytest.fixture(autouse=True)
def ensure_db_clean():
    init_all_databases()
    truncate_all_data()
    set_region_paused("in", False)
    set_region_paused("eu", False)


def create_signed_payload(guard_id: str, secret: str, tenant_id: str, seq: int, prev_hash: str, window_start: str, payload_id: str = None):
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pid = payload_id or f"pay-{tenant_id}-{uuid.uuid4().hex[:8]}"
    payload = {
        "schema": "airlock.v1",
        "payload_id": pid,
        "tenant_id": tenant_id,
        "guard_id": guard_id,
        "seq": seq,
        "prev_hash": prev_hash,
        "policy_version": "sha256:v1-default-policy",
        "sent_at": now_iso,
        "window": {
            "start": window_start,
            "end": window_start,
            "source_tz": "UTC"
        },
        "metrics": [
            {"name": "cpu_pct", "source": "host-7f3a1234", "avg": 25.0, "max": 40.0}
        ],
        "events": [],
        "log_patterns": [],
        "health": {
            "guard_version": "0.2.0",
            "guard_cpu_pct": 1.0,
            "guard_mem_mb": 45.0,
            "buffer_depth": 0,
            "config_ok": True,
            "canaries_planted": 0,
            "secrets_redacted": 0,
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    headers = {
        "X-Airlock-Guard-ID": guard_id,
        "X-Airlock-Signature": sig,
        "X-Airlock-Timestamp": now_iso,
        "Content-Type": "application/json",
    }
    return raw_body, headers, payload


@pytest.mark.anyio
async def test_data_residency_enforcement():
    """T6: Acme & Contoso data only in airlock_in, Globex only in airlock_eu."""
    app_in = create_ingest_app(region="in")
    app_eu = create_ingest_app(region="eu")

    # Acme guard (assigned to 'in')
    register_guard("guard-acme-res", "acme", "sec-acme-key")
    # Globex guard (assigned to 'eu')
    register_guard("guard-globex-res", "globex", "sec-globex-key")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with AsyncClient(transport=ASGITransport(app=app_in), base_url="http://ingest-in") as client_in, \
               AsyncClient(transport=ASGITransport(app=app_eu), base_url="http://ingest-eu") as client_eu:

        # 1. Acme to IN -> Success 200
        body, headers, _ = create_signed_payload("guard-acme-res", "sec-acme-key", "acme", 1, "GENESIS", now_iso)
        res_acme_in = await client_in.post("/ingest", content=body, headers=headers)
        assert res_acme_in.status_code == 200
        assert res_acme_in.json()["status"] == "stored"

        # 2. Acme to EU -> 403 Forbidden (Residency violation)
        body_acme_eu, headers_acme_eu, _ = create_signed_payload("guard-acme-res", "sec-acme-key", "acme", 2, res_acme_in.json()["sha256"], now_iso)
        res_acme_eu = await client_eu.post("/ingest", content=body_acme_eu, headers=headers_acme_eu)
        assert res_acme_eu.status_code == 403
        assert "Data residency violation" in res_acme_eu.json()["error"]

        # 3. Globex to EU -> Success 200
        body_globex_eu, headers_globex_eu, _ = create_signed_payload("guard-globex-res", "sec-globex-key", "globex", 1, "GENESIS", now_iso)
        res_globex_eu = await client_eu.post("/ingest", content=body_globex_eu, headers=headers_globex_eu)
        assert res_globex_eu.status_code == 200

        # 4. Globex to IN -> 403 Forbidden (Residency violation)
        body_globex_in, headers_globex_in, _ = create_signed_payload("guard-globex-res", "sec-globex-key", "globex", 2, res_globex_eu.json()["sha256"], now_iso)
        res_globex_in = await client_in.post("/ingest", content=body_globex_in, headers=headers_globex_in)
        assert res_globex_in.status_code == 403
        assert "Data residency violation" in res_globex_in.json()["error"]


@pytest.mark.anyio
async def test_region_pause_switch_and_no_failover():
    """T6: Region pause returns 503 and never forwards."""
    app_in = create_ingest_app(region="in")
    app_eu = create_ingest_app(region="eu")

    register_guard("guard-acme-pause", "acme", "sec-pause-key")
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://hq-api") as client_api, \
               AsyncClient(transport=ASGITransport(app=app_in), base_url="http://ingest-in") as client_in, \
               AsyncClient(transport=ASGITransport(app=app_eu), base_url="http://ingest-eu") as client_eu:

        # Login as engineer
        login_res = await client_api.post("/api/login", json={"username": "admin", "password": "admin123"})
        token = login_res.json()["token"]
        headers_api = {"Authorization": f"Bearer {token}"}

        # 1. Pause region 'in'
        pause_res = await client_api.post("/api/regions/in/pause", headers=headers_api)
        assert pause_res.status_code == 200
        assert pause_res.json()["is_paused"] is True

        # Check status
        st_res = await client_api.get("/api/regions/in/status")
        assert st_res.json()["is_paused"] is True

        # 2. Try to ingest to region 'in' -> 503 Service Unavailable
        body, headers, _ = create_signed_payload("guard-acme-pause", "sec-pause-key", "acme", 1, "GENESIS", now_iso)
        ingest_res = await client_in.post("/ingest", content=body, headers=headers)
        assert ingest_res.status_code == 503
        assert "paused" in ingest_res.json()["error"]

        # 3. Unpause region 'in'
        unpause_res = await client_api.post("/api/regions/in/unpause", headers=headers_api)
        assert unpause_res.status_code == 200
        assert unpause_res.json()["is_paused"] is False

        # Ingestion succeeds after unpause
        ingest_res2 = await client_in.post("/ingest", content=body, headers=headers)
        assert ingest_res2.status_code == 200
        assert ingest_res2.json()["status"] == "stored"


@pytest.mark.anyio
async def test_replayed_and_shuffled_stream_reconciliation():
    """T7, T8: Out of order late windows, replayed duplicates, reconciliation stats."""
    app_in = create_ingest_app(region="in")
    guard_id = f"guard-reconcile-{uuid.uuid4().hex[:6]}"
    secret = "sec-reconcile-secret"
    register_guard(guard_id, "acme", secret)

    base_time = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = (base_time).strftime("%Y-%m-%dT%H:%M:%SZ")
    t2 = (base_time + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t3 = (base_time + timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Generate 3 payloads in advance with chained prev_hashes
    pid1 = f"pay-seq1-{uuid.uuid4().hex[:6]}"
    pid2 = f"pay-seq2-{uuid.uuid4().hex[:6]}"
    pid3 = f"pay-seq3-{uuid.uuid4().hex[:6]}"

    body1, h1, _ = create_signed_payload(guard_id, secret, "acme", 1, "GENESIS", t1, payload_id=pid1)
    sha1 = "sha256:" + hashlib.sha256(body1).hexdigest()

    body2, h2, _ = create_signed_payload(guard_id, secret, "acme", 2, sha1, t2, payload_id=pid2)
    sha2 = "sha256:" + hashlib.sha256(body2).hexdigest()

    body3, h3, _ = create_signed_payload(guard_id, secret, "acme", 3, sha2, t3, payload_id=pid3)

    async with AsyncClient(transport=ASGITransport(app=app_in), base_url="http://ingest-in") as client_in, \
               AsyncClient(transport=ASGITransport(app=app), base_url="http://hq-api") as client_api:

        # Login to API
        login_res = await client_api.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        headers_api = {"Authorization": f"Bearer {login_res.json()['token']}"}

        # Step A: Send seq 1
        r1 = await client_in.post("/ingest", content=body1, headers=h1)
        assert r1.status_code == 200
        assert r1.json()["status"] == "stored"

        # Step B: Send seq 3 (shuffled / out-of-order, seq 2 buffered)
        r3 = await client_in.post("/ingest", content=body3, headers=h3)
        assert r3.status_code == 200
        assert r3.json()["status"] == "stored"

        # Check reconciliation: gaps should contain [2]
        recon_mid = await client_api.get(f"/api/reconciliation/{guard_id}", headers=headers_api)
        assert recon_mid.status_code == 200
        d_mid = recon_mid.json()
        assert d_mid["sent_count"] == 3
        assert d_mid["received_count"] == 2
        assert d_mid["duplicate_count"] == 0
        assert d_mid["gaps"] == [2]

        # Step C: Send seq 2 (late arrival, fills gap)
        r2 = await client_in.post("/ingest", content=body2, headers=h2)
        assert r2.status_code == 200
        assert r2.json()["status"] == "stored"

        # Check reconciliation: gaps should be empty now
        recon_filled = await client_api.get(f"/api/reconciliation/{guard_id}", headers=headers_api)
        d_filled = recon_filled.json()
        assert d_filled["sent_count"] == 3
        assert d_filled["received_count"] == 3
        assert d_filled["gaps"] == []

        # Step D: Replay seq 2 (duplicate)
        r2_dup = await client_in.post("/ingest", content=body2, headers=h2)
        assert r2_dup.status_code == 200
        assert r2_dup.json()["status"] == "duplicate"

        # Step E: Replay seq 1 (duplicate)
        r1_dup = await client_in.post("/ingest", content=body1, headers=h1)
        assert r1_dup.status_code == 200
        assert r1_dup.json()["status"] == "duplicate"

        # Final reconciliation check
        recon_final = await client_api.get(f"/api/reconciliation/{guard_id}", headers=headers_api)
        d_final = recon_final.json()
        assert d_final["sent_count"] == 3
        assert d_final["received_count"] == 3
        assert d_final["duplicate_count"] == 2
        assert d_final["gaps"] == []

        # Verify ordering by window.start (event time):
        # Query metrics via API and check order
        m_res = await client_api.get("/api/metrics", headers=headers_api)
        assert m_res.status_code == 200
        metrics = m_res.json()["metrics"]
        # Find metrics matching this guard's payloads
        matching_m = [m for m in metrics if m["payload_id"] in (pid1, pid2, pid3)]
        assert len(matching_m) == 3
        # Should be ordered DESC by event_time: t3, then t2, then t1
        assert matching_m[0]["payload_id"] == pid3
        assert matching_m[1]["payload_id"] == pid2
        assert matching_m[2]["payload_id"] == pid1
