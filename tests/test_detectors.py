"""
tests/test_detectors.py
Verification for T9, T13, and T19 Local Security & Change Detectors:
- 50 wrong passwords produce exactly one auth_failure_burst with count=50, severity=high, and no usernames/IPs
- Successful login after failures -> login_after_failures
- Odd hour login (03:00 shop time) -> odd_hour_login
- Trap user 'admin_backup' -> honeypot_hit (severity=critical)
- Charger unplugged -> power_on_battery event + battery_pct, on_battery, battery_min_left metrics
- Restarting shop-api produces app_restarted in next payload
- Changing .env produces config_changed in next payload
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

from guard.config import GuardConfig
from guard.detectors import AuthDetector, PowerDetector, ChangeDetector
from guard.pseudonym import PseudonymManager
from guard.thin_slice import GuardThinSlice


def test_auth_burst_50_wrong_passwords_produces_one_burst_event(tmp_path):
    reveal_db = str(tmp_path / "reveal_auth.db")
    mgr = PseudonymManager(tenant_secret="secret-salt-test", db_path=reveal_db)
    detector = AuthDetector(pseudonym_mgr=mgr, tenant_tz_str="Asia/Kolkata")

    service_pseudo = "proc-11223344"
    attacker_ip = "198.51.100.42"

    # 1. Loop with 0.6s sleeps between 50 logins (simulated)
    now = time.time()
    for i in range(50):
        events = detector.record_login(
            raw_username=f"user_{i}",
            raw_ip=attacker_ip,
            success=False,
            service_pseudonym=service_pseudo,
            timestamp=now + (i * 0.6),
        )
        assert len(events) == 0  # Bursts are evaluated per window

    last_attempt_ts = now + (49 * 0.6)

    # Mid-burst check (while still ongoing, e.g. 1s after last failure; quiet_time < 4.0s):
    # must NOT prematurely emit
    mid_burst = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=last_attempt_ts + 1.0)
    assert len(mid_burst) == 0

    # 2. Evaluate burst at completion (4s quiet window elapsed: quiet_time >= 4.0s):
    # must produce EXACTLY ONE auth_failure_burst with count=50
    burst_events = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=last_attempt_ts + 4.1)
    assert len(burst_events) == 1
    ev = burst_events[0]
    assert ev.category == "auth_failure_burst"
    assert ev.severity == "high"
    assert ev.count == 50
    assert ev.actor.startswith("src-")
    assert attacker_ip not in ev.actor  # Zero raw IPs
    assert "user_" not in ev.actor  # Zero usernames

    # Subsequent evaluation in same window produces no duplicate
    second_eval = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=last_attempt_ts + 5.0)
    assert len(second_eval) == 0


def test_auth_burst_29_wrong_passwords_produces_none(tmp_path):
    reveal_db = str(tmp_path / "reveal_auth_29.db")
    mgr = PseudonymManager(tenant_secret="secret-salt-test", db_path=reveal_db)
    detector = AuthDetector(pseudonym_mgr=mgr, tenant_tz_str="Asia/Kolkata")

    service_pseudo = "proc-11223344"
    attacker_ip = "198.51.100.43"

    now = time.time()
    for i in range(29):
        detector.record_login(
            raw_username=f"user_{i}",
            raw_ip=attacker_ip,
            success=False,
            service_pseudonym=service_pseudo,
            timestamp=now + (i * 0.6),
        )

    last_attempt_ts = now + (28 * 0.6)
    # After 4s quiet period, 29 failures (< 30) must give none
    burst_events = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=last_attempt_ts + 4.1)
    assert len(burst_events) == 0


def test_auth_burst_two_bursts_10s_apart_gives_two_events(tmp_path):
    reveal_db = str(tmp_path / "reveal_auth_two.db")
    mgr = PseudonymManager(tenant_secret="secret-salt-test", db_path=reveal_db)
    detector = AuthDetector(pseudonym_mgr=mgr, tenant_tz_str="Asia/Kolkata")

    service_pseudo = "proc-11223344"
    attacker_ip = "198.51.100.44"

    # Burst 1: 35 logins with 0.5s intervals
    t0 = 1000.0
    for i in range(35):
        detector.record_login(
            raw_username=f"user_b1_{i}",
            raw_ip=attacker_ip,
            success=False,
            service_pseudonym=service_pseudo,
            timestamp=t0 + (i * 0.5),
        )

    end_b1 = t0 + (34 * 0.5)
    # 4.1s quiet period finishes Burst 1
    ev1 = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=end_b1 + 4.1)
    assert len(ev1) == 1
    assert ev1[0].count == 35

    # 10s gap after burst 1 finishes
    t_gap = end_b1 + 4.1 + 10.0

    # Burst 2: 40 logins with 0.5s intervals
    for i in range(40):
        detector.record_login(
            raw_username=f"user_b2_{i}",
            raw_ip=attacker_ip,
            success=False,
            service_pseudonym=service_pseudo,
            timestamp=t_gap + (i * 0.5),
        )

    end_b2 = t_gap + (39 * 0.5)
    # 4.1s quiet period finishes Burst 2
    ev2 = detector.evaluate_bursts(service_pseudonym=service_pseudo, now=end_b2 + 4.1)
    assert len(ev2) == 1
    assert ev2[0].count == 40


def test_honeypot_and_login_after_failures_and_odd_hour(tmp_path):
    reveal_db = str(tmp_path / "reveal_sec.db")
    mgr = PseudonymManager(tenant_secret="secret-salt-test", db_path=reveal_db)
    detector = AuthDetector(pseudonym_mgr=mgr, tenant_tz_str="Asia/Kolkata")
    service_pseudo = "proc-11223344"

    # 1. Honeypot hit with trap user 'admin_backup'
    ev_honey = detector.record_login(
        raw_username="admin_backup",
        raw_ip="203.0.113.9",
        success=False,
        service_pseudonym=service_pseudo,
    )
    assert len(ev_honey) == 1
    assert ev_honey[0].category == "honeypot_hit"
    assert ev_honey[0].severity == "critical"
    assert ev_honey[0].actor.startswith("src-")

    # 2. Login after failures
    # First a failure
    detector.record_login(raw_username="bob", raw_ip="203.0.113.10", success=False, service_pseudonym=service_pseudo)
    # Then a success from same IP
    ev_recover = detector.record_login(raw_username="bob", raw_ip="203.0.113.10", success=True, service_pseudonym=service_pseudo)
    assert any(e.category == "login_after_failures" for e in ev_recover)

    # 3. Odd hour login (03:15 Asia/Kolkata)
    tz = ZoneInfo("Asia/Kolkata")
    odd_dt = datetime(2026, 11, 21, 3, 15, 0, tzinfo=tz)
    odd_ts = odd_dt.timestamp()

    ev_odd = detector.record_login(
        raw_username="charlie",
        raw_ip="203.0.113.11",
        success=True,
        service_pseudonym=service_pseudo,
        timestamp=odd_ts,
    )
    assert any(e.category == "odd_hour_login" for e in ev_odd)


def test_power_detector_charger_unplugged():
    host_pseudo = "host-aabbccdd"
    detector = PowerDetector(host_pseudonym=host_pseudo)

    # Initially plugged in
    detector.set_override(percent=95.0, power_plugged=True, secsleft=7200)
    m1, e1 = detector.check_power()
    assert len(e1) == 0
    m_map1 = {m.name: m.avg for m in m1}
    assert m_map1["on_battery"] == 0.0
    assert m_map1["battery_pct"] == 95.0

    # Charger unplugged!
    detector.set_override(percent=94.0, power_plugged=False, secsleft=3600)
    m2, e2 = detector.check_power()
    assert len(e2) == 1
    assert e2[0].category == "power_on_battery"
    assert e2[0].severity == "high"

    m_map2 = {m.name: m.avg for m in m2}
    assert m_map2["on_battery"] == 1.0
    assert m_map2["battery_pct"] == 94.0
    assert m_map2["battery_min_left"] == 60.0  # 3600s / 60


def test_guard_app_restarted_and_config_changed_in_payload(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("TENANT_ID=acme\nPOLICY_VERSION=v1\n")

    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev.db")

    guard = GuardThinSlice(cfg=cfg)
    guard.change_detector.env_path = str(env_file)
    guard.change_detector.last_env_hash = guard.change_detector._compute_env_hash()

    # 1. First notify of shop process
    guard.notify_shop_process(pid=1001, create_time=1700000000.0)
    p1, _ = guard.collect_window(duration_seconds=1.0)
    cats1 = [e.category for e in p1.events]
    assert "app_restarted" not in cats1

    # 2. Restart shop-api with new PID
    guard.notify_shop_process(pid=1002, create_time=1700000050.0)
    p2, _ = guard.collect_window(duration_seconds=1.0)
    cats2 = [e.category for e in p2.events]
    assert "app_restarted" in cats2

    # 3. Modify .env
    env_file.write_text("TENANT_ID=acme\nPOLICY_VERSION=v2\n")
    p3, _ = guard.collect_window(duration_seconds=1.0)
    cats3 = [e.category for e in p3.events]
    assert "config_changed" in cats3
