"""
tests/test_demo_shop_api.py
Verification for T16 Demo Shop App:
- GET /health: Health probe with PID and uptime
- POST /auth/login: records failures and successes
- GET /catalog: products listing
- POST /cart/checkout: records orders and logs card details for scrubber
- POST /chaos/inject-log: writes arbitrary try-to-leak text to shop-api log
- End-to-end integration with Guard:
  * 50 wrong passwords flow through the log and produce exactly one auth_failure_burst
  * Injected secrets (AWS keys, cards) are masked, tracked in health.secrets_redacted,
    stored in local raw.db, and blocked from egress payloads.
"""

import os
import time
import pytest
from starlette.testclient import TestClient

from guard.config import GuardConfig
from guard.thin_slice import GuardThinSlice
import sys

# Import shop-api app using importlib or sys.path
import importlib.util
from pathlib import Path

shop_api_path = Path(__file__).parent.parent / "shop-api" / "main.py"
spec = importlib.util.spec_from_file_location("shop_api_main", str(shop_api_path))
shop_api_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shop_api_mod)
shop_app = shop_api_mod.app


def test_shop_api_endpoints(tmp_path):
    log_file = str(tmp_path / "test_shop.log")
    shop_api_mod.LOG_FILE_PATH = log_file

    with TestClient(shop_app) as client:
        # 1. GET /health
        res_h = client.get("/health")
        assert res_h.status_code == 200
        assert res_h.json()["status"] == "ok"
        assert "pid" in res_h.json()

        # 2. GET /catalog
        res_c = client.get("/catalog")
        assert res_c.status_code == 200
        assert len(res_c.json()) >= 3

        # 3. POST /auth/login success
        res_ls = client.post("/auth/login", json={"username": "admin", "password": "securepass2026"})
        assert res_ls.status_code == 200
        assert res_ls.json()["status"] == "success"

        # 4. POST /auth/login failure
        res_lf = client.post("/auth/login", json={"username": "attacker", "password": "wrong"})
        assert res_lf.status_code == 401

        # 5. POST /cart/checkout
        res_co = client.post("/cart/checkout", json={"card_number": "4111 2222 3333 4444", "amount": 149.50})
        assert res_co.status_code == 200
        assert res_co.json()["status"] == "completed"

        # 6. POST /chaos/inject-log
        leak_msg = "Leaked AWS secret key: AKIAIOSFODNN7EXAMPLE for root"
        res_inj = client.post("/chaos/inject-log", json={"text": leak_msg})
        assert res_inj.status_code == 200
        assert res_inj.json()["status"] == "injected"

        # Verify log file was written
        assert os.path.exists(log_file)
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 4


def test_shop_api_logs_flow_through_guard_pipeline(tmp_path):
    log_file = str(tmp_path / "flow_shop.log")
    shop_api_mod.LOG_FILE_PATH = log_file

    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g_flow.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r_flow.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "rev_flow.db")
    cfg.SHOP_LOG_PATH = log_file

    guard = GuardThinSlice(cfg=cfg)

    with TestClient(shop_app) as client:
        # 1. Inject 50 wrong password attempts
        for i in range(50):
            client.post("/auth/login", json={"username": f"user_{i}", "password": f"bad_pwd_{i}"})

        # Wait briefly for burst stream to conclude
        time.sleep(0.55)

        # 2. Inject sensitive text with an AWS access key and credit card number
        leak_text = "Backup failure: AKIAIOSFODNN7EXAMPLE and card 5555 4444 3333 2222 logged"
        client.post("/chaos/inject-log", json={"text": leak_text})

        # 3. Guard collects window: log tailer processes all 51 lines automatically
        payload, body_bytes = guard.collect_window(duration_seconds=1.0)

        # Confirm 50 failures produced exactly one auth_failure_burst with count=50
        burst_events = [e for e in payload.events if e.category == "auth_failure_burst"]
        assert len(burst_events) == 1
        assert burst_events[0].count == 50
        assert burst_events[0].severity == "high"

        # Confirm secrets were scrubbed and counted
        assert payload.health.secrets_redacted >= 2
        assert any(e.category == "secret_redacted" for e in payload.events)

        # Confirm raw logs stored in local raw.db
        assert guard.raw_store.count() >= 51
        raw_found = guard.raw_store.search_raw_logs("AKIAIOSFODNN7EXAMPLE")
        assert len(raw_found) >= 1

        # Confirm sensitive leak never escaped into payload bytes
        body_str = body_bytes.decode("utf-8")
        assert "AKIAIOSFODNN7EXAMPLE" not in body_str
        assert "5555 4444 3333 2222" not in body_str
        assert "bad_pwd_0" not in body_str
