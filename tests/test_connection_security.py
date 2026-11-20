"""Connection security: guard-signed requests, anonymous access closed, tenant scoping, CORS, guard clock follow."""
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
from httpx import ASGITransport, AsyncClient

from contracts.request_auth import guard_request_headers
from guard.config import GuardConfig
from guard.thin_slice import GuardThinSlice
from hq.api.main import app
from hq.db import create_reveal_request, init_all_databases, register_guard, truncate_all_data

ACME_SECRET = "sec-acme-super-secret-key-2026"
GLOBEX_SECRET = "sec-globex-test-secret"


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()
    register_guard("guard-acme-01", "acme", ACME_SECRET)
    register_guard("guard-globex-01", "globex", GLOBEX_SECRET)
    yield
    truncate_all_data()


def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def signed(guard="guard-acme-01", secret=ACME_SECRET, method="GET", path="/api/actions/pending", body=b"", now=None):
    return guard_request_headers(guard, secret, method, path, body, now=now)


@pytest.mark.anyio
async def test_anonymous_callers_are_rejected():
    async with client() as c:
        for method, path in [("GET", "/api/actions/pending"), ("GET", "/reveal-requests"), ("GET", "/api/actions/audit"),
                             ("GET", "/api/counters/acme"), ("GET", "/api/baselines/acme"), ("GET", "/api/damage-map/acme")]:
            assert (await c.request(method, path)).status_code == 401, path
        for path in ["/api/actions/propose", "/api/feedback", "/reveal-requests", "/api/actions/x/dry-run", "/api/actions/x/approve"]:
            assert (await c.post(path, json={})).status_code == 401, path
        assert (await c.post("/api/actions/x/result", json={"guard_id": "guard-acme-01"})).status_code == 401


@pytest.mark.anyio
async def test_guard_signature_must_be_valid_fresh_and_bound_to_the_request():
    async with client() as c:
        assert (await c.get("/api/actions/pending", headers=signed())).status_code == 200
        # wrong secret, unknown guard, tampered path, stale timestamp
        assert (await c.get("/api/actions/pending", headers=signed(secret="nope"))).status_code == 401
        assert (await c.get("/api/actions/pending", headers=signed(guard="guard-rogue", secret="x"))).status_code == 401
        assert (await c.get("/api/actions/pending", headers=signed(path="/reveal-requests"))).status_code == 401
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        assert (await c.get("/api/actions/pending", headers=signed(now=old))).status_code == 401


@pytest.mark.anyio
async def test_guard_sees_and_decides_only_its_own_tenant():
    create_reveal_request(tenant_id="acme", pseudonym="src-11111111", requested_by="analyst", reason="r", request_id="req-acme")
    create_reveal_request(tenant_id="globex", pseudonym="src-22222222", requested_by="analyst", reason="r", request_id="req-globex")
    async with client() as c:
        path = "/reveal-requests?status=pending"
        listed = (await c.get(path, headers=signed(path=path))).json()["reveal_requests"]
        assert [r["request_id"] for r in listed] == ["req-acme"]

        body = json.dumps({"status": "approved"}).encode()
        h = {"Content-Type": "application/json"}
        other = "/reveal-requests/req-globex/decision"
        assert (await c.post(other, content=body, headers={**h, **signed(method="POST", path=other, body=body)})).status_code == 404
        mine = "/reveal-requests/req-acme/decision"
        assert (await c.post(mine, content=body, headers={**h, **signed(method="POST", path=mine, body=body)})).status_code == 200


@pytest.mark.anyio
async def test_cors_allows_private_networks_only():
    async with client() as c:
        for origin, allowed in [("http://192.168.137.1:5173", True), ("http://localhost:5173", True),
                                ("http://172.17.1.76:5173", True), ("https://evil.example", False), ("http://192.169.1.1", False)]:
            r = await c.get("/health", headers={"Origin": origin})
            assert (r.headers.get("access-control-allow-origin") == origin) is allowed, origin


def test_guard_follows_head_office_clock(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "g.db")
    cfg.RAW_DB_PATH = str(tmp_path / "r.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "v.db")
    cfg.SHOP_LOG_PATH = str(tmp_path / "s.log")
    g = GuardThinSlice(cfg=cfg)
    hq_now = datetime.now(timezone.utc) + timedelta(seconds=45)
    g.learn_clock_offset(format_datetime(hq_now, usegmt=True))
    assert 43 <= g.clock_offset_s <= 47
    assert abs((g.now_utc() - hq_now).total_seconds()) < 3
    g.learn_clock_offset(format_datetime(datetime.now(timezone.utc), usegmt=True))   # clocks agree again
    assert g.clock_offset_s == 0
    g.learn_clock_offset("not a date")
    assert g.clock_offset_s == 0
