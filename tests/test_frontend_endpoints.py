"""Endpoints the web UI polls: bounded metrics, health history, action list, damage map. Run: python -m pytest tests/test_frontend_endpoints.py -q"""
import pytest
from httpx import AsyncClient, ASGITransport
from hq.api.main import app
from hq.db import init_all_databases, truncate_all_data


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()


async def login(c, user="admin", pw="admin123"):
    r = await c.post("/api/login", json={"username": user, "password": pw})
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.anyio
async def test_polled_endpoints_answer_and_need_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get("/api/metrics")).status_code == 401
        h = await login(c)
        assert (await c.get("/api/metrics?limit=10", headers=h)).json() == {"metrics": []}
        assert (await c.get("/api/metrics?since=2999-01-01T00:00:00Z", headers=h)).status_code == 200
        assert (await c.get("/api/events?limit=5", headers=h)).json() == {"events": []}
        assert (await c.get("/api/health/history", headers=h)).json() == {"history": []}
        assert (await c.get("/api/actions", headers=h)).json() == {"intents": []}
        assert set((await c.get("/api/damage-map/acme")).json()) == {"nodes", "edges"}


@pytest.mark.anyio
async def test_actions_list_follows_propose_and_is_tenant_scoped():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        h = await login(c)
        p = await c.post("/api/actions/propose", headers=h, json={"action": "investigate", "target": "host-1", "tenant_id": "acme"})
        assert p.status_code == 200
        assert [i["intent_id"] for i in (await c.get("/api/actions", headers=h)).json()["intents"]] == [p.json()["intent_id"]]
        hg = await login(c, "user-globex", "globex123")
        assert (await c.get("/api/actions", headers=hg)).json() == {"intents": []}
