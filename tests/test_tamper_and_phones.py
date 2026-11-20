"""
tests/test_tamper_and_phones.py
Tests for T13 Tamper scenario alert rows & WebSocket pushes, and T14 Phone Join backend on real PostgreSQL.
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from contracts.models import AirlockPayload, EventItem, GuardHealth, MetricItem, TimeWindow
from hq.api.main import app as hq_app, _phones
from hq.db import (
    execute_query,
    init_all_databases,
    register_guard,
    truncate_all_data,
)
from hq.ingest.main import create_ingest_app

SECRET = "sec-tamper-test-2026"
GUARD_ID = "guard-tamper-01"
TENANT_ID = "acme"  # Ingest IN


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()
    _phones.clear()
    register_guard(GUARD_ID, TENANT_ID, SECRET)
    yield
    truncate_all_data()
    _phones.clear()


def make_valid_payload(seq=1, prev_hash="GENESIS", policy="sha256:v1-default-policy", skew_seconds=0):
    now_dt = datetime.now(timezone.utc)
    sent_ts = datetime.fromtimestamp(now_dt.timestamp() - skew_seconds, tz=timezone.utc)
    sent_iso = sent_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = AirlockPayload(
        payload_id=f"tamper-{uuid.uuid4().hex[:12]}",
        guard_id=GUARD_ID,
        tenant_id=TENANT_ID,
        seq=seq,
        prev_hash=prev_hash,
        policy_version=policy,
        sent_at=sent_iso,
        window=TimeWindow(start=sent_iso, end=sent_iso, source_tz="UTC"),
        metrics=[
            MetricItem(source="host-7f3a1b2c", name="cpu_pct", avg=20.0, max=30.0),
        ],
        events=[
            EventItem(source="host-7f3a1b2c", category="auth_failure_burst", severity="low", actor="src-00000001", count=1, window_s=2),
        ],
        health=GuardHealth(
            guard_version="0.3.1",
            guard_cpu_pct=1.0,
            guard_mem_mb=50.0,
            buffer_depth=0,
            config_ok=True,
            canaries_planted=5,
            secrets_redacted=0,
        ),
    )
    raw_body = payload.model_dump_json(by_alias=True).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    cur_hash = "sha256:" + hashlib.sha256(raw_body).hexdigest()
    return raw_body, sig, sent_iso, cur_hash


@pytest.mark.anyio
async def test_tamper_scenarios_generate_alert_rows():
    ingest_app = create_ingest_app(region="in")

    async with AsyncClient(transport=ASGITransport(app=ingest_app), base_url="http://ingest") as client:
        # 1. Tamper Case: Bad signature
        raw, sig, ts, _ = make_valid_payload(seq=1, prev_hash="GENESIS")
        bad_sig = "deadbeef" * 8
        headers_bad_sig = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": GUARD_ID,
            "X-Airlock-Signature": bad_sig,
            "X-Airlock-Timestamp": ts,
        }
        r_sig = await client.post("/ingest", content=raw, headers=headers_bad_sig)
        assert r_sig.status_code == 401
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts WHERE severity = 'critical';")
        assert any("bad_signature" in str(a.get("body", "")) for a in alerts)

        # 2. Tamper Case: Rogue Guard
        headers_rogue = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": "guard-rogue-unregistered-99",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": ts,
        }
        r_rogue = await client.post("/ingest", content=raw, headers=headers_rogue)
        assert r_rogue.status_code == 401
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts WHERE severity = 'critical';")
        assert any("rogue_guard" in str(a.get("body", "")) for a in alerts)

        # 3. Tamper Case: Policy Mismatch
        raw_pol, sig_pol, ts_pol, _ = make_valid_payload(seq=1, prev_hash="GENESIS", policy="sha256:unapproved-tampered-policy")
        headers_pol = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": GUARD_ID,
            "X-Airlock-Signature": sig_pol,
            "X-Airlock-Timestamp": ts_pol,
        }
        r_pol = await client.post("/ingest", content=raw_pol, headers=headers_pol)
        assert r_pol.status_code == 422
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts WHERE severity = 'high';")
        assert any("policy_mismatch" in str(a.get("body", "")) for a in alerts)

        # 4. Tamper Case: Clock Skew Warning (> 30s skew)
        raw_skew, sig_skew, ts_skew, cur_hash1 = make_valid_payload(seq=1, prev_hash="GENESIS", skew_seconds=45)
        headers_skew = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": GUARD_ID,
            "X-Airlock-Signature": sig_skew,
            "X-Airlock-Timestamp": ts_skew,
        }
        r_skew = await client.post("/ingest", content=raw_skew, headers=headers_skew)
        assert r_skew.status_code == 200
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts WHERE severity = 'medium';")
        assert any("clock_skew_warning" in str(a.get("body", "")) for a in alerts)

        # 5. Tamper Case: Hash Chain Break (seq 2 without matching prev_hash)
        raw_chain, sig_chain, ts_chain, _ = make_valid_payload(seq=2, prev_hash="sha256:broken_hash_00000000")
        headers_chain = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": GUARD_ID,
            "X-Airlock-Signature": sig_chain,
            "X-Airlock-Timestamp": ts_chain,
        }
        r_chain = await client.post("/ingest", content=raw_chain, headers=headers_chain)
        assert r_chain.status_code == 422
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts WHERE severity = 'critical';")
        assert any("chain_break" in str(a.get("body", "")) for a in alerts)

        # 6. Tamper Case: Duplicate Replay
        # Send raw_skew again (same payload_id)
        r_dup = await client.post("/ingest", content=raw_skew, headers=headers_skew)
        assert r_dup.status_code == 200
        assert r_dup.json()["status"] == "duplicate"
        alerts = execute_query("airlock_in", "SELECT * FROM aiops_alerts;")
        assert any("duplicate_replay" in str(a.get("body", "")) for a in alerts)


@pytest.mark.anyio
async def test_phone_join_backend_heartbeat_and_offline():
    async with AsyncClient(transport=ASGITransport(app=hq_app), base_url="http://test") as client:
        # 1. Normal heartbeat under low latency (green)
        res_green = await client.post("/api/phones/heartbeat", json={"phone_id": "phone-judge-01", "latency_ms": 24.5})
        assert res_green.status_code == 200
        data_g = res_green.json()
        assert data_g["state"] == "online"
        assert data_g["color"] == "green"
        assert data_g["tenant_id"] == "guests"

        # 2. Simulated latency spike > 150ms (turns red)
        res_spike = await client.post("/api/phones/heartbeat", json={"phone_id": "phone-judge-02", "latency_ms": 195.0})
        assert res_spike.status_code == 200
        data_s = res_spike.json()
        assert data_s["state"] == "online"
        assert data_s["color"] == "red"

        # 3. Check health and phones list
        r_phones = await client.get("/api/phones")
        assert r_phones.status_code == 200
        phones_list = r_phones.json()["phones"]
        assert len(phones_list) == 2
        p1 = [p for p in phones_list if p["phone_id"] == "phone-judge-01"][0]
        assert p1["status"] == "online"
        assert p1["color"] == "green"

        p2 = [p for p in phones_list if p["phone_id"] == "phone-judge-02"][0]
        assert p2["status"] == "online"
        assert p2["color"] == "red"

        # 4. Check GET /health includes phones
        h_res = await client.get("/health")
        assert h_res.status_code == 200
        assert "phones" in h_res.json()
        assert len(h_res.json()["phones"]) == 2

        # 5. Heartbeat stops > 60s -> marked offline and red
        _phones["phone-judge-01"]["last_heartbeat_ts"] = time.time() - 75.0
        r_off = await client.get("/api/phones")
        p1_off = [p for p in r_off.json()["phones"] if p["phone_id"] == "phone-judge-01"][0]
        assert p1_off["status"] == "offline"
        assert p1_off["color"] == "red"
