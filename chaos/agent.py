"""
chaos/agent.py
Airlock Chaos Engineering Agent (runs on shop or test harness, default port 9100).
Provides endpoints for:
- cpu_spike
- latency (tc netem / Toxiproxy / sleep)
- brute_force (or login_burst)
- leak (try-to-leak challenge)
- region_outage (or outage)
- replay_shuffle (out_of_order / duplicates)
- tamper
- kill_chain
- backup_job
- restart_app
"""

import os
import time
import uuid
import threading
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Airlock Chaos Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active chaos state registry
_active_scenarios: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


class ScenarioRequest(BaseModel):
    duration_s: int = 15
    target: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class TriggerRequest(BaseModel):
    scenario: str
    duration_s: int = 15
    target: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


def _activate_scenario(name: str, duration_s: int, target: Optional[str] = None, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _lock:
        now = time.time()
        scn_id = f"chaos-{uuid.uuid4().hex[:8]}"
        entry = {
            "id": scn_id,
            "name": name,
            "target": target or "default",
            "duration_s": duration_s,
            "started_at": now,
            "expires_at": now + duration_s,
            "status": "active",
            "params": params or {},
        }
        _active_scenarios[name] = entry
        return entry


def _prune_expired():
    with _lock:
        now = time.time()
        expired = [k for k, v in _active_scenarios.items() if v.get("expires_at", 0) < now]
        for k in expired:
            _active_scenarios.pop(k, None)


@app.get("/health")
def health():
    return {"status": "ok", "service": "chaos-agent", "port": 9100}


@app.get("/scenarios")
@app.get("/chaos/scenarios")
def list_scenarios():
    return {
        "scenarios": [
            "cpu_spike",
            "latency",
            "brute_force",
            "leak",
            "region_outage",
            "replay_shuffle",
            "tamper",
            "kill_chain",
            "backup_job",
            "restart_app",
        ]
    }


@app.get("/chaos/active")
def get_active_scenarios():
    _prune_expired()
    with _lock:
        return {"active": list(_active_scenarios.values())}


@app.post("/chaos/reset")
def reset_all_chaos():
    with _lock:
        _active_scenarios.clear()
    return {"status": "ok", "message": "All chaos scenarios reset"}


@app.post("/chaos/trigger")
def trigger_scenario(req: TriggerRequest):
    return _activate_scenario(req.scenario, req.duration_s, req.target, req.params)


# Explicit scenario endpoints matching simulate_timeline.py & PRD
@app.post("/scenarios/cpu_spike")
@app.post("/chaos/cpu_spike")
def trigger_cpu_spike(req: ScenarioRequest = ScenarioRequest()):
    """Triggers high CPU utilization spike."""
    return _activate_scenario("cpu_spike", req.duration_s, req.target, req.params)


@app.post("/scenarios/latency")
@app.post("/chaos/latency")
def trigger_latency(req: ScenarioRequest = ScenarioRequest()):
    """Triggers packet latency injection (e.g. 450ms, 3% packet loss)."""
    return _activate_scenario("latency", req.duration_s, req.target, req.params)


@app.post("/scenarios/brute_force")
@app.post("/chaos/brute_force")
@app.post("/scenarios/login_burst")
@app.post("/chaos/login_burst")
def trigger_brute_force(req: ScenarioRequest = ScenarioRequest()):
    """Triggers authentication failure burst."""
    return _activate_scenario("brute_force", req.duration_s, req.target, req.params)


@app.post("/scenarios/leak")
@app.post("/chaos/leak")
@app.post("/scenarios/try_to_leak")
@app.post("/chaos/try_to_leak")
def trigger_leak(req: ScenarioRequest = ScenarioRequest()):
    """Triggers try-to-leak challenge payload containing canary or secrets."""
    params = req.params or {}
    leak_text = params.get("leak_text", "AKIACANARY99999999SECRET")
    return _activate_scenario("leak", req.duration_s, req.target, {"leak_text": leak_text, **params})


@app.post("/scenarios/region_outage")
@app.post("/chaos/region_outage")
@app.post("/scenarios/outage")
@app.post("/chaos/outage")
def trigger_region_outage(req: ScenarioRequest = ScenarioRequest()):
    """Triggers region outage / drop connection."""
    target_region = req.target or "in"
    return _activate_scenario("region_outage", req.duration_s, target_region, req.params)


@app.post("/scenarios/replay_shuffle")
@app.post("/chaos/replay_shuffle")
@app.post("/scenarios/duplicates")
@app.post("/chaos/duplicates")
@app.post("/scenarios/out_of_order")
@app.post("/chaos/out_of_order")
def trigger_replay_shuffle(req: ScenarioRequest = ScenarioRequest()):
    """Triggers out-of-order and duplicated stream injection."""
    return _activate_scenario("replay_shuffle", req.duration_s, req.target, req.params)


@app.post("/scenarios/tamper")
@app.post("/chaos/tamper")
def trigger_tamper(req: ScenarioRequest = ScenarioRequest()):
    """Triggers payload tampering simulation."""
    return _activate_scenario("tamper", req.duration_s, req.target, req.params)


@app.post("/scenarios/kill_chain")
@app.post("/chaos/kill_chain")
def trigger_kill_chain(req: ScenarioRequest = ScenarioRequest()):
    """Triggers compressed multi-stage kill chain progression."""
    return _activate_scenario("kill_chain", req.duration_s, req.target, req.params)


@app.post("/scenarios/backup_job")
@app.post("/chaos/backup_job")
def trigger_backup_job(req: ScenarioRequest = ScenarioRequest()):
    """Triggers periodic backup job resource consumption."""
    return _activate_scenario("backup_job", req.duration_s, req.target, req.params)


@app.post("/scenarios/restart_app")
@app.post("/chaos/restart_app")
def trigger_restart_app(req: ScenarioRequest = ScenarioRequest()):
    """Triggers application restart simulation."""
    return _activate_scenario("restart_app", req.duration_s, req.target, req.params)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9100"))
    uvicorn.run("chaos.agent:app", host="0.0.0.0", port=port, reload=False)
