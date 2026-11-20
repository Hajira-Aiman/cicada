"""AIOps worker: every 2 s read new windows from airlock_in + airlock_eu, run the engine, write health.
  python -m hq.aiops.worker
Tables it reads (metrics, events, payloads: Sahiti's scripts/init_postgres.sql); it owns health_history, health_current, tenant_thresholds.
All table access is in this file, so swapping to the real ingest schema only touches the SELECTs below."""
import json, logging, time
from datetime import datetime, timezone
import psycopg
from hq.aiops.engine import Engine, Thresholds
from hq.aiops.anomaly import Detector
from hq.aiops.incidents import Manager
import os
from dotenv import load_dotenv
load_dotenv()


def dsn(db):
    g = os.getenv
    return f"postgresql://{g('DB_USER','postgres')}:{g('DB_PASSWORD','postgres')}@{g('DB_HOST','localhost')}:{g('DB_PORT',5432)}/{db}"

log = logging.getLogger("aiops")
SCHEMA = """
CREATE TABLE IF NOT EXISTS health_history(id bigserial PRIMARY KEY, tenant_id text, source text, state text, old_state text, reasons jsonb, at timestamptz);
CREATE TABLE IF NOT EXISTS health_current(tenant_id text, source text, state text, reasons jsonb, since timestamptz, flaps_prevented int, updated timestamptz, PRIMARY KEY(tenant_id, source));
CREATE TABLE IF NOT EXISTS aiops_alerts(alert_id text PRIMARY KEY, tenant_id text, kind text, severity text, title text, signals jsonb, second_opinion real, agrees boolean, started_at timestamptz, updated_at timestamptz, closed_at timestamptz);
CREATE TABLE IF NOT EXISTS aiops_counters(tenant_id text PRIMARY KEY, raw_alerts int, incidents int, noise_cut_pct real, flaps_prevented int, updated timestamptz);
CREATE TABLE IF NOT EXISTS tenant_thresholds(tenant_id text PRIMARY KEY, config jsonb);
"""
REPLAY_S = 300  # on start, rebuild baselines from the last 5 minutes


class Region:
    def __init__(self, name, overrides):
        # one engine per region: Globex (EU) signals never touch the India engine or database
        self.name, self.overrides = name, overrides
        self.engine = Engine(lambda tenant: Thresholds.with_overrides(self.overrides.get(tenant)))
        self.detector = Detector(self.engine)
        self.manager = Manager(self.engine, self.detector)
        self.db = psycopg.connect(dsn("airlock_" + name), autocommit=True)
        self.db.execute(SCHEMA)
        self.cursor = datetime.fromtimestamp(time.time() - REPLAY_S, timezone.utc)

    def load_overrides(self):
        self.overrides.update({t: c for t, c in self.db.execute("SELECT tenant_id, config FROM tenant_thresholds")})

    def fetch(self):
        """New windows since the cursor, grouped per (tenant, source, window) and sorted by event time."""
        # 300 ms lag: ingest inserts the payload row before its metrics, so wait for the rows to land
        rows = self.db.execute("""SELECT m.tenant_id, m.source, extract(epoch from m.event_time), extract(epoch from p.received_at),
                                         m.name, m.avg, p.received_at
                                  FROM metrics m JOIN payloads p USING(payload_id)
                                  WHERE p.received_at > %s AND p.received_at <= now() - interval '300 ms'""", (self.cursor,)).fetchall()
        evs = self.db.execute("""SELECT e.tenant_id, e.source, extract(epoch from e.event_time), e.category, e.severity, e.count
                                 FROM events e JOIN payloads p USING(payload_id)
                                 WHERE p.received_at > %s AND p.received_at <= now() - interval '300 ms'""", (self.cursor,)).fetchall()
        win = {}
        for t, s, ts, arr, name, avg, rcv in rows:
            w = win.setdefault((float(ts), t, s), {"arr": 0.0, "m": {}, "e": []})
            w["arr"] = max(w["arr"], float(arr)); w["m"][name] = avg
            self.cursor = max(self.cursor, rcv)
        for t, s, ts, cat, sev, cnt in evs:
            win.setdefault((float(ts), t, s), {"arr": float(ts), "m": {}, "e": []})["e"].append((cat, sev, cnt))
        return [(k, win[k]) for k in sorted(win)]

    def tick(self, now, replay=False):
        self.load_overrides()
        for (ts, t, s), w in self.fetch():
            self.engine.ingest(t, s, ts, w["arr"], w["m"], w["e"])
            self.detector.observe(t, s)
        if replay:
            return
        for c in self.engine.evaluate(now):
            self.db.execute("INSERT INTO health_history(tenant_id,source,state,old_state,reasons,at) VALUES(%s,%s,%s,%s,%s,%s)",
                            (c.tenant_id, c.source, c.state, c.old_state, json.dumps(c.reasons), c.at))
            log.info("%s %s %s -> %s %s", c.at, c.source, c.old_state, c.state, c.reasons)
        for kind, a in self.detector.step(now):
            self.db.execute("""INSERT INTO aiops_alerts VALUES(%s,%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s)
                               ON CONFLICT(alert_id) DO UPDATE SET kind=EXCLUDED.kind, severity=EXCLUDED.severity, title=EXCLUDED.title,
                               signals=EXCLUDED.signals, second_opinion=EXCLUDED.second_opinion, agrees=EXCLUDED.agrees,
                               updated_at=EXCLUDED.updated_at, closed_at=EXCLUDED.closed_at""",
                            (a.alert_id, a.tenant_id, a.kind, a.severity, a.title, json.dumps(a.signals), a.second_opinion, a.agrees,
                             a.started, a.last_flag, datetime.fromtimestamp(now, timezone.utc) if a.closed else None))
            log.info("alert %s %s [%s/%s] river=%.2f agrees=%s", kind, a.title, a.kind, a.severity, a.second_opinion, a.agrees)
        for kind, inc in self.manager.step(now):
            c = inc.to_contract()
            self.db.execute("""INSERT INTO incidents(incident_id,tenant_id,body,status,started_at,updated_at) VALUES(%s,%s,%s,%s,to_timestamp(%s),now())
                               ON CONFLICT(incident_id) DO UPDATE SET body=EXCLUDED.body, status=EXCLUDED.status, updated_at=now()""",
                            (c.incident_id, c.tenant_id, c.model_dump_json(), "closed" if inc.closed else "open", inc.started))
            log.info("incident %s %s [%s %.2f] %s", kind, c.incident_id, c.severity, c.confidence, c.title)
        for t in {t for (t, _s) in self.engine.src}:
            k = self.manager.counters(t)
            flaps = sum(st.flaps for (tt, _s), st in self.engine.src.items() if tt == t)
            self.db.execute("""INSERT INTO aiops_counters VALUES(%s,%s,%s,%s,%s,now()) ON CONFLICT(tenant_id) DO UPDATE SET
                               raw_alerts=EXCLUDED.raw_alerts, incidents=EXCLUDED.incidents, noise_cut_pct=EXCLUDED.noise_cut_pct,
                               flaps_prevented=EXCLUDED.flaps_prevented, updated=now()""", (t, k["raw_alerts"], k["incidents"], k["noise_cut_pct"], flaps))
        for (t, s), st in self.engine.src.items():
            if st.committed:
                self.db.execute("""INSERT INTO health_current VALUES(%s,%s,%s,%s,to_timestamp(%s),%s,now())
                                   ON CONFLICT(tenant_id,source) DO UPDATE SET state=EXCLUDED.state, reasons=EXCLUDED.reasons,
                                   since=EXCLUDED.since, flaps_prevented=EXCLUDED.flaps_prevented, updated=now()""",
                                (t, s, st.committed, json.dumps(st.reasons), st.since, st.flaps))


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ov = {}  # tenant -> threshold overrides, filled from each region's tenant_thresholds table
    regions = [Region(n, ov) for n in ("in", "eu")]
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
