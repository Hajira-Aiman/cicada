"""T4 checks. Run: AIRLOCK_USE_SQLITE=true python -m pytest tests/test_anomaly.py -q"""
import random
from hq.aiops.engine import Engine
from hq.aiops.anomaly import Detector, HST_THRESHOLD

T, S = "acme", "host-1"


def setup():
    random.seed(1)
    e = Engine()
    return e, Detector(e), [0.0]


def feed(e, d, clock, **over):
    clock[0] += 2
    m = {"cpu_pct": 21 + random.gauss(0, 0.3), "mem_pct": 45 + random.gauss(0, 0.2), "latency_ms": 60 + random.gauss(0, 0.5),
         "packet_loss_pct": 0.2, "net_out_kbps": 40 + random.gauss(0, 0.5), "service_up": 1.0}
    m.update(over)
    e.ingest(T, S, clock[0], clock[0], m)
    d.observe(T, S)
    return d.step(clock[0])


def warm(e, d, clock, n=60):
    for _ in range(n):
        feed(e, d, clock)


def run(e, d, clock, n, **over):
    out = []
    for _ in range(n):
        out += feed(e, d, clock, **over)
    return out


def test_one_or_two_blips_are_ignored():
    e, d, c = setup(); warm(e, d, c)
    assert run(e, d, c, 2, cpu_pct=95) == []
    assert run(e, d, c, 5) == []


def test_cpu_alone_is_usage_spike_info():
    e, d, c = setup(); warm(e, d, c)
    ch = run(e, d, c, 4, cpu_pct=95)
    assert [(k, a.kind, a.severity) for k, a in ch] == [("open", "usage_spike", "info")]
    assert ch[0][1].agrees and ch[0][1].second_opinion >= HST_THRESHOLD  # River agrees


def test_cpu_plus_latency_is_an_incident_candidate():
    e, d, c = setup(); warm(e, d, c)
    ch = run(e, d, c, 4, cpu_pct=95, latency_ms=450)
    assert ch[-1][1].kind == "incident_candidate" and ch[-1][1].severity == "high"
    assert {s["name"] for s in ch[-1][1].signals} >= {"cpu_pct", "latency_ms"}


def test_usage_spike_upgrades_when_latency_joins_then_closes_after_20s():
    e, d, c = setup(); warm(e, d, c)
    run(e, d, c, 4, cpu_pct=95)
    ch = run(e, d, c, 4, cpu_pct=95, latency_ms=450)
    assert [(k, a.kind) for k, a in ch] == [("update", "incident_candidate")]
    assert run(e, d, c, 5) == []                      # flags cleared < 20 s ago: still open
    ch = run(e, d, c, 8)
    assert [k for k, _ in ch] == ["close"]


def test_service_down_counts_as_error_for_cpu():
    e, d, c = setup(); warm(e, d, c)
    ch = run(e, d, c, 4, cpu_pct=95, service_up=0.0)
    assert ch[-1][1].kind == "incident_candidate"


def test_river_scores_normal_low_and_anomaly_high():
    e, d, c = setup(); warm(e, d, c, n=120)
    run(e, d, c, 1)
    assert d.score[(T, S)] < HST_THRESHOLD
    run(e, d, c, 1, cpu_pct=95, latency_ms=450)
    assert d.score[(T, S)] >= HST_THRESHOLD
