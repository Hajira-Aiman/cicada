"""AIOps core (pure logic, no I/O): EWMA baselines, health states with reasons, stale handling, hysteresis.
Math decides what is wrong; nothing here calls an LLM. Clock is passed in, so tests can fake time."""
import math
from dataclasses import dataclass, fields
from datetime import datetime, timezone

@dataclass
class Change:
    """Committed health transition (lower-case states). to_contract() gives Sahiti's HealthTransition."""
    tenant_id: str
    source: str
    state: str
    old_state: str | None
    reasons: list
    at: str

    def to_contract(self):
        from contracts.models import HealthTransition
        cap = lambda x: x.capitalize()  # contract uses Excellent/Good/Fair/Poor; first sighting reports old = new
        return HealthTransition(tenant_id=self.tenant_id, source=self.source, old_state=cap(self.old_state or self.state),
                                new_state=cap(self.state), reasons=self.reasons, transition_at=self.at)


RANK = {"excellent": 0, "good": 1, "fair": 2, "poor": 3}
Z_METRICS = {"cpu_pct", "mem_pct", "disk_pct", "net_in_kbps", "net_out_kbps", "latency_ms", "packet_loss_pct"}


@dataclass
class Thresholds:
    """Defaults from the PRD health table. Override per tenant with Thresholds.with_overrides({...})."""
    warmup: int = 30            # points before z-scores are trusted (60 s at 2 s windows)
    alpha: float = 0.1
    z_good: float = 2.0
    z_flag: float = 3.0
    z_windows: int = 3
    latency_fair: float = 200.0
    latency_poor: float = 1000.0
    loss_fair: float = 2.0
    loss_poor: float = 10.0
    cpu_fair: float = 85.0
    mem_fair: float = 90.0
    disk_fair: float = 90.0
    stale_s: float = 10.0
    offline_s: float = 30.0
    enter_s: float = 6.0        # bad data this long before entering a worse state
    exit_s: float = 20.0        # good data this long before returning to a better one
    event_hold_s: float = 10.0  # how long an event keeps its health effect

    @classmethod
    def with_overrides(cls, o: dict | None):
        ok = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (o or {}).items() if k in ok})


class Baseline:
    """Exponentially weighted mean + spread. Cumulative average while warming up."""
    def __init__(self):
        self.n, self.mean, self.var, self.streak = 0, 0.0, 0.0, 0

    def std(self):
        return max(math.sqrt(self.var), 0.05 * abs(self.mean), 0.01)  # floor so flat metrics don't explode z

    def z(self, x, th):
        return None if self.n < th.warmup else (x - self.mean) / self.std()

    def update(self, x, th):
        z = self.z(x, th)
        flagged = z is not None and abs(z) >= th.z_flag
        self.streak = self.streak + 1 if flagged else 0
        # ponytail: don't learn from anomalies, but re-learn after 30 flagged windows (60 s) so a new normal is accepted
        if not (flagged and self.streak <= 30):
            a = max(th.alpha, 1 / (self.n + 1))
            d = x - self.mean
            self.mean += a * d
            self.var = (1 - a) * (self.var + a * d * d)
            self.n += 1
        return z


class Source:
    def __init__(self):
        self.last_arrival = None
        self.last = {}          # latest value per metric
        self.z = {}             # latest z per metric
        self.events = {}        # category -> (event ts, severity)
        self.committed = None   # state shown to users (after hysteresis)
        self.reasons = []
        self.pending = None     # (direction, since) of a not-yet-committed change
        self.flaps = 0          # blocked flip-flops
        self.since = None


class Engine:
    def __init__(self, thresholds_for=lambda tenant: Thresholds()):
        self.th = thresholds_for
        self.base, self.src = {}, {}

    def ingest(self, tenant, source, ts, arrived, metrics: dict, events=()):
        """One window for one source. ts = event time, arrived = receive time (both epoch seconds)."""
        st = self.src.setdefault((tenant, source), Source())
        st.last_arrival = max(st.last_arrival or 0, arrived)
        th = self.th(tenant)
        for name, v in metrics.items():
            st.last[name] = v
            if name in Z_METRICS:
                st.z[name] = self.base.setdefault((tenant, source, name), Baseline()).update(v, th)
        for cat, sev in events:
            st.events[cat] = (ts, sev)

    def raw(self, tenant, source, now):
        """Instant health from current data, before hysteresis. Returns (state, reasons, immediate)."""
        st, th = self.src[(tenant, source)], self.th(tenant)
        age = now - st.last_arrival
        if age >= th.offline_s:
            return "poor", [f"no heartbeat for {age:.0f} s"], True
        if age >= th.stale_s:  # stale: never show the last good value
            return "fair", [f"no data for {age:.0f} s"], True
        poor, fair, good, warming = [], [], [], False
        v = st.last
        if v.get("service_up", 1) < 1:
            poor.append("service down")
        for cat, (ts, sev) in st.events.items():
            if now - ts > th.event_hold_s:
                continue
            if cat == "service_down":
                poor.append("service_down event")
            elif cat == "honeypot_hit":
                poor.append("honeypot account used")
            elif cat == "auth_failure_burst" and sev in ("medium", "high", "critical"):
                fair.append(f"login failure burst ({sev})")
        lat, loss = v.get("latency_ms", 0), v.get("packet_loss_pct", 0)
        if lat > th.latency_poor: poor.append(f"latency {lat:.0f} ms > {th.latency_poor:.0f}")
        elif lat > th.latency_fair: fair.append(f"latency {lat:.0f} ms > {th.latency_fair:.0f}")
        if loss > th.loss_poor: poor.append(f"packet loss {loss:.1f} % > {th.loss_poor:.0f}")
        elif loss > th.loss_fair: fair.append(f"packet loss {loss:.1f} % > {th.loss_fair:.0f}")
        for name, lim in (("cpu_pct", th.cpu_fair), ("mem_pct", th.mem_fair), ("disk_pct", th.disk_fair)):
            if v.get(name, 0) > lim: fair.append(f"{name} {v[name]:.0f} % > {lim:.0f}")
        for name in Z_METRICS:
            b = self.base.get((tenant, source, name))
            if not b: continue
            if b.n < th.warmup: warming = True; continue
            z = st.z.get(name)
            if b.streak >= th.z_windows: fair.append(f"{name} {z:+.1f} sigma from baseline for {b.streak} windows")
            elif z is not None and th.z_good <= abs(z) < th.z_flag: good.append(f"{name} {z:+.1f} sigma from baseline")
        for lvl, rs in (("poor", poor), ("fair", fair), ("good", good)):
            if rs: return lvl, rs, False
        return "excellent", ["warming up baselines"] if warming else ["heartbeat fresh, all metrics in normal band"], False

    def _commit(self, tenant, source, now):
        st, th = self.src[(tenant, source)], self.th(tenant)
        raw, reasons, immediate = self.raw(tenant, source, now)
        old = st.committed
        if old is None:
            pass  # first sighting: show it straight away
        elif raw == old:
            if st.pending: st.flaps += 1; st.pending = None  # bad/good spell ended before it counted
            st.reasons = reasons
            return None
        else:
            d = "worse" if RANK[raw] > RANK[old] else "better"
            if not (immediate and d == "worse"):  # staleness has its own 10 s / 30 s clock
                if st.pending and st.pending[0] != d: st.flaps += 1; st.pending = None
                if not st.pending: st.pending = (d, now)
                if now - st.pending[1] < (th.enter_s if d == "worse" else th.exit_s):
                    return None
        st.committed, st.reasons, st.pending, st.since = raw, reasons, None, now
        return Change(tenant_id=tenant, source=source, state=raw, old_state=old, reasons=reasons,
                            at=datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def evaluate(self, now):
        """Run every source once; returns the committed state changes."""
        return [c for (t, s) in list(self.src) if (c := self._commit(t, s, now))]
