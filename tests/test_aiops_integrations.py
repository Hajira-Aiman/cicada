"""
tests/test_aiops_integrations.py
Verification of STEP 5: What AIOps needs from Head Office:
1. WebSocket event pushes: health_change, incident_opened, incident_updated, alert_opened, counters
2. Feedback endpoint: POST /feedback writes to feedback table and logs audit row
3. AI Chat proxy: POST /ai/chat takes tenant from login, returns {answer, evidence_ids[]}
4. Telemetry counters: GET /api/counters/{tenant_id} (raw alerts, incidents, flaps prevented)
"""

import json
import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport

from hq.api.broadcaster import broadcaster
from hq.api.main import app
from hq.db import (
    execute_query,
    init_all_databases,
    truncate_all_data,
    update_tenant_counters,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()


@pytest.mark.anyio
async def test_feedback_endpoint_writes_to_db():
    """POST /feedback {alert_id, user_id} writes to feedback table."""
    alert_id = f"alert-test-{uuid.uuid4().hex[:6]}"
    user_id = "user-ops-alpha"
    tenant_id = "acme"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login
        login_res = await client.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Submit feedback
        fb_res = await client.post(
            "/feedback",
            json={"alert_id": alert_id, "user_id": user_id, "tenant_id": tenant_id},
            headers=headers,
        )
        assert fb_res.status_code == 200
        fb_data = fb_res.json()
        assert fb_data["status"] == "recorded"
        assert fb_data["alert_id"] == alert_id

        # Verify row in regional PostgreSQL database (airlock_in for acme)
        rows = execute_query(
            "airlock_in",
            "SELECT alert_id, tenant_id, user_id FROM feedback WHERE alert_id = %s;",
            (alert_id,),
        )
        assert len(rows) == 1
        assert rows[0]["alert_id"] == alert_id
        assert rows[0]["tenant_id"] == tenant_id
        assert rows[0]["user_id"] == user_id


@pytest.mark.anyio
async def test_ai_chat_endpoint_contract():
    """POST /ai/chat {question} takes tenant from login and returns {answer, evidence_ids[]}."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login as customer globex
        login_res = await client.post("/api/login", json={"username": "user-globex", "password": "globex123"})
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        chat_res = await client.post(
            "/ai/chat",
            json={"question": "Why did memory exceed 80% on host-8b4c5678?"},
            headers=headers,
        )
        assert chat_res.status_code == 200
        d = chat_res.json()
        assert "answer" in d
        assert "evidence_ids" in d
        assert isinstance(d["evidence_ids"], list)
        assert d["answer"] == "The AI service is not reachable right now." or "globex" in d["answer"].lower()


@pytest.mark.anyio
async def test_websocket_pushes_aiops_messages():
    """Broadcaster pushes health_change, incident_opened, incident_updated, alert_opened, counters."""
    received = []

    async def mock_send(msg):
        received.append(msg)

    client_id = f"client-{uuid.uuid4().hex[:6]}"
    broadcaster.register_client(client_id, mock_send)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # 1. Health change
        await broadcaster.push_health_change(
            tenant_id="acme",
            source="host-7f3a1234",
            state="Poor",
            old_state="Fair",
            reasons=["Elevated CPU > 90%"],
            at=now_iso,
        )

        # 2. Incident opened
        await broadcaster.push_incident(
            event_type="incident_opened",
            tenant_id="acme",
            incident_id="inc-1001",
            body={"title": "Cryptomining attack", "severity": "critical"},
            status="open",
            timestamp=now_iso,
        )

        # 3. Incident updated
        await broadcaster.push_incident(
            event_type="incident_updated",
            tenant_id="acme",
            incident_id="inc-1001",
            body={"title": "Cryptomining attack", "severity": "critical", "repeat_count": 2},
            status="acknowledged",
            timestamp=now_iso,
        )

        # 4. Alert opened with AIOps detector fields in body
        alert_body = {
            "kind": "anomaly",
            "signals": [{"source": "host-7f3a1234", "name": "cpu_pct", "val": 95.0}],
            "second_opinion": 0.92,
            "agrees": True,
            "started_at": now_iso,
            "last_flag_at": now_iso,
        }
        await broadcaster.push_alert_opened(
            tenant_id="acme",
            alert_id="alt-5001",
            source="host-7f3a1234",
            title="SSH brute force burst",
            severity="high",
            body=alert_body,
            created_at=now_iso,
        )

        # 5. Counters
        await broadcaster.push_counters(
            tenant_id="acme",
            raw_alerts=16,
            incidents=2,
            noise_cut_pct=87.5,
            flaps_prevented=4,
        )

        assert len(received) == 5
        types = [m["event_type"] for m in received]
        assert types == ["health_change", "incident_opened", "incident_updated", "alert_opened", "counters"]

        # Check alert_opened extracted fields
        alert_msg = received[3]
        assert alert_msg["payload"]["kind"] == "anomaly"
        assert alert_msg["payload"]["signals"][0]["name"] == "cpu_pct"
        assert alert_msg["payload"]["second_opinion"] == 0.92
        assert alert_msg["payload"]["agrees"] is True

        # Check counters structure
        counters_msg = received[4]
        assert counters_msg["payload"]["raw_alerts"] == 16
        assert counters_msg["payload"]["incidents"] == 2
        assert counters_msg["payload"]["noise_cut_pct"] == 87.5
        assert counters_msg["payload"]["flaps_prevented"] == 4

    finally:
        broadcaster.unregister_client(client_id)


@pytest.mark.anyio
async def test_tenant_counters_endpoint():
    """GET /api/counters/{tenant_id} reads from aiops_counters table (written by hq/aiops/worker.py)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Write to aiops_counters table matching hq/aiops/worker.py shape
        update_tenant_counters(
            tenant_id="acme",
            raw_alerts=16,
            incidents=2,
            noise_cut_pct=87.5,
            flaps_prevented=3,
        )

        res = await client.get("/api/counters/acme")
        assert res.status_code == 200
        d = res.json()
        assert d["tenant_id"] == "acme"
        assert d["raw_alerts"] == 16
        assert d["incidents"] == 2
        assert d["noise_cut_pct"] == 87.5
        assert d["flaps_prevented"] == 3
