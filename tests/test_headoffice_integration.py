# tests/test_headoffice_integration.py
import json
import pytest
from httpx import AsyncClient, ASGITransport
from contracts.models import IngestReceipt
from hq.api.broadcaster import broadcaster
from hq.db import execute_query, init_all_databases, register_guard
from hq.ingest.main import create_ingest_app
from tools.simulate import SimulatedGuardState, compute_hmac_signature


@pytest.mark.anyio
async def test_end_to_end_head_office_pipeline():
    init_all_databases()
    # Register guards for Acme (India) and Globex (Europe)
    register_guard("guard-globex-01", "globex", "sec-globex-super-secret-key-2026")
    register_guard("guard-acme-01", "acme", "sec-acme-super-secret-key-2026")

    ingest_eu_app = create_ingest_app(region="eu")
    ingest_in_app = create_ingest_app(region="in")

    ws_events = []

    async def ws_collector(msg):
        ws_events.append(msg)

    broadcaster.register_client("test-subscriber", ws_collector)

    # 1. Simulate Globex guard posting to Europe Ingest (:8002)
    globex_guard = SimulatedGuardState(
        tenant_id="globex",
        guard_id="guard-globex-01",
        secret="sec-globex-super-secret-key-2026",
    )
    p_eu = globex_guard.generate_payload(scenario="normal")
    p_eu_bytes = json.dumps(p_eu, sort_keys=True).encode("utf-8")
    sig_eu = compute_hmac_signature(p_eu_bytes, globex_guard.secret)

    headers_eu = {
        "Content-Type": "application/json",
        "X-Airlock-Guard-ID": globex_guard.guard_id,
        "X-Airlock-Signature": sig_eu,
        "X-Airlock-Timestamp": p_eu["sent_at"],
    }

    async with AsyncClient(transport=ASGITransport(app=ingest_eu_app), base_url="http://ingest-eu") as client_eu:
        resp1 = await client_eu.post("/ingest", content=p_eu_bytes, headers=headers_eu)
        assert resp1.status_code == 200
        receipt1 = IngestReceipt.model_validate(resp1.json())
        assert receipt1.status == "stored"
        assert receipt1.payload_id == p_eu["payload_id"]

        # 2. Re-send duplicate payload -> verify duplicate status
        resp2 = await client_eu.post("/ingest", content=p_eu_bytes, headers=headers_eu)
        assert resp2.status_code == 200
        receipt2 = IngestReceipt.model_validate(resp2.json())
        assert receipt2.status == "duplicate"

    import asyncio
    await asyncio.sleep(0.05)

    # 3. Verify WebSocket broadcaster received the live event
    assert len(ws_events) >= 1
    assert ws_events[-1]["tenant_id"] == "globex"
    assert ws_events[-1]["event_type"] == "metrics_batch"

    # 4. Simulate Acme guard posting to India Ingest (:8001)
    acme_guard = SimulatedGuardState(
        tenant_id="acme",
        guard_id="guard-acme-01",
        secret="sec-acme-super-secret-key-2026",
    )
    p_in = acme_guard.generate_payload(scenario="cpu_spike")
    p_in_bytes = json.dumps(p_in, sort_keys=True).encode("utf-8")
    sig_in = compute_hmac_signature(p_in_bytes, acme_guard.secret)

    headers_in = {
        "Content-Type": "application/json",
        "X-Airlock-Guard-ID": acme_guard.guard_id,
        "X-Airlock-Signature": sig_in,
        "X-Airlock-Timestamp": p_in["sent_at"],
    }

    async with AsyncClient(transport=ASGITransport(app=ingest_in_app), base_url="http://ingest-in") as client_in:
        resp_in = await client_in.post("/ingest", content=p_in_bytes, headers=headers_in)
        assert resp_in.status_code == 200
        receipt_in = IngestReceipt.model_validate(resp_in.json())
        assert receipt_in.status == "stored"

    # 5. Verify strict Regional Residency Isolation
    # Europe DB has Globex, 0 Acme
    globex_in_eu = execute_query("airlock_eu", "SELECT payload_id FROM payloads WHERE tenant_id = 'globex';")
    acme_in_eu = execute_query("airlock_eu", "SELECT payload_id FROM payloads WHERE tenant_id = 'acme';")
    assert len(globex_in_eu) >= 1
    assert len(acme_in_eu) == 0

    # India DB has Acme, 0 Globex
    acme_in_in = execute_query("airlock_in", "SELECT payload_id FROM payloads WHERE tenant_id = 'acme';")
    globex_in_in = execute_query("airlock_in", "SELECT payload_id FROM payloads WHERE tenant_id = 'globex';")
    assert len(acme_in_in) >= 1
    assert len(globex_in_in) == 0

    broadcaster.unregister_client("test-subscriber")
