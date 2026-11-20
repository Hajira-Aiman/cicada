"""
tests/test_guard_to_headoffice.py
Cross-branch integration test:
Verifies that Guard (Tenant 1 - Shop A Acme) successfully delivers signed payloads
to Sahiti's Head Office Ingest service (hq/ingest) and receives authentic IngestReceipt.
"""

import pytest
from starlette.testclient import TestClient
from hq.ingest.main import create_ingest_app
from hq.db import get_sqlite_conn
from guard.thin_slice import GuardThinSlice


def test_guard_to_real_headoffice_ingest():
    app = create_ingest_app(region="in")
    with TestClient(app, base_url="http://localhost:8001") as client:
        guard = GuardThinSlice()
        payload, body_bytes = guard.collect_window(duration_seconds=2.0)

        # Ingest endpoint is /ingest
        guard.config.REGION_URL = "/ingest"
        receipt = guard.send_payload(payload, body_bytes, client=client)

        assert receipt is not None
        assert receipt.payload_id == payload.payload_id
        assert receipt.status == "stored"
        assert receipt.sha256.startswith("sha256:")

        # Verify payload landed in airlock_in database
        conn = get_sqlite_conn("airlock_in")
        cur = conn.cursor()
        cur.execute("SELECT payload_id, guard_id, tenant_id FROM payloads WHERE payload_id = ?", (payload.payload_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == payload.payload_id
        assert row[1] == "guard-acme-01"
        assert row[2] == "acme"
