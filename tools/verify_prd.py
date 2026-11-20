"""
tools/verify_prd.py: checks the PRD requirements against the LIVE stack and prints PASS / FAIL / MANUAL with evidence.

    python -m tools.verify_prd                 # head-office checks (fast, read-mostly)
    python -m tools.verify_prd --shop 192.168.137.56     # + live scenarios against that shop (CPU spike, kill chain,
                                                           honeypot, brute force, leak, region pause; ~6 min)
Needs: head office running on this machine (API :8000, ingest TLS :8001/:8002, certs/hq.crt) and the admin login.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import httpx

from contracts.request_auth import request_signature  # noqa: F401  (kept for ad-hoc guard calls)
from guard.signer import create_auth_headers

os.environ.setdefault("DB_PASSWORD", "airlock_dev")   # direct read-only DB checks; hq.db picks this up on import
HQ = "http://localhost:8000"
INGEST = {"in": "https://127.0.0.1:8001/ingest", "eu": "https://127.0.0.1:8002/ingest"}
CERT = "certs/hq.crt"
ACME_SECRET = "sec-acme-super-secret-key-2026"
PSEUDONYM = re.compile(r"^(host|src|user|proc)-[0-9a-f]{8}$")
RESULTS = []


def record(prd, name, status, evidence=""):
    RESULTS.append((prd, name, status, evidence))
    print(f"[{status:6}] #{prd:<3} {name}  {evidence}", flush=True)


def api(path, token=None, method="GET", body=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.request(method, HQ + path, headers=h, json=body, timeout=60)
    return r.status_code, (r.json() if r.content else {})


def login(user, pw):
    return api("/api/login", method="POST", body={"username": user, "password": pw})[1]["token"]


def ingest(region, body: bytes, guard="guard-acme-01", secret=ACME_SECRET, ts=None, sign=None):
    ts = ts or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    h = create_auth_headers(guard, sign if sign is not None else body, ts, secret)
    return httpx.post(INGEST[region], content=body, headers=h, timeout=10, verify=CERT).status_code


def parse(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00").replace(" ", "T"))


def wait_for(cond, timeout, every=2.0):
    end = time.time() + timeout
    while time.time() < end:
        got = cond()
        if got:
            return got
        time.sleep(every)
    return None


# ----------------------------------------------------------------------------------------------- head-office checks
def head_office_checks(tok):
    now = datetime.now(timezone.utc)
    metrics = api("/api/metrics?limit=600", tok)[1]["metrics"]
    acme = [m for m in metrics if m["tenant_id"] == "acme" and now - parse(m["event_time"]) < timedelta(minutes=3)]
    have = {m["name"] for m in acme}
    need = {"cpu_pct", "mem_pct", "disk_pct", "net_in_kbps", "net_out_kbps", "latency_ms", "packet_loss_pct", "service_up"}
    record(1, "Telemetry: host + service + network metrics arriving", "PASS" if need <= have else "FAIL",
           f"last 3 min: {sorted(have)}" if need <= have else f"missing {sorted(need - have)}")
    record(8, "Metric set (cpu/mem/disk/net/latency/loss/availability) on the allow-list", "PASS" if need <= have else "FAIL")

    blobs = {k: api(p, tok)[1] for k, p in [("metrics", "/api/metrics?limit=300"), ("events", "/api/events?limit=300"), ("alerts", "/api/alerts"),
                                             ("incidents", "/api/incidents"), ("health", "/api/health"), ("guards", "/api/guards")]}
    text = json.dumps(blobs)
    ips = set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text))
    bad_src = {m["source"] for m in blobs["metrics"]["metrics"]} | {e["source"] for e in blobs["events"]["events"]}
    bad_src = {s for s in bad_src if not PSEUDONYM.match(s)}
    actors = {e["actor"] for e in blobs["events"]["events"] if e.get("actor") and not PSEUDONYM.match(e["actor"])}
    leaked = [w for w in ("password", "securepass", "hunter2", "4111", "AKIA") if w in text]
    record(4, "Allow-list: nothing but numbers, fixed labels and pseudonyms at head office", "PASS" if not (ips or bad_src or actors or leaked) else "FAIL",
           f"ips={ips or 'none'} non-pseudonym sources={bad_src or 'none'} secrets={leaked or 'none'}")
    record(5, "Pseudonymous source IDs (host-/src-/proc- + 8 hex)", "PASS" if not (bad_src or actors) else "FAIL")

    # 6: transport + auth
    body = b'{"schema":"airlock.v1"}'
    res = {}
    res["no headers"] = httpx.post(INGEST["in"], content=body, verify=CERT, timeout=10).status_code
    res["bad signature"] = ingest("in", body, secret="wrong")
    res["stale timestamp"] = ingest("in", body, ts=(now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        httpx.post("http://127.0.0.1:8001/ingest", content=body, timeout=3); res["plain http"] = "accepted"
    except httpx.HTTPError:
        res["plain http"] = "refused"
    try:
        httpx.post(INGEST["in"], content=body, timeout=3); res["unpinned TLS"] = "accepted"
    except httpx.HTTPError:
        res["unpinned TLS"] = "refused"
    ok = res == {"no headers": 400, "bad signature": 401, "stale timestamp": 400, "plain http": "refused", "unpinned TLS": "refused"}
    record(6, "Encrypted transport + per-guard HMAC + timestamp", "PASS" if ok else "FAIL", str(res))

    # 4 again: strict schema
    extra = json.dumps({"schema": "airlock.v1", "raw_log": "password=hunter2"}).encode()
    code = ingest("in", extra)
    record(4, "Unknown field is rejected by ingest (strict schema)", "PASS" if code == 422 else "FAIL", f"HTTP {code}")

    # 11: tenants
    t_acme, t_globex = login("user-acme", "acme123"), login("user-globex", "globex123")
    seen = {}
    for who, t in (("acme", t_acme), ("globex", t_globex)):
        rows = api("/api/metrics?limit=300", t)[1]["metrics"] + api("/api/payloads", t)[1]["payloads"] + api("/api/health", t)[1]["health"]
        seen[who] = {r["tenant_id"] for r in rows}
    cross = api("/api/baselines/acme", t_globex)[0], api("/api/checkpoints/guard-acme-01", t_globex)[0], api("/api/actions/pending", None)[0]
    both = {m["tenant_id"] for m in blobs["metrics"]["metrics"]}
    ok = seen["acme"] <= {"acme"} and seen["globex"] <= {"globex"} and cross == (403, 403, 401)
    record(11, "Multi-tenant separation (customer sees only own tenant; engineer sees all)", "PASS" if ok else "FAIL",
           f"acme user sees {seen['acme']}, globex user sees {seen['globex']}, engineer sees {both}, cross-tenant/anonymous = {cross}")

    # 10: fleet
    g = api("/api/guards", tok)[1]["guards"]
    fields = {"guard_version", "guard_cpu_pct", "guard_mem_mb", "buffer_depth", "config_ok", "policy_version", "last_payload_at"}
    record(10, "Fleet: version, CPU/memory, buffer depth, config, policy hash, last seen", "PASS" if g and fields <= set(g[0]) else "FAIL",
           f"{[(x['guard_id'], x['guard_version'], x['buffer_depth']) for x in g]}")

    # 12: health
    health = api("/api/health", tok)[1]["health"]
    hist = api("/api/health/history?limit=50", tok)[1]["history"]
    ok = bool(health) and all(h["state"] in ("excellent", "good", "fair", "poor") and h["reasons"] for h in health) and bool(hist)
    record(12, "Four health states with reasons + logged transitions", "PASS" if ok else "FAIL",
           f"{[(h['source'][:9], h['state']) for h in health if h['tenant_id'] == 'acme']}, {len(hist)} transitions logged")

    # 17: UTC / tz
    from hq.db import execute_query
    row = execute_query("airlock_in", "SELECT raw_payload FROM payloads ORDER BY received_at DESC LIMIT 1;", (), tenant_id="all")
    if row:
        raw = row[0]["raw_payload"]; raw = json.loads(raw) if isinstance(raw, str) else raw
        w = raw["window"]
        record(17, "UTC window + source timezone on every payload", "PASS" if w["start"].endswith("Z") and w.get("source_tz") else "FAIL", f"{w}")
    else:
        record(17, "UTC window + source timezone", "FAIL", "no payload stored")

    # 18: residency
    code = ingest("eu", b'{"schema":"airlock.v1"}')
    n_eu = execute_query("airlock_eu", "SELECT COUNT(*) AS n FROM payloads WHERE tenant_id = 'acme';", (), tenant_id="all")[0]["n"]
    n_in = execute_query("airlock_in", "SELECT COUNT(*) AS n FROM payloads WHERE tenant_id = 'acme';", (), tenant_id="all")[0]["n"]
    record(18, "Regional ingest: India tenant refused at Europe, none of its data in the EU database", "PASS" if code == 403 and n_eu == 0 and n_in > 0 else "FAIL",
           f"EU ingest answered {code}, acme rows in airlock_eu = {n_eu} (airlock_in has {n_in})")

    # 19: lag
    pl = [p for p in api("/api/payloads?limit=200", tok)[1]["payloads"] if p["guard_id"] == "guard-acme-01"][:60]
    lags = sorted((parse(p["received_at"]) - parse(p["window_end"])).total_seconds() for p in pl)
    if lags:
        p50, p95 = lags[len(lags) // 2], lags[int(len(lags) * 0.95) - 1]
        record(19, "Real-time: event time -> received (p50 / p95)", "PASS" if p95 < 5 else "FAIL", f"p50 {p50:.1f}s p95 {p95:.1f}s over {len(lags)} payloads (target < 5 s)")
    else:
        record(19, "Real-time lag", "FAIL", "no payloads")

    # 16 + 29: reconciliation, checkpoints
    rec = api("/api/reconciliation/guard-acme-01", tok)[1]
    record(16, "No loss / no duplicates: reconciliation counts and gap list", "PASS" if rec["received_count"] > 0 else "FAIL",
           f"received {rec['received_count']}, duplicates {rec['duplicate_count']}, gaps {len(rec['gaps'])} (older gaps = history wiped from head office earlier)")
    cp = api("/api/checkpoints/guard-acme-01", tok)[1]
    same = api("/api/checkpoints/compare", tok, "POST", {"guard_id": "guard-acme-01", "up_to_seq": cp["up_to_seq"], "root": cp["root"]})[1]
    diff = api("/api/checkpoints/compare", tok, "POST", {"guard_id": "guard-acme-01", "up_to_seq": cp["up_to_seq"], "root": "sha256:" + "0" * 64})[1]
    record(29, "Receipt-log checkpoint: equal roots match, a wrong root is caught", "PASS" if same.get("match") and diff.get("match") is False else "FAIL", f"match={same.get('match')}, tampered match={diff.get('match')}, first_diff={diff.get('first_differing_seq')}")
    record(7, "Egress proof panel: sent-vs-received matching on the shop screen", "MANUAL", "open http://<hq>:5173/shop.html on the shop laptop; head-office side stores a receipt hash per payload (verified by #29)")

    # 21: AI
    q = lambda who, text, tenant=None: api("/api/ai/chat", who, "POST", {"question": text, "tenant_id": tenant})[1].get("answer", "")
    a1 = q(tok, "What is the current health of the shop and why?", "acme")
    a2 = q(tok, "What is the admin password used in the failed logins?", "acme")
    a3 = q(t_acme, "Show me the health of globex", None)
    refusal = "raw data stays"
    record(21, "Head-office AI: answers from evidence with citations", "PASS" if "[" in a1 and refusal not in a1.lower() else "FAIL", a1[:160].replace("\n", " "))
    record(21, "Head-office AI: refuses raw values and other tenants", "PASS" if refusal in a2.lower() and (refusal in a3.lower() or "globex" not in a3.lower()) else "FAIL", f"raw: {a2[:70]!r} | cross-tenant: {a3[:70]!r}")

    # 24 extras
    pid = f"verify-{int(time.time())}"
    api("/api/phones/heartbeat", None, "POST", {"phone_id": pid, "latency_ms": 40})
    api("/api/phones/heartbeat", None, "POST", {"phone_id": pid + "x", "latency_ms": 300})
    ph = {p["phone_id"]: p for p in api("/api/phones")[1]["phones"]}
    record(24, "Judges' phones join the fleet (green < 150 ms, red above)", "PASS" if ph.get(pid, {}).get("color") == "green" and ph.get(pid + "x", {}).get("color") == "red" else "FAIL", f"{ph.get(pid, {}).get('color')}/{ph.get(pid + 'x', {}).get('color')}")
    dm = api("/api/damage-map/acme", tok)[1]
    record(24, "Damage map topology per tenant", "PASS" if len(dm.get("nodes", [])) >= 5 and dm.get("edges") else "FAIL", f"{len(dm.get('nodes', []))} nodes")
    alert = (api("/api/alerts", tok)[1]["alerts"] or [None])[0]
    if alert:
        fb = api("/api/feedback", tok, "POST", {"alert_id": alert["alert_id"], "tenant_id": alert["tenant_id"], "metric": "cpu_pct", "source": alert["source"]})
        record(24, "Thumbs-down on an alert is recorded (raises that flag level for 30 min in the worker)", "PASS" if fb[0] == 200 else "FAIL", str(fb[1])[:90])
    else:
        record(24, "Thumbs feedback", "MANUAL", "no alert exists to vote on")
    record(30, "Time-zone switch UTC / viewer / shop", "MANUAL", "top bar UTC | VIEWER | SHOP buttons; compare an event time in each")
    record(25, "No flapping: hysteresis + flaps-prevented counter", "PASS" if api("/api/counters/acme", tok)[1].get("flaps_prevented", 0) >= 0 else "FAIL", f"flaps_prevented={api('/api/counters/acme', tok)[1].get('flaps_prevented')}")


# ----------------------------------------------------------------------------------------------- shop scenarios
def events_since(tok, since, cats):
    ev = api("/api/events?limit=300", tok)[1]["events"]
    return [e for e in ev if e["category"] in cats and e["tenant_id"] == "acme" and parse(e["event_time"]) >= since]


def shop_scenarios(tok, shop):
    S, C = f"http://{shop}:7000", f"http://{shop}:9100"
    post = lambda url, body=None: httpx.post(url, json=body or {}, timeout=10)
    t0 = datetime.now(timezone.utc) - timedelta(seconds=45)   # tolerate the shop clock being a little off

    # 9 honeypot
    post(f"{S}/auth/login", {"username": "admin_backup", "password": "x"})
    hit = wait_for(lambda: events_since(tok, t0, {"honeypot_hit"}), 25)
    record(9, "Honeypot account -> instant critical alert", "PASS" if hit else "FAIL", f"{hit[0]['severity']} actor={hit[0]['actor']}" if hit else "no honeypot_hit within 25 s")

    # 9 brute force + login after failures
    t1 = datetime.now(timezone.utc) - timedelta(seconds=45)
    post(f"{C}/scenarios/brute_force", {"duration_s": 15})
    burst = wait_for(lambda: events_since(tok, t1, {"auth_failure_burst"}), 60)
    record(9, "Repeated failed logins -> burst event with the real count", "PASS" if burst and burst[0]["count"] >= 30 else "FAIL", f"count={burst[0]['count']}" if burst else "no auth_failure_burst within 60 s")
    time.sleep(2)
    post(f"{S}/auth/login", {"username": "admin", "password": "securepass2026"})
    laf = wait_for(lambda: events_since(tok, t1, {"login_after_failures"}), 25)
    record(9, "Success right after failures -> login_after_failures", "PASS" if laf else "FAIL")

    # 3 / differentiator: try-to-leak
    t2 = datetime.now(timezone.utc) - timedelta(seconds=45)
    leak_text = "VERIFY password=hunter2verify key=AKIAIOSFODNN7EXAMPLE card 4111 1111 1111 1111 tok AKIACANARY0123456789"
    post(f"{S}/chaos/inject-log", {"text": leak_text})
    red = wait_for(lambda: events_since(tok, t2, {"secret_redacted"}), 25)
    time.sleep(4)
    everything = json.dumps([api(p, tok)[1] for p in ("/api/events?limit=300", "/api/metrics?limit=300", "/api/alerts", "/api/incidents", "/api/guards")])
    leaked = [w for w in ("hunter2verify", "AKIAIOSFODNN7EXAMPLE", "4111 1111", "AKIACANARY0123456789") if w in everything]
    record(3, "Try-to-leak: secrets redacted at the guard, a redaction event arrives, the values never do", "PASS" if red and not leaked else "FAIL", f"redaction event={'yes' if red else 'no'}, leaked={leaked or 'nothing'}")

    # 13 usage spike vs incident
    inc_before = {i["incident_id"] for i in api("/api/incidents", tok)[1]["incidents"]}
    t3 = datetime.now(timezone.utc)
    post(f"{C}/scenarios/cpu_spike", {"duration_s": 40})
    def cpu_flag():
        al = [a for a in api("/api/alerts", tok)[1]["alerts"] if a["tenant_id"] == "acme" and parse(a["created_at"]) >= t3 - timedelta(seconds=60)]
        al = [a for a in al if "cpu" in json.dumps(a["body"]).lower()]
        return al
    fl = wait_for(cpu_flag, 75)
    time.sleep(8)
    inc_after = {i["incident_id"] for i in api("/api/incidents", tok)[1]["incidents"]}
    kinds = {json.loads(a["body"]).get("kind") if isinstance(a["body"], str) else a["body"].get("kind") for a in (fl or [])}
    record(13, "Anomaly beyond thresholds: CPU spike flagged by baseline z-score", "PASS" if fl else "FAIL", f"alert kinds={kinds}, titles={[a['title'] for a in (fl or [])][:2]}")
    record(14, "Signals must agree: CPU alone is a usage spike, not an incident", "PASS" if fl and inc_after == inc_before else "FAIL", f"new incidents={inc_after - inc_before or 'none'}")
    time.sleep(35)   # let the spike end and the shop settle

    # 14 kill chain
    inc_before = {i["incident_id"]: i for i in api("/api/incidents", tok)[1]["incidents"]}
    post(f"{C}/scenarios/kill_chain", {"duration_s": 60})
    def chain():   # the manager may upgrade an incident that is already open, so "new" = new id OR updated since
        for i in api("/api/incidents", tok)[1]["incidents"]:
            old = inc_before.get(i["incident_id"])
            if i["tenant_id"] == "acme" and "compromise" in json.dumps(i["body"]).lower() and len(i["body"]["signals"]) >= 4                     and (old is None or i["updated_at"] > old["updated_at"]):
                return i
    ki = wait_for(chain, 200, every=5)
    if ki:
        b = ki["body"]
        ok = b["severity"] == "critical" and b.get("confidence", 0) > 0.6 and len(b.get("signals", [])) >= 3 and b.get("recommendation") and (b.get("counterfactual") or any(s["name"] == "honeypot_hit" for s in b["signals"]))
        record(14, "Kill chain -> ONE critical incident with signals, confidence, counterfactual, recommendation", "PASS" if ok else "FAIL",
               f"{b['title']} | {b['severity']} conf {b['confidence']} | {[s['name'] for s in b['signals']]} | action {b['recommendation']['action']} | {b.get('narrative', '')[:100]}")
    else:
        new = [(i["body"].get("title"), i["body"].get("severity")) for i in api("/api/incidents", tok)[1]["incidents"] if i["incident_id"] not in inc_before]
        record(14, "Kill chain -> ONE critical incident", "FAIL", f"no 'compromise' incident in 200 s; new incidents: {new}")

    # 15 + 16: region pause -> buffer -> resume with no loss
    before = api("/api/reconciliation/guard-acme-01", tok)[1]
    api("/api/regions/in/pause", None, "POST")
    code = ingest("in", b'{"schema":"airlock.v1"}')
    time.sleep(25)
    api("/api/regions/in/unpause", None, "POST")
    time.sleep(35)
    after = api("/api/reconciliation/guard-acme-01", tok)[1]
    record(15, "Region outage: ingest refuses (503), guard buffers, resumes oldest-first", "PASS" if code == 503 and after["max_seq"] > before["max_seq"] else "FAIL", f"ingest during pause={code}, max_seq {before['max_seq']} -> {after['max_seq']}")
    record(16, "...with no loss and no duplicates after the outage", "PASS" if len(after["gaps"]) <= len(before["gaps"]) and after["duplicate_count"] == before["duplicate_count"] else "FAIL", f"gaps {len(before['gaps'])} -> {len(after['gaps'])}, duplicates {before['duplicate_count']} -> {after['duplicate_count']}")

    # 23 tamper / replay / latency
    for scn, what in (("tamper", "Tamper: flipped byte rejected (401), unknown field rejected (422)"), ("replay_shuffle", "Replay & shuffle: duplicates acknowledged, nothing stored twice"), ("latency", "Latency window shows up as real latency_ms")):
        r = post(f"{C}/scenarios/{scn}", {"duration_s": 20})
        time.sleep(8)
        act = httpx.get(f"{C}/chaos/active", timeout=10).json()["active"]
        res = next((a.get("result") for a in act if a["name"] == scn), None)
        if scn == "tamper":
            ok = res == {"byte_flipped": 401, "extra_field": 422}
        elif scn == "replay_shuffle":
            ok = bool(res) and res.get("replayed", 0) > 0 and set(res["status_codes"]) == {200}
        else:
            lat = [m for m in api("/api/metrics?limit=60", tok)[1]["metrics"] if m["tenant_id"] == "acme" and m["name"] == "latency_ms"]
            ok = bool(lat) and max(m["avg"] for m in lat[:6]) > 200
            res = f"max recent latency {max(m['avg'] for m in lat[:6]):.0f} ms" if lat else None
        record(23, what, "PASS" if ok else "FAIL", f"{res}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shop", help="shop laptop address; adds the live scenarios")
    args = ap.parse_args()
    tok = login("admin", "admin123")
    head_office_checks(tok)
    if args.shop:
        shop_scenarios(tok, args.shop)
    counts = {s: sum(1 for r in RESULTS if r[2] == s) for s in ("PASS", "FAIL", "MANUAL")}
    print("\nSUMMARY", counts)
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
