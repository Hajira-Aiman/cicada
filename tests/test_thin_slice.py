"""
tests/test_thin_slice.py
End-to-end verification for Phase 2 Thin Slice (T2):
- psutil reading -> payload build -> HMAC signing -> send -> receipt
"""

import pytest
from starlette.testclient import TestClient
from guard.thin_slice import GuardThinSlice
from guard.config import GuardConfig
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

    # Assert CPU metric item
    assert len(payload.metrics) == 1
    metric = payload.metrics[0]
    assert metric.name == "cpu_pct"
    assert metric.source.startswith("host-")
    assert isinstance(metric.avg, float)

    # Next window increments seq and chains hash
    p2, b2 = guard.collect_window(duration_seconds=2.0)
    assert p2.seq == 2
    assert p2.prev_hash.startswith("sha256:")


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
        assert ingested["metrics"][0].name == "cpu_pct"


from guard.signer import create_auth_headers, verify_payload_signature


def test_reject_tampered_signature():
    with TestClient(mock_ingest_app, base_url="http://localhost:8001") as client:
        guard = GuardThinSlice()
        payload, body_bytes = guard.collect_window(duration_seconds=2.0)

        # Generate authentic headers for original body
        headers = create_auth_headers(
            guard_id=guard.config.GUARD_ID,
            payload_id=payload.payload_id,
            body_bytes=body_bytes,
            timestamp_iso=payload.sent_at,
            secret_key=guard.config.GUARD_SECRET_KEY,
        )

        # Simulate in-flight tampering of body
        tampered_body = body_bytes.replace(b"acme", b"evil")

        response = client.post("/v1/ingest", content=tampered_body, headers=headers)
        assert response.status_code == 401
        assert "Invalid HMAC" in response.text

        # Simulate bogus signature
        corrupted_headers = dict(headers)
        corrupted_headers["X-Signature"] = "0" * 64
        res2 = client.post("/v1/ingest", content=body_bytes, headers=corrupted_headers)
        assert res2.status_code == 401
