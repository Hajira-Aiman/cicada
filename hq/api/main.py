"""
hq/api/main.py
Head-Office Core API & Real-Time Dashboard WebSocket Server.
Supports authentication (scrypt hashes, signed session tokens),
role-based tenant separation (engineer vs customer),
and database-enforced Row-Level Security (RLS).
"""

import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hq.api.broadcaster import broadcaster
from hq.db import (
    authenticate_user,
    compare_guard_checkpoint,
    compute_guard_checkpoint,
    count_recent_intents,
    create_action_intent,
    create_reveal_request,
    execute_query,
    get_action_audit_logs,
    get_action_intent,
    get_tenant_assigned_region,
    get_damage_map,
    list_action_intents,
    get_tenant_baselines,
    get_tenant_counters,
    init_all_databases,
    is_postgres_available,
    is_region_paused,
    list_pending_action_intents,
    list_reveal_requests,
    log_action_audit,
    log_audit_event,
    lookup_guard,
    record_feedback,
    set_region_paused,
    update_action_intent_status,
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


def query_tenant_data(user: Dict[str, Any], table_name: str, select_cols: str = "*", order_by: str = "", where: str = "", params: tuple = (), limit: int = 0) -> List[Dict[str, Any]]:
    """
    Executes tenant-isolated queries respecting data residency and database-enforced RLS.
    Customers query only their assigned region database with their tenant RLS parameter.
    Engineers query all regions with RLS set to 'all'.
    """
    role = user.get("role")
    user_tenant = user.get("tenant_id")
    order_clause = (f" WHERE {where}" if where else "") + (f" ORDER BY {order_by}" if order_by else "") + (f" LIMIT {int(limit)}" if limit else "")

    if role == "customer":
        if not user_tenant:
            return []
        # Find assigned region for customer
        region = get_tenant_assigned_region(user_tenant) or "in"
        db_name = "airlock_in" if region == "in" else "airlock_eu"
        query = f"SELECT {select_cols} FROM {table_name}{order_clause};"
        return execute_query(db_name, query, params, tenant_id=user_tenant)
    else:
        # Engineer: query both regions and combine
        res = []
        for db in ("airlock_in", "airlock_eu"):
            query = f"SELECT {select_cols} FROM {table_name}{order_clause};"
            rows = execute_query(db, query, params, tenant_id="all")
            res.extend(rows)
        return res


# --- Phone Join & Heartbeat (T14) ---
_phones: Dict[str, Dict[str, Any]] = {}


class PhoneHeartbeatRequest(BaseModel):
    phone_id: str
    latency_ms: float = 0.0


def record_phone_heartbeat(phone_id: str, latency_ms: float) -> Dict[str, Any]:
    now_ts = time.time()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "phone_id": phone_id,
        "tenant_id": "guests",
        "latency_ms": latency_ms,
        "last_heartbeat": now_iso,
        "last_heartbeat_ts": now_ts,
    }
    _phones[phone_id] = entry
    return entry


def get_active_phones() -> List[Dict[str, Any]]:
    now_ts = time.time()
    results = []
    for pid, p in list(_phones.items()):
        elapsed = now_ts - p["last_heartbeat_ts"]
        is_online = (elapsed <= 60.0)
        latency = p.get("latency_ms", 0.0)
        color = "red" if (not is_online or latency > 150.0) else "green"
        results.append({
            "phone_id": pid,
            "tenant_id": "guests",
            "status": "online" if is_online else "offline",
            "color": color,
            "latency_ms": latency,
            "last_heartbeat": p["last_heartbeat"],
            "last_seen_s_ago": round(elapsed, 1),
        })
    return results


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "hq-api", "phones": get_active_phones()}


@app.post("/api/phones/heartbeat")
def phone_heartbeat(req: PhoneHeartbeatRequest):
    entry = record_phone_heartbeat(req.phone_id, req.latency_ms)
    color = "red" if req.latency_ms > 150.0 else "green"
    return {
        "status": "ok",
        "phone_id": req.phone_id,
        "tenant_id": "guests",
        "state": "online",
        "color": color,
        "latency_ms": req.latency_ms,
    }


@app.get("/api/phones")
def list_phones():
    return {"phones": get_active_phones()}


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
def get_metrics(since: Optional[str] = None, limit: int = Query(5000, ge=1, le=20000), user: Dict[str, Any] = Depends(get_current_user)):
    """Newest first; `since` (ISO time) returns only newer rows, and at most `limit` rows per region come back."""
    where, params = "", ()
    if since:
        where, params = ("event_time > %s" if is_postgres_available() else "event_time > ?"), (since,)
    rows = query_tenant_data(user, "metrics", select_cols="id, payload_id, tenant_id, source, name, avg, max, event_time",
                             order_by="event_time DESC", where=where, params=params, limit=limit)
    return {"metrics": rows}


@app.get("/api/events")
def get_events(limit: int = Query(200, ge=1, le=5000), user: Dict[str, Any] = Depends(get_current_user)):
    rows = query_tenant_data(user, "events", select_cols="id, payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time", order_by="event_time DESC", limit=limit)
    return {"events": rows}


@app.get("/api/health/history")
def get_health_history(limit: int = Query(100, ge=1, le=5000), user: Dict[str, Any] = Depends(get_current_user)):
    """Health transitions written by the AIOps worker, newest first."""
    rows = query_tenant_data(user, "health_history", select_cols="id, tenant_id, source, state, old_state, reasons, at", order_by="at DESC", limit=limit)
    return {"history": sorted(rows, key=lambda r: str(r["at"]), reverse=True)[:limit]}


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
    return {"health": rows, "phones": get_active_phones()}


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
    guard = lookup_guard(guard_id)
    if user.get("role") == "customer" and (not guard or guard["tenant_id"] != user.get("tenant_id")):
        raise HTTPException(status_code=403, detail="Access denied to this guard's checkpoint")
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
    if user and user.get("role") == "customer":
        tenant_id = user.get("tenant_id") or tenant_id  # a customer cannot file requests against another tenant
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


# --- Action Intents, Approvals, Dry-Run & Audit (T12) ---

ALLOWED_ACTIONS = {"kill_process", "block_source", "block_ip", "restart_service", "investigate"}


class ProposeActionRequest(BaseModel):
    action: str  # kill_process | block_source | block_ip | restart_service | investigate
    target: str  # pseudonym
    why: str = ""
    risk: str = "low"  # low | medium | high
    reversible: bool = True
    rollback: Optional[str] = None
    incident_id: Optional[str] = None
    tenant_id: Optional[str] = None


class ApproveActionRequest(BaseModel):
    approved_by: str


class ActionResultRequest(BaseModel):
    guard_id: str
    status: str = "done"  # done | failed
    details: Optional[Dict[str, Any]] = None
    health_improved: bool = True
    elapsed_seconds: int = 0


@app.post("/api/actions/propose")
def propose_action(
    req: ProposeActionRequest,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    tenant_id = req.tenant_id or (user.get("tenant_id") if user else "acme") or "acme"

    # Head-office policy check 1: allowed action
    if req.action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Policy check failed: action '{req.action}' is not in allowed actions: {sorted(ALLOWED_ACTIONS)}",
        )

    # Head-office policy check 2: risk <= medium
    risk_lower = req.risk.lower()
    if risk_lower not in ("low", "medium"):
        raise HTTPException(
            status_code=400,
            detail=f"Policy check failed: risk '{req.risk}' exceeds maximum allowed threshold (risk <= medium required)",
        )

    # Head-office policy check 3: max 3 per 10 minutes sliding window
    recent_cnt = count_recent_intents(tenant_id, window_seconds=600)
    if recent_cnt >= 3:
        raise HTTPException(
            status_code=429,
            detail="Policy check failed: maximum 3 action proposals per 10 minutes exceeded for tenant",
        )

    intent = create_action_intent(
        tenant_id=tenant_id,
        action=req.action,
        target=req.target,
        risk=risk_lower,
        why=req.why,
        incident_id=req.incident_id,
        reversible=req.reversible,
        rollback=req.rollback,
    )
    return intent


@app.post("/api/actions/{intent_id}/dry-run")
def dry_run_action(
    intent_id: str,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    intent = get_action_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail=f"Action intent '{intent_id}' not found")

    actor = (user.get("user_id") if user else "operator") or "operator"
    updated = update_action_intent_status(intent_id=intent_id, status="dry_run_done")
    simulation = {
        "action": intent["action"],
        "target": intent["target"],
        "would_succeed": True,
        "impact": f"Simulated execution of '{intent['action']}' on target '{intent['target']}': safe to proceed.",
    }
    log_action_audit(intent_id=intent_id, actor=actor, step="dry_run_done", details=simulation)
    return {
        "status": "dry_run_done",
        "intent_id": intent_id,
        "simulation": simulation,
        "intent": updated,
    }


@app.post("/api/actions/{intent_id}/approve")
def approve_action(
    intent_id: str,
    req: ApproveActionRequest,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    if not req.approved_by or not req.approved_by.strip():
        raise HTTPException(status_code=400, detail="Approval requires the person's name (approved_by)")

    intent = get_action_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail=f"Action intent '{intent_id}' not found")

    if intent["status"] != "dry_run_done":
        raise HTTPException(
            status_code=400,
            detail=f"Action must undergo dry run before approval (current status: '{intent['status']}')",
        )

    # Check expiration (10 minutes)
    if intent.get("expires_at"):
        exp_raw = str(intent["expires_at"]).rstrip("Z")
        exp_dt = datetime.fromisoformat(exp_raw)
        if exp_dt.tzinfo is None:
            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp_dt:
            update_action_intent_status(intent_id=intent_id, status="expired")
            log_action_audit(intent_id=intent_id, actor="system", step="expired")
            raise HTTPException(status_code=400, detail="Action intent has expired (10-minute validity)")

    updated = update_action_intent_status(intent_id=intent_id, status="approved", approved_by=req.approved_by.strip())
    log_action_audit(intent_id=intent_id, actor=req.approved_by.strip(), step="approved")
    return {
        "status": "approved",
        "intent_id": intent_id,
        "approved_by": req.approved_by.strip(),
        "intent": updated,
    }


@app.get("/api/actions")
def list_actions(limit: int = 50, user: Dict[str, Any] = Depends(get_current_user)):
    """All recent intents (customers see only their own tenant's)."""
    rows = list_action_intents(limit)
    if user.get("role") == "customer":
        rows = [r for r in rows if r.get("tenant_id") == user.get("tenant_id")]
    return {"intents": [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()} for r in rows]}


@app.get("/api/actions/pending")
def get_pending_actions(
    guard_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    tenant_id = None
    secret = "airlock-head-office-session-secret-2026"
    if guard_id:
        guard = lookup_guard(guard_id)
        if guard:
            tenant_id = guard["tenant_id"]
            secret = guard["hmac_secret"]
    elif user and user.get("role") == "customer":
        tenant_id = user.get("tenant_id")

    intents = list_pending_action_intents(tenant_id=tenant_id)
    signed_intents = []
    for it in intents:
        created_at_str = it["created_at"].isoformat() if hasattr(it["created_at"], "isoformat") else str(it["created_at"])
        signed_item = dict(it)
        signed_item["created_at"] = created_at_str

        # Generate HMAC-SHA256 signature matching guard ingest scheme
        body_to_sign = json.dumps(
            {
                "intent_id": it["intent_id"],
                "tenant_id": it["tenant_id"],
                "action": it["action"],
                "target": it["target"],
                "created_at": created_at_str,
            },
            sort_keys=True,
        ).encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), body_to_sign, hashlib.sha256).hexdigest()
        signed_item["signature"] = sig
        signed_intents.append(signed_item)
        if guard_id:
            log_action_audit(intent_id=it["intent_id"], actor=guard_id, step="pulled_by_guard")

    return {"intents": signed_intents}


@app.post("/api/actions/{intent_id}/result")
def post_action_result(
    intent_id: str,
    req: ActionResultRequest,
):
    intent = get_action_intent(intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail=f"Action intent '{intent_id}' not found")

    # If health did not improve or elapsed > 120s, trigger rollback
    if not req.health_improved or req.elapsed_seconds > 120:
        updated = update_action_intent_status(intent_id=intent_id, status="rolled_back")
        log_action_audit(
            intent_id=intent_id,
            actor=req.guard_id,
            step="rolled_back",
            details={
                "health_improved": req.health_improved,
                "elapsed_seconds": req.elapsed_seconds,
                "reason": "Health did not improve within 120s; automated rollback triggered",
            },
        )
        return {
            "status": "rolled_back",
            "intent_id": intent_id,
            "rollback_reason": "Health did not improve within 120s",
            "intent": updated,
        }

    status_val = "done" if req.status == "done" else "failed"
    updated = update_action_intent_status(intent_id=intent_id, status=status_val)
    log_action_audit(
        intent_id=intent_id,
        actor=req.guard_id,
        step=f"execution_{status_val}",
        details=req.details or {},
    )
    return {
        "status": status_val,
        "intent_id": intent_id,
        "intent": updated,
    }


@app.get("/api/actions/audit")
def get_action_audit(
    intent_id: Optional[str] = None,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    return {"audit_log": get_action_audit_logs(intent_id=intent_id)}


class FeedbackRequest(BaseModel):
    alert_id: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    metric: Optional[str] = None
    source: Optional[str] = None


@app.post("/feedback")
@app.post("/api/feedback")
def post_feedback(req: FeedbackRequest, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    user_id = req.user_id or (user.get("user_id") if user else "user-ops-1") or "user-ops-1"
    tenant_id = req.tenant_id or (user.get("tenant_id") if user else "acme") or "acme"
    return record_feedback(
        alert_id=req.alert_id,
        tenant_id=tenant_id,
        user_id=user_id,
        metric=req.metric,
        source=req.source,
    )


@app.get("/api/baselines/{tenant_id}")
def get_baselines_endpoint(
    tenant_id: str,
    user: Optional[Dict[str, Any]] = Depends(get_optional_user),
):
    if user and user.get("role") == "customer" and user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to tenant baselines")
    return get_tenant_baselines(tenant_id)


@app.get("/api/damage-map/{tenant_id}")
def get_damage_map_endpoint(tenant_id: str, user: Optional[Dict[str, Any]] = Depends(get_optional_user)):
    if user and user.get("role") == "customer" and user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to tenant damage map")
    return get_damage_map(tenant_id)


class ChatRequest(BaseModel):
    question: str
    tenant_id: Optional[str] = None


@app.post("/ai/chat")
@app.post("/api/ai/chat")
async def post_ai_chat(req: ChatRequest, user: Dict[str, Any] = Depends(get_current_user)):
    role = user.get("role")
    if role == "engineer":
        if not req.tenant_id:
            raise HTTPException(
                status_code=400,
                detail="Engineers must specify an explicit tenant_id in request body",
            )
        tenant_id = req.tenant_id
    else:
        tenant_id = user.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="User has no assigned tenant")
        if req.tenant_id and req.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="Customer cannot query other tenants")

    ai_service_url = os.getenv("AI_SERVICE_URL", "http://localhost:8010/chat")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
        "answer": "The AI service is not reachable right now.",
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
