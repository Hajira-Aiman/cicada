"""T5-T8: group signals into explained incidents. Pure logic (no I/O), one instance per region (data residency).

Raw alert  = a metric flag turning on, or one event occurrence (a repeating burst counts every window).
Incident   = raw alerts of one tenant on related components (topology) within 120 s, merged into one object.
             Usage spikes, non-security anomalies and learned scheduled jobs count as raw alerts but never open an incident.
Kill chain = failed-login burst -> login success / odd-hour login -> CPU anomaly -> outbound spike, in order, within 10 min
             -> one critical "Possible compromise: cryptomining" incident.
Contribution = share of each signal's |z| (events: count ratio, capped) in the total.
Confidence   = 0.4 + 0.15 x agreeing signals + 0.1 if a named rule matched + 0.1 if a change preceded it, capped at 0.95.
Counterfactual = re-run the health rule without each signal. Runbook = incident type -> safe action with why/risk/rollback."""
from datetime import datetime, timezone
from contracts.models import ActionRecommendation, Incident, SignalEvidence

JOIN_WINDOW_S = 120
CHAIN_WINDOW_S = 600     # kill chain must complete within 10 min
CHANGE_WINDOW_S = 300    # a change counts if it happened up to 5 min before the first signal
EVENT_BASELINE = 2.0     # a "normal" event count, so count / baseline gives the ratio
EVENT_WEIGHT_CAP = 10.0  # ponytail: cap so one big burst can't hide the metric signals; tune on real data
SECURITY_EVENTS = {"auth_failure_burst", "login_after_failures", "odd_hour_login", "honeypot_hit", "service_down"}
CHANGE_EVENTS = {"app_restarted", "version_changed", "config_changed", "new_process"}
CHANGE_LABEL = {"app_restarted": "the app restarted", "version_changed": "the version changed",
                "config_changed": "the config changed", "new_process": "a new process appeared"}
NETWORK_METRICS = {"latency_ms", "packet_loss_pct"}
COMPONENT = {"cpu_pct": "host", "mem_pct": "host", "disk_pct": "host", "net_in_kbps": "host", "net_out_kbps": "host",
             "latency_ms": "shop-api", "packet_loss_pct": "shop-api", "service_up": "shop-api", "service_down": "shop-api",
             "auth_failure_burst": "login", "login_after_failures": "login", "odd_hour_login": "login", "honeypot_hit": "login"}
# default shop topology (edges); T9 can replace it per tenant. Related = connected in this graph.
TOPOLOGY = [("host", "shop-api"), ("shop-api", "login"), ("shop-api", "checkout"), ("shop-api", "db")]
LABEL = {"auth_failure_burst": "login failure burst", "login_after_failures": "login succeeded after failures",
         "odd_hour_login": "login at an odd hour", "honeypot_hit": "honeypot account used", "service_down": "service down",
         "cpu_pct": "CPU anomaly", "latency_ms": "latency anomaly", "packet_loss_pct": "packet loss anomaly",
         "mem_pct": "memory anomaly", "net_out_kbps": "outbound traffic anomaly", "net_in_kbps": "inbound traffic anomaly",
         "disk_pct": "disk anomaly"}
SEV_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
HEALTH_RANK = {"Excellent": 0, "Good": 1, "Fair": 2, "Poor": 3}
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def related(a, b, edges=TOPOLOGY):
    """True if components a and b are connected in the topology (or equal)."""
    if a == b:
        return True
    seen, todo = {a}, [a]
    while todo:
        n = todo.pop()
        for x, y in edges:
            for u, v in ((x, y), (y, x)):
                if u == n and v not in seen:
                    seen.add(v); todo.append(v)
    return b in seen


def chain_match(occ):
    """occ: stage -> [(time, item)]. Returns the 4 chain items in order if the kill chain is complete, else None."""
    burst = sorted(occ.get("burst", []), key=lambda x: x[0])
    login, cpu, net = (sorted(occ.get(k, []), key=lambda x: x[0]) for k in ("login", "cpu", "net"))
    for tb, ib in burst:
        step = lambda lst, after: next(((t, i) for t, i in lst if t >= after), None)
        l = step(login, tb)
        c = step(cpu, l[0]) if l else None
        n = step(net, c[0]) if c else None
        if n and n[0] - tb <= CHAIN_WINDOW_S:
            return [ib, l[1], c[1], n[1]]
    return None


class Inc:
    def __init__(self, iid, tenant, now):
        self.id, self.tenant, self.started, self.last = iid, tenant, now, now
        self.sig = {}        # (source, name) -> dict
        self.rules, self.river = set(), False
        self.changes = []    # [(delta_s, label)] changes in the 5 min before the first signal
        self.proc = None     # pseudonym of the suspicious new process, if the guard reported one
        self.sent = None     # signature of the last emitted version
        self.closed = False

    def components(self):
        return {COMPONENT.get(n, "host") for (_s, n) in self.sig}

    def severity(self):
        if "kill_chain" in self.rules:
            return "critical"
        return max((s["sev"] for s in self.sig.values()), key=SEV_RANK.get, default="low")

    def weights(self):
        w = {k: (abs(s["z"]) if s["z"] is not None else min(s["count"] / EVENT_BASELINE, EVENT_WEIGHT_CAP))
             for k, s in self.sig.items()}
        tot = sum(w.values()) or 1.0
        return {k: 100.0 * v / tot for k, v in w.items()}

    def confidence(self):
        agreeing = len(self.sig) + (1 if self.river else 0)
        raw = 0.4 + 0.15 * agreeing + (0.1 if self.rules else 0.0) + (0.1 if self.changes else 0.0)
        return min(raw, 0.95), agreeing, raw

    def title(self):
        names = {n for (_s, n) in self.sig}
        if "kill_chain" in self.rules:
            return "Possible compromise: cryptomining"
        for n, t in (("honeypot_hit", "Honeypot account used"), ("service_down", "Service down")):
            if n in names:
                return t
        if "auth_failure_burst" in names:
            return "Repeated failed logins (possible brute force)"
        if "cpu_pct" in names:
            return "CPU anomaly with " + ", ".join(sorted(LABEL[n].split()[0].lower() for n in names - {"cpu_pct"}))
        if names & NETWORK_METRICS:
            return "Network degradation"
        return "Security event: " + ", ".join(sorted(LABEL.get(n, n) for n in names))

    # ---- T8: counterfactual -------------------------------------------------
    def _assess(self, keys):
        """Health state + severity if only `keys` had happened (the health rule re-run on a subset)."""
        names = {n for (_s, n) in keys}
        chain = ("auth_failure_burst" in names and names & {"login_after_failures", "odd_hour_login"}
                 and "cpu_pct" in names and "net_out_kbps" in names)
        bad = any((n == "latency_ms" and self.sig[(s, n)]["value"] > 1000) or (n == "packet_loss_pct" and self.sig[(s, n)]["value"] > 10)
                  for (s, n) in keys)
        poor = chain or names & {"honeypot_hit", "service_down"} or bad
        state = "Poor" if poor else "Fair" if keys else "Excellent"
        sev = "critical" if chain else max((self.sig[k]["sev"] for k in keys), key=SEV_RANK.get, default="info")
        return state, sev

    def counterfactual(self):
        keys = set(self.sig)
        state, sev = self._assess(keys)
        contrib = self.weights()
        for k in sorted(keys, key=lambda k: -contrib[k]):
            s2, v2 = self._assess(keys - {k})
            noun = f"the {LABEL.get(k[1], k[1])}"
            if HEALTH_RANK[s2] < HEALTH_RANK[state]:
                return f"If {noun} had stayed normal, this would be {s2}, not {state}"
            if SEV_RANK[v2] < SEV_RANK[sev]:
                return f"Without {noun} this would be a {v2} incident, not {sev.capitalize()}"
        return None

    # ---- T8: runbook ---------------------------------------------------------
    def recommendation(self):
        names = {n for (_s, n) in self.sig}
        actor = lambda n: next((s["actor"] for (_x, nn), s in self.sig.items() if nn == n and s.get("actor")), None)
        src = lambda n: next((x for (x, nn) in self.sig if nn == n), None)
        cpu = next((s["value"] for (_x, nn), s in self.sig.items() if nn == "cpu_pct"), None)
        if "kill_chain" in self.rules or ("cpu_pct" in names and self.proc):
            if self.proc:
                why = f"Process {self.proc} appeared after the suspicious login" + (f" while CPU is {cpu:.0f} %" if cpu else "")
                return ActionRecommendation(action="kill_process", target=self.proc, why=why, risk="low", reversible=True,
                                            rollback="Restart shop-api if it was affected")
            a = actor("auth_failure_burst")
            if a:
                return ActionRecommendation(action="block_source", target=a, why="No suspicious process was reported; cut off the attacker first",
                                            risk="low", reversible=True, rollback="Auto-unblock after 15 min or Undo button")
        if "honeypot_hit" in names and actor("honeypot_hit"):
            return ActionRecommendation(action="block_source", target=actor("honeypot_hit"), why="A trap account was used; no legitimate user does that",
                                        risk="low", reversible=True, rollback="Auto-unblock after 15 min or Undo button")
        if "service_down" in names:
            return ActionRecommendation(action="restart_service", target=src("service_down"), why="The service failed its health check",
                                        risk="medium", reversible=True, rollback="Escalate if still down after 10 s")
        if "auth_failure_burst" in names and actor("auth_failure_burst"):
            n = self.sig[(src("auth_failure_burst"), "auth_failure_burst")]["count"]
            return ActionRecommendation(action="block_source", target=actor("auth_failure_burst"), why=f"{n} failed logins from one source",
                                        risk="low", reversible=True, rollback="Auto-unblock after 15 min or Undo button")
        return ActionRecommendation(action="investigate", target=None, why="Latency or resource anomaly with no safe automatic fix",
                                    risk="low", reversible=True, rollback=None)

    def to_contract(self):
        conf, agreeing, raw = self.confidence()
        contrib = self.weights()
        order = sorted(self.sig.items(), key=lambda kv: kv[1]["first"])
        sigs = [SignalEvidence(evidence_id=f"ev-{i}", name=n, value=s["value"], baseline=s["baseline"], z=s["z"],
                               contribution_pct=round(contrib[(src, n)], 1))
                for i, ((src, n), s) in enumerate(order, 1)]
        path = [f"{LABEL.get(n, n)} at {iso(s['first'])[11:19]}" + (f" (x{s['repeats']})" if s["repeats"] > 1 else "")
                for (_src, n), s in order]
        path += [f"rule matched: {r}" for r in sorted(self.rules)]
        if self.river:
            path.append("River second opinion agrees")
        path.append(f"confidence = 0.4 + 0.15 x {agreeing} agreeing signals + {0.1 if self.rules else 0} rule bonus"
                    f" + {0.1 if self.changes else 0} change bonus = {raw:.2f}" + (" (capped at 0.95)" if raw > 0.95 else ""))
        return Incident(incident_id=self.id, tenant_id=self.tenant, title=self.title(), severity=self.severity(),
                        confidence=round(conf, 2), started_at=iso(self.started),
                        affected=sorted({s for (s, _n) in self.sig} | self.components()),
                        signals=sigs, reasoning_path=path, counterfactual=self.counterfactual(),
                        recommendation=self.recommendation(),
                        changes_before=[f"started {d:.0f} s after {lab}" for d, lab in self.changes],
                        repeat_count=sum(s["repeats"] for s in self.sig.values()))

    def signature(self):
        return (self.title(), self.severity(), tuple(sorted(self.sig)), round(self.confidence()[0], 2),
                sum(s["repeats"] for s in self.sig.values()), len(self.changes), self.proc, self.closed)


class Manager:
    def __init__(self, engine, detector, topology=TOPOLOGY):
        self.e, self.d, self.edges = engine, detector, topology
        self.open, self.n = {}, {}            # tenant -> Inc, tenant -> counter
        self.raw, self.incidents = {}, {}     # per tenant counters
        self.active_flags, self.event_seen = set(), {}
        self.occ, self.chg = {}, {}           # kill-chain stage times, change events: per tenant

    def _signal(self, inc, key, now, new, first=None, **kw):
        s = inc.sig.get(key)
        if s is None:
            s = inc.sig[key] = {"first": first if first is not None else now, "repeats": 1}
        elif new:
            s["repeats"] += 1
        s.update(kw)
        inc.started = min(inc.started, s["first"])

    def _stage(self, tenant, stage, t, item):
        self.occ.setdefault(tenant, {}).setdefault(stage, []).append((t, item))

    def step(self, now):
        """Returns [(kind, Inc)] for opened / updated / closed incidents. Also updates raw + incident counters."""
        changes = []
        for tenant in {t for (t, _s) in self.e.src}:
            th = self.e.th(tenant)
            items = []   # incident-worthy signals seen this step
            alert = self.d.open.get(tenant)
            # 1) metric flags: raw alert on rising edge; worthy only when the detector says incident-level
            live = {(tenant, f["source"], f["name"]): f for f in self.d.flags(tenant)}
            for k, f in live.items():
                new = k not in self.active_flags
                if new:
                    self.raw[tenant] = self.raw.get(tenant, 0) + 1
                item = dict(key=(f["source"], f["name"]), new=new, value=f["value"], baseline=f["baseline"], z=f["z"],
                            count=0, sev="high", first=now, actor=None)
                if new and not f["scheduled"] and f["name"] in ("cpu_pct", "net_out_kbps"):
                    self._stage(tenant, "cpu" if f["name"] == "cpu_pct" else "net", now, item)
                worthy = alert and not f["scheduled"] and (
                    alert.kind == "incident_candidate" or (alert.kind == "anomaly" and f["name"] in NETWORK_METRICS))
                if worthy:
                    items.append({**item, "sev": "high" if alert.kind == "incident_candidate" else "medium"})
            self.active_flags = {k for k in self.active_flags if k[0] != tenant} | set(live)
            # 2) events: every window with the event is a raw alert (a burst repeats); security ones are worthy
            for (t, s), st in self.e.src.items():
                if t != tenant:
                    continue
                for cat, (ts, sev, cnt, actor) in st.events.items():
                    if now - ts > th.event_hold_s or self.event_seen.get((t, s, cat)) == ts:
                        continue
                    self.event_seen[(t, s, cat)] = ts
                    self.raw[tenant] = self.raw.get(tenant, 0) + 1
                    item = dict(key=(s, cat), new=True, value=float(cnt), baseline=EVENT_BASELINE, z=None, count=cnt,
                                sev=sev, first=ts, actor=actor)
                    if cat in CHANGE_EVENTS:
                        self.chg.setdefault(tenant, []).append((ts, cat, s, actor))
                    if cat == "auth_failure_burst":
                        self._stage(tenant, "burst", ts, item)
                    elif cat in ("login_after_failures", "odd_hour_login"):
                        self._stage(tenant, "login", ts, item)
                    if cat in SECURITY_EVENTS:
                        items.append(item)
            # 3) kill chain: stages in order within 10 min -> add all four stages to the incident
            inc = self.open.get(tenant)
            kill = chain_match(self.occ.get(tenant, {}))
            if kill:
                self.occ[tenant] = {}   # consume the stage history so one chain can never fire twice
            if kill and not (inc and "kill_chain" in inc.rules):
                items += [{**i, "new": False} for i in kill]
            else:
                kill = None
            # 4) group into an incident
            if items:
                comps = {COMPONENT.get(i["key"][1], "host") for i in items}
                joins = inc and now - inc.last <= JOIN_WINDOW_S and any(
                    related(a, b, self.edges) for a in comps for b in inc.components())
                if not joins:
                    if inc:
                        inc.closed = True; changes.append(("close", inc))
                    self.n[tenant] = self.n.get(tenant, 0) + 1
                    self.incidents[tenant] = self.incidents.get(tenant, 0) + 1
                    inc = self.open[tenant] = Inc(f"inc-{tenant}-{self.n[tenant]:04d}", tenant, now)
                for i in items:
                    self._signal(inc, i["key"], now, i["new"], first=i["first"], value=i["value"], baseline=i["baseline"],
                                 z=i["z"], count=i["count"], sev=i["sev"], actor=i["actor"])
                inc.last = now
                inc.river = inc.river or bool(alert and alert.agrees)
                names = {n for (_s, n) in inc.sig}
                if "auth_failure_burst" in names: inc.rules.add("brute_force")
                if "honeypot_hit" in names: inc.rules.add("honeypot")
                if "service_down" in names: inc.rules.add("service_down")
                if "cpu_pct" in names and names & (NETWORK_METRICS | {"service_down"}): inc.rules.add("cpu_with_latency_or_errors")
                if kill: inc.rules.add("kill_chain")
            if inc and not inc.closed:
                # what changed just before the first signal, and the suspicious process (if any)
                inc.changes = [(inc.started - ts, CHANGE_LABEL[c]) for ts, c, _s, _a in self.chg.get(tenant, [])
                               if 0 <= inc.started - ts <= CHANGE_WINDOW_S]
                if "kill_chain" in inc.rules or "cpu_pct" in {n for (_s, n) in inc.sig}:
                    inc.proc = next((a for ts, c, _s, a in reversed(self.chg.get(tenant, []))
                                     if c == "new_process" and a and ts >= inc.started - CHANGE_WINDOW_S), inc.proc)
                if items and inc.sent is None:
                    inc.sent = inc.signature(); changes.append(("open", inc))
                elif items and inc.signature() != inc.sent:
                    inc.sent = inc.signature(); changes.append(("update", inc))
                elif not items and now - inc.last > JOIN_WINDOW_S:
                    inc.closed = True; del self.open[tenant]; changes.append(("close", inc))
            # forget stage times and change events older than the 10 min kill-chain window
            for lst in self.occ.get(tenant, {}).values():
                lst[:] = [(t, i) for t, i in lst if now - t <= CHAIN_WINDOW_S]
            self.chg[tenant] = [c for c in self.chg.get(tenant, []) if now - c[0] <= CHAIN_WINDOW_S]
        return changes

    def counters(self, tenant):
        raw, inc = self.raw.get(tenant, 0), self.incidents.get(tenant, 0)
        return {"raw_alerts": raw, "incidents": inc, "noise_cut_pct": round(100.0 * (1 - inc / raw), 1) if raw else 0.0}
