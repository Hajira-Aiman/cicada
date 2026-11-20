"""Chaos effects that must do something real: tamper, replay-shuffle, latency window (no network: ingest is faked)."""
import json
import sqlite3
import time

import chaos.agent as agent
from guard.config import config
from guard.ledger import GuardLedger


def seed_ledger(tmp_path, n=3):
    db = str(tmp_path / "g.db")
    led = GuardLedger(db_path=db)
    prev = "GENESIS"
    for i in range(1, n + 1):
        body = json.dumps({"schema": "airlock.v1", "seq": i})
        sha = f"sha256:{i:064x}"
        led.record_payload(seq=i, payload_id=f"p{i}", sha256=sha, prev_hash=prev, body=body)
        prev = sha
    return db


def test_tamper_sends_a_flipped_byte_and_an_unknown_field(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GUARD_DB_PATH", seed_ledger(tmp_path))
    sent = []
    monkeypatch.setattr(agent, "_post_ingest", lambda body, signed_body=None: sent.append((body, signed_body)) or 401)
    res = agent._run_tamper()
    flipped, signed = sent[0]
    assert flipped != signed and len(flipped) == len(signed)                  # bytes changed after signing
    assert json.loads(sent[1][0])["raw_log"] == "password=hunter2"            # field the allow-list rejects
    assert set(res) == {"byte_flipped", "extra_field"}


def test_replay_shuffle_resends_recent_payloads_shuffled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GUARD_DB_PATH", seed_ledger(tmp_path, 4))
    sent = []
    monkeypatch.setattr(agent, "_post_ingest", lambda body, signed_body=None: sent.append(json.loads(body)["seq"]) or 200)
    res = agent._run_replay_shuffle()
    assert sorted(sent) == [1, 2, 3, 4] and res["replayed"] == 4 and res["status_codes"] == [200] * 4


def test_shop_api_latency_window_slows_requests_then_ends():
    from fastapi.testclient import TestClient
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("shop_main", pathlib.Path(__file__).parents[1] / "shop-api" / "main.py")
    shop = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shop)
    c = TestClient(shop.app)
    assert c.post("/chaos/latency", json={"delay_ms": 300, "duration_s": 1}).json()["status"] == "slow"
    t = time.time(); c.get("/health"); slow = time.time() - t
    time.sleep(1.1)
    t = time.time(); c.get("/health"); fast = time.time() - t
    assert slow >= 0.28 and fast < 0.2


def test_backup_job_bursts_on_half_the_cores_every_minute(monkeypatch):
    burns, sleeps = [], []
    monkeypatch.setattr(agent, "_run_cpu_burner", lambda d, cores=None: burns.append((round(d), cores)))
    monkeypatch.setattr(agent.time, "sleep", lambda s: sleeps.append(s))
    clock = iter(range(0, 10_000, 12))
    monkeypatch.setattr(agent.time, "time", lambda: next(clock))
    agent._run_backup_job(130)
    assert burns and all(d <= 12 and (cores or 0) >= 2 for d, cores in burns)


def test_cpu_burner_is_capped_and_low_priority():
    import psutil
    from chaos import agent
    psutil.cpu_percent(None)
    import threading, time
    t = threading.Thread(target=agent._run_cpu_burner, args=(4, psutil.cpu_count(), 0.5))
    t.start()
    time.sleep(2.5)
    load = psutil.cpu_percent(None)
    t.join()
    assert load < 97   # never pinned at 100% like the old burner, so the guard keeps running
