"""
tests/test_checkpoints_reveal_chaos.py
Verification of T9, T10, T11:
1. Receipt-log checkpoints (T9): running SHA-256 root, compare endpoint, first differing seq on mismatch
2. Reveal-request API (T10): POST /reveal-requests, decision logging, audit rows on both sides
3. Chaos agent (T11): 10 scenario endpoints matching simulate_timeline.py
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport

from chaos.agent import app as chaos_app
from hq.api.main import app as hq_api_app
from hq.db import (
    execute_query,
    init_all_databases,
    register_guard,
    store_payload,
    truncate_all_data,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()


@pytest.mark.anyio
async def test_receipt_log_checkpoint_compare_and_mismatch():
    """T9: Running SHA-256 root over payload hashes; compare endpoint identifies first differing seq."""
    guard_id = f"guard-chk-{uuid.uuid4().hex[:6]}"
    tenant_id = "acme"
    register_guard(guard_id, tenant_id, "sec-chk-secret")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Ingest 3 payloads into airlock_in
    hashes = []
    prev_h = "GENESIS"
    for s in (1, 2, 3):
        pid = f"pay-chk-{s}-{uuid.uuid4().hex[:6]}"
        payload = {
            "schema": "airlock.v1",
            "payload_id": pid,
            "tenant_id": tenant_id,
            "guard_id": guard_id,
            "seq": s,
            "prev_hash": prev_h,
            "policy_version": "sha256:v1-default-policy",
            "sent_at": now_iso,
            "window": {"start": now_iso, "end": now_iso, "source_tz": "UTC"},
            "metrics": [{"name": "cpu_pct", "source": "host-7f3a1234", "avg": 20.0, "max": 30.0}],
            "events": [],
            "log_patterns": [],
            "health": {"guard_version": "0.2.0", "guard_cpu_pct": 1.0, "guard_mem_mb": 40.0, "buffer_depth": 0, "config_ok": True, "canaries_planted": 0, "secrets_redacted": 0},
        }
        sha = "sha256:" + hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()
        store_payload("airlock_in", payload, sha)
        hashes.append(sha)
        prev_h = sha

    # Compute expected running root:
    # running = sha256(h1); running = sha256(running + h2); running = sha256(running + h3)
    running = ""
    for h in hashes:
        running = hashlib.sha256((running + h).encode("utf-8")).hexdigest()
    expected_root = f"sha256:{running}"

    async with AsyncClient(transport=ASGITransport(app=hq_api_app), base_url="http://hq-api") as client:
        # Login
        login_res = await client.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Fetch HQ checkpoint
        chk_res = await client.get(f"/api/checkpoints/{guard_id}", headers=headers)
        assert chk_res.status_code == 200
        chk_data = chk_res.json()
        assert chk_data["up_to_seq"] == 3
        assert chk_data["root"] == expected_root

        # 2. Compare when guard matches
        cmp_ok = await client.post(
            "/api/checkpoints/compare",
            json={"guard_id": guard_id, "up_to_seq": 3, "root": expected_root, "hashes": hashes},
            headers=headers,
        )
        assert cmp_ok.status_code == 200
        res_ok = cmp_ok.json()
        assert res_ok["match"] is True
        assert res_ok["status"] == "verified"
        assert res_ok["first_differing_seq"] is None

        # 3. Compare when guard tampered seq 2
        tampered_hashes = list(hashes)
        tampered_hashes[1] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
        t_running = ""
        for h in tampered_hashes:
            t_running = hashlib.sha256((t_running + h).encode("utf-8")).hexdigest()
        tampered_root = f"sha256:{t_running}"

        cmp_bad = await client.post(
            "/api/checkpoints/compare",
            json={"guard_id": guard_id, "up_to_seq": 3, "root": tampered_root, "hashes": tampered_hashes},
            headers=headers,
        )
        assert cmp_bad.status_code == 200
        res_bad = cmp_bad.json()
        assert res_bad["match"] is False
        assert res_bad["status"] == "mismatch"
        assert res_bad["first_differing_seq"] == 2


@pytest.mark.anyio
async def test_reveal_request_lifecycle_and_audit():
    """T10: POST /reveal-requests, decision logging, audit rows, no secret leakage."""
    async with AsyncClient(transport=ASGITransport(app=hq_api_app), base_url="http://hq-api") as client:
        # Login as customer
        login_res = await client.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create reveal request
        req_body = {
            "pseudonym": "user-7f3a1234",
            "reason": "Investigating high volume SSH brute force attempts from Shop A",
            "tenant_id": "acme",
        }
        r_create = await client.post("/api/reveal-requests", json=req_body, headers=headers)
        assert r_create.status_code == 200
        data = r_create.json()
        assert data["pseudonym"] == "user-7f3a1234"
        assert data["status"] == "pending"
        req_id = data["request_id"]

        # 2. Check pending list
        r_list = await client.get("/api/reveal-requests?status=pending", headers=headers)
        assert r_list.status_code == 200
        pending = r_list.json()["reveal_requests"]
        assert any(r["request_id"] == req_id for r in pending)

        # 3. Guard / Shop owner decides
        dec_body = {"status": "approved", "decision_reason": "Authorized by security lead for incident analysis"}
        r_dec = await client.post(f"/api/reveal-requests/{req_id}/decision", json=dec_body, headers=headers)
        assert r_dec.status_code == 200
        dec_data = r_dec.json()
        assert dec_data["status"] == "approved"
        # Crucial security guarantee: real secret/raw credential is NOT in response
        assert "password" not in dec_data
        assert "secret" not in dec_data

        # 4. Verify audit log has rows
        audits = execute_query(
            "airlock_core",
            "SELECT action, actor, details FROM audit_log WHERE details::text LIKE %s;",
            (f"%{req_id}%",),
        )
        actions = [a["action"] for a in audits]
        assert "reveal_requested" in actions
        assert "reveal_approved" in actions


@pytest.mark.anyio
async def test_chaos_agent_endpoints():
    """T11: Chaos agent on port 9100 with endpoints matching simulate_timeline.py."""
    async with AsyncClient(transport=ASGITransport(app=chaos_app), base_url="http://chaos") as client:
        # Health check
        h_res = await client.get("/health")
        assert h_res.status_code == 200
        assert h_res.json()["service"] == "chaos-agent"
        assert h_res.json()["port"] == 9100

        # Scenarios list
        scns_res = await client.get("/scenarios")
        assert scns_res.status_code == 200
        all_scns = scns_res.json()["scenarios"]
        expected = [
            "cpu_spike",
            "latency",
            "brute_force",
            "leak",
            "region_outage",
            "replay_shuffle",
            "tamper",
            "kill_chain",
            "backup_job",
            "restart_app",
        ]
        for s in expected:
            assert s in all_scns

        # Trigger each scenario endpoint
        for s in expected:
            trig_res = await client.post(f"/scenarios/{s}", json={"duration_s": 10, "target": "test-host"})
            assert trig_res.status_code == 200
            d = trig_res.json()
            assert d["name"] == s
            assert d["status"] == "active"

        # Check active scenarios
        act_res = await client.get("/chaos/active")
        assert act_res.status_code == 200
        assert len(act_res.json()["active"]) >= 10

        # Reset
        rst_res = await client.post("/chaos/reset")
        assert rst_res.status_code == 200
        act_res2 = await client.get("/chaos/active")
        assert len(act_res2.json()["active"]) == 0
