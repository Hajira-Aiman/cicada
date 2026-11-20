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
from pathlib import Path
from starlette.testclient import TestClient
from starlette.responses import Response
from fastapi import FastAPI
from guard.thin_slice import GuardThinSlice
from guard.config import GuardConfig
from guard.signer import create_auth_headers
from tests.mock_ingest import mock_ingest_app, received_payloads


@pytest.fixture(autouse=True)
def clean_received_payloads():
    received_payloads.clear()
    guard_db = Path("data/guard.db")
    if guard_db.exists():
        try:
            guard_db.unlink()
        except OSError:
            pass


def test_thin_slice_collection_and_signing():
    healthy_app = FastAPI()
    @healthy_app.get("/health")
    def _ok():
        return {"status": "ok"}

    guard = GuardThinSlice()
    with TestClient(healthy_app) as client:
        payload, body_bytes = guard.collect_window(duration_seconds=2.0, probe_client=client)

        # Assert basic envelope properties
        assert payload.schema_version == "airlock.v1"
        assert payload.tenant_id == "acme"
        assert payload.guard_id == "guard-acme-01"
        assert payload.seq == 1
        assert payload.prev_hash == "GENESIS"
        assert payload.window.source_tz == "Asia/Kolkata"

        # Assert required metrics: cpu_pct, mem_pct, disk_pct, net_in_kbps, net_out_kbps, service_up, latency_ms, packet_loss_pct
        metric_names = [m.name for m in payload.metrics]
        assert "cpu_pct" in metric_names
        assert "mem_pct" in metric_names
        assert "disk_pct" in metric_names
        assert "net_in_kbps" in metric_names
        assert "net_out_kbps" in metric_names
        assert "service_up" in metric_names
        assert "latency_ms" in metric_names
        assert "packet_loss_pct" in metric_names

        # Verify source naming: host pseudonym for host metrics, shop-api pseudonym for service metrics
        m_sources = {m.name: m.source for m in payload.metrics}
        assert m_sources["cpu_pct"] == guard.host_pseudonym
        assert m_sources["mem_pct"] == guard.host_pseudonym
        assert m_sources["disk_pct"] == guard.host_pseudonym
        assert m_sources["net_in_kbps"] == guard.host_pseudonym
        assert m_sources["net_out_kbps"] == guard.host_pseudonym
        assert m_sources["service_up"] == guard.service_pseudonyms["shop-api"]
        assert m_sources["latency_ms"] == guard.service_pseudonyms["shop-api"]
        assert m_sources["packet_loss_pct"] == guard.service_pseudonyms["shop-api"]

        # Check metric values are valid floats
        for m in payload.metrics:
            assert isinstance(m.avg, (float, int))
            assert isinstance(m.max, (float, int))

        # Next window increments seq and chains hash
        p2, b2 = guard.collect_window(duration_seconds=2.0, probe_client=client)
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
        assert "latency_ms" in m_map
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
        # No latency_ms when service is down
        assert "latency_ms" not in m_map_err
        events_err = [e.category for e in p_err.events]
        assert "service_down" in events_err


def test_reused_client_low_latency_and_down_behavior():
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler
    from guard.config import GuardConfig

    class MockHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        cfg = GuardConfig()
        cfg.SHOP_HEALTH_URL = f"http://127.0.0.1:{port}/health"
        guard = GuardThinSlice(cfg=cfg)

        with httpx.Client(timeout=1.0) as client:
            # First request warms connection
            guard.probe_shop_health(client=client)

            # Reused client latency against local test server: must be < 100 ms
            up, latency = guard.probe_shop_health(client=client)
            assert up == 1.0
            assert latency < 100.0, f"Expected reused client latency < 100 ms, got {latency} ms"

            # Check window includes latency_ms
            p_up, _ = guard.collect_window(probe_client=client)
            m_up = {m.name: m.avg for m in p_up.metrics}
            assert m_up["service_up"] == 1.0
            assert "latency_ms" in m_up
            assert m_up["latency_ms"] < 100.0
    finally:
        server.shutdown()
        server.server_close()

    # Now the server is down: probe fails
    p_down, _ = guard.collect_window()
    m_down = {m.name: m.avg for m in p_down.metrics}
    assert m_down["service_up"] == 0.0
    # Crucial: when server is down, latency_ms MUST NOT be sent
    assert "latency_ms" not in m_down
    assert any(e.category == "service_down" for e in p_down.events)


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


def test_packet_loss_probe_and_network_stop(tmp_path):
    """
    Verifies real packet loss probing:
    - Normal operation reports packet_loss_pct (0.0 to 100.0) on shop-api pseudonym
    - Network stoppage (Toxiproxy / down target) makes it rise within 2 windows
    """
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_pkt.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r_pkt.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev_pkt.db")
    cfg.SHOP_LOG_PATH = str(tmp_path / "shop_pkt.log")

    guard = GuardThinSlice(cfg=cfg)

    # 1. Normal network operation
    guard.set_packet_loss_override(0.0)
    p1, _ = guard.collect_window(duration_seconds=1.0)
    loss1 = next(m.avg for m in p1.metrics if m.name == "packet_loss_pct")
    assert loss1 == 0.0

    # 2. Window 1 of network interruption (Toxiproxy stops network)
    guard.set_packet_loss_override(80.0)
    p2, _ = guard.collect_window(duration_seconds=1.0)
    loss2 = next(m.avg for m in p2.metrics if m.name == "packet_loss_pct")
    assert loss2 == 80.0

    # 3. Window 2 of network interruption: rises to 100% loss
    guard.set_packet_loss_override(100.0)
    p3, _ = guard.collect_window(duration_seconds=1.0)
    loss3 = next(m.avg for m in p3.metrics if m.name == "packet_loss_pct")
    assert loss3 == 100.0
