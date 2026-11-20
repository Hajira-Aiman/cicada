"""Run: .venv/Scripts/python -m pytest tests -q"""
import random
from hq.aiops.engine import Engine, Thresholds

T, S = "acme", "host-1"


def feed(e, t, **over):
    m = {"cpu_pct": 21 + random.gauss(0, 0.3), "mem_pct": 45.0, "latency_ms": 60 + random.gauss(0, 0.5),
         "packet_loss_pct": 0.2, "net_out_kbps": 40.0, "service_up": 1.0}
    m.update(over)
    e.ingest(T, S, t, t, m)


def warm(e, n=40):
    random.seed(1)
    for i in range(n):
        feed(e, i * 2.0)
        e.evaluate(i * 2.0)
    return (n - 1) * 2.0


def state(e): return e.src[(T, S)].committed


def test_stale_then_offline():
    e = Engine(); t = warm(e)
    assert state(e) == "excellent"
    e.evaluate(t + 9);  assert state(e) == "excellent"
    ch = e.evaluate(t + 10); assert state(e) == "fair" and "no data for 10 s" in ch[0].reasons[0]
    ch = e.evaluate(t + 30); assert state(e) == "poor" and ch[0].old_state == "fair"


def test_enter_needs_6s_and_exit_needs_20s():
    e = Engine(); t = warm(e)
    for i in range(1, 3):  # 2 s of high latency: not enough
        t += 2; feed(e, t, latency_ms=450); e.evaluate(t)
    assert state(e) == "excellent"
    for i in range(3): t += 2; feed(e, t, latency_ms=450); e.evaluate(t)
    assert state(e) == "fair"
    for i in range(9): t += 2; feed(e, t); e.evaluate(t)  # 18 s good: still fair
    assert state(e) == "fair"
    t += 2; feed(e, t); e.evaluate(t); t += 2; feed(e, t); e.evaluate(t)
    assert state(e) == "excellent"


def test_blip_is_a_prevented_flap():
    e = Engine(); t = warm(e)
    t += 2; feed(e, t, latency_ms=450); e.evaluate(t)
    t += 2; feed(e, t); e.evaluate(t)
    assert state(e) == "excellent" and e.src[(T, S)].flaps == 1


def test_z_streak_and_poor_and_overrides():
    e = Engine(); t = warm(e)
    for i in range(8): t += 2; feed(e, t, cpu_pct=70); e.evaluate(t)  # +49 sigma, below the 85 % limit
    assert state(e) == "fair" and "sigma" in e.src[(T, S)].reasons[0]
    e2 = Engine(lambda tenant: Thresholds.with_overrides({"latency_fair": 100}))
    t = warm(e2)
    for i in range(4): t += 2; feed(e2, t, latency_ms=150); e2.evaluate(t)
    assert state(e2) == "fair"
    e3 = Engine(); t = warm(e3)
    for i in range(4): t += 2; feed(e3, t, service_up=0.0); e3.evaluate(t)
    assert state(e3) == "poor"
