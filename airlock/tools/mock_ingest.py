"""Stand-in for the real ingest until H6: verify signature + schema, dedupe by payload_id, store metrics/events.
  REGION=in python -m tools.mock_ingest      (port from .env)"""
import os
from datetime import datetime, timezone
import psycopg
from fastapi import FastAPI, Request, Response
from pydantic import ValidationError
from contracts.models import Payload
from tools.common import PORTS, TENANTS, dsn, sign

REGION = os.getenv("REGION", "in")
app = FastAPI()
SCHEMA = """
CREATE TABLE IF NOT EXISTS payloads(payload_id text PRIMARY KEY, tenant_id text, guard_id text, seq int, window_start timestamptz, received_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS metrics(payload_id text, tenant_id text, source text, name text, ts timestamptz, avg real, max real);
CREATE TABLE IF NOT EXISTS events(payload_id text, tenant_id text, source text, category text, severity text, actor text, count int, window_s int, ts timestamptz);
CREATE INDEX IF NOT EXISTS metrics_k ON metrics(tenant_id, source, name, ts);
CREATE INDEX IF NOT EXISTS events_k ON events(tenant_id, ts);
CREATE TABLE IF NOT EXISTS heartbeats(tenant_id text, guard_id text, ts timestamptz, version text, buffer_depth int, PRIMARY KEY(tenant_id, guard_id));
"""
db = psycopg.connect(dsn("airlock_" + REGION), autocommit=True)
db.execute(SCHEMA)


@app.post("/ingest")
async def ingest(req: Request):
    body = await req.body()
    gid, ts = req.headers.get("X-Guard-Id", ""), req.headers.get("X-Timestamp", "")
    if sign(gid, ts, body) != req.headers.get("X-Signature"):
        return Response("bad signature", 401)
    try:
        p = Payload.model_validate_json(body)
    except ValidationError as e:
        return Response(str(e)[:300], 422)
    if TENANTS.get(p.tenant_id, (None, None))[1] != REGION:
        return Response("wrong region", 403)
    w = p.window.start
    cur = db.execute("INSERT INTO payloads(payload_id,tenant_id,guard_id,seq,window_start) VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                     (p.payload_id, p.tenant_id, p.guard_id, p.seq, w))
    if cur.rowcount:
        for m in p.metrics:
            db.execute("INSERT INTO metrics VALUES(%s,%s,%s,%s,%s,%s,%s)", (p.payload_id, p.tenant_id, m.source, m.name, w, m.avg, m.max))
        for e in p.events:
            db.execute("INSERT INTO events VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (p.payload_id, p.tenant_id, e.source, e.category, e.severity, e.actor, e.count, e.window_s, w))
        db.execute("INSERT INTO heartbeats VALUES(%s,%s,now(),%s,%s) ON CONFLICT(tenant_id,guard_id) DO UPDATE SET ts=now(),version=EXCLUDED.version,buffer_depth=EXCLUDED.buffer_depth",
                   (p.tenant_id, p.guard_id, p.health.guard_version, p.health.buffer_depth))
    return {"payload_id": p.payload_id, "received_at": datetime.now(timezone.utc).isoformat(), "status": "stored" if cur.rowcount else "duplicate"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORTS[REGION], log_level="warning")
