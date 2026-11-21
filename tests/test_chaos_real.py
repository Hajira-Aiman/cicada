"""
tests/test_chaos_real.py
Tests for T11 Real-effect chaos agent triggers on real PostgreSQL.
"""

import time
import pytest
from httpx import ASGITransport, AsyncClient

from chaos.agent import app as chaos_app
from hq.db import init_all_databases, is_region_paused, truncate_all_data


@pytest.fixture(autouse=True)
def setup_db():
    init_all_databases()
    truncate_all_data()
    yield
    truncate_all_data()


@pytest.mark.anyio
async def test_chaos_agent_real_effects():
    async with AsyncClient(transport=ASGITransport(app=chaos_app), base_url="http://chaos") as client:
        # 1. Trigger cpu_spike
        res_cpu = await client.post("/scenarios/cpu_spike", json={"duration_s": 2})
        assert res_cpu.status_code == 200
        data_cpu = res_cpu.json()
        assert data_cpu["status"] == "active"
        assert data_cpu["name"] == "cpu_spike"

        # 2. Trigger region_outage on region 'in'
        res_outage = await client.post("/scenarios/region_outage", json={"duration_s": 3, "target": "in"})
        assert res_outage.status_code == 200
        # Allow thread to set pause switch in airlock_core
        time.sleep(0.3)
        assert is_region_paused("in") is True

        # 3. Trigger backup_job
        res_bk = await client.post("/scenarios/backup_job", json={"duration_s": 1})
        assert res_bk.status_code == 200
        assert res_bk.json()["name"] == "backup_job"

        # 4. Trigger kill_chain
        res_kc = await client.post("/scenarios/kill_chain", json={"duration_s": 1})
        assert res_kc.status_code == 200
        assert res_kc.json()["name"] == "kill_chain"

        # 5. Trigger brute_force
        res_bf = await client.post("/scenarios/brute_force", json={"duration_s": 1})
        assert res_bf.status_code == 200
        assert res_bf.json()["name"] == "brute_force"

        # 6. Verify list of active scenarios
        res_active = await client.get("/chaos/active")
        assert res_active.status_code == 200
        active_names = [s["name"] for s in res_active.json()["active"]]
        assert "cpu_spike" in active_names
        assert "region_outage" in active_names

        # 7. Reset all chaos
        res_reset = await client.post("/chaos/reset")
        assert res_reset.status_code == 200
        res_active_empty = await client.get("/chaos/active")
        assert len(res_active_empty.json()["active"]) == 0
