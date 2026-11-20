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
