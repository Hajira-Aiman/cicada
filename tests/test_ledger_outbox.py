"""
tests/test_ledger_outbox.py
Verification for T11 Cryptographic Ledger + Outbox + Sender:
- SQLite table ledger(seq, payload_id, sha256, prev_hash, body, status, receipt_at)
- Contiguous sequence with zero gaps
- Cryptographic hash chain validation
- Outbox buffer growth when Ingest is unreachable (buffer depth in GuardHealth)
- Full drain to 0 when Ingest returns, with sent = received, duplicates = 0, gaps = 0
- Idempotent duplicate receipt handling and mismatch protection
"""

import uuid
import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI
from hq.ingest.main import create_ingest_app
from hq.db import init_all_databases, get_sqlite_conn, register_guard, execute_query
from guard.config import GuardConfig
from guard.ledger import GuardLedger
from guard.outbox import GuardOutbox
from guard.thin_slice import GuardThinSlice


@pytest.fixture(autouse=True)
def setup_databases():
    init_all_databases()


def test_ledger_chain_and_gap_detection(tmp_path):
    db_file = str(tmp_path / "test_ledger.db")
    ledger = GuardLedger(db_path=db_file)

    # 1. First record must have seq=1 and prev_hash="GENESIS"
    body1 = '{"seq": 1, "test": "payload1"}'
    sha1 = "sha256:1111111111111111111111111111111111111111111111111111111111111111"
    ledger.record_payload(
        seq=1,
        payload_id="p-001",
        sha256=sha1,
        prev_hash="GENESIS",
        body=body1,
    )

    # 2. Recording seq=3 directly must fail with gap detection
    with pytest.raises(ValueError, match="Ledger sequence gap detected"):
        ledger.record_payload(
            seq=3,
            payload_id="p-003",
            sha256="sha256:3333",
            prev_hash=sha1,
            body="{}",
        )

    # 3. Recording wrong prev_hash must fail
    with pytest.raises(ValueError, match="Ledger hash chain mismatch"):
        ledger.record_payload(
            seq=2,
            payload_id="p-002",
            sha256="sha256:2222",
            prev_hash="WRONG_PREV",
            body="{}",
        )

    # 4. Valid seq 2
    body2 = '{"seq": 2, "test": "payload2"}'
    sha2 = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
    ledger.record_payload(
        seq=2,
        payload_id="p-002",
        sha256=sha2,
        prev_hash=sha1,
        body=body2,
    )

    last_seq, last_hash = ledger.get_last_seq_and_hash()
    assert last_seq == 2
    assert last_hash == sha2


def test_outbox_buffer_grows_when_ingest_stopped_and_drains_when_restored(tmp_path):
    db_file = str(tmp_path / "guard_test.db")
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = db_file
    cfg.TENANT_ID = "acme"
    unique_guard_id = f"guard-test-{uuid.uuid4().hex[:8]}"
    unique_secret = "sec-test-unique-key-2026"
    register_guard(guard_id=unique_guard_id, tenant_id="acme", hmac_secret=unique_secret)
    cfg.GUARD_ID = unique_guard_id
    cfg.GUARD_SECRET_KEY = unique_secret
    cfg.REGION_URL = "/ingest"

    healthy_shop = FastAPI()
    @healthy_shop.get("/health")
    def _h():
        return {"status": "ok"}

    with TestClient(healthy_shop) as probe_client:
        guard = GuardThinSlice(cfg=cfg)

        # Ingest is currently STOPPED / unreachable (no client provided)
        # 1. Collect window 1
        p1, b1 = guard.collect_window(duration_seconds=1.0, probe_client=probe_client)
        assert p1.seq == 1
        assert p1.prev_hash == "GENESIS"
        assert p1.health.buffer_depth == 0  # Initial depth before enqueue
        assert guard.outbox.get_buffer_depth() == 1

        # 2. Collect window 2 while ingest is down
        p2, b2 = guard.collect_window(duration_seconds=1.0, probe_client=probe_client)
        assert p2.seq == 2
        assert p2.prev_hash.startswith("sha256:")
        assert p2.health.buffer_depth == 1  # 1 item queued from before
        assert guard.outbox.get_buffer_depth() == 2

        # 3. Collect window 3 while ingest is down
        p3, b3 = guard.collect_window(duration_seconds=1.0, probe_client=probe_client)
        assert p3.seq == 3
        assert p3.health.buffer_depth == 2  # 2 items queued from before
        assert guard.outbox.get_buffer_depth() == 3

        # Confirm ledger state: 3 rows with status 'pending'
        rows = guard.ledger.get_all_rows()
        assert len(rows) == 3
        for r in rows:
            assert r["status"] == "pending"
            assert r["receipt_at"] is None

        # Verify hash chain continuity (no gaps)
        valid, err = guard.ledger.verify_chain()
        assert valid, f"Chain validation failed: {err}"

        # NOW INGEST RETURNS: Start ingest test server
        ingest_app = create_ingest_app(region="in")
        with TestClient(ingest_app, base_url="http://localhost:8001") as ingest_client:
            # Drain outbox to live Ingest
            sent_count, fail_count = guard.drain_outbox(client=ingest_client, ignore_backoff=True)
            assert fail_count == 0
            assert sent_count == 3

            # Buffer drains to 0
            assert guard.outbox.get_buffer_depth() == 0

            # Ledger updated: all marked stored with receipt timestamp
            updated_rows = guard.ledger.get_all_rows()
            assert len(updated_rows) == 3
            for r in updated_rows:
                assert r["status"] in ("stored", "duplicate")
                assert r["receipt_at"] is not None

            # Confirm Head Office DB has all 3 payloads stored
            db_rows = execute_query(
                "airlock_in",
                f"SELECT seq, payload_id FROM payloads WHERE guard_id = '{unique_guard_id}' ORDER BY seq ASC;",
            )
            assert len(db_rows) == 3
            db_seqs = [r["seq"] for r in db_rows]
            assert db_seqs == [1, 2, 3]  # Zero gaps!

            # Next window collected reflects buffer_depth == 0
            p4, b4 = guard.collect_window(duration_seconds=1.0, probe_client=probe_client)
            assert p4.health.buffer_depth == 0
            assert p4.seq == 4


def test_duplicate_receipt_and_no_resend_when_already_received(tmp_path):
    db_file = str(tmp_path / "guard_dup.db")
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = db_file
    cfg.TENANT_ID = "acme"
    unique_guard_id = f"guard-test-{uuid.uuid4().hex[:8]}"
    unique_secret = "sec-test-unique-key-2026"
    register_guard(guard_id=unique_guard_id, tenant_id="acme", hmac_secret=unique_secret)
    cfg.GUARD_ID = unique_guard_id
    cfg.GUARD_SECRET_KEY = unique_secret
    cfg.REGION_URL = "/ingest"

    healthy_shop = FastAPI()
    @healthy_shop.get("/health")
    def _h():
        return {"status": "ok"}

    with TestClient(healthy_shop) as probe_client:
        guard = GuardThinSlice(cfg=cfg)
        p, b = guard.collect_window(duration_seconds=1.0, probe_client=probe_client)

        ingest_app = create_ingest_app(region="in")
        with TestClient(ingest_app, base_url="http://localhost:8001") as ingest_client:
            # Send once -> receipt 'stored'
            receipt1 = guard.send_payload(p, b, client=ingest_client)
            assert receipt1 is not None
            assert receipt1.status == "stored"
            assert guard.outbox.get_buffer_depth() == 0

            # Mark in outbox as if re-queued
            guard.outbox.enqueue(seq=p.seq, payload_id=p.payload_id, sha256=f"sha256:{receipt1.sha256}", body=b.decode("utf-8"))
            # Drain: ledger already has it as stored, outbox removes it without resending!
            sent, failed = guard.drain_outbox(client=ingest_client, ignore_backoff=True)
            assert sent == 0
            assert guard.outbox.get_buffer_depth() == 0
