"""Regression checks for the deep-review fixes (log tailer, scrubber, pseudonyms, send timestamp)."""
from guard.log_tailer import LogTailer
from guard.pseudonym import PseudonymManager
from guard.scrubber import Scrubber


def test_tailer_waits_for_full_line_and_survives_truncation(tmp_path):
    p = tmp_path / "shop.log"
    t = LogTailer(log_path=str(p))
    p.write_bytes(b'{"a":1}\n{"b"')
    assert t.read_new_lines() == ['{"a":1}']          # half-written line not consumed
    with open(p, "ab") as f:
        f.write(b':2}\n')
    assert t.read_new_lines() == ['{"b":2}']
    p.write_bytes(b"fresh\n")                           # rotated/truncated, shorter than offset
    assert t.read_new_lines() == ["fresh"]


def test_scrubber_masks_json_and_kv_passwords_on_one_line():
    out, n = Scrubber().scrub_text('{"password": "a1"} then password=b2')
    assert "a1" not in out and "b2" not in out and n == 2


def test_pseudonym_get_or_create_keeps_first_created_at():
    m = PseudonymManager(tenant_secret="s", db_path=":memory:")
    ps = m.get_or_create("src", "1.2.3.4")
    first = m.get_all_reveals()[0]["created_at"]
    assert m.get_or_create("src", "1.2.3.4") == ps
    assert m.get_all_reveals()[0]["created_at"] == first


def test_tailer_resumes_after_restart_instead_of_replaying(tmp_path):
    p = tmp_path / "shop.log"
    p.write_bytes(b"old1\nold2\n")
    assert LogTailer(log_path=str(p)).read_new_lines() == ["old1", "old2"]        # first ever run reads history once
    p.write_bytes(b"old1\nold2\nnew\n")
    assert LogTailer(log_path=str(p)).read_new_lines() == ["new"]                  # restart: only what is new


def test_tailer_skips_history_when_guard_ran_before_but_has_no_saved_position(tmp_path):
    p = tmp_path / "shop.log"
    p.write_bytes(b"old\n")
    t = LogTailer(log_path=str(p), start_at_end=True)
    assert t.read_new_lines() == []
    p.write_bytes(b"old\nnew\n")
    assert t.read_new_lines() == ["new"]


def test_engine_retires_silent_sources_only():
    from hq.aiops.engine import Engine
    e = Engine()
    e.ingest("acme", "host-old", 1000.0, 1000.0, {"cpu_pct": 10.0})
    e.ingest("acme", "host-live", 1590.0, 1590.0, {"cpu_pct": 10.0})
    assert e.retire(1599.0) == []                      # old one silent 599 s: still shown (offline)
    assert e.retire(1601.0) == [("acme", "host-old")]  # 601 s: forgotten, with its baselines
    assert ("acme", "host-live") in e.src and not any(k[1] == "host-old" for k in e.base)


def test_packet_loss_probe_counts_refused_connections_and_is_fast():
    import socket, time
    from guard.thin_slice import GuardThinSlice
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(16)
    up_port = srv.getsockname()[1]
    dead = socket.socket(); dead.bind(("127.0.0.1", 0)); down_port = dead.getsockname()[1]; dead.close()
    probe = GuardThinSlice.measure_packet_loss
    stub = type("G", (), {"_packet_loss_override": None})()
    t0 = time.time()
    assert probe(stub, host="127.0.0.1", port=up_port) == 0.0
    assert probe(stub, host="127.0.0.1", port=down_port) == 100.0
    assert time.time() - t0 < 3
    srv.close()


def test_drain3_patterns_group_lines_and_never_carry_text(tmp_path):
    import json
    from guard.log_patterns import PatternMiner
    m = PatternMiner()
    if m.miner is None:
        import pytest; pytest.skip("drain3 not installed")
    for i in range(12):
        m.add(json.dumps({"level": "WARNING", "message": f"Authentication failed for user 'u{i}' from 10.0.0.{i}"}))
    m.add(json.dumps({"level": "INFO", "message": "Customer browsed catalog"}))
    first = m.drain()
    assert sum(s.count for s in first) == 13 and any(s.count == 12 and s.level == "WARNING" and s.is_new for s in first)
    assert all(s.pattern_id.startswith("tpl-") for s in first)
    m.add(json.dumps({"level": "WARNING", "message": "Authentication failed for user 'zz' from 10.9.9.9"}))
    again = m.drain()
    assert len(again) == 1 and again[0].is_new is False        # same pattern seen before: not new


def test_baseline_floor_keeps_idle_network_noise_from_flagging():
    from hq.aiops.engine import Engine, Thresholds
    e = Engine()
    th = Thresholds()
    for i in range(40):
        e.ingest("acme", "host-x", float(i), float(i), {"net_in_kbps": 8.0 + (i % 3) * 0.2})
    e.ingest("acme", "host-x", 41.0, 41.0, {"net_in_kbps": 60.0})   # an ordinary burst on an idle NIC
    assert abs(e.src[("acme", "host-x")].z["net_in_kbps"]) < 3
    e.ingest("acme", "host-x", 42.0, 42.0, {"net_in_kbps": 900.0})  # a real exfil-sized burst still flags
    assert abs(e.src[("acme", "host-x")].z["net_in_kbps"]) >= 3


def test_packet_loss_median_ignores_one_stall_but_not_an_outage(tmp_path):
    import statistics
    from collections import deque
    h = deque(maxlen=5)
    for v in (0, 0, 100, 0, 0):
        h.append(v)
    assert statistics.median(h) == 0          # one stalled window: healthy
    for v in (100, 100, 100):
        h.append(v)
    assert statistics.median(h) == 100        # sustained: reported
