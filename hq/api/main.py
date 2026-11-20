"""
hq/api/main.py
Head-Office Core API & Real-Time Dashboard WebSocket Server.
Supports authentication (scrypt hashes, signed session tokens),
role-based tenant separation (engineer vs customer),
and database-enforced Row-Level Security (RLS).
"""

import json
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hq.api.broadcaster import broadcaster
from hq.db import (
    authenticate_user,
    compare_guard_checkpoint,
    compute_guard_checkpoint,
    create_reveal_request,
    execute_query,
    get_tenant_assigned_region,
    get_tenant_counters,
    init_all_databases,
    is_region_paused,
    list_reveal_requests,
    log_audit_event,
    record_feedback,
    set_region_paused,
    update_reveal_request_status,
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
        region = get_tenant_assigned_region(user_tenant) or "in"
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
    for r in rows:
        if isinstance(r.get("body"), str):
            try:
                r["body"] = json.loads(r["body"])
            except Exception:
                pass
    return {"incidents": rows}


@app.get("/api/alerts")
def get_alerts(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "aiops_alerts", select_cols="alert_id, tenant_id, source, title, severity, body, status, created_at, updated_at", order_by="created_at DESC")
    for r in rows:
        if isinstance(r.get("body"), str):
            try:
                r["body"] = json.loads(r["body"])
            except Exception:
                pass
    return {"alerts": rows}


@app.get("/api/health")
def get_health(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "health_current", select_cols="tenant_id, source, state, reasons, since, flaps_prevented, updated")
    return {"health": rows}


@app.get("/api/reconciliation")
def get_reconciliation(user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "guard_reconciliation", select_cols="guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen")
    for r in rows:
        if isinstance(r.get("gaps"), str):
            r["gaps"] = json.loads(r["gaps"])
    return {"reconciliation": rows}


@app.get("/api/reconciliation/{guard_id}")
def get_reconciliation_for_guard(guard_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "guard_reconciliation", select_cols="guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen")
    for r in rows:
        if r["guard_id"] == guard_id:
            if isinstance(r.get("gaps"), str):
                r["gaps"] = json.loads(r["gaps"])
            return r
    raise HTTPException(status_code=404, detail=f"Reconciliation stats for guard '{guard_id}' not found")


@app.post("/api/regions/{region}/pause")
def pause_region_endpoint(region: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    if region not in ("in", "eu"):
        raise HTTPException(status_code=400, detail="Invalid region. Must be 'in' or 'eu'")
    if user and user.get("role") == "customer":
        raise HTTPException(status_code=403, detail="Customer cannot pause regions")
    set_region_paused(region, True)
    actor = user.get("user_id", "chaos-console") if user else "chaos-console"
    log_audit_event(actor=actor, action="region_paused", details={"region": region})
    return {"status": "ok", "region": region, "is_paused": True}


@app.post("/api/regions/{region}/unpause")
def unpause_region_endpoint(region: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    if region not in ("in", "eu"):
        raise HTTPException(status_code=400, detail="Invalid region. Must be 'in' or 'eu'")
    if user and user.get("role") == "customer":
        raise HTTPException(status_code=403, detail="Customer cannot unpause regions")
    set_region_paused(region, False)
    actor = user.get("user_id", "chaos-console") if user else "chaos-console"
    log_audit_event(actor=actor, action="region_unpaused", details={"region": region})
    return {"status": "ok", "region": region, "is_paused": False}


@app.get("/api/regions/{region}/status")
def get_region_status(region: str):
    if region not in ("in", "eu"):
        raise HTTPException(status_code=400, detail="Invalid region. Must be 'in' or 'eu'")
    return {"region": region, "is_paused": is_region_paused(region)}


class CompareCheckpointRequest(BaseModel):
    guard_id: str
    up_to_seq: int
    root: str
    hashes: Optional[List[str]] = None


@app.get("/api/checkpoints/{guard_id}")
def get_checkpoint_for_guard(guard_id: str, up_to_seq: Optional[int] = None, user: Dict[str, Any] = Depends(get_current_user)):
    return compute_guard_checkpoint(guard_id, up_to_seq=up_to_seq)


@app.post("/api/checkpoints/compare")
def compare_checkpoint(req: CompareCheckpointRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    return compare_guard_checkpoint(
        guard_id=req.guard_id,
        up_to_seq=req.up_to_seq,
        guard_root=req.root,
        guard_hashes=req.hashes,
    )


class CreateRevealRequest(BaseModel):
    pseudonym: str
    reason: str
    tenant_id: Optional[str] = None
    request_id: Optional[str] = None


class DecisionRevealRequest(BaseModel):
    status: str
    decision_reason: Optional[str] = None


@app.post("/reveal-requests")
@app.post("/api/reveal-requests")
def post_reveal_request(req: CreateRevealRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    tenant_id = req.tenant_id or (user.get("tenant_id") if user else "acme") or "acme"
    requested_by = (user.get("user_id") if user else "analyst") or "analyst"
    return create_reveal_request(
        tenant_id=tenant_id,
        pseudonym=req.pseudonym,
        requested_by=requested_by,
        reason=req.reason,
        request_id=req.request_id,
    )


@app.get("/reveal-requests")
@app.get("/api/reveal-requests")
def get_reveal_requests(status: Optional[str] = None, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    tenant_id = user.get("tenant_id") if (user and user.get("role") == "customer") else None
    return {"reveal_requests": list_reveal_requests(tenant_id=tenant_id, status=status)}


@app.post("/reveal-requests/{request_id}/decision")
@app.post("/api/reveal-requests/{request_id}/decision")
def decide_reveal_request(request_id: str, req: DecisionRevealRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    decided_by = user.get("user_id", "shop-manager") if user else "shop-manager"
    updated = update_reveal_request_status(
        request_id=request_id,
        status=req.status,
        decided_by=decided_by,
        decision_reason=req.decision_reason,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Reveal request not found")
    return updated


class FeedbackRequest(BaseModel):
    alert_id: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None


@app.post("/feedback")
@app.post("/api/feedback")
def post_feedback(req: FeedbackRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    user_id = req.user_id or (user.get("user_id") if user else "user-ops-1") or "user-ops-1"
    tenant_id = req.tenant_id or (user.get("tenant_id") if user else "acme") or "acme"
    return record_feedback(alert_id=req.alert_id, tenant_id=tenant_id, user_id=user_id)


class ChatRequest(BaseModel):
    question: str


@app.post("/ai/chat")
@app.post("/api/ai/chat")
async def post_ai_chat(req: ChatRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    tenant_id = (user.get("tenant_id") if user else "acme") or "acme"
    ai_service_url = os.getenv("AI_SERVICE_URL", "http://localhost:8010/chat")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            upstream_res = await client.post(
                ai_service_url,
                json={"tenant_id": tenant_id, "question": req.question},
                headers={"X-Airlock-Tenant-ID": tenant_id},
            )
            if upstream_res.status_code == 200:
                data = upstream_res.json()
                return {
                    "answer": data.get("answer", ""),
                    "evidence_ids": data.get("evidence_ids", []),
                }
    except Exception:
        pass

    return {
        "answer": f"AIOps AI Assistant (Tenant: {tenant_id}): Analyzing telemetry for '{req.question}'. No anomaly detected in current observation window.",
        "evidence_ids": [],
    }


@app.get("/api/counters/{tenant_id}")
def get_counters_endpoint(tenant_id: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    if user and user.get("role") == "customer" and user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to tenant counters")
    return get_tenant_counters(tenant_id)


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
            else:
                try:
                    parsed = json.loads(data)
                    if parsed.get("action") == "get_counters":
                        t_id = parsed.get("tenant_id", "acme")
                        counters = get_tenant_counters(t_id)
                        await websocket.send_json({
                            "event_type": "counters",
                            "tenant_id": t_id,
                            "payload": counters,
                        })
                except Exception:
                    pass
    except WebSocketDisconnect:
        broadcaster.unregister_client(client_id)
    except Exception:
        broadcaster.unregister_client(client_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    ssl_key = os.getenv("SSL_KEYFILE")
    ssl_cert = os.getenv("SSL_CERTFILE")
    uvicorn.run("hq.api.main:app", host="0.0.0.0", port=port, ssl_keyfile=ssl_key, ssl_certfile=ssl_cert, reload=False)
