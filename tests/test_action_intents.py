"""
tests/test_action_intents.py
Tests for T12 Action intents, approvals, dry run, and audit lifecycle on real PostgreSQL.
"""

import hashlib
import hmac
import json
import pytest
from httpx import ASGITransport, AsyncClient

from hq.api.main import app
from hq.db import init_all_databases, register_guard, truncate_all_data, get_action_audit_logs


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()
    register_guard("guard-acme-01", "acme", "sec-acme-super-secret-key-2026")
    yield
    truncate_all_data()


@pytest.mark.anyio
async def test_action_propose_and_policy_checks():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Successful proposal
        res = await client.post(
            "/api/actions/propose",
            json={
                "tenant_id": "acme",
                "action": "kill_process",
                "target": "proc-7f3a1b2c",
                "risk": "medium",
                "why": "High CPU burst and unauthorized outbound socket",
                "reversible": True,
                "rollback": "systemctl restart shop-api",
            },
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "proposed"
        assert data["action"] == "kill_process"
        assert data["target"] == "proc-7f3a1b2c"
        assert "expires_at" in data
        intent_id = data["intent_id"]

        # Verify audit log
        audit_res = await client.get(f"/api/actions/audit?intent_id={intent_id}")
        assert audit_res.status_code == 200
        logs = audit_res.json()["audit_log"]
        assert any(l["step"] == "proposed" for l in logs)

        # 2. Policy check: disallowed action
        res_bad_action = await client.post(
            "/api/actions/propose",
            json={
                "tenant_id": "acme",
                "action": "delete_database",
                "target": "proc-7f3a1b2c",
                "risk": "low",
            },
        )
        assert res_bad_action.status_code == 400
        assert "not in allowed actions" in res_bad_action.json()["detail"]

        # 3. Policy check: high risk requires manual escalation
        res_high_risk = await client.post(
            "/api/actions/propose",
            json={
                "tenant_id": "acme",
                "action": "kill_process",
                "target": "proc-7f3a1b2c",
                "risk": "high",
            },
        )
        assert res_high_risk.status_code == 400
        assert "exceeds maximum allowed threshold" in res_high_risk.json()["detail"]

        # 4. Policy check: maximum 3 per 10 minutes
        # We already proposed 1. Propose 2 more successfully:
        p2 = await client.post("/api/actions/propose", json={"tenant_id": "acme", "action": "block_source", "target": "src-001", "risk": "low"})
        assert p2.status_code == 200
        p3 = await client.post("/api/actions/propose", json={"tenant_id": "acme", "action": "restart_service", "target": "srv-001", "risk": "medium"})
        assert p3.status_code == 200

        # 4th proposal should be rate-limited
        p4 = await client.post("/api/actions/propose", json={"tenant_id": "acme", "action": "investigate", "target": "proc-002", "risk": "low"})
        assert p4.status_code == 429
        assert "maximum 3 action proposals per 10 minutes exceeded" in p4.json()["detail"]


@pytest.mark.anyio
async def test_action_dry_run_and_approval_workflow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Propose an intent
        prop_res = await client.post(
            "/api/actions/propose",
            json={
                "tenant_id": "acme",
                "action": "block_source",
                "target": "src-9c2e0011",
                "risk": "low",
                "why": "Credential brute-force burst",
            },
        )
        intent_id = prop_res.json()["intent_id"]

        # Try to approve before dry run -> MUST FAIL
        appr_early = await client.post(
            f"/api/actions/{intent_id}/approve",
            json={"approved_by": "Alice Engineer"},
        )
        assert appr_early.status_code == 400
        assert "must undergo dry run before approval" in appr_early.json()["detail"]

        # Execute dry run
        dry_res = await client.post(f"/api/actions/{intent_id}/dry-run")
        assert dry_res.status_code == 200
        dry_data = dry_res.json()
        assert dry_data["status"] == "dry_run_done"
        assert dry_data["simulation"]["would_succeed"] is True

        # Try approving without approved_by name -> MUST FAIL
        appr_noname = await client.post(
            f"/api/actions/{intent_id}/approve",
            json={"approved_by": ""},
        )
        assert appr_noname.status_code == 400

        # Approve with valid person name
        appr_res = await client.post(
            f"/api/actions/{intent_id}/approve",
            json={"approved_by": "Alice Engineer"},
        )
        assert appr_res.status_code == 200
        appr_data = appr_res.json()
        assert appr_data["status"] == "approved"
        assert appr_data["approved_by"] == "Alice Engineer"


@pytest.mark.anyio
async def test_guard_pull_signed_intent_and_result_rollback():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Propose, dry run, and approve
        prop = await client.post(
            "/api/actions/propose",
            json={
                "tenant_id": "acme",
                "action": "kill_process",
                "target": "proc-999",
                "risk": "medium",
            },
        )
        intent_id = prop.json()["intent_id"]
        await client.post(f"/api/actions/{intent_id}/dry-run")
        await client.post(f"/api/actions/{intent_id}/approve", json={"approved_by": "Bob SRE"})

        # Guard pulls pending signed intents
        pull_res = await client.get("/api/actions/pending?guard_id=guard-acme-01")
        assert pull_res.status_code == 200
        intents = pull_res.json()["intents"]
        assert len(intents) >= 1
        target_intent = [i for i in intents if i["intent_id"] == intent_id][0]

        # Verify signature
        secret = "sec-acme-super-secret-key-2026"
        body_to_verify = json.dumps(
            {
                "intent_id": target_intent["intent_id"],
                "tenant_id": target_intent["tenant_id"],
                "action": target_intent["action"],
                "target": target_intent["target"],
                "created_at": str(target_intent["created_at"]),
            },
            sort_keys=True,
        ).encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), body_to_verify, hashlib.sha256).hexdigest()
        assert target_intent["signature"] == expected_sig

        # Case A: Guard reports execution with health_improved=False -> triggers automated rollback
        res_fail = await client.post(
            f"/api/actions/{intent_id}/result",
            json={
                "guard_id": "guard-acme-01",
                "status": "done",
                "health_improved": False,
                "elapsed_seconds": 130,
            },
        )
        assert res_fail.status_code == 200
        assert res_fail.json()["status"] == "rolled_back"
        assert "120s" in res_fail.json()["rollback_reason"]

        # Verify full audit chain exists
        audit_res = await client.get(f"/api/actions/audit?intent_id={intent_id}")
        steps = [l["step"] for l in audit_res.json()["audit_log"]]
        assert "proposed" in steps
        assert "dry_run_done" in steps
        assert "approved" in steps
        assert "pulled_by_guard" in steps
        assert "rolled_back" in steps
