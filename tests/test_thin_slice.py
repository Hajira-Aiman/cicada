"""
tests/test_thin_slice.py
End-to-end verification for Guard Telemetry Collector:
- psutil reading -> payload build -> HMAC signing -> send -> receipt
- Verifies presence of cpu_pct, mem_pct, disk_pct, net_in_kbps, net_out_kbps, service_up, and latency_ms
- Verifies real probe behavior: HTTP 200 -> service_up=1.0; failure -> service_up=0.0 + service_down event
- Verifies change event emission
- Verifies rejection of tampered body or invalid signature
"""

import pytest
import httpx
from starlette.testclient import TestClient
from starlette.responses import Response
from fastapi import FastAPI
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

    # Assert required metrics: cpu_pct, mem_pct, disk_pct, net_in_kbps, net_out_kbps, service_up, latency_ms
    metric_names = [m.name for m in payload.metrics]
    assert "cpu_pct" in metric_names
    assert "mem_pct" in metric_names
    assert "disk_pct" in metric_names
    assert "net_in_kbps" in metric_names
    assert "net_out_kbps" in metric_names
    assert "service_up" in metric_names
    assert "latency_ms" in metric_names

    # Check metric values are valid floats
    for m in payload.metrics:
        assert isinstance(m.avg, (float, int))
        assert isinstance(m.max, (float, int))

    # Next window increments seq and chains hash
    p2, b2 = guard.collect_window(duration_seconds=2.0)
    assert p2.seq == 2
    assert p2.prev_hash.startswith("sha256:")


def test_real_probe_service_up_and_service_down():
    # 1. Mock shop-api that is healthy (200)
    healthy_app = FastAPI()
    @healthy_app.get("/health")
    def health_ok():
        return {"status": "ok"}

    guard = GuardThinSlice()
    with TestClient(healthy_app) as client:
        service_up, latency = guard.probe_shop_health(client=client)
        assert service_up == 1.0
        assert latency > 0.0

        p, _ = guard.collect_window(probe_client=client)
        m_map = {m.name: m.avg for m in p.metrics}
        assert m_map["service_up"] == 1.0
        # No service_down event should be present
        events = [e.category for e in p.events]
        assert "service_down" not in events

    # 2. Mock shop-api that returns 500 error
    error_app = FastAPI()
    @error_app.get("/health")
    def health_err():
        return Response(content="error", status_code=500)

    guard_err = GuardThinSlice()
    with TestClient(error_app) as client:
        service_up, latency = guard_err.probe_shop_health(client=client)
        assert service_up == 0.0

        p_err, _ = guard_err.collect_window(probe_client=client)
        m_map_err = {m.name: m.avg for m in p_err.metrics}
        assert m_map_err["service_up"] == 0.0
        events_err = [e.category for e in p_err.events]
        assert "service_down" in events_err


def test_thin_slice_change_event_emission():
    guard = GuardThinSlice()
    guard.emit_change_event("app_restarted")
    payload, body_bytes = guard.collect_window(duration_seconds=2.0)

    event_categories = [e.category for e in payload.events]
    assert "app_restarted" in event_categories


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
