"""T4: anomaly flags, River second opinion, usage-spike rule. Pure logic on top of engine.Engine (no I/O, no LLM).

Flag        = |z| >= 3 for 3 windows in a row on one metric (the Baseline streak in engine.py).
Second view = River HalfSpaceTrees on [cpu, mem, latency, loss, net_out]; score >= 0.7 means it agrees.
Rule        = CPU flagged alone -> info "usage spike". CPU + latency/loss flag or an error event -> incident candidate.
              Anything else flagged -> low "anomaly". T5 turns candidates into grouped incidents.
One open alert per tenant; it closes after the flags have been gone for exit_s (no alert flapping)."""
from dataclasses import dataclass, field
from river import anomaly
from hq.aiops.engine import Engine, Z_METRICS

# feature -> value that maps to 1.0 (HalfSpaceTrees wants inputs in [0, 1])
SCALE = {"cpu_pct": 100.0, "mem_pct": 100.0, "latency_ms": 1000.0, "packet_loss_pct": 10.0, "net_out_kbps": 1000.0}
ERROR_EVENTS = {"service_down", "log_pattern_spike"}
HST_THRESHOLD = 0.7
SEVERITY = {"usage_spike": "info", "anomaly": "low", "incident_candidate": "high"}


@dataclass
class Alert:
    alert_id: str
    tenant_id: str
    kind: str                 # usage_spike | anomaly | incident_candidate
    severity: str
    title: str
    signals: list             # [{name, source, value, baseline, z}] (+ events as {name, source, value: count})
    second_opinion: float     # best HalfSpaceTrees score among the flagged sources (0 if unknown)
    agrees: bool              # second opinion >= HST_THRESHOLD
    started: float
    last_flag: float
    closed: bool = False


class Detector:
    def __init__(self, engine: Engine, window_size: int = 30, seed: int = 42):
        self.e = engine
        self.window_size, self.seed = window_size, seed
        self.hst, self.n, self.score = {}, {}, {}   # per (tenant, source)
        self.open = {}                               # tenant -> Alert

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
        """Active flags for a tenant: metrics with |z| >= 3 for 3+ windows."""
        th, out = self.e.th(tenant), []
        for (t, s, name), b in self.e.base.items():
            if t == tenant and name in Z_METRICS and b.streak >= th.z_windows:
                st = self.e.src[(t, s)]
                out.append({"name": name, "source": s, "value": round(st.last[name], 2),
                            "baseline": round(b.mean, 2), "z": round(st.z[name], 1)})
        return out

    def errors(self, tenant, now):
        th, out = self.e.th(tenant), []
        for (t, s), st in self.e.src.items():
            if t != tenant:
                continue
            for cat, (ts, _sev) in st.events.items():
                if cat in ERROR_EVENTS and now - ts <= th.event_hold_s:
                    out.append({"name": cat, "source": s, "value": 1.0})
            if st.last.get("service_up", 1) < 1 and now - (st.last_arrival or 0) < th.stale_s:
                out.append({"name": "service_up", "source": s, "value": 0.0})
        return out

    def step(self, now):
        """Evaluate every tenant; returns [("open"|"update"|"close", Alert)]."""
        changes, tenants = [], {t for (t, _s) in self.e.src}
        for tenant in tenants:
            fl, errs, alert = self.flags(tenant), self.errors(tenant, now), self.open.get(tenant)
            if not fl:
                if alert and now - alert.last_flag >= self.e.th(tenant).exit_s:
                    alert.closed = True
                    del self.open[tenant]
                    changes.append(("close", alert))
                continue
            names = {f["name"] for f in fl}
            if "cpu_pct" in names:
                companions = names & {"latency_ms", "packet_loss_pct"}
                kind = "incident_candidate" if companions or errs else "usage_spike"
            else:
                kind = "anomaly"
            title = {"usage_spike": "CPU usage spike (latency and errors normal)",
                     "incident_candidate": "CPU anomaly with " + ", ".join(sorted((names - {"cpu_pct"}) | {e["name"] for e in errs})),
                     "anomaly": "Anomaly: " + ", ".join(sorted(names))}[kind]
            so = max((self.score.get((tenant, f["source"]), 0.0) for f in fl), default=0.0)
            signals = fl + errs
            if alert is None:
                alert = self.open[tenant] = Alert(f"alr-{tenant}-{int(now)}", tenant, kind, SEVERITY[kind], title, signals,
                                                  round(so, 2), so >= HST_THRESHOLD, now, now)
                changes.append(("open", alert))
            else:
                alert.last_flag = now
                if (kind, [s["name"] for s in signals]) != (alert.kind, [s["name"] for s in alert.signals]):
                    alert.kind, alert.severity, alert.title, alert.signals = kind, SEVERITY[kind], title, signals
                    alert.second_opinion, alert.agrees = round(so, 2), so >= HST_THRESHOLD
                    changes.append(("update", alert))
        return changes
