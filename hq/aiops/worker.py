"""AIOps worker: every 2 s read new windows from airlock_in + airlock_eu, run the engine, write health.
  python -m hq.aiops.worker
Tables it reads (metrics, events, payloads) come from ingest; it owns health_history, health_current, tenant_thresholds.
All table access is in this file, so swapping to the real ingest schema only touches the SELECTs below."""
import json, logging, time
from datetime import datetime, timezone
import psycopg
from hq.aiops.engine import Engine, Thresholds
from tools.common import dsn

log = logging.getLogger("aiops")
SCHEMA = """
CREATE TABLE IF NOT EXISTS health_history(id bigserial PRIMARY KEY, tenant_id text, source text, state text, old_state text, reasons jsonb, at timestamptz);
CREATE TABLE IF NOT EXISTS health_current(tenant_id text, source text, state text, reasons jsonb, since timestamptz, flaps_prevented int, updated timestamptz, PRIMARY KEY(tenant_id, source));
CREATE TABLE IF NOT EXISTS tenant_thresholds(tenant_id text PRIMARY KEY, config jsonb);
"""
REPLAY_S = 300  # on start, rebuild baselines from the last 5 minutes


class Region:
    def __init__(self, name, engine):
        self.name, self.engine = name, engine
        self.db = psycopg.connect(dsn("airlock_" + name), autocommit=True)
        self.db.execute(SCHEMA)
        self.cursor = datetime.fromtimestamp(time.time() - REPLAY_S, timezone.utc)
        self.overrides = {}

    def load_overrides(self):
        self.overrides.update({t: c for t, c in self.db.execute("SELECT tenant_id, config FROM tenant_thresholds")})

    def fetch(self):
        """New windows since the cursor, grouped per (tenant, source, window) and sorted by event time."""
        # 300 ms lag: ingest inserts the payload row before its metrics, so wait for the rows to land
        rows = self.db.execute("""SELECT m.tenant_id, m.source, extract(epoch from m.ts), extract(epoch from p.received_at),
                                         m.name, m.avg, p.received_at
                                  FROM metrics m JOIN payloads p USING(payload_id)
                                  WHERE p.received_at > %s AND p.received_at <= now() - interval '300 ms'""", (self.cursor,)).fetchall()
        evs = self.db.execute("""SELECT e.tenant_id, e.source, extract(epoch from e.ts), e.category, e.severity
                                 FROM events e JOIN payloads p USING(payload_id)
                                 WHERE p.received_at > %s AND p.received_at <= now() - interval '300 ms'""", (self.cursor,)).fetchall()
        win = {}
        for t, s, ts, arr, name, avg, rcv in rows:
            w = win.setdefault((float(ts), t, s), {"arr": 0.0, "m": {}, "e": []})
            w["arr"] = max(w["arr"], float(arr)); w["m"][name] = avg
            self.cursor = max(self.cursor, rcv)
        for t, s, ts, cat, sev in evs:
            win.setdefault((float(ts), t, s), {"arr": float(ts), "m": {}, "e": []})["e"].append((cat, sev))
        return [(k, win[k]) for k in sorted(win)]

    def tick(self, now, replay=False):
        self.load_overrides()
        for (ts, t, s), w in self.fetch():
            self.engine.ingest(t, s, ts, w["arr"], w["m"], w["e"])
        if replay:
            return
        for c in self.engine.evaluate(now):
            self.db.execute("INSERT INTO health_history(tenant_id,source,state,old_state,reasons,at) VALUES(%s,%s,%s,%s,%s,%s)",
                            (c.tenant_id, c.source, c.state, c.old_state, json.dumps(c.reasons), c.at))
            log.info("%s %s %s -> %s %s", c.at, c.source, c.old_state, c.state, c.reasons)
        for (t, s), st in self.engine.src.items():
            if st.committed:
                self.db.execute("""INSERT INTO health_current VALUES(%s,%s,%s,%s,to_timestamp(%s),%s,now())
                                   ON CONFLICT(tenant_id,source) DO UPDATE SET state=EXCLUDED.state, reasons=EXCLUDED.reasons,
                                   since=EXCLUDED.since, flaps_prevented=EXCLUDED.flaps_prevented, updated=now()""",
                                (t, s, st.committed, json.dumps(st.reasons), st.since, st.flaps))


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ov = {}  # tenant -> threshold overrides, filled from each region's tenant_thresholds table
    engine = Engine(lambda tenant: Thresholds.with_overrides(ov.get(tenant)))
    regions = [Region(n, engine) for n in ("in", "eu")]
    for r in regions: r.overrides = ov  # shared dict
    for r in regions: r.tick(time.time(), replay=True)
    log.info("replayed last %ds, running", REPLAY_S)
    while True:
        t0 = time.time()
        for r in regions:
            try: r.tick(t0)
            except psycopg.Error as e: log.warning("%s db error: %s", r.name, e)
        time.sleep(max(0, 2 - (time.time() - t0)))


if __name__ == "__main__":
    main()
