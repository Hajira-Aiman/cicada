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
import sys
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
_history: List[Dict[str, Any]] = []   # every scenario started since the agent came up (the dashboard draws these as markers)
_lock = threading.Lock()


# --- Real Chaos Effect Implementations ---

# request-supplied names (service, interface) reach subprocess argv: allow plain identifiers only
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")

def _run_cpu_burner(duration_s: float, cores: Optional[int] = None, duty: float = 1.0):
    """Loads `cores` cores (default: every core but one) for duration_s, each busy `duty` of the time, so duty=0.7 on every core
    is about 70% CPU overall. One child process per core (a Python thread would only reach one core), at below-normal priority so
    the guard and the network stack keep getting scheduled while the spike is still clearly visible."""
    import subprocess
    import sys
    duty = min(1.0, max(0.05, duty))
    code = (f"import time; e = time.time() + {duration_s}\n"
            f"while time.time() < e:\n"
            f"    t = time.time() + 0.1 * {duty}\n"
            f"    while time.time() < t: pass\n"
            f"    time.sleep(0.1 * {1 - duty})")
    flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)   # Windows; on Linux the child lowers itself below
    pre = (lambda: os.nice(10)) if hasattr(os, "nice") else None
    kids = [subprocess.Popen([sys.executable, "-c", code], creationflags=flags, preexec_fn=pre) if pre else
            subprocess.Popen([sys.executable, "-c", code], creationflags=flags)
            for _ in range(cores or max(1, (os.cpu_count() or 2) - 1))]
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
SHOP_API_URL = os.getenv("SHOP_API_URL", "http://localhost:7000")
SHOP_LOGIN_URL = os.getenv("SHOP_LOGIN_URL", f"{SHOP_API_URL}/auth/login")


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
    """Periodic noisy backup job: a 12 s burst on half the cores (a real spike on the host's CPU, one thread was invisible on a
    many-core laptop), then idle until the next minute: the steady 60 s interval head office learns as a scheduled job."""
    end_time = time.time() + duration_s
    while time.time() < end_time:
        _run_cpu_burner(min(12.0, end_time - time.time()), cores=max(2, (os.cpu_count() or 4) // 2))
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


def _guard_ledger_bodies(limit: int = 5) -> List[bytes]:
    """The most recent payload bodies this shop's guard sent (exact bytes it signed), newest first."""
    import sqlite3
    from guard.config import config
    try:
        with sqlite3.connect(config.GUARD_DB_PATH) as conn:
            return [r[0].encode("utf-8") for r in conn.execute("SELECT body FROM ledger ORDER BY seq DESC LIMIT ?", (limit,))]
    except sqlite3.Error:
        return []


def _post_ingest(body: bytes, signed_body: Optional[bytes] = None) -> int:
    """POST a body to this shop's ingest endpoint; the signature covers signed_body (default: the body itself)."""
    import httpx
    from datetime import datetime, timezone
    from guard.config import config
    from guard.signer import create_auth_headers
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = create_auth_headers(config.GUARD_ID, signed_body if signed_body is not None else body, ts, config.GUARD_SECRET_KEY)
    return httpx.post(config.REGION_URL, content=body, headers=headers, timeout=5, verify=config.TLS_VERIFY).status_code


def _run_tamper() -> Dict[str, Any]:
    """Two attacks on a copy of a real payload. Expect 401 (a byte flipped after signing) and 422 (a valid signature over
    a body with a field the allow-list does not know). Nothing is stored; head office raises tamper alerts."""
    import json
    bodies = _guard_ledger_bodies(1)
    base = bodies[0] if bodies else b'{"schema":"airlock.v1"}'
    flipped = bytearray(base)
    flipped[len(flipped) // 2] ^= 0x01
    extra = json.loads(base)
    extra["raw_log"] = "password=hunter2"
    return {"byte_flipped": _post_ingest(bytes(flipped), signed_body=base), "extra_field": _post_ingest(json.dumps(extra).encode())}


def _run_replay_shuffle() -> Dict[str, Any]:
    """Re-sends the last payloads, shuffled, with fresh signatures. Head office already has them: expect 200 'duplicate' each
    (counted on the reconciliation panel, nothing stored twice)."""
    import random
    bodies = _guard_ledger_bodies(5)
    random.shuffle(bodies)
    return {"replayed": len(bodies), "status_codes": [_post_ingest(b) for b in bodies]}


def _run_shop_latency(duration_s: float, delay_ms: int) -> None:
    """Windows/any OS: the shop API itself waits delay_ms per request, so the guard's probe measures it for real."""
    import httpx
    try:
        httpx.post(f"{SHOP_API_URL}/chaos/latency", json={"delay_ms": delay_ms, "duration_s": int(duration_s)}, timeout=3)
    except httpx.HTTPError:
        pass


def _restart_shop_api_by_pid() -> None:
    """Windows/any OS: stop the running shop-api (pid from its /health) and start it again; the guard sees a new pid."""
    import subprocess
    import sys
    import httpx
    import psutil
    try:
        pid = int(httpx.get(f"{SHOP_API_URL}/health", timeout=2).json()["pid"])
        psutil.Process(pid).terminate()
    except Exception:
        return
    time.sleep(1.0)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([sys.executable, os.path.join("shop-api", "main.py")], cwd=root, creationflags=flags,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


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
        _history.append({"id": scn_id, "name": name, "started_at": now, "duration_s": duration_s, "target": entry["target"]})
        del _history[:-200]

    # Trigger real effect in background worker thread
    p = params or {}
    if name == "cpu_spike":
        pct = min(95, max(10, int(p.get("target_pct", 70))))   # overall CPU to reach: 70% by default, never pinned at 100%
        import psutil
        load = psutil.cpu_percent(interval=0.5)   # what the machine already uses: only add the difference
        duty = max(0.1, pct - load) / 100.0
        threading.Thread(target=_run_cpu_burner, args=(duration_s, os.cpu_count() or 2, duty), daemon=True).start()
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
        if sys.platform.startswith("linux"):
            threading.Thread(target=_run_latency_netem, args=(duration_s, delay, loss, iface), daemon=True).start()
        else:
            threading.Thread(target=_run_shop_latency, args=(duration_s, delay), daemon=True).start()
    elif name == "restart_app":
        worker = _run_restart_app if sys.platform.startswith("linux") else _restart_shop_api_by_pid
        threading.Thread(target=worker, args=(target,) if worker is _run_restart_app else (), daemon=True).start()
    elif name in ("tamper", "replay_shuffle"):
        run = _run_tamper if name == "tamper" else _run_replay_shuffle

        def record():
            try:
                entry["result"] = run()
            except Exception as exc:   # ingest unreachable etc.
                entry["result"] = {"error": str(exc)}
        threading.Thread(target=record, daemon=True).start()

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


@app.get("/chaos/history")
def get_history():
    with _lock:
        return {"history": list(_history)}


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
