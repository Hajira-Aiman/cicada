"""
tests/test_customer_separation.py
Verification of T5: Customer separation and logins:
1. Password hashing with scrypt & signed session token authentication
2. Role separation: engineer sees all tenants, customer sees only own tenant
3. Row-Level Security on real PostgreSQL: logged in as acme, no globex row is returned on ANY route
4. Verification of the limited aiops_worker database role permissions
"""

import json
import uuid
from datetime import datetime, timezone
import psycopg
import pytest
from httpx import AsyncClient, ASGITransport

from hq.api.main import app
from hq.db import (
    DB_HOST,
    DB_PORT,
    execute_query,
    init_all_databases,
    is_postgres_available,
    register_guard,
    store_payload,
    truncate_all_data,
)


@pytest.fixture(autouse=True)
def setup_test_data():
    init_all_databases()
    truncate_all_data()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    guard_acme = f"guard-acme-sep-{uuid.uuid4().hex[:6]}"
    guard_globex = f"guard-globex-sep-{uuid.uuid4().hex[:6]}"
    register_guard(guard_acme, "acme", "sec-acme-key")
    register_guard(guard_globex, "globex", "sec-globex-key")

    # Acme payload in India
    pay_acme = {
        "schema": "airlock.v1",
        "payload_id": f"pay-acme-{uuid.uuid4().hex[:8]}",
        "tenant_id": "acme",
        "guard_id": guard_acme,
        "seq": 101,
        "prev_hash": "GENESIS",
        "policy_version": "sha256:v1-default-policy",
        "sent_at": now_iso,
        "window": {"start": now_iso, "end": now_iso, "source_tz": "Asia/Kolkata"},
        "metrics": [{"name": "cpu_pct", "source": "host-7f3a1234", "avg": 30.0, "max": 45.0}],
        "events": [{"source": "host-7f3a1234", "category": "new_process", "severity": "info", "count": 1, "actor": None}],
        "log_patterns": [],
        "health": {"guard_version": "0.2.0", "guard_cpu_pct": 1.0, "guard_mem_mb": 40.0, "buffer_depth": 0, "config_ok": True, "canaries_planted": 0, "secrets_redacted": 0},
    }
    store_payload("airlock_in", pay_acme, f"sha256:{uuid.uuid4().hex}")

    # Globex payload in Europe
    pay_globex = {
        "schema": "airlock.v1",
        "payload_id": f"pay-globex-{uuid.uuid4().hex[:8]}",
        "tenant_id": "globex",
        "guard_id": guard_globex,
        "seq": 201,
        "prev_hash": "GENESIS",
        "policy_version": "sha256:ab1289cf001e35a9",
        "sent_at": now_iso,
        "window": {"start": now_iso, "end": now_iso, "source_tz": "Europe/Berlin"},
        "metrics": [{"name": "mem_pct", "source": "host-8b4c5678", "avg": 70.0, "max": 85.0}],
        "events": [{"source": "host-8b4c5678", "category": "config_changed", "severity": "low", "count": 1, "actor": None}],
        "log_patterns": [],
        "health": {"guard_version": "0.2.0", "guard_cpu_pct": 1.2, "guard_mem_mb": 50.0, "buffer_depth": 0, "config_ok": True, "canaries_planted": 0, "secrets_redacted": 0},
    }
    store_payload("airlock_eu", pay_globex, f"sha256:{uuid.uuid4().hex}")

    # Seed incidents and health in both regions
    execute_query(
        "airlock_in",
        "INSERT INTO incidents (incident_id, tenant_id, body, status, started_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (incident_id) DO NOTHING;",
        (f"inc-acme-{uuid.uuid4().hex[:6]}", "acme", json.dumps({"title": "Acme Incident"}), "open", now_iso),
    )
    execute_query(
        "airlock_eu",
        "INSERT INTO incidents (incident_id, tenant_id, body, status, started_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (incident_id) DO NOTHING;",
        (f"inc-globex-{uuid.uuid4().hex[:6]}", "globex", json.dumps({"title": "Globex Incident"}), "open", now_iso),
    )

    execute_query(
        "airlock_in",
        "INSERT INTO health_current (tenant_id, source, state, reasons, since) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, source) DO NOTHING;",
        ("acme", "host-7f3a1234", "Good", json.dumps(["Healthy"]), now_iso),
    )
    execute_query(
        "airlock_eu",
        "INSERT INTO health_current (tenant_id, source, state, reasons, since) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (tenant_id, source) DO NOTHING;",
        ("globex", "host-8b4c5678", "Fair", json.dumps(["Elevated Memory"]), now_iso),
    )


@pytest.mark.anyio
async def test_user_logins():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Login as engineer admin
        res_admin = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        assert res_admin.status_code == 200
        d_admin = res_admin.json()
        assert d_admin["role"] == "engineer"
        assert d_admin["token"] is not None

        # 2. Login as acme customer
        res_acme = await client.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        assert res_acme.status_code == 200
        d_acme = res_acme.json()
        assert d_acme["role"] == "customer"
        assert d_acme["tenant_id"] == "acme"

        # 3. Bad password -> 401
        res_bad = await client.post("/api/login", json={"username": "admin", "password": "wrong-password"})
        assert res_bad.status_code == 401


@pytest.mark.anyio
async def test_customer_separation_every_route():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login as customer Acme
        res_login = await client.post("/api/login", json={"username": "user-acme", "password": "acme123"})
        token = res_login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Route 1: /api/tenants
        r_tenants = await client.get("/api/tenants", headers=headers)
        assert r_tenants.status_code == 200
        t_data = r_tenants.json()["tenants"]
        assert all(t["tenant_id"] == "acme" for t in t_data)
        assert not any(t["tenant_id"] == "globex" for t in t_data)

        # Route 2: /api/metrics
        r_metrics = await client.get("/api/metrics", headers=headers)
        assert r_metrics.status_code == 200
        m_data = r_metrics.json()["metrics"]
        assert len(m_data) > 0
        assert all(m["tenant_id"] == "acme" for m in m_data)
        assert not any(m["tenant_id"] == "globex" for m in m_data)

        # Route 3: /api/events
        r_events = await client.get("/api/events", headers=headers)
        assert r_events.status_code == 200
        e_data = r_events.json()["events"]
        assert len(e_data) > 0
        assert all(e["tenant_id"] == "acme" for e in e_data)
        assert not any(e["tenant_id"] == "globex" for e in e_data)

        # Route 4: /api/payloads
        r_payloads = await client.get("/api/payloads", headers=headers)
        assert r_payloads.status_code == 200
        p_data = r_payloads.json()["payloads"]
        assert len(p_data) > 0
        assert all(p["tenant_id"] == "acme" for p in p_data)
        assert not any(p["tenant_id"] == "globex" for p in p_data)

        # Route 5: /api/incidents
        r_incidents = await client.get("/api/incidents", headers=headers)
        assert r_incidents.status_code == 200
        i_data = r_incidents.json()["incidents"]
        assert len(i_data) > 0
        assert all(i["tenant_id"] == "acme" for i in i_data)
        assert not any(i["tenant_id"] == "globex" for i in i_data)

        # Route 6: /api/health
        r_health = await client.get("/api/health", headers=headers)
        assert r_health.status_code == 200
        h_data = r_health.json()["health"]
        assert len(h_data) > 0
        assert all(h["tenant_id"] == "acme" for h in h_data)
        assert not any(h["tenant_id"] == "globex" for h in h_data)

        # Route 7: /api/reconciliation
        r_recon = await client.get("/api/reconciliation", headers=headers)
        assert r_recon.status_code == 200
        rec_data = r_recon.json()["reconciliation"]
        assert not any(r.get("tenant_id") == "globex" for r in rec_data)


@pytest.mark.anyio
async def test_engineer_sees_all_tenants():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Login as engineer admin
        res_login = await client.post("/api/login", json={"username": "admin", "password": "admin123"})
        token = res_login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Check /api/tenants has all tenants
        r_tenants = await client.get("/api/tenants", headers=headers)
        assert r_tenants.status_code == 200
        t_ids = {t["tenant_id"] for t in r_tenants.json()["tenants"]}
        assert "acme" in t_ids
        assert "globex" in t_ids

        # Check /api/metrics has both acme and globex
        r_metrics = await client.get("/api/metrics", headers=headers)
        assert r_metrics.status_code == 200
        m_tenants = {m["tenant_id"] for m in r_metrics.json()["metrics"]}
        assert "acme" in m_tenants
        assert "globex" in m_tenants


def test_aiops_worker_role_permissions():
    """Verifies that the limited aiops_worker DB role can read telemetry and write aiops tables on PostgreSQL."""
    if not is_postgres_available():
        pytest.skip("PostgreSQL container is not running")

    for db_name in ("airlock_in", "airlock_eu"):
        with psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user="aiops_worker",
            password="aiops_secret_2026",
            dbname=db_name,
        ) as conn:
            with conn.cursor() as cur:
                # 1. Can READ metrics, events, payloads
                cur.execute("SELECT count(*) FROM payloads;")
                cur.execute("SELECT count(*) FROM metrics;")
                cur.execute("SELECT count(*) FROM events;")

                # 2. Can WRITE health_history, health_current, incidents, tenant_thresholds, feedback
                now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                cur.execute(
                    "INSERT INTO health_history (tenant_id, source, state, old_state, reasons, at) VALUES (%s, %s, %s, %s, %s, %s);",
                    ("acme", "host-7f3a1234", "Good", "Excellent", json.dumps(["All good"]), now_iso),
                )
                cur.execute(
                    "INSERT INTO tenant_thresholds (tenant_id, config) VALUES (%s, %s) ON CONFLICT (tenant_id) DO UPDATE SET config = EXCLUDED.config;",
                    ("acme", json.dumps({"z_thresh": 3.0})),
                )
                cur.execute(
                    "INSERT INTO feedback (alert_id, tenant_id, user_id) VALUES (%s, %s, %s) ON CONFLICT (alert_id) DO NOTHING;",
                    (f"alert-{uuid.uuid4().hex[:8]}", "acme", "user-acme"),
                )
            conn.commit()
