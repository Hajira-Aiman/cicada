# tests/test_headoffice_ingest.py
import hashlib
import hmac
import json
import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from hq.db import init_all_databases, register_guard
from hq.ingest.main import create_ingest_app


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


def sample_payload_dict(guard_id="guard-globex-01", tenant_id="globex", payload_id="0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1", timestamp=None):
    now_iso = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema": "airlock.v1",
        "payload_id": payload_id,
        "tenant_id": tenant_id,
        "guard_id": guard_id,
        "seq": 1042,
        "prev_hash": "sha256:0000000000000000",
        "policy_version": "sha256:ab1289cf001e35a9",
        "sent_at": now_iso,
        "window": {
            "start": now_iso,
            "end": now_iso,
            "source_tz": "Europe/Berlin",
        },
        "metrics": [
            {
                "name": "cpu_pct",
                "source": "host-7f3a1234",
                "avg": 34.2,
                "max": 51.0,
            }
        ],
        "events": [],
        "log_patterns": [],
        "health": {
            "guard_version": "0.1.0",
            "guard_cpu_pct": 1.2,
            "guard_mem_mb": 80.0,
            "buffer_depth": 0,
            "config_ok": True,
            "canaries_planted": 12,
            "secrets_redacted": 3,
        },
    }


@pytest.mark.anyio
async def test_ingest_valid_and_duplicate():
    init_all_databases()
    register_guard("guard-globex-01", "globex", "sec-globex-super-secret-key-2026")
    app = create_ingest_app(region="eu")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = sample_payload_dict()
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sig = compute_signature(payload_bytes, "sec-globex-super-secret-key-2026")

        headers = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": "guard-globex-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": payload["sent_at"],
        }

        # 1. First submission -> stored
        resp1 = await client.post("/ingest", content=payload_bytes, headers=headers)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["status"] == "stored"
        assert data1["payload_id"] == payload["payload_id"]

        # 2. Duplicate submission -> duplicate
        resp2 = await client.post("/ingest", content=payload_bytes, headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["status"] == "duplicate"


@pytest.mark.anyio
async def test_ingest_invalid_signature():
    init_all_databases()
    app = create_ingest_app(region="eu")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = sample_payload_dict(payload_id="0193f2c1-bad0-7c3a-9f10-4be2a1d0c9e1")
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": "guard-globex-01",
            "X-Airlock-Signature": "wrong-invalid-signature",
            "X-Airlock-Timestamp": payload["sent_at"],
        }
        resp = await client.post("/ingest", content=payload_bytes, headers=headers)
        assert resp.status_code == 401


@pytest.mark.anyio
async def test_ingest_expired_timestamp():
    init_all_databases()
    app = create_ingest_app(region="eu")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Timestamp from 10 minutes ago (> 300s)
        expired_ts = "2020-01-01T00:00:00Z"
        payload = sample_payload_dict(payload_id="0193f2c1-old0-7c3a-9f10-4be2a1d0c9e1", timestamp=expired_ts)
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        sig = compute_signature(payload_bytes, "sec-globex-super-secret-key-2026")

        headers = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": "guard-globex-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": expired_ts,
        }
        resp = await client.post("/ingest", content=payload_bytes, headers=headers)
        assert resp.status_code == 400
