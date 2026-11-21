"""T9 checks. Run: python -m pytest tests/test_t9.py -q"""
from hq.aiops.engine import Engine
from hq.aiops.incidents import damage_map


def feed(e, vals, t0=1000.0):
    for i, v in enumerate(vals):
        e.ingest("acme", "host-1", t0 + 2 * i, t0 + 2 * i, {"cpu_pct": v})
    return e.src[("acme", "host-1")].z["cpu_pct"]


def test_thumbs_down_raises_the_flag_level_for_30_minutes():
    # steady 20 +- tiny noise, then a value ~3.2 sigma away (cpu std floor = 3.0, see engine.STD_FLOOR)
    base = [20.0 + (0.1 if i % 2 else -0.1) for i in range(40)]
    plain, damped = Engine(), Engine()
    damped.thumbs_down("acme", "host-1", "cpu_pct", now=1000.0)
    feed(plain, base + [29.6] * 3); feed(damped, base + [29.6] * 3)
    assert plain.base[("acme", "host-1", "cpu_pct")].streak == 3       # flagged
    assert damped.base[("acme", "host-1", "cpu_pct")].streak == 0      # 3.2 < 3.5, not flagged
    feed(damped, [45.0] * 3, t0=1200.0)
    assert damped.base[("acme", "host-1", "cpu_pct")].streak == 3      # real anomaly still flags
    e = Engine(); e.thumbs_down("acme", "host-1", "cpu_pct", now=1000.0)
    feed(e, base, t0=1000.0 + 1900)                                    # after 30 min: back to 3.0
    feed(e, [29.6] * 3, t0=1000.0 + 1900 + 100)
    assert e.base[("acme", "host-1", "cpu_pct")].streak == 3


def test_damage_map_lights_dependents():
    st = {n["id"]: n["state"] for n in damage_map({"db"})["nodes"]}
    assert st == {"db": "affected", "shop-api": "impacted", "checkout": "impacted", "login": "impacted", "host": "ok"}
    assert {n["state"] for n in damage_map(set())["nodes"]} == {"ok"}
