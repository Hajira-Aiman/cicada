import pytest
from hq.aiops.baseline import EWMABaselineManager, MetricStreamBaseline
from hq.aiops.health import HealthEngine, SourceHealthTracker


def test_baseline_warmup_and_consecutive_flagging():
    baseline = MetricStreamBaseline(alpha=0.1, warmup_points=10)

    # Feed 10 baseline samples around 20.0
    for _ in range(10):
        mean, z, flagged = baseline.update(20.0)
        assert not flagged

    assert baseline.is_warmed_up
    assert baseline.consecutive_anomalies == 0

    # First spike to 95.0 -> high z, but should NOT flag on step 1
    mean, z1, flagged1 = baseline.update(95.0)
    assert abs(z1) >= 3.0
    assert not flagged1
    assert baseline.consecutive_anomalies == 1

    # Second spike to 95.0 -> should NOT flag on step 2
    mean, z2, flagged2 = baseline.update(95.0)
    assert not flagged2
    assert baseline.consecutive_anomalies == 2

    # Third consecutive spike -> MUST flag on step 3!
    mean, z3, flagged3 = baseline.update(95.0)
    assert flagged3
    assert baseline.consecutive_anomalies == 3

    # Recovery sample resets consecutive counter
    mean, z4, flagged4 = baseline.update(20.0)
    assert not flagged4
    assert baseline.consecutive_anomalies == 0


def test_baseline_thumbs_down_feedback():
    baseline = MetricStreamBaseline(alpha=0.1, warmup_points=5)
    for _ in range(5):
        baseline.update(50.0)

    assert baseline.active_z_threshold == 3.0
    baseline.apply_feedback_thumbs_down(duration_s=60.0)
    assert baseline.active_z_threshold == 3.5


def test_health_hysteresis_and_flaps_prevented():
    engine = HealthEngine()
    tenant = "globex"
    source = "host-7f3a1234"
    t0 = 1700000000.0

    # 1. Normal baseline -> Excellent
    state = engine.process_window(
        tenant_id=tenant,
        source=source,
        now_epoch=t0,
        metrics_by_name={"cpu_pct": 25.0, "latency_ms": 15.0},
        metric_z_scores={"cpu_pct": 0.2},
        flagged_anomalies=set(),
        event_categories=[],
    )
    assert state == "Excellent"
    assert engine.total_flaps_prevented == 0

    # 2. Transient spike (step 1) -> should remain Excellent due to hysteresis
    state = engine.process_window(
        tenant_id=tenant,
        source=source,
        now_epoch=t0 + 2.0,
        metrics_by_name={"cpu_pct": 98.0},
        metric_z_scores={"cpu_pct": 5.0},
        flagged_anomalies={"cpu_pct"},
        event_categories=[],
    )
    assert state == "Excellent"
    assert engine.total_flaps_prevented == 1

    # Step 2 -> still Excellent
    state = engine.process_window(
        tenant_id=tenant,
        source=source,
        now_epoch=t0 + 4.0,
        metrics_by_name={"cpu_pct": 98.0},
        metric_z_scores={"cpu_pct": 5.0},
        flagged_anomalies={"cpu_pct"},
        event_categories=[],
    )
    assert state == "Excellent"
    assert engine.total_flaps_prevented == 2

    # Step 3 (6s sustained) -> Must transition to Fair!
    state = engine.process_window(
        tenant_id=tenant,
        source=source,
        now_epoch=t0 + 6.0,
        metrics_by_name={"cpu_pct": 98.0},
        metric_z_scores={"cpu_pct": 5.0},
        flagged_anomalies={"cpu_pct"},
        event_categories=[],
    )
    assert state == "Fair"


def test_health_stale_data_handling():
    engine = HealthEngine()
    tenant = "globex"
    source = "host-7f3a1234"
    t0 = 1700000000.0

    # Initial data
    engine.process_window(
        tenant_id=tenant,
        source=source,
        now_epoch=t0,
        metrics_by_name={"cpu_pct": 20.0},
        metric_z_scores={},
        flagged_anomalies=set(),
        event_categories=[],
    )

    # 12 seconds pass without data -> Stale data (Fair)
    tracker = engine.get_or_create(tenant, source)
    stale_state = tracker.evaluate(
        now_epoch=t0 + 12.0,
        metrics_by_name={},
        metric_z_scores={},
        flagged_anomalies=set(),
        event_categories=[],
    )
    # Trigger 3 times for hysteresis
    tracker.evaluate(t0 + 14.0, {}, {}, set(), [])
    confirmed_stale = tracker.evaluate(t0 + 16.0, {}, {}, set(), [])
    assert confirmed_stale == "Fair"
    assert any("Stale data" in r for r in tracker.last_transition_reasons)

    # 35 seconds pass -> Offline (Poor)
    tracker.evaluate(t0 + 36.0, {}, {}, set(), [])
    tracker.evaluate(t0 + 38.0, {}, {}, set(), [])
    confirmed_offline = tracker.evaluate(t0 + 40.0, {}, {}, set(), [])
    assert confirmed_offline == "Poor"
    assert any("offline" in r for r in tracker.last_transition_reasons)
