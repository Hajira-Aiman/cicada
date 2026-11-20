"""T5 + T6: group signals into explained incidents, count the noise cut, compute contributions and confidence.
Pure logic (no I/O). Fed by engine.Engine + anomaly.Detector, one instance per region (data residency).

Raw alert  = a metric flag turning on, or one event occurrence (a repeating burst counts every window).
Incident   = raw alerts of one tenant on related components (topology) within 120 s, merged into one object.
Info-level usage spikes and non-security anomalies are counted as raw alerts but never open an incident.
Contribution = share of each signal's |z| (events: count ratio, capped) in the total.
Confidence   = 0.4 + 0.15 x agreeing signals + 0.1 if a named rule matched, capped at 0.95."""
from datetime import datetime, timezone
from contracts.models import Incident, SignalEvidence

JOIN_WINDOW_S = 120
EVENT_BASELINE = 2.0   # a "normal" event count, so count / baseline gives the ratio
EVENT_WEIGHT_CAP = 10.0  # ponytail: cap so one big burst can't hide the metric signals; tune on real data
SECURITY_EVENTS = {"auth_failure_burst", "login_after_failures", "odd_hour_login", "honeypot_hit", "service_down"}
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


class Inc:
    def __init__(self, iid, tenant, now):
        self.id, self.tenant, self.started, self.last, self.now = iid, tenant, now, now, now
        self.sig = {}        # (source, name) -> dict
        self.rules, self.river = set(), False
        self.sent = None     # signature of the last emitted version
        self.closed = False

    def components(self):
        return {COMPONENT.get(n, "host") for (_s, n) in self.sig}

    def severity(self):
        return max((s["sev"] for s in self.sig.values()), key=SEV_RANK.get, default="low")

    def weights(self):
        w = {k: (abs(s["z"]) if s["z"] is not None else min(s["count"] / EVENT_BASELINE, EVENT_WEIGHT_CAP))
             for k, s in self.sig.items()}
        tot = sum(w.values()) or 1.0
        return {k: 100.0 * v / tot for k, v in w.items()}

    def confidence(self):
        agreeing = len(self.sig) + (1 if self.river else 0)
        raw = 0.4 + 0.15 * agreeing + (0.1 if self.rules else 0.0)
        return min(raw, 0.95), agreeing, raw

    def title(self):
        names = {n for (_s, n) in self.sig}
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
                    f" = {raw:.2f}" + (" (capped at 0.95)" if raw > 0.95 else ""))
        return Incident(incident_id=self.id, tenant_id=self.tenant, title=self.title(), severity=self.severity(),
                        confidence=round(conf, 2), started_at=iso(self.started),
                        affected=sorted({s for (s, _n) in self.sig} | self.components()),
                        signals=sigs, reasoning_path=path, repeat_count=sum(s["repeats"] for s in self.sig.values()))

    def signature(self):
        return (self.title(), self.severity(), tuple(sorted(self.sig)), round(self.confidence()[0], 2),
                sum(s["repeats"] for s in self.sig.values()), self.closed)


class Manager:
    def __init__(self, engine, detector, topology=TOPOLOGY):
        self.e, self.d, self.edges = engine, detector, topology
        self.open, self.n = {}, {}            # tenant -> Inc, tenant -> counter
        self.raw, self.incidents = {}, {}     # per tenant counters
        self.active_flags, self.event_seen = set(), {}

    def _signal(self, inc, key, now, new, **kw):
        s = inc.sig.setdefault(key, {"first": now, "repeats": 0})
        s.update(kw)
        s["repeats"] += 1 if new else 0

    def step(self, now):
        """Returns [(kind, Inc)] for opened / updated / closed incidents. Also updates raw + incident counters."""
        changes = []
        for tenant in {t for (t, _s) in self.e.src}:
            th = self.e.th(tenant)
            items = []   # incident-worthy signals seen this step
            # 1) metric flags: raw alert on rising edge; worthy only when the detector says incident-level
            alert = self.d.open.get(tenant)
            live = {(tenant, f["source"], f["name"]): f for f in self.d.flags(tenant)}
            for k, f in live.items():
                new = k not in self.active_flags
                if new:
                    self.raw[tenant] = self.raw.get(tenant, 0) + 1
                worthy = alert and (alert.kind == "incident_candidate" or (alert.kind == "anomaly" and f["name"] in NETWORK_METRICS))
                if worthy:
                    items.append(dict(key=(f["source"], f["name"]), new=new, value=f["value"], baseline=f["baseline"], z=f["z"],
                                      count=0, sev="high" if alert.kind == "incident_candidate" else "medium"))
            self.active_flags = {k for k in self.active_flags if k[0] != tenant} | set(live)
            # 2) events: every window with the event is a raw alert (a burst repeats); security ones are worthy
            for (t, s), st in self.e.src.items():
                if t != tenant:
                    continue
                for cat, (ts, sev, *cnt) in st.events.items():
                    if now - ts > th.event_hold_s or self.event_seen.get((t, s, cat)) == ts:
                        continue
                    self.event_seen[(t, s, cat)] = ts
                    self.raw[tenant] = self.raw.get(tenant, 0) + 1
                    if cat in SECURITY_EVENTS:
                        items.append(dict(key=(s, cat), new=True, value=float(cnt[0] if cnt else 1), baseline=EVENT_BASELINE, z=None,
                                          count=cnt[0] if cnt else 1, sev=sev))
            inc = self.open.get(tenant)
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
                    self._signal(inc, i["key"], now, i["new"], value=i["value"], baseline=i["baseline"], z=i["z"],
                                 count=i["count"], sev=i["sev"])
                inc.last = now
                inc.river = inc.river or bool(alert and alert.agrees)
                names = {n for (_s, n) in inc.sig}
                if "auth_failure_burst" in names: inc.rules.add("brute_force")
                if "honeypot_hit" in names: inc.rules.add("honeypot")
                if "service_down" in names: inc.rules.add("service_down")
                if "cpu_pct" in names and names & (NETWORK_METRICS | {"service_down"}): inc.rules.add("cpu_with_latency_or_errors")
            if inc and not inc.closed:
                if items and inc.sent is None:
                    inc.sent = inc.signature(); changes.append(("open", inc))
                elif items and inc.signature() != inc.sent:
                    inc.sent = inc.signature(); changes.append(("update", inc))
                elif not items and now - inc.last > JOIN_WINDOW_S:
                    inc.closed = True; del self.open[tenant]; changes.append(("close", inc))
        return changes

    def counters(self, tenant):
        raw, inc = self.raw.get(tenant, 0), self.incidents.get(tenant, 0)
        return {"raw_alerts": raw, "incidents": inc, "noise_cut_pct": round(100.0 * (1 - inc / raw), 1) if raw else 0.0}
