"""T4 + T8c: anomaly flags, River second opinion, usage-spike rule, learned scheduled jobs. Pure logic on top of engine.Engine.

Flag        = |z| >= 3 for 3 windows in a row on one metric (the Baseline streak in engine.py).
Second view = River HalfSpaceTrees on [cpu, mem, latency, loss, net_out]; score >= 0.7 means it agrees.
Rule        = CPU flagged alone -> info "usage spike". CPU + latency/loss flag or an error event -> incident candidate.
              Anything else flagged -> low "anomaly". Incidents are built from these in incidents.py.
Schedule    = a spike that starts at a steady interval (3 gaps within +/-10 %) is learned as a scheduled job and
              suppressed with the reason shown; an off-schedule or clearly larger spike still alerts.
One open alert per tenant; it closes after the flags have been gone for exit_s (no alert flapping)."""
from dataclasses import dataclass
from river import anomaly
from hq.aiops.engine import Engine, Z_METRICS

# feature -> value that maps to 1.0 (HalfSpaceTrees wants inputs in [0, 1])
SCALE = {"cpu_pct": 100.0, "mem_pct": 100.0, "latency_ms": 1000.0, "packet_loss_pct": 10.0, "net_out_kbps": 1000.0}
ERROR_EVENTS = {"service_down", "log_pattern_spike"}
HST_THRESHOLD = 0.7
SEVERITY = {"usage_spike": "info", "anomaly": "low", "incident_candidate": "high", "scheduled_job": "info"}
SCHED_TOLERANCE, SCHED_BIGGER = 0.10, 1.5   # +/-10 % on timing; "larger than usual" = 1.5x the learned peak


@dataclass
class Alert:
    alert_id: str
    tenant_id: str
    kind: str                 # usage_spike | anomaly | incident_candidate | scheduled_job
    severity: str
    title: str
    signals: list             # [{name, source, value, baseline, z}] (+ events as {name, source, value})
    second_opinion: float     # best HalfSpaceTrees score among the flagged sources (0 if unknown)
    agrees: bool              # second opinion >= HST_THRESHOLD
    started: float
    last_flag: float
    closed: bool = False
    suppressed_reason: str | None = None


class ScheduleLearner:
    """Learns steady-interval spikes per (tenant, source, metric) from the times each spike starts."""
    def __init__(self):
        self.edges, self.vals, self.learned = {}, {}, {}

    def on_spike(self, key, t, value):
        """Call at each spike start. Returns the learned interval (s) if this spike is on schedule, else None."""
        L = self.learned.get(key)
        if L:
            n = max(1, round((t - L["last"]) / L["interval"]))
            on_time = abs(t - (L["last"] + n * L["interval"])) <= SCHED_TOLERANCE * L["interval"]
            if on_time and value <= SCHED_BIGGER * L["peak"]:
                L["last"], L["count"] = t, L["count"] + 1
                return L["interval"]
            return None  # off schedule or bigger than usual: alert, but keep the learned schedule
        e, v = self.edges.setdefault(key, []), self.vals.setdefault(key, [])
        e.append(t); v.append(value)
        del e[:-4], v[:-4]
        if len(e) == 4:
            gaps = [b - a for a, b in zip(e, e[1:])]
            mean = sum(gaps) / 3
            if all(abs(g - mean) <= SCHED_TOLERANCE * mean for g in gaps):
                self.learned[key] = {"interval": mean, "last": t, "peak": sum(v) / len(v), "count": 4}
                return mean
        return None


class Detector:
    def __init__(self, engine: Engine, window_size: int = 30, seed: int = 42):
        self.e = engine
        self.window_size, self.seed = window_size, seed
        self.hst, self.n, self.score = {}, {}, {}   # per (tenant, source)
        self.open = {}                               # tenant -> Alert
        self.learner, self.active, self.sched = ScheduleLearner(), set(), {}

    def observe(self, tenant, source):
        """Call right after engine.ingest() for that window: scores it, and learns from it unless it is anomalous."""
        st = self.e.src[(tenant, source)]
        x = {k: min(max(st.last.get(k, 0.0) / s, 0.0), 1.0) for k, s in SCALE.items()}
        if not any(k in st.last for k in SCALE):
            return
        m = self.hst.setdefault((tenant, source), anomaly.HalfSpaceTrees(
            n_trees=25, height=8, window_size=self.window_size, limits={k: (0.0, 1.0) for k in SCALE}, seed=self.seed))
        n = self.n.get((tenant, source), 0)
        # scores before the first full window are meaningless, so report 0 until warmed up
        self.score[(tenant, source)] = m.score_one(x) if n >= self.window_size else 0.0
        if not any(b.streak > 0 for (t, s, _), b in self.e.base.items() if (t, s) == (tenant, source)):
            m.learn_one(x)  # ponytail: don't learn from anomalies; same idea as the EWMA baseline
            self.n[(tenant, source)] = n + 1

    def flags(self, tenant):
        """Active flags for a tenant: metrics with |z| >= 3 for 3+ windows. 'scheduled' = learned interval or None."""
        th, out = self.e.th(tenant), []
        for (t, s, name), b in self.e.base.items():
            if t == tenant and name in Z_METRICS and b.streak >= th.z_windows:
                st = self.e.src[(t, s)]
                out.append({"name": name, "source": s, "value": round(st.last[name], 2), "baseline": round(b.mean, 2),
                            "z": round(st.z[name], 1), "scheduled": self.sched.get((t, s, name))})
        return out

    def errors(self, tenant, now):
        th, out = self.e.th(tenant), []
        for (t, s), st in self.e.src.items():
            if t != tenant:
                continue
            for cat, (ts, _sev, _cnt, _actor) in st.events.items():
                if cat in ERROR_EVENTS and now - ts <= th.event_hold_s:
                    out.append({"name": cat, "source": s, "value": 1.0})
            if st.last.get("service_up", 1) < 1 and now - (st.last_arrival or 0) < th.stale_s:
                out.append({"name": "service_up", "source": s, "value": 0.0})
        return out

    def _spike_starts(self, tenant, now):
        """Learn from spike starts: a flag that was not active last step is a new spike."""
        live = {(tenant, f["source"], f["name"]): f for f in self.flags(tenant)}
        for key, f in live.items():
            if key not in self.active:
                interval = self.learner.on_spike(key, now, f["value"])
                if interval:
                    self.sched[key] = interval
                else:
                    self.sched.pop(key, None)
        self.active = {k for k in self.active if k[0] != tenant} | set(live)
        for key in [k for k in self.sched if k[0] == tenant and k not in live]:
            del self.sched[key]

    def step(self, now):
        """Evaluate every tenant; returns [("open"|"update"|"close", Alert)]."""
        changes, tenants = [], {t for (t, _s) in self.e.src}
        for tenant in tenants:
            self._spike_starts(tenant, now)
            all_fl, errs, alert = self.flags(tenant), self.errors(tenant, now), self.open.get(tenant)
            fl = [f for f in all_fl if not f["scheduled"]]
            sched = [f for f in all_fl if f["scheduled"]]
            if not all_fl:
                if alert and now - alert.last_flag >= self.e.th(tenant).exit_s:
                    alert.closed = True
                    del self.open[tenant]
                    changes.append(("close", alert))
                continue
            names = {f["name"] for f in fl}
            reason = None
            if not fl and not errs:   # only learned scheduled spikes are active
                kind = "scheduled_job"
                f0 = sched[0]
                title = f"Scheduled job: {f0['name']} spike (every ~{f0['scheduled']:.0f} s)"
                reason = (f"{f0['name']} spikes every ~{f0['scheduled']:.0f} s (3 equal gaps within 10 %); "
                          "learned as a scheduled job, suppressed")
                fl = sched
            elif "cpu_pct" in names:
                companions = names & {"latency_ms", "packet_loss_pct"}
                kind = "incident_candidate" if companions or errs else "usage_spike"
            else:
                kind = "anomaly"
            if kind != "scheduled_job":
                title = {"usage_spike": "CPU usage spike (latency and errors normal)",
                         "incident_candidate": "CPU anomaly with " + ", ".join(sorted((names - {"cpu_pct"}) | {e["name"] for e in errs})),
                         "anomaly": "Anomaly: " + ", ".join(sorted(names))}[kind]
            so = max((self.score.get((tenant, f["source"]), 0.0) for f in fl), default=0.0)
            signals = fl + errs
            if alert is None:
                alert = self.open[tenant] = Alert(f"alr-{tenant}-{int(now)}", tenant, kind, SEVERITY[kind], title, signals,
                                                  round(so, 2), so >= HST_THRESHOLD, now, now, suppressed_reason=reason)
                changes.append(("open", alert))
            else:
                alert.last_flag = now
                if (kind, [s["name"] for s in signals]) != (alert.kind, [s["name"] for s in alert.signals]):
                    alert.kind, alert.severity, alert.title, alert.signals = kind, SEVERITY[kind], title, signals
                    alert.suppressed_reason = reason
                    alert.second_opinion, alert.agrees = round(so, 2), so >= HST_THRESHOLD
                    changes.append(("update", alert))
        return changes
