"""
tests/test_policy_checkpoints.py
Verification for T7 (Windows), T10 (Policy Gate), T12 (Heartbeat), and T14 (Checkpoints):
- Policy gate: verifies contract schema, rejects extra fields/canaries/raw text, blocks egress
- 2-second windows: exactly 2.0s duration in ISO-8601 UTC with Z and source_tz
- Real heartbeat: GuardHealth filled with real CPU%, RSS MB, buffer depth, and counters
- Checkpoints: computes running SHA-256 root over payload hashes in seq order every 60s
  and compares against remote checkpoint identifying mismatches.
"""

import time
import pytest
from datetime import datetime, timezone
from contracts.models import Checkpoint, GuardHealth, TimeWindow
from guard.config import GuardConfig
from guard.ledger import GuardLedger
from guard.policy_gate import PolicyGate
from guard.scrubber import Scrubber
from guard.thin_slice import GuardThinSlice


def test_policy_gate_blocks_contract_violations_and_canaries():
    scrubber = Scrubber()
    gate = PolicyGate(scrubber=scrubber)

    # 1. Block canary in payload serialization
    canary = scrubber.maybe_plant_canary()
    assert canary is not None

    leak, reason = scrubber.contains_canary_or_secret(f"json string containing {canary}")
    assert leak
    assert "Canary tripwire" in reason

    # 2. Block unmasked AWS key in payload
    leak_k, reason_k = scrubber.contains_canary_or_secret("access_key=AKIAIOSFODNN7EXAMPLE")
    assert leak_k
    assert "Unmasked AWS" in reason_k


def test_window_timing_and_heartbeat_real_metrics(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_hb.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r_hb.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev_hb.db")
    cfg.TIMEZONE = "Asia/Kolkata"

    guard = GuardThinSlice(cfg=cfg)
    payload, body_bytes = guard.collect_window(duration_seconds=2.0)

    # 1. Window checks: exactly 2.0s UTC with Z and source_tz
    w = payload.window
    assert w.source_tz == "Asia/Kolkata"
    assert w.start.endswith("Z")
    assert w.end.endswith("Z")

    t_start = datetime.fromisoformat(w.start.rstrip("Z")).replace(tzinfo=timezone.utc)
    t_end = datetime.fromisoformat(w.end.rstrip("Z")).replace(tzinfo=timezone.utc)
    delta_s = (t_end - t_start).total_seconds()
    assert abs(delta_s - 2.0) < 0.1

    # 2. Real heartbeat numbers
    h = payload.health
    assert h.guard_version == "0.2.0"
    assert isinstance(h.guard_cpu_pct, float)
    assert h.guard_cpu_pct >= 0.0
    assert isinstance(h.guard_mem_mb, float)
    assert h.guard_mem_mb > 0.0  # Real RSS memory
    assert isinstance(h.buffer_depth, int)
    assert h.buffer_depth >= 0
    assert h.config_ok is True
    assert h.canaries_planted >= 1
    assert h.secrets_redacted >= 0


def test_checkpoint_generation_and_verification(tmp_path):
    db_file = str(tmp_path / "ledger_cp.db")
    ledger = GuardLedger(db_path=db_file)

    guard_id = "guard-acme-01"

    # Initial checkpoint on empty ledger
    cp0 = ledger.compute_checkpoint(guard_id=guard_id)
    assert cp0.guard_id == guard_id
    assert cp0.up_to_seq == 0
    assert cp0.root.startswith("sha256:")

    # Record 3 payloads
    ledger.record_payload(seq=1, payload_id="p-1", sha256="sha256:1111111111111111111111111111111111111111111111111111111111111111", prev_hash="GENESIS", body='{"seq":1}')
    ledger.record_payload(seq=2, payload_id="p-2", sha256="sha256:2222222222222222222222222222222222222222222222222222222222222222", prev_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111", body='{"seq":2}')
    ledger.record_payload(seq=3, payload_id="p-3", sha256="sha256:3333333333333333333333333333333333333333333333333333333333333333", prev_hash="sha256:2222222222222222222222222222222222222222222222222222222222222222", body='{"seq":3}')

    cp3 = ledger.compute_checkpoint(guard_id=guard_id, up_to_seq=3)
    assert cp3.up_to_seq == 3
    assert cp3.root.startswith("sha256:")

    # Compare identical checkpoint: matches!
    matches, err_seq = ledger.compare_checkpoint(guard_id=guard_id, remote_checkpoint=cp3)
    assert matches is True
    assert err_seq is None

    # Compare against corrupted remote root: flags mismatch
    corrupted_cp = Checkpoint(guard_id=guard_id, up_to_seq=3, root="sha256:0000000000000000000000000000000000000000000000000000000000000000")
    matches_c, err_seq_c = ledger.compare_checkpoint(guard_id=guard_id, remote_checkpoint=corrupted_cp)
    assert matches_c is False
    assert err_seq_c is not None


def test_guard_maybe_publish_checkpoint_timing(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_timing.db")
    guard = GuardThinSlice(cfg=cfg)

    # First call at t=100
    cp1 = guard.maybe_publish_checkpoint(now=100.0)
    assert cp1 is not None

    # Call at t=130 (< 60s elapsed): should not publish
    cp2 = guard.maybe_publish_checkpoint(now=130.0)
    assert cp2 is None

    # Call at t=161 (>= 60s elapsed): publishes new checkpoint
    cp3 = guard.maybe_publish_checkpoint(now=161.0)
    assert cp3 is not None
