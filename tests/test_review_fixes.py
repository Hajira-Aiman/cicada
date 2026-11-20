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
