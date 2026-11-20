"""Fake guards posting valid, HMAC-signed airlock.v1 payloads every 2 s.
  python -m tools.simulate --tenants acme globex contoso --scenario cpu_spike:10:20 --scenario outage:40:15
Scenario format name[:after_s[:for_s]]; repeat --scenario. Names: cpu_spike latency login_burst outage
duplicates out_of_order kill_chain backup_job restart_app."""
import argparse, asyncio, hashlib, random, time, uuid
from datetime import datetime, timedelta, timezone
import httpx
from contracts.models import Payload
from tools.common import TENANTS, PORTS, sign, pseudo

HOSTS = {t: pseudo("host", t) for t in TENANTS}
ATTACKER = pseudo("src", "10.6.6.6")
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")


class Scn:
    def __init__(self, spec, t0):
        p = spec.split(":")
        self.name = p[0]
        self.start = t0 + (float(p[1]) if len(p) > 1 else 0)
        self.end = self.start + (float(p[2]) if len(p) > 2 else 30)

    def active(self, now): return self.start <= now < self.end
    def at(self, now): return now - self.start


def build(tenant, seq, prev_hash, win_start, scns, now):
    """One 2 s window: baseline noise + whatever scenarios are active."""
    r = random.gauss
    m = {"cpu_pct": r(21, 3), "mem_pct": r(45, 2), "disk_pct": 60.0, "net_in_kbps": r(120, 15),
         "net_out_kbps": r(40, 5), "latency_ms": r(60, 6), "packet_loss_pct": abs(r(0.2, 0.1)), "service_up": 1.0}
    ev, src = [], HOSTS[tenant]
    for s in scns:
        if not s.active(now):
            continue
        t = s.at(now)
        if s.name == "cpu_spike":
            m["cpu_pct"] = r(95, 2)
        elif s.name == "latency":
            m["latency_ms"] = r(450, 30); m["packet_loss_pct"] = abs(r(3, .3))
        elif s.name == "login_burst":
            ev.append(dict(category="auth_failure_burst", severity="high", source=src, actor=ATTACKER, count=50, window_s=60))
        elif s.name == "backup_job" and int(t) % 60 < 4:  # CPU spike every 60 s
            m["cpu_pct"] = r(80, 2)
        elif s.name == "restart_app" and t < 2:
            ev.append(dict(category="app_restarted", severity="info", source=src))
        elif s.name == "kill_chain":  # compressed: 0s burst, 6s login ok, 12s+ cpu + outbound
            if t < 4:
                ev.append(dict(category="auth_failure_burst", severity="high", source=src, actor=ATTACKER, count=50, window_s=60))
            elif 6 <= t < 8:
                ev.append(dict(category="login_after_failures", severity="high", source=src, actor=ATTACKER))
            elif t >= 12:
                m["cpu_pct"] = r(96, 1); m["net_out_kbps"] = r(900, 30)
    metrics = [dict(name=k, source=src, avg=round(v, 2), max=round(v * 1.08, 2)) for k, v in m.items()]
    return Payload.model_validate({
        "schema": "airlock.v1", "payload_id": str(uuid.uuid4()), "tenant_id": tenant, "guard_id": TENANTS[tenant][0],
        "seq": seq, "prev_hash": prev_hash, "policy_version": "sha256:sim", "sent_at": iso(datetime.now(timezone.utc)),
        "window": {"start": iso(win_start), "end": iso(win_start + timedelta(seconds=2)), "source_tz": TENANTS[tenant][2]},
        "metrics": metrics, "events": ev,
        "health": {"guard_version": "sim-0.1", "guard_cpu_pct": 1.0, "guard_mem_mb": 80, "buffer_depth": 0, "config_ok": True}})


async def post(client, tenant, body: bytes, host):
    gid, region, _ = TENANTS[tenant]
    ts = iso(datetime.now(timezone.utc))
    try:
        r = await client.post(f"http://{host}:{PORTS[region]}/ingest", content=body, timeout=5, headers={
            "X-Guard-Id": gid, "X-Timestamp": ts, "X-Signature": sign(gid, ts, body), "Content-Type": "application/json"})
        return r.status_code
    except httpx.HTTPError as e:
        return f"err {type(e).__name__}"


async def guard(tenant, scns, host, interval):
    seq, prev, last, held = 0, "sha256:genesis", None, []
    async with httpx.AsyncClient() as c:
        while True:
            now = time.time(); seq += 1
            win = datetime.fromtimestamp(now, timezone.utc).replace(microsecond=0)
            body = build(tenant, seq, prev, win, scns, now).model_dump_json(by_alias=True).encode()
            prev = "sha256:" + hashlib.sha256(body).hexdigest()
            act = {s.name for s in scns if s.active(now)}
            if "outage" in act:
                pass  # stop sending; the real guard buffers in its outbox
            elif "out_of_order" in act:
                held.append(body)
                if len(held) >= 5:  # send a shuffled batch, windows keep their event time
                    random.shuffle(held)
                    for b in held: await post(c, tenant, b, host)
                    held = []
            else:
                for b in held: await post(c, tenant, b, host)
                held = []
                st = await post(c, tenant, body, host)
                if "duplicates" in act and last:
                    await post(c, tenant, last, host); await post(c, tenant, body, host)
                print(f"{iso(win)} {tenant} seq={seq} -> {st} {sorted(act) or ''}", flush=True)
            last = body
            await asyncio.sleep(interval)


async def main():
    a = argparse.ArgumentParser()
    a.add_argument("--tenants", nargs="+", default=list(TENANTS))
    a.add_argument("--scenario", action="append", default=[])
    a.add_argument("--host", default="localhost")
    a.add_argument("--interval", type=float, default=2.0)
    a = a.parse_args()
    t0 = time.time()
    scns = [Scn(s, t0) for s in a.scenario]
    await asyncio.gather(*(guard(t, scns, a.host, a.interval) for t in a.tenants))


if __name__ == "__main__":
    asyncio.run(main())
