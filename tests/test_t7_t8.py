"""T7/T8 checks: kill chain, counterfactual, runbook, scheduled jobs, change linking.
Run: AIRLOCK_USE_SQLITE=true python -m pytest tests/test_t7_t8.py -q"""
import random
from hq.aiops.engine import Engine
from hq.aiops.anomaly import Detector
from hq.aiops.incidents import Manager

T, S = "acme", "host-1"
ATK, PROC = "src-9c2e0011", "proc-1a2b3c4d"


class Rig:
    def __init__(self):
        random.seed(1)
        self.e = Engine(); self.d = Detector(self.e); self.m = Manager(self.e, self.d); self.t = 0.0
        self.log, self.alerts = [], []

    def feed(self, events=(), **over):
        self.t += 2
        v = {"cpu_pct": 21 + random.gauss(0, .3), "mem_pct": 45 + random.gauss(0, .2), "latency_ms": 60 + random.gauss(0, .5),
             "packet_loss_pct": 0.2, "net_out_kbps": 40 + random.gauss(0, .5), "service_up": 1.0}
        v.update(over)
        self.e.ingest(T, S, self.t, self.t, v, events)
        self.d.observe(T, S)
        self.alerts += self.d.step(self.t)
        self.log += self.m.step(self.t)

    def run(self, n, **kw):
        for _ in range(n):
            self.feed(**kw)

    def inc(self):
        return self.m.open[T].to_contract()


def warmed():
    r = Rig(); r.run(60)
    return r


def kill_chain(r):
    for _ in range(2): r.feed(events=[("auth_failure_burst", "high", 50, ATK)])
    r.run(2)
    r.feed(events=[("login_after_failures", "high", 1, ATK)])
    r.run(2)
    r.feed(cpu_pct=96, net_out_kbps=900, events=[("new_process", "medium", 1, PROC)])
    r.run(5, cpu_pct=96, net_out_kbps=900)


def test_kill_chain_four_alerts_become_one_critical_incident():
    r = warmed(); kill_chain(r)
    c = r.inc()
    assert c.title == "Possible compromise: cryptomining" and c.severity == "critical"
    assert r.m.counters(T)["incidents"] == 1
    path = " | ".join(c.reasoning_path)
    for step in ("login failure burst", "login succeeded after failures", "CPU anomaly", "outbound traffic anomaly", "rule matched: kill_chain"):
        assert step in path
    assert path.index("login failure burst") < path.index("login succeeded") < path.index("CPU anomaly")


def test_kill_chain_needs_the_right_order():
    r = warmed()
    r.feed(cpu_pct=96, net_out_kbps=900); r.run(5, cpu_pct=96, net_out_kbps=900)   # cpu+net first, no login burst before
    r.run(10)
    for _ in range(2): r.feed(events=[("auth_failure_burst", "high", 50, ATK)])
    assert all("Possible compromise" not in i.title() for i in [r.m.open[T]])


def test_counterfactual_and_runbook_for_kill_chain():
    r = warmed(); kill_chain(r)
    c = r.inc()
    assert "this would be Fair, not Poor" in c.counterfactual
    rec = c.recommendation
    assert (rec.action, rec.target, rec.risk, rec.reversible) == ("kill_process", PROC, "low", True) and rec.rollback


def test_runbook_for_each_incident_type():
    r = warmed()
    for _ in range(3): r.feed(events=[("auth_failure_burst", "high", 50, ATK)])
    assert (r.inc().recommendation.action, r.inc().recommendation.target) == ("block_source", ATK)
    assert "15 min" in r.inc().recommendation.rollback
    r = warmed(); r.run(4, latency_ms=450)
    assert r.m.open[T].to_contract().recommendation.action == "investigate"
    r = warmed(); r.feed(events=[("service_down", "high", 1, None)]); r.feed(events=[("service_down", "high", 1, None)])
    assert r.inc().recommendation.action == "restart_service"
    r = warmed(); r.feed(events=[("honeypot_hit", "critical", 1, ATK)])
    assert (r.inc().recommendation.action, r.inc().severity) == ("block_source", "critical")


def test_scheduled_job_alerts_three_times_then_is_suppressed_and_off_schedule_still_alerts():
    r = warmed()
    for _ in range(5):
        r.run(4, cpu_pct=80)       # an 8 s spike ...
        r.run(26)                  # ... every 60 s
    opened = [a.kind for k, a in r.alerts if k == "open"]
    assert opened == ["usage_spike"] * 3 + ["scheduled_job"] * 2
    sched = [a for k, a in r.alerts if k == "open" and a.kind == "scheduled_job"][0]
    assert sched.severity == "info" and "every ~60 s" in sched.title and "suppressed" in sched.suppressed_reason
    assert r.log == []             # none of them opened an incident
    r.run(14)                      # wait 28 s longer than the 60 s period, then spike: off schedule
    r.run(4, cpu_pct=80)
    r.run(20)
    assert [a.kind for k, a in r.alerts if k == "open"][-1] == "usage_spike"


def test_change_just_before_is_linked_and_adds_confidence():
    r = warmed()
    r.feed(events=[("app_restarted", "info", 1, None)])
    r.run(20)
    r.run(4, cpu_pct=95, latency_ms=450)
    c = r.inc()
    assert len(c.changes_before) == 1 and c.changes_before[0].startswith("started ") and "after the app restarted" in c.changes_before[0]
    assert "+ 0.1 change bonus" in c.reasoning_path[-1]
    base = warmed(); base.run(4, cpu_pct=95, latency_ms=450)
    assert c.confidence >= base.inc().confidence and r.m.open[T].changes
    r2 = warmed(); r2.feed(events=[("app_restarted", "info", 1, None)]); r2.run(160)    # 5+ min old change is not linked
    r2.run(4, cpu_pct=95, latency_ms=450)
    assert r2.inc().changes_before == []


def test_a_closed_kill_chain_incident_is_not_reopened_by_the_same_chain():
    r = warmed(); kill_chain(r)
    r.run(70)                               # >120 s of silence closes the incident
    assert "close" in [k for k, _ in r.log]
    r.run(40)                               # stage times are still < 10 min old
    assert r.m.counters(T)["incidents"] == 1 and [k for k, _ in r.log].count("open") == 1
