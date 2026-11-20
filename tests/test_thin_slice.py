"""
tests/test_thin_slice.py
End-to-end verification for Guard Telemetry Collector:
- psutil reading -> payload build -> HMAC signing -> send -> receipt
- Verifies presence of cpu_pct, service_up, and latency_ms
- Verifies change event emission
- Verifies rejection of tampered body or invalid signature
"""

import pytest
from starlette.testclient import TestClient
from guard.thin_slice import GuardThinSlice
from guard.signer import create_auth_headers
from tests.mock_ingest import mock_ingest_app, received_payloads


@pytest.fixture(autouse=True)
def clean_received_payloads():
    received_payloads.clear()


def test_thin_slice_collection_and_signing():
    guard = GuardThinSlice()
    payload, body_bytes = guard.collect_window(duration_seconds=2.0)

    # Assert basic envelope properties
    assert payload.schema_version == "airlock.v1"
    assert payload.tenant_id == "acme"
    assert payload.guard_id == "guard-acme-01"
    assert payload.seq == 1
    assert payload.prev_hash == "GENESIS"
    assert payload.window.source_tz == "Asia/Kolkata"

    # Assert required metrics: cpu_pct, service_up, latency_ms
    metric_names = [m.name for m in payload.metrics]
    assert "cpu_pct" in metric_names
    assert "service_up" in metric_names
    assert "latency_ms" in metric_names

    # Next window increments seq and chains hash
    p2, b2 = guard.collect_window(duration_seconds=2.0)
    assert p2.seq == 2
    assert p2.prev_hash.startswith("sha256:")


def test_thin_slice_change_event_emission():
    guard = GuardThinSlice()
    guard.emit_change_event("app_restarted")
    payload, body_bytes = guard.collect_window(duration_seconds=2.0)

    assert len(payload.events) == 1
    assert payload.events[0].category == "app_restarted"
    assert payload.events[0].source.startswith("proc-")


def test_thin_slice_send_to_mock_ingest():
    with TestClient(mock_ingest_app, base_url="http://localhost:8001") as client:
        guard = GuardThinSlice()
        payload, body_bytes = guard.collect_window(duration_seconds=2.0)

        receipt = guard.send_payload(payload, body_bytes, client=client)

        assert receipt is not None
        assert receipt.payload_id == payload.payload_id
        assert receipt.status == "stored"
        assert receipt.sha256.startswith("sha256:")

        # Verify ingested data
        assert len(received_payloads) == 1
        ingested = received_payloads[0]
        assert ingested["payload_id"] == payload.payload_id
        assert ingested["tenant_id"] == "acme"


def test_reject_tampered_signature():
    with TestClient(mock_ingest_app, base_url="http://localhost:8001") as client:
        guard = GuardThinSlice()
        payload, body_bytes = guard.collect_window(duration_seconds=2.0)

        # Generate authentic headers for original body
        headers = create_auth_headers(
            guard_id=guard.config.GUARD_ID,
            body_bytes=body_bytes,
            timestamp_iso=payload.sent_at,
            secret_key=guard.config.GUARD_SECRET_KEY,
        )

        # Simulate in-flight tampering of body
        tampered_body = body_bytes.replace(b"acme", b"evil")

        response = client.post("/ingest", content=tampered_body, headers=headers)
        assert response.status_code == 401
        assert "Invalid HMAC" in response.text

        # Simulate bogus signature
        corrupted_headers = dict(headers)
        corrupted_headers["X-Airlock-Signature"] = "0" * 64
        res2 = client.post("/ingest", content=body_bytes, headers=corrupted_headers)
        assert res2.status_code == 401
