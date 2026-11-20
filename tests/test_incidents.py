"""T5/T6 checks. Run: AIRLOCK_USE_SQLITE=true python -m pytest tests/test_incidents.py -q"""
import random
from hq.aiops.engine import Engine
from hq.aiops.anomaly import Detector
from hq.aiops.incidents import Manager, related

T, S = "acme", "host-1"


class Rig:
    def __init__(self):
        random.seed(1)
        self.e = Engine(); self.d = Detector(self.e); self.m = Manager(self.e, self.d); self.t = 0.0
        self.log = []

    def feed(self, events=(), **over):
        self.t += 2
        v = {"cpu_pct": 21 + random.gauss(0, .3), "mem_pct": 45 + random.gauss(0, .2), "latency_ms": 60 + random.gauss(0, .5),
             "packet_loss_pct": 0.2, "net_out_kbps": 40 + random.gauss(0, .5), "service_up": 1.0}
        v.update(over)
        self.e.ingest(T, S, self.t, self.t, v, events)
        self.d.observe(T, S)
        self.d.step(self.t)
        self.log += self.m.step(self.t)

    def run(self, n, **kw):
        for _ in range(n):
            self.feed(**kw)

    def kinds(self):
        return [k for k, _ in self.log]


def warmed():
    r = Rig(); r.run(60)
    return r


def test_failed_login_burst_is_one_incident_with_a_repeat_counter():
    r = warmed()
    for _ in range(10):
        r.feed(events=[("auth_failure_burst", "high", 50)])
    assert r.kinds().count("open") == 1
    c = r.log[-1][1].to_contract()
    assert c.repeat_count == 10 and c.severity == "high" and "brute force" in c.title
    k = r.m.counters(T)
    assert k["raw_alerts"] == 10 and k["incidents"] == 1 and k["noise_cut_pct"] == 90.0


def test_cpu_alone_is_a_raw_alert_but_no_incident():
    r = warmed(); r.run(6, cpu_pct=95)
    assert r.kinds() == [] and r.m.counters(T)["raw_alerts"] == 1 and r.m.counters(T)["incidents"] == 0


def test_cpu_plus_latency_incident_contributions_and_confidence_by_hand():
    r = warmed(); r.run(6, cpu_pct=95, latency_ms=450)
    c = r.log[-1][1].to_contract()
    assert {s.name for s in c.signals} == {"cpu_pct", "latency_ms"}
    assert abs(sum(s.contribution_pct for s in c.signals) - 100) < 0.2
    z = {s.name: abs(s.z) for s in c.signals}
    assert abs([s for s in c.signals if s.name == "cpu_pct"][0].contribution_pct - 100 * z["cpu_pct"] / sum(z.values())) < 0.2
    # 2 signals, +1 if River agrees, + 0.1 named rule (cpu_with_latency_or_errors)
    agreeing = 2 + (1 if r.m.open[T].river else 0)
    assert c.confidence == round(min(0.4 + 0.15 * agreeing + 0.1, 0.95), 2)
    assert c.reasoning_path[-1].startswith("confidence = 0.4 + 0.15 x")


def test_confidence_is_capped_at_95():
    r = warmed()
    for _ in range(4):
        r.feed(events=[("auth_failure_burst", "high", 50), ("honeypot_hit", "critical", 1), ("service_down", "high", 1)],
               cpu_pct=95, latency_ms=450, service_up=0.0)
    c = r.log[-1][1].to_contract()
    assert c.confidence == 0.95 and c.severity == "critical"


def test_related_signals_join_within_120s_but_not_after():
    r = warmed()
    r.feed(events=[("auth_failure_burst", "high", 50)])
    r.run(10, cpu_pct=95, latency_ms=450)            # login component + shop-api component are related
    assert r.kinds().count("open") == 1
    r.run(70)                                        # silence > 120 s total
    assert "close" in r.kinds()
    r.feed(events=[("auth_failure_burst", "high", 50)])
    assert r.kinds().count("open") == 2


def test_topology_relation():
    assert related("host", "login") and not related("host", "billing")
