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
import re
import time
import uuid
import threading
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from contracts.request_auth import PRIVATE_ORIGIN_REGEX

app = FastAPI(title="Airlock Chaos Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=PRIVATE_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active chaos state registry
_active_scenarios: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


# --- Real Chaos Effect Implementations ---

# request-supplied names (service, interface) reach subprocess argv: allow plain identifiers only
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")

def _run_cpu_burner(duration_s: float):
    """Pins every core but one (the guard needs one) for duration_s (one busy child process per core; a Python thread would only reach one core)."""
    import subprocess
    import sys
    code = f"import time; e = time.time() + {duration_s}; exec('while time.time() < e: pass')"
    kids = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(max(1, (os.cpu_count() or 2) - 1))]
    for k in kids:
        k.wait()


def _run_exfil(duration_s: float, rate_kbps: int = 4000):
    """Real outbound burst: UDP datagrams to a TEST-NET address (RFC 5737, never routed). They still leave through
    the network card, so the guard's net_out_kbps (psutil NIC counters) really spikes. Nothing is delivered anywhere."""
    import socket
    end_time = time.time() + duration_s
    chunk = b"x" * 1200
    per_s = max(1, int(rate_kbps * 1000 / 8 / len(chunk)))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while time.time() < end_time:
            for _ in range(per_s // 10):
                try:
                    sock.sendto(chunk, ("192.0.2.1", 9))
                except OSError:
                    pass
            time.sleep(0.1)


# the attack must hit the shop's own login: the guard reads that log, HQ never sees raw logins
SHOP_LOGIN_URL = os.getenv("SHOP_LOGIN_URL", "http://localhost:7000/auth/login")


def _run_brute_force(duration_s: float, target_url: str):
    """Sends rapid burst of invalid authentication attempts."""
    import httpx
    end_time = time.time() + duration_s
    with httpx.Client(timeout=2.0) as client:
        while time.time() < end_time:
            try:
                client.post(
                    target_url,
                    json={"username": f"attacker_{uuid.uuid4().hex[:6]}", "password": "wrong_password_123"},
                )
            except Exception:
                pass
            time.sleep(0.1)


def _run_backup_job(duration_s: float):
    """Periodic noisy backup job: 12 s CPU burst followed by 48 s idle."""
    end_time = time.time() + duration_s
    while time.time() < end_time:
        burst_end = min(time.time() + 12.0, end_time)
        while time.time() < burst_end:
            _ = 999999.0 ** 0.5
        idle_until = min(time.time() + 48.0, end_time)
        remaining = idle_until - time.time()
        if remaining > 0:
            time.sleep(remaining)


def _run_kill_chain(duration_s: float):
    """Multi-stage kill chain progression: Recon -> Brute Force -> Resource Exhaustion -> Outbound socket."""
    import httpx
    # the guard samples about every 4 s and a flag needs 3 windows, so every stage must last >= 15 s
    step_duration = max(duration_s / 4.0, 15.0)
    # Stage 1: recon
    try:
        with httpx.Client(timeout=2.0) as client:
            client.get("http://localhost:8000/api/health")
    except Exception:
        pass
    time.sleep(1)

    # Stage 2: login failure burst against the shop, then a quiet gap so the guard closes the burst
    _run_brute_force(10, SHOP_LOGIN_URL)
    time.sleep(6)
    # a success right after the failures = login_after_failures
    try:
        with httpx.Client(timeout=2.0) as client:
            client.post(SHOP_LOGIN_URL, json={"username": "admin", "password": "securepass2026"})
    except Exception:
        pass

    # Stage 3: CPU on every core; Stage 4: outbound burst on top of it (miner talking to its pool)
    threading.Thread(target=lambda: (time.sleep(step_duration), _run_exfil(step_duration, 30000)), daemon=True).start()
    _run_cpu_burner(step_duration * 2)


def _run_region_outage(region: str, duration_s: float):
    """Real region outage: sets region_states.is_paused = True in airlock_core."""
    try:
        from hq.db import set_region_paused
        set_region_paused(region, True)
        time.sleep(duration_s)
        set_region_paused(region, False)
    except Exception:
        pass


def _run_latency_netem(duration_s: float, delay_ms: int = 450, loss_pct: int = 3, iface: str = "lo"):
    """Applies kernel traffic control delay and packet loss via tc netem on interface."""
    import subprocess
    if not SAFE_NAME.match(iface):
        return
    add = ["sudo", "/usr/sbin/tc", "qdisc", "add", "dev", iface, "root", "netem", "delay", f"{int(delay_ms)}ms", "loss", f"{int(loss_pct)}%"]
    delete = ["sudo", "/usr/sbin/tc", "qdisc", "del", "dev", iface, "root"]
    quiet = dict(check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        subprocess.run(add, **quiet)
        time.sleep(duration_s)
    finally:
        subprocess.run(delete, **quiet)


def _run_restart_app(target: Optional[str] = None):
    """Restarts application service via systemctl or docker."""
    import subprocess
    app_name = target or "shop-api"
    if not SAFE_NAME.match(app_name):
        return
    quiet = dict(check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if subprocess.run(["systemctl", "restart", app_name], **quiet).returncode != 0:
            subprocess.run(["docker", "restart", app_name], **quiet)
    except OSError:
        pass  # neither systemctl nor docker on this host (e.g. Windows)


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

    # Trigger real effect in background worker thread
    p = params or {}
    if name == "cpu_spike":
        threading.Thread(target=_run_cpu_burner, args=(duration_s,), daemon=True).start()
    elif name in ("brute_force", "login_burst"):
        target_url = p.get("url", SHOP_LOGIN_URL)
        threading.Thread(target=_run_brute_force, args=(duration_s, target_url), daemon=True).start()
    elif name == "backup_job":
        threading.Thread(target=_run_backup_job, args=(duration_s,), daemon=True).start()
    elif name == "kill_chain":
        threading.Thread(target=_run_kill_chain, args=(duration_s,), daemon=True).start()
    elif name in ("region_outage", "outage"):
        reg = target or p.get("region", "in")
        threading.Thread(target=_run_region_outage, args=(reg, duration_s), daemon=True).start()
    elif name == "latency":
        delay = int(p.get("delay_ms", 450))
        loss = int(p.get("loss_pct", 3))
        iface = str(p.get("interface", "lo"))
        threading.Thread(target=_run_latency_netem, args=(duration_s, delay, loss, iface), daemon=True).start()
    elif name == "restart_app":
        threading.Thread(target=_run_restart_app, args=(target,), daemon=True).start()

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
