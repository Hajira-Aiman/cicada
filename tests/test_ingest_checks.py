"""
tests/test_ingest_checks.py
Comprehensive verification of T4 ingest checks:
- Strict order: known guard -> HMAC -> timestamp -> schema -> pinned policy -> tripwire -> insert -> chain/gaps
- Dedicated test for each tamper case, HTTP status codes, and audit row creation
- Verified against real PostgreSQL database
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport

from hq.db import (
    get_audit_logs,
    get_leak_badge_count,
    get_guard_reconciliation,
    init_all_databases,
    register_guard,
    set_tenant_pinned_policy,
    execute_query,
)
from hq.ingest.main import create_ingest_app


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def make_payload(
    guard_id="guard-acme-01",
    tenant_id="acme",
    seq=1,
    prev_hash="GENESIS",
    policy_version="sha256:v1-default-policy",
    timestamp=None,
    extra_field=None,
    custom_metric=None,
):
    now_iso = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "schema": "airlock.v1",
        "payload_id": f"pay-{uuid.uuid4().hex[:16]}",
        "tenant_id": tenant_id,
        "guard_id": guard_id,
        "seq": seq,
        "prev_hash": prev_hash,
        "policy_version": policy_version,
        "sent_at": now_iso,
        "window": {
            "start": now_iso,
            "end": now_iso,
            "source_tz": "Asia/Kolkata",
        },
        "metrics": [
            custom_metric
            or {
                "name": "cpu_pct",
                "source": "host-7f3a1234",
                "avg": 25.5,
                "max": 40.0,
            }
        ],
        "events": [],
        "log_patterns": [],
        "health": {
            "guard_version": "0.2.0",
            "guard_cpu_pct": 1.5,
            "guard_mem_mb": 45.0,
            "buffer_depth": 0,
            "config_ok": True,
            "canaries_planted": 5,
            "secrets_redacted": 1,
        },
    }
    if extra_field:
        data[extra_field[0]] = extra_field[1]
    return data


@pytest.fixture(autouse=True)
def setup_test_db():
    init_all_databases()
    register_guard("guard-acme-01", "acme", "sec-acme-super-secret-key-2026")
    set_tenant_pinned_policy("acme", "sha256:v1-default-policy,sha256:ab1289cf001e35a9")


@pytest.mark.anyio
async def test_rogue_guard_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = make_payload(guard_id="rogue-guard-999")
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "arbitrary-secret")

        headers = {
            "X-Airlock-Guard-ID": "rogue-guard-999",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 401
        assert "Rogue guard" in res.json()["error"]

        # Verify audit log entry
        audits = get_audit_logs(action="rogue_guard", limit=5)
        assert any(a["actor"] == "rogue-guard-999" for a in audits)


@pytest.mark.anyio
async def test_bad_signature_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = make_payload()
        body_bytes = json.dumps(payload).encode("utf-8")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": "tampered-hmac-signature-deadbeef",
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 401
        assert "Invalid HMAC-SHA256" in res.json()["error"]

        audits = get_audit_logs(action="bad_signature", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_stale_timestamp_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Timestamp from 10 minutes ago (> 300s)
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = make_payload(timestamp=stale_ts)
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": stale_ts,
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 400
        assert "skewed by" in res.json()["error"]

        audits = get_audit_logs(action="stale_timestamp", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_clock_skew_warning_logged():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Timestamp with 45s skew (>30s but <300s: allowed, warning logged)
        skewed_ts = (datetime.now(timezone.utc) - timedelta(seconds=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = make_payload(timestamp=skewed_ts)
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": skewed_ts,
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "stored"

        audits = get_audit_logs(action="clock_skew_warning", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_schema_violation_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = make_payload(extra_field=("unapproved_leak", "secret_value_123"))
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 422
        assert "Schema contract violation" in res.json()["error"]

        audits = get_audit_logs(action="schema_violation", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_pinned_policy_mismatch_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = make_payload(policy_version="sha256:malicious_unapproved_drift")
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 422
        assert "Policy mismatch" in res.json()["error"]

        audits = get_audit_logs(action="policy_mismatch", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_canary_tripwire_detected_and_increments_badge():
    app = create_ingest_app(region="in")
    initial_leaks = get_leak_badge_count("acme")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Plant fake canary in payload_id
        canary_str = "AKIACANARY99TESTLEAK"
        payload = make_payload()
        payload["payload_id"] = f"pay-{canary_str}"
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 422
        assert "Tripwire triggered" in res.json()["error"]

        # Assert leak badge incremented
        current_leaks = get_leak_badge_count("acme")
        assert current_leaks == initial_leaks + 1

        audits = get_audit_logs(action="tripwire_triggered", limit=5)
        assert any("canary" in str(a["details"]) for a in audits)


@pytest.mark.anyio
async def test_secret_tripwire_detected_and_increments_badge():
    app = create_ingest_app(region="in")
    initial_leaks = get_leak_badge_count("acme")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Plant unmasked AWS key in health guard_version
        secret_key = "AKIAIOSFODNN7EXAMPLE"
        payload = make_payload()
        payload["health"]["guard_version"] = f"0.2.0-{secret_key}"
        body_bytes = json.dumps(payload).encode("utf-8")
        sig = compute_signature(body_bytes, "sec-acme-super-secret-key-2026")

        headers = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        res = await client.post("/ingest", content=body_bytes, headers=headers)
        assert res.status_code == 422
        assert "Tripwire triggered" in res.json()["error"]

        # Assert leak badge incremented
        current_leaks = get_leak_badge_count("acme")
        assert current_leaks == initial_leaks + 1

        audits = get_audit_logs(action="tripwire_triggered", limit=5)
        assert any("aws_secret_key" in str(a["details"]) for a in audits)


@pytest.mark.anyio
async def test_chain_break_rejected():
    app = create_ingest_app(region="in")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Send seq 1
        p1 = make_payload(seq=1, prev_hash="GENESIS")
        b1 = json.dumps(p1).encode("utf-8")
        sig1 = compute_signature(b1, "sec-acme-super-secret-key-2026")
        headers1 = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig1,
            "X-Airlock-Timestamp": p1["sent_at"],
        }
        res1 = await client.post("/ingest", content=b1, headers=headers1)
        assert res1.status_code == 200
        sha1 = res1.json()["sha256"]

        # 2. Send seq 2 with tampered prev_hash (does not match sha1)
        p2 = make_payload(seq=2, prev_hash="sha256:corrupted_break_000000000000")
        b2 = json.dumps(p2).encode("utf-8")
        sig2 = compute_signature(b2, "sec-acme-super-secret-key-2026")
        headers2 = {
            "X-Airlock-Guard-ID": "guard-acme-01",
            "X-Airlock-Signature": sig2,
            "X-Airlock-Timestamp": p2["sent_at"],
        }
        res2 = await client.post("/ingest", content=b2, headers=headers2)
        assert res2.status_code == 422
        assert "Hash chain break" in res2.json()["error"]

        audits = get_audit_logs(action="chain_break", limit=5)
        assert any(a["actor"] == "guard-acme-01" for a in audits)


@pytest.mark.anyio
async def test_seq_gap_allowed_as_buffered():
    app = create_ingest_app(region="in")
    test_guard = f"guard-gap-{uuid.uuid4().hex[:6]}"
    register_guard(test_guard, "acme", "sec-acme-super-secret-key-2026")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Send seq 1
        p1 = make_payload(guard_id=test_guard, seq=1, prev_hash="GENESIS")
        b1 = json.dumps(p1).encode("utf-8")
        headers1 = {
            "X-Airlock-Guard-ID": test_guard,
            "X-Airlock-Signature": compute_signature(b1, "sec-acme-super-secret-key-2026"),
            "X-Airlock-Timestamp": p1["sent_at"],
        }
        res1 = await client.post("/ingest", content=b1, headers=headers1)
        assert res1.status_code == 200

        # Send seq 3 directly (seq 2 buffered in guard outbox)
        p3 = make_payload(guard_id=test_guard, seq=3, prev_hash="sha256:placeholder_for_seq_2")
        b3 = json.dumps(p3).encode("utf-8")
        headers3 = {
            "X-Airlock-Guard-ID": test_guard,
            "X-Airlock-Signature": compute_signature(b3, "sec-acme-super-secret-key-2026"),
            "X-Airlock-Timestamp": p3["sent_at"],
        }
        res3 = await client.post("/ingest", content=b3, headers=headers3)
        # Must be accepted as still buffered
        assert res3.status_code == 200
        assert res3.json()["status"] == "stored"

        # Check reconciliation gaps shows seq 2 missing
        recon = get_guard_reconciliation("airlock_in", test_guard)
        assert recon is not None
        assert 2 in recon["gaps"]


@pytest.mark.anyio
async def test_idempotent_duplicate_storage():
    app = create_ingest_app(region="in")
    test_guard = f"guard-dup-{uuid.uuid4().hex[:6]}"
    register_guard(test_guard, "acme", "sec-acme-super-secret-key-2026")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        p = make_payload(guard_id=test_guard, seq=1, prev_hash="GENESIS")
        b = json.dumps(p).encode("utf-8")
        sig = compute_signature(b, "sec-acme-super-secret-key-2026")
        headers = {
            "X-Airlock-Guard-ID": test_guard,
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": p["sent_at"],
        }

        # Submission 1 -> stored
        res1 = await client.post("/ingest", content=b, headers=headers)
        assert res1.status_code == 200
        assert res1.json()["status"] == "stored"

        # Submission 2 (same payload) -> duplicate
        res2 = await client.post("/ingest", content=b, headers=headers)
        assert res2.status_code == 200
        assert res2.json()["status"] == "duplicate"

        # Verify only 1 row exists in payloads table
        rows = execute_query("airlock_in", "SELECT payload_id FROM payloads WHERE payload_id = %s;", (p["payload_id"],))
        assert len(rows) == 1
