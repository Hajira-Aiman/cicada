"""
tests/test_executor_and_adapters.py
Automated Verification for:
1. T18 Remediation Executor with dry run, rate limiting (max 3 per 10m), rollback timer, and audit logging.
2. T17 Linux auth.log tailing (sshd Failed/Accepted password parsing).
3. T21 Contoso organizer-stream adapter.
"""

import time
import pytest
from contracts.models import ActionIntent
from guard.config import GuardConfig
from guard.thin_slice import GuardThinSlice
from guard.executor import RemediationExecutor
from guard.log_tailer import LogTailer
from guard.organizer_adapter import OrganizerAdapter


@pytest.fixture
def isolated_guard(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_exec.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r_exec.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev_exec.db")
    cfg.SHOP_LOG_PATH = str(tmp_path / "shop_exec.log")
    return GuardThinSlice(cfg=cfg)


def test_remediation_executor_dry_run_and_execution(isolated_guard):
    executor = RemediationExecutor(guard=isolated_guard)

    # 1. Register a fake process in reveal table
    proc_pseudo = isolated_guard.pseudonym_mgr.get_or_create("proc", "fake-miner")

    intent = ActionIntent(
        intent_id="intent-001",
        tenant_id="acme",
        action="kill_process",
        target=proc_pseudo,
        timestamp="2026-11-20T16:00:00Z",
        signature="sig-mock",
        rollback_window_s=120,
    )

    # Dry run test
    dry_result = executor.dry_run(intent)
    assert dry_result["dry_run"] is True
    assert dry_result["allowed"] is True
    assert "would kill process" in dry_result["description"]
    assert "fake-miner" in dry_result["description"]

    # Real execution
    exec_result = executor.execute(intent)
    assert exec_result["status"] == "executed"
    assert exec_result["rollback_window_s"] == 120

    # Verify audit row was logged locally
    with isolated_guard.pseudonym_mgr.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT action, details FROM local_audit WHERE action = 'action_executed:kill_process'")
        row = cur.fetchone()
        assert row is not None

    # Rollback execution
    rb_res = executor.rollback("intent-001")
    assert rb_res["status"] == "rolled_back"


def test_remediation_executor_rate_limiting(isolated_guard):
    executor = RemediationExecutor(guard=isolated_guard)

    # Execute 3 actions (allowed)
    for i in range(3):
        intent = ActionIntent(
            intent_id=f"intent-rate-{i}",
            tenant_id="acme",
            action="restart_service",
            target="proc-11223344",
            timestamp="2026-11-20T16:00:00Z",
            signature="sig-mock",
            rollback_window_s=120,
        )
        res = executor.execute(intent)
        assert res["status"] == "executed"

    # 4th action must be blocked by rate limit
    intent_4 = ActionIntent(
        intent_id="intent-rate-4",
        tenant_id="acme",
        action="restart_service",
        target="proc-11223344",
        timestamp="2026-11-20T16:00:00Z",
        signature="sig-mock",
        rollback_window_s=120,
    )
    res_4 = executor.execute(intent_4)
    assert res_4["status"] == "rejected"
    assert "rate limit exceeded" in res_4["reason"]


def test_linux_auth_log_sshd_tailing(isolated_guard, tmp_path):
    log_file = str(tmp_path / "auth.log")
    tailer = LogTailer(log_path=log_file, guard=isolated_guard)

    # Write Linux sshd auth.log failure and success lines
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("Nov 20 21:00:01 laptop4 sshd[1234]: Failed password for invalid user admin from 198.51.100.42 port 45231 ssh2\n")
        f.write("Nov 20 21:00:05 laptop4 sshd[1235]: Accepted password for ubuntu from 198.51.100.42 port 45232 ssh2\n")

    tailer.process_pending_logs()

    # Verify that failed and accepted logins were dispatched to the guard
    # The success after failures generates login_after_failures event
    events = [e.category for e in isolated_guard.pending_events]
    assert "login_after_failures" in events


def test_organizer_adapter_contoso(isolated_guard):
    adapter = OrganizerAdapter(guard=isolated_guard)

    # 1. Latency check event from organizer
    ok = adapter.process_organizer_event({
        "type": "latency_check",
        "latency_ms": 32.5,
        "status": "up",
    })
    assert ok is True

    # 2. App restart event from organizer
    ok2 = adapter.process_organizer_event({"type": "app_restarted"})
    assert ok2 is True
    assert any(e.category == "app_restarted" for e in isolated_guard.pending_events)

    # 3. Disallowed event rejected
    bad = adapter.process_organizer_event({"type": "random_unauthorized_noise"})
    assert bad is False


def test_guard_restart_continuity_no_gap_no_duplicate(tmp_path):
    """
    T17: Proves that killing and restarting a Guard continues its seq and prev_hash
    without 422, gaps, or duplicates.
    """
    db_file = str(tmp_path / "restart_guard.db")
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = db_file
    cfg.RAW_DB_PATH = str(tmp_path / "restart_raw.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "restart_rev.db")
    cfg.SHOP_LOG_PATH = str(tmp_path / "restart_shop.log")

    # Instance 1 runs for 3 windows
    guard1 = GuardThinSlice(cfg=cfg)
    p1, b1 = guard1.collect_window(duration_seconds=1.0)
    p2, b2 = guard1.collect_window(duration_seconds=1.0)
    p3, b3 = guard1.collect_window(duration_seconds=1.0)

    assert p1.seq == 1
    assert p2.seq == 2
    assert p3.seq == 3
    last_hash_before_kill = p3.prev_hash

    # Guard 1 is killed / terminated
    del guard1

    # Guard 2 starts up fresh with the same ledger DB
    guard2 = GuardThinSlice(cfg=cfg)
    assert guard2.seq == 4
    # Chained hash matches previous payload
    p4, b4 = guard2.collect_window(duration_seconds=1.0)
    assert p4.seq == 4
    assert p4.prev_hash.startswith("sha256:")

    # Verify cryptographic chain has zero gaps across the restart boundary
    valid, err = guard2.ledger.verify_chain()
    assert valid is True, f"Chain invalid after restart: {err}"
