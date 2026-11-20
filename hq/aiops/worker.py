"""AIOps worker: every 2 s read new windows from airlock_in + airlock_eu, run the engine, write health.
  python -m hq.aiops.worker
Tables it reads (metrics, events, payloads: Sahiti's scripts/init_postgres.sql); it owns health_history, health_current, tenant_thresholds.
All table access is in this file, so swapping to the real ingest schema only touches the SELECTs below."""
import json, logging, queue, threading, time
from datetime import datetime, timezone
import psycopg
from hq.aiops.engine import Engine, Thresholds
from hq.aiops.anomaly import Detector
from hq.aiops.incidents import Manager, COMPONENT, damage_map
from hq.ai.assistant import deterministic_narrative, llm_narrative
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
CREATE TABLE IF NOT EXISTS aiops_counters(tenant_id text PRIMARY KEY, raw_alerts int, incidents int, noise_cut_pct real, flaps_prevented int, updated timestamptz);
CREATE TABLE IF NOT EXISTS tenant_thresholds(tenant_id text PRIMARY KEY, config jsonb);
CREATE TABLE IF NOT EXISTS aiops_damage_map(tenant_id text PRIMARY KEY, body jsonb, updated_at timestamptz);
"""
iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
REPLAY_S = 300  # on start, rebuild baselines from the last 5 minutes


class Narrator(threading.Thread):
    """Rewrites incident narratives with the local LLM in the background, so the 2 s loop never waits for the model."""
    def __init__(self, db_name):
        super().__init__(daemon=True)
        self.db_name, self.q, self.db = db_name, queue.Queue(), None
        self.start()

    def submit(self, inc, data):
        self.q.put((inc, inc.narrated, data))

    def run(self):
        while True:
            inc, key, data = self.q.get()
            try:
                text = llm_narrative(data)
                if text and inc.narrated == key:   # skip if the incident changed while the model was thinking
                    inc.narrative = text
                    self.db = self.db or psycopg.connect(dsn(self.db_name), autocommit=True)
                    self.db.execute("UPDATE incidents SET body = jsonb_set(body, '{narrative}', to_jsonb(%s::text)) WHERE incident_id=%s",
                                    (text, inc.id))
                    log.info("narrative for %s written by the model", inc.id)
            except Exception as e:   # model or db down: the deterministic text stays
                log.warning("narrative for %s kept deterministic: %s", inc.id, e)
                self.db = None


class Region:
    def __init__(self, name, overrides):
        # one engine per region: Globex (EU) signals never touch the India engine or database
        self.name, self.overrides = name, overrides
        self.engine = Engine(lambda tenant: Thresholds.with_overrides(self.overrides.get(tenant)))
        self.detector = Detector(self.engine)
        self.manager = Manager(self.engine, self.detector)
        self.last_write = 0.0
        self.narrator = Narrator("airlock_" + name)
        self.connect()
        for stmt in filter(None, (x.strip() for x in SCHEMA.split(";"))):
            try:
                self.db.execute(stmt)
            except psycopg.errors.InsufficientPrivilege:
                log.warning("%s: no rights to create tables (limited role); Sahiti's init script must create them", name)
                break
        self.cursor = datetime.fromtimestamp(time.time() - REPLAY_S, timezone.utc)
        try:   # health_current is derived from engine memory; rows left by a previous run describe sources this run has not seen
            self.db.execute("DELETE FROM health_current")
        except psycopg.Error:
            pass

    def connect(self):
        self.db = psycopg.connect(dsn("airlock_" + self.name), autocommit=True)

    def load_overrides(self):
        self.overrides.update({t: c for t, c in self.db.execute("SELECT tenant_id, config FROM tenant_thresholds")})

    def load_feedback(self, now):
        """T9: new thumbs-downs raise that signal's flag level (3 -> 3.5 sigma) for 30 minutes."""
        for t, src, metric, at in self.db.execute("SELECT tenant_id, source, metric, extract(epoch from at) FROM feedback "
                                                  "WHERE metric IS NOT NULL AND source IS NOT NULL AND at > now() - interval '30 minutes'"):
            if (t, src, metric) not in self.engine.relaxed:
                self.engine.thumbs_down(t, src, metric, float(at))
                log.info("thumbs-down on %s/%s/%s: flag level 3.5 until %s", t, src, metric, iso(float(at) + 1800))

    def write_baselines_and_map(self, now):
        by = {}
        for (t, s, name), b in self.engine.base.items():
            if b.n >= self.engine.th(t).warmup:
                by.setdefault(t, []).append((s, name, round(b.mean, 3), round(b.std(), 3)))
        for t in {t for (t, _s) in self.engine.src}:
            with self.db.transaction():
                self.db.execute("DELETE FROM aiops_baselines WHERE tenant_id=%s", (t,))
                for r in by.get(t, []):
                    self.db.execute("INSERT INTO aiops_baselines(tenant_id,source,metric,mean,std) VALUES(%s,%s,%s,%s,%s)", (t, *r))
            hit = {COMPONENT.get(f["name"], "host") for f in self.detector.flags(t) + self.detector.errors(t, now)}
            self.db.execute("""INSERT INTO aiops_damage_map VALUES(%s,%s,now()) ON CONFLICT(tenant_id) DO UPDATE SET body=EXCLUDED.body, updated_at=now()""",
                            (t, json.dumps(damage_map(hit))))

    def fetch(self):
        """New windows since the cursor, grouped per (tenant, source, window) and sorted by event time."""
        # 300 ms lag: ingest inserts the payload row before its metrics, so wait for the rows to land
        rows = self.db.execute("""SELECT m.tenant_id, m.source, extract(epoch from m.event_time), extract(epoch from p.received_at),
                                         m.name, m.avg, p.received_at
                                  FROM metrics m JOIN payloads p USING(payload_id)
                                  WHERE p.received_at > %s AND p.received_at <= now() - interval '300 ms'""", (self.cursor,)).fetchall()
        win = {}
        old_cursor = self.cursor   # events are read for exactly the range the metrics query consumed (no double count next tick)
        for t, s, ts, arr, name, avg, rcv in rows:
            w = win.setdefault((float(ts), t, s), {"arr": 0.0, "m": {}, "e": []})
            w["arr"] = max(w["arr"], float(arr)); w["m"][name] = avg
            self.cursor = max(self.cursor, rcv)
        evs = self.db.execute("""SELECT e.tenant_id, e.source, extract(epoch from e.event_time), e.category, e.severity, e.count, e.actor
                                 FROM events e JOIN payloads p USING(payload_id)
                                 WHERE p.received_at > %s AND p.received_at <= %s""", (old_cursor, self.cursor)).fetchall()
        for t, s, ts, cat, sev, cnt, actor in evs:
            win.setdefault((float(ts), t, s), {"arr": float(ts), "m": {}, "e": []})["e"].append((cat, sev, cnt, actor))
        return [(k, win[k]) for k in sorted(win)]

    def tick(self, now, replay=False):
        self.load_overrides()
        self.load_feedback(now)
        for (ts, t, s), w in self.fetch():
            self.engine.ingest(t, s, ts, w["arr"], w["m"], w["e"])
            self.detector.observe(t, s)
        if replay:
            return
        for t, s in self.engine.retire(now):
            self.db.execute("DELETE FROM health_current WHERE tenant_id=%s AND source=%s", (t, s))
            log.info("retired silent source %s/%s", t, s)
        for c in self.engine.evaluate(now):
            self.db.execute("INSERT INTO health_history(tenant_id,source,state,old_state,reasons,at) VALUES(%s,%s,%s,%s,%s,%s)",
                            (c.tenant_id, c.source, c.state, c.old_state, json.dumps(c.reasons), c.at))
            log.info("%s %s %s -> %s %s", c.at, c.source, c.old_state, c.state, c.reasons)
        if now - self.last_write >= 5:
            self.last_write = now
            self.write_baselines_and_map(now)
        for kind, a in self.detector.step(now):
            body = {"kind": a.kind, "signals": a.signals, "second_opinion": a.second_opinion, "agrees": a.agrees,
                    "started_at": iso(a.started), "last_flag_at": iso(a.last_flag), "suppressed_reason": a.suppressed_reason}
            self.db.execute("""INSERT INTO aiops_alerts(alert_id,tenant_id,source,title,severity,body,status,created_at,updated_at)
                               VALUES(%s,%s,%s,%s,%s,%s,%s,to_timestamp(%s),now())
                               ON CONFLICT(alert_id) DO UPDATE SET title=EXCLUDED.title, severity=EXCLUDED.severity,
                               body=EXCLUDED.body, status=EXCLUDED.status, updated_at=now()""",
                            (a.alert_id, a.tenant_id, a.signals[0]["source"] if a.signals else None, a.title, a.severity,
                             json.dumps(body), "closed" if a.closed else ("suppressed" if a.suppressed_reason else "open"), a.started))
            log.info("alert %s %s [%s/%s] river=%.2f agrees=%s", kind, a.title, a.kind, a.severity, a.second_opinion, a.agrees)
        for kind, inc in self.manager.step(now):
            if kind != "close" and inc.narrated != (inc.title(), inc.severity()):   # narrative is written when an incident opens or changes class
                inc.narrated = (inc.title(), inc.severity())
                inc.narrative = deterministic_narrative(inc.to_contract().model_dump())
                self.narrator.submit(inc, inc.to_contract().model_dump())
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
            except psycopg.Error as e:
                log.warning("%s db error: %s", r.name, e)
                if r.db.closed or isinstance(e, psycopg.OperationalError):
                    try: r.connect()  # postgres restarted or dropped us: reconnect instead of failing forever
                    except psycopg.Error: pass
        time.sleep(max(0, 2 - (time.time() - t0)))


if __name__ == "__main__":
    main()
