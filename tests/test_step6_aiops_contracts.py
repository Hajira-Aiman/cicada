"""
tests/test_step6_aiops_contracts.py
Comprehensive tests for Step 6 items:
1. Broadcaster throttling of incident_updated (only send on change or >= 10s).
2. Thumbs-down feedback storing metric and source (and extracting from aiops_alerts.body.signals).
3. Tenant baselines API (GET /api/baselines/{tenant_id}).
4. AI Chat proxy with timeout and readable fallback.
"""

import asyncio
import json
import pytest
from fastapi.testclient import TestClient

from hq.api.main import app
from hq.api.broadcaster import broadcaster
from hq.db import (
    execute_query,
    get_tenant_baselines,
    is_postgres_available,
    record_aiops_alert,
    record_feedback,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_broadcaster_throttles_incident_updated():
    """Verify incident_updated is suppressed when attributes haven't changed within 10s."""
    async def _run_test():
        received = []

        async def mock_send(msg):
            received.append(msg)

        client_id = "test-throttle-client"
        broadcaster.register_client(client_id, mock_send)

        try:
            now_iso = "2026-11-21T04:20:00Z"
            incident_id = "inc-throttle-test"

            # 1. First event: incident_opened -> should broadcast
            await broadcaster.push_incident(
                event_type="incident_opened",
                tenant_id="acme",
                incident_id=incident_id,
                body={"title": "Spike in CPU", "severity": "high", "signals": ["cpu_pct"]},
                status="open",
                timestamp=now_iso,
            )
            assert len(received) == 1
            assert received[-1]["event_type"] == "incident_opened"

            # 2. Second event: incident_updated with identical attributes immediately (<10s) -> should throttle
            await broadcaster.push_incident(
                event_type="incident_updated",
                tenant_id="acme",
                incident_id=incident_id,
                body={"title": "Spike in CPU", "severity": "high", "signals": ["cpu_pct"]},
                status="open",
                timestamp=now_iso,
            )
            assert len(received) == 1  # No new message broadcast

            # 3. Third event: incident_updated with changed severity -> should broadcast
            await broadcaster.push_incident(
                event_type="incident_updated",
                tenant_id="acme",
                incident_id=incident_id,
                body={"title": "Spike in CPU", "severity": "critical", "signals": ["cpu_pct"]},
                status="open",
                timestamp=now_iso,
            )
            assert len(received) == 2
            assert received[-1]["payload"]["body"]["severity"] == "critical"

            # 4. Fourth event: simulate 11s elapsed with identical attributes -> should broadcast
            broadcaster._incident_last_sent[incident_id] -= 11.0
            await broadcaster.push_incident(
                event_type="incident_updated",
                tenant_id="acme",
                incident_id=incident_id,
                body={"title": "Spike in CPU", "severity": "critical", "signals": ["cpu_pct"]},
                status="open",
                timestamp=now_iso,
            )
            assert len(received) == 3

        finally:
            broadcaster.unregister_client(client_id)

    asyncio.run(_run_test())


def test_feedback_with_explicit_and_extracted_metric_source(client):
    """Verify feedback stores metric and source, falling back to aiops_alerts.body.signals."""
    # 1. Explicit metric & source
    res1 = client.post(
        "/api/feedback",
        json={
            "alert_id": "alt-test-explicit-1",
            "tenant_id": "acme",
            "user_id": "user-ops-1",
            "metric": "mem_pct",
            "source": "host-00000001",
        },
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["status"] == "recorded"
    assert data1["metric"] == "mem_pct"
    assert data1["source"] == "host-00000001"

    # Verify in DB
    rows1 = execute_query(
        "airlock_in",
        "SELECT alert_id, tenant_id, user_id, metric, source FROM feedback WHERE alert_id = %s;"
        if is_postgres_available()
        else "SELECT alert_id, tenant_id, user_id, metric, source FROM feedback WHERE alert_id = ?;",
        ("alt-test-explicit-1",),
        tenant_id="acme",
    )
    assert len(rows1) == 1
    assert rows1[0]["metric"] == "mem_pct"
    assert rows1[0]["source"] == "host-00000001"

    # 2. Alert with signals in aiops_alerts -> feedback automatically extracts metric & source
    alert_id = "alt-test-extract-2"
    record_aiops_alert(
        alert_id=alert_id,
        tenant_id="acme",
        source="host-00000002",
        title="High Disk IO",
        severity="medium",
        body={
            "kind": "anomaly",
            "signals": [{"source": "host-00000002", "name": "disk_io_pct", "val": 88.0}],
        },
    )

    res2 = client.post(
        "/api/feedback",
        json={
            "alert_id": alert_id,
            "tenant_id": "acme",
            "user_id": "user-ops-2",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["metric"] == "disk_io_pct"
    assert data2["source"] == "host-00000002"

    rows2 = execute_query(
        "airlock_in",
        "SELECT alert_id, metric, source FROM feedback WHERE alert_id = %s;"
        if is_postgres_available()
        else "SELECT alert_id, metric, source FROM feedback WHERE alert_id = ?;",
        (alert_id,),
        tenant_id="acme",
    )
    assert len(rows2) == 1
    assert rows2[0]["metric"] == "disk_io_pct"
    assert rows2[0]["source"] == "host-00000002"


def test_tenant_baselines_api(client):
    """Verify GET /api/baselines/{tenant_id} returns empty list when none exist, and returns normal bands when present."""
    # 1. Empty baselines for non-existent tenant
    res_empty = client.get("/api/baselines/nonexistent_tenant")
    assert res_empty.status_code == 200
    assert res_empty.json() == []

    import uuid
    unique_src = f"host-{uuid.uuid4().hex[:8]}"

    # 2. Insert baseline row for acme
    if is_postgres_available():
        execute_query(
            "airlock_in",
            """
            INSERT INTO aiops_baselines (tenant_id, source, metric, mean, std)
            VALUES (%s, %s, %s, %s, %s);
            """,
            ("acme", unique_src, "cpu_pct", 42.5, 3.8),
            tenant_id="acme",
        )
    else:
        execute_query(
            "airlock_in",
            """
            INSERT INTO aiops_baselines (tenant_id, source, metric, mean, std)
            VALUES (?, ?, ?, ?, ?);
            """,
            ("acme", unique_src, "cpu_pct", 42.5, 3.8),
            tenant_id="acme",
        )

    res_acme = client.get("/api/baselines/acme")
    assert res_acme.status_code == 200
    data = res_acme.json()
    assert isinstance(data, list)
    matching = [b for b in data if b["source"] == unique_src and b["metric"] == "cpu_pct"]
    assert len(matching) == 1
    assert matching[0]["mean"] == 42.5
    assert matching[0]["std"] == 3.8

    # 3. Customer tenant isolation
    login_res = client.post("/api/login", json={"username": "user-globex", "password": "globex123"})
    assert login_res.status_code == 200
    token = login_res.json()["token"]

    # user-globex cannot view acme baselines
    forbidden_res = client.get("/api/baselines/acme", headers={"Authorization": f"Bearer {token}"})
    assert forbidden_res.status_code == 403


def test_ai_chat_proxy_auth_and_fallback(client):
    """Verify /ai/chat enforces login (401), requires tenant for engineers (400), and returns proper fallback."""
    # 1. Unauthenticated request -> 401
    res_no_auth = client.post("/ai/chat", json={"question": "What is the CPU status?"})
    assert res_no_auth.status_code == 401

    # 2. Engineer login without tenant_id -> 400
    login_admin = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert login_admin.status_code == 200
    admin_token = login_admin.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    res_eng_no_tenant = client.post(
        "/ai/chat",
        json={"question": "What is the CPU status?"},
        headers=admin_headers,
    )
    assert res_eng_no_tenant.status_code == 400

    # 3. Engineer login with explicit tenant_id -> 200 with exact fallback
    res_eng_with_tenant = client.post(
        "/ai/chat",
        json={"question": "What is the CPU status?", "tenant_id": "acme"},
        headers=admin_headers,
    )
    assert res_eng_with_tenant.status_code == 200
    data_eng = res_eng_with_tenant.json()
    assert data_eng == {
        "answer": "The AI service is not reachable right now.",
        "evidence_ids": [],
    }

    # 4. Customer login querying different tenant -> 403
    login_globex = client.post("/api/login", json={"username": "user-globex", "password": "globex123"})
    assert login_globex.status_code == 200
    globex_token = login_globex.json()["token"]
    globex_headers = {"Authorization": f"Bearer {globex_token}"}

    res_cust_wrong_tenant = client.post(
        "/ai/chat",
        json={"question": "What is the CPU status?", "tenant_id": "acme"},
        headers=globex_headers,
    )
    assert res_cust_wrong_tenant.status_code == 403

    # 5. Customer login without tenant_id (uses own tenant) -> 200 with fallback
    res_cust = client.post(
        "/ai/chat",
        json={"question": "What is the CPU status?"},
        headers=globex_headers,
    )
    assert res_cust.status_code == 200
    assert res_cust.json() == {
        "answer": "The AI service is not reachable right now.",
        "evidence_ids": [],
    }
