"""
hq/api/main.py
Head-Office Core API & Real-Time Dashboard WebSocket Server.
Supports authentication (scrypt hashes, signed session tokens),
role-based tenant separation (engineer vs customer),
and database-enforced Row-Level Security (RLS).
"""

import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hq.api.broadcaster import broadcaster
from hq.db import (
    authenticate_user,
    execute_query,
    init_all_databases,
    verify_session_token,
)

init_all_databases()

app = FastAPI(title="Airlock Head-Office API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str
    tenant_id: Optional[str] = None
    role: str


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Extracts and validates signed session bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required: missing Bearer token")
    token = authorization.split("Bearer ", 1)[1].strip()
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return payload


def query_tenant_data(user: Dict[str, Any], table_name: str, select_cols: str = "*", order_by: str = "") -> List[Dict[str, Any]]:
    """
    Executes tenant-isolated queries respecting data residency and database-enforced RLS.
    Customers query only their assigned region database with their tenant RLS parameter.
    Engineers query all regions with RLS set to 'all'.
    """
    role = user.get("role")
    user_tenant = user.get("tenant_id")
    order_clause = f" ORDER BY {order_by}" if order_by else ""

    if role == "customer":
        if not user_tenant:
            return []
        # Find assigned region for customer
        tenant_rows = execute_query("airlock_core", "SELECT assigned_region FROM tenants WHERE tenant_id = %s;", (user_tenant,))
        region = tenant_rows[0]["assigned_region"] if tenant_rows else "in"
        db_name = "airlock_in" if region == "in" else "airlock_eu"
        query = f"SELECT {select_cols} FROM {table_name}{order_clause};"
        return execute_query(db_name, query, tenant_id=user_tenant)
    else:
        # Engineer: query both regions and combine
        res = []
        for db in ("airlock_in", "airlock_eu"):
            query = f"SELECT {select_cols} FROM {table_name}{order_clause};"
            rows = execute_query(db, query, tenant_id="all")
            res.extend(rows)
        return res


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "hq-api"}


@app.post("/api/login", response_model=LoginResponse)
def login(req: LoginRequest):
    auth_data = authenticate_user(req.username, req.password)
    if not auth_data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(
        token=auth_data["token"],
        user_id=auth_data["user_id"],
        tenant_id=auth_data.get("tenant_id"),
        role=auth_data["role"],
    )


async def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extracts and validates optional signed session bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split("Bearer ", 1)[1].strip()
    return verify_session_token(token)


@app.get("/api/tenants")
def list_tenants(user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    rows = execute_query("airlock_core", "SELECT tenant_id, name, assigned_region FROM tenants;")
    if user and user.get("role") == "customer":
        rows = [r for r in rows if r["tenant_id"] == user.get("tenant_id")]
    return {"tenants": rows}


@app.get("/api/metrics")
def get_metrics(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "metrics", select_cols="id, payload_id, tenant_id, source, name, avg, max, event_time", order_by="event_time DESC")
    return {"metrics": rows}


@app.get("/api/events")
def get_events(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "events", select_cols="id, payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time", order_by="event_time DESC")
    return {"events": rows}


@app.get("/api/payloads")
def get_payloads(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "payloads", select_cols="payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, received_at", order_by="seq DESC")
    return {"payloads": rows}


@app.get("/api/incidents")
def get_incidents(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "incidents", select_cols="incident_id, tenant_id, body, status, started_at, updated_at", order_by="started_at DESC")
    return {"incidents": rows}


@app.get("/api/health")
def get_health(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "health_current", select_cols="tenant_id, source, state, reasons, since, flaps_prevented, updated")
    return {"health": rows}


@app.get("/api/reconciliation")
def get_reconciliation(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "guard_reconciliation", select_cols="guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen")
    return {"reconciliation": rows}


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid.uuid4())

    async def send_json(message: dict):
        await websocket.send_json(message)

    broadcaster.register_client(client_id, send_json)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        broadcaster.unregister_client(client_id)
    except Exception:
        broadcaster.unregister_client(client_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("hq.api.main:app", host="0.0.0.0", port=port, reload=False)
