# tests/test_headoffice_websocket.py
import pytest
from httpx import AsyncClient, ASGITransport
from hq.api.main import app
from hq.api.broadcaster import broadcaster

@pytest.mark.anyio
async def test_hq_api_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_hq_api_tenants():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/tenants")
        assert resp.status_code == 200
        data = resp.json()
        assert "tenants" in data
        assert any(t["tenant_id"] == "globex" for t in data["tenants"])


@pytest.mark.anyio
async def test_broadcaster_pub_sub():
    received = []
    
    async def dummy_ws(msg):
        received.append(msg)

    broadcaster.register_client("client-1", dummy_ws)
    await broadcaster.broadcast({"event_type": "metrics_batch", "tenant_id": "globex"})
    broadcaster.unregister_client("client-1")

    assert len(received) == 1
    assert received[0]["tenant_id"] == "globex"
