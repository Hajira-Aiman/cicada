"""
tests/test_guard_to_headoffice.py
Cross-branch integration test:
Verifies that Guard successfully delivers signed payloads to Head Office Ingest
for both India (8001) and Europe (8002) regions, confirming 200 receipts and rows in metrics.
"""

import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from hq.ingest.main import create_ingest_app
from hq.db import get_sqlite_conn, init_all_databases
from guard.thin_slice import GuardThinSlice
from guard.config import GuardConfig

healthy_shop = FastAPI()
@healthy_shop.get("/health")
def _health_ok():
    return {"status": "ok"}


@pytest.fixture(autouse=True)
def setup_dbs():
    init_all_databases()


def test_guard_to_headoffice_ingest_in():
    app_in = create_ingest_app(region="in")
    with TestClient(app_in, base_url="http://localhost:8001") as client:
        cfg = GuardConfig()
        cfg.TENANT_ID = "acme"
        cfg.GUARD_ID = "guard-acme-01"
        cfg.GUARD_SECRET_KEY = "sec-acme-super-secret-key-2026"
        cfg.REGION_URL = "/ingest"

        guard = GuardThinSlice(cfg=cfg)
        with TestClient(healthy_shop) as probe_client:
            payload, body_bytes = guard.collect_window(duration_seconds=2.0, probe_client=probe_client)

        receipt = guard.send_payload(payload, body_bytes, client=client)

        assert receipt is not None
        assert receipt.payload_id == payload.payload_id
        assert receipt.status == "stored"
        assert receipt.sha256.startswith("sha256:")

        # Verify payload and metrics stored in airlock_in database
        conn = get_sqlite_conn("airlock_in")
        cur = conn.cursor()
        cur.execute("SELECT payload_id, guard_id, tenant_id FROM payloads WHERE payload_id = ?", (payload.payload_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == payload.payload_id

        # Verify metrics table rows
        cur.execute("SELECT name, source, avg, max FROM metrics WHERE payload_id = ?", (payload.payload_id,))
        metric_rows = cur.fetchall()
        assert len(metric_rows) >= 4  # cpu_pct, service_up, latency_ms, packet_loss_pct
        names = [r[0] for r in metric_rows]
        assert "cpu_pct" in names
        assert "service_up" in names
        assert "latency_ms" in names
        assert "packet_loss_pct" in names


def test_guard_to_headoffice_ingest_eu():
    app_eu = create_ingest_app(region="eu")
    with TestClient(app_eu, base_url="http://localhost:8002") as client:
        cfg = GuardConfig()
        cfg.TENANT_ID = "globex"
        cfg.GUARD_ID = "guard-globex-01"
        cfg.GUARD_SECRET_KEY = "sec-globex-super-secret-key-2026"
        cfg.REGION_URL = "/ingest"
        cfg.TIMEZONE = "Europe/Berlin"

        guard = GuardThinSlice(cfg=cfg)
        with TestClient(healthy_shop) as probe_client:
            payload, body_bytes = guard.collect_window(duration_seconds=2.0, probe_client=probe_client)

        receipt = guard.send_payload(payload, body_bytes, client=client)

        assert receipt is not None
        assert receipt.payload_id == payload.payload_id
        assert receipt.status == "stored"

        # Verify stored in airlock_eu database
        conn = get_sqlite_conn("airlock_eu")
        cur = conn.cursor()
        cur.execute("SELECT payload_id, guard_id, tenant_id FROM payloads WHERE payload_id = ?", (payload.payload_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "guard-globex-01"
        assert row[2] == "globex"

        cur.execute("SELECT name, avg FROM metrics WHERE payload_id = ?", (payload.payload_id,))
        metrics = cur.fetchall()
        assert len(metrics) >= 3
