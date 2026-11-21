"""
guard/api/server.py
Guard Local API for the Shop Screen (T15):
Runs on port 9000 (binds to 127.0.0.1).
Endpoints:
- GET /api/status: guard health, version, buffer depth, retention countdown, policy hash, canaries/secrets
- GET /api/raw-logs?minutes=N: raw lines with secrets visible (shop-local only)
- GET /api/egress: last 50 payloads (exact JSON, sha256, receipt status, receipt time)
- GET /api/checkpoint: latest cryptographic running checkpoint
- GET /api/reveal-requests: list reveal requests
- POST /api/reveal-requests: create a reveal request
- POST /api/reveal-requests/{id}/approve: approve reveal request locally
- POST /api/reveal-requests/{id}/reject: reject reveal request locally
- GET /api/reveal/{pseudonym}: local reverse lookup
"""

import os
import json
import psutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from contracts.request_auth import PRIVATE_ORIGIN_REGEX
from guard.action_loop import ActionQueue, approve_request, pull_actions_forever, reject_request
from guard.config import GuardConfig
from guard.executor import RemediationExecutor
from guard.hq_client import hq_call as _hq_call
from guard.shop_ai import ShopAIAssistant
from guard.thin_slice import GuardThinSlice


class DecisionRequest(BaseModel):
    decision_reason: str = Field(default="Authorized by local shop operator", description="Reason for the reveal decision")


class CreateRevealRequest(BaseModel):
    pseudonym: str = Field(..., description="The pseudonym to reveal")
    reason: str = Field(..., description="Justification for the reveal request")


def create_guard_api_app(guard: Optional[GuardThinSlice] = None) -> FastAPI:
    _guard = guard or GuardThinSlice()

    api = FastAPI(
        title="Airlock Guard Local Shop API",
        version=_guard.config.GUARD_VERSION,
        description="Local-only API for the Shop Screen and Shop AI",
    )

    api.add_middleware(
        CORSMiddleware,
        allow_origin_regex=PRIVATE_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.get("/api/status")
    def get_status():
        """Returns real-time Guard health, buffer depth, retention countdown, and policy hash."""
        proc = psutil.Process(os.getpid())
        guard_cpu = round(proc.cpu_percent(interval=None), 2)
        guard_mem = round(proc.memory_info().rss / (1024 * 1024), 2)
        last_seq, _ = _guard.ledger.get_last_seq_and_hash()
        health = {}
        try:   # the collector runs as another process: its real counters are in the newest payload it sent
            rows = _guard.ledger.get_recent_rows(limit=1)
            health = (json.loads(rows[0]["body"]).get("health") or {}) if rows else {}
        except Exception:
            pass
        return {
            "guard_id": _guard.config.GUARD_ID,
            "tenant_id": _guard.config.TENANT_ID,
            "guard_version": _guard.config.GUARD_VERSION,
            "status": "active",
            "buffer_depth": _guard.outbox.get_buffer_depth(),
            "retention_countdown_seconds": _guard.raw_store.get_retention_countdown(),
            "policy_version": _guard.config.POLICY_VERSION,
            "canaries_planted": health.get("canaries_planted", _guard.scrubber.canaries_planted),
            "secrets_redacted": health.get("secrets_redacted", _guard.scrubber.secrets_redacted),
            "guard_cpu_pct": health.get("guard_cpu_pct", guard_cpu),
            "guard_mem_mb": health.get("guard_mem_mb", guard_mem),
            "last_seq": last_seq,
        }

    @api.get("/api/raw-logs")
    def get_raw_logs(request: Request, minutes: int = 60):
        """
        Returns raw log lines WITH secrets visible.
        Only reachable locally from the shop machine (127.0.0.1).
        """
        client_ip = request.client.host if request.client else "127.0.0.1"
        if client_ip not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(status_code=403, detail="Raw logs are only accessible locally on the shop host")

        logs = _guard.raw_store.search_raw_logs(minutes=minutes)
        return {
            "minutes": minutes,
            "count": len(logs),
            "logs": logs,
        }

    class AskRequest(BaseModel):
        question: str = Field(..., max_length=500)

    @api.post("/api/ask")
    def ask_shop_ai(req: AskRequest, request: Request):
        """Shop AI: answers from this shop's raw logs (local Lemonade model). Raw data never leaves this machine."""
        client_ip = request.client.host if request.client else "127.0.0.1"
        if client_ip not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(status_code=403, detail="The shop AI reads raw logs and is only reachable on the shop host")
        return {"answer": ShopAIAssistant(raw_db_path=_guard.config.RAW_DB_PATH, guard_db_path=_guard.config.GUARD_DB_PATH).chat(req.question)}

    @api.get("/api/egress")
    def get_egress():
        """
        Returns the last 50 payloads recorded in the egress ledger:
        Exact JSON sent, SHA-256 hash, receipt status (stored|duplicate|pending), and receipt time.
        """
        rows = _guard.ledger.get_recent_rows(limit=50)
        payloads = []
        for r in rows:
            body_obj = None
            try:
                body_obj = json.loads(r["body"])
            except Exception:
                body_obj = r["body"]
            payloads.append({
                "seq": r["seq"],
                "payload_id": r["payload_id"],
                "sha256": r["sha256"],
                "prev_hash": r["prev_hash"],
                "status": r["status"],
                "receipt_at": r["receipt_at"],
                "body": body_obj,
            })
        return {
            "count": len(payloads),
            "payloads": payloads,
        }

    @api.get("/api/checkpoint")
    def get_checkpoint():
        """Returns the current cryptographic running SHA-256 checkpoint."""
        cp = _guard.ledger.compute_checkpoint(guard_id=_guard.config.GUARD_ID)
        return {
            "guard_id": cp.guard_id,
            "up_to_seq": cp.up_to_seq,
            "root": cp.root,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    hq = os.getenv("HQ_URL", "http://localhost:8000")

    def hq_call(method, path, params=None, json_body=None):
        """Every guard -> head-office call is signed with this guard's secret (see contracts/request_auth.py)."""
        return _hq_call(_guard.config, hq, method, path, params, json_body)

    def pull_reveals():
        """Head office never reaches into the shop: the guard asks for pending reveal requests for its own tenant."""
        import time
        while True:
            try:
                rows = hq_call("GET", "/reveal-requests", params={"status": "pending"}).json().get("reveal_requests", [])
                known = {r["id"] for r in _guard.pseudonym_mgr.list_reveal_requests()}
                for r in rows:
                    if r.get("tenant_id") == _guard.config.TENANT_ID and r["request_id"] not in known:
                        _guard.pseudonym_mgr.create_reveal_request(pseudonym=r["pseudonym"], reason=r["reason"], req_id=r["request_id"])
            except Exception:
                pass
            time.sleep(3)

    def push_decision(req_id, status, reason):
        """Only the decision goes back to head office, never the revealed value."""
        try:
            hq_call("POST", f"/reveal-requests/{req_id}/decision", json_body={"status": status, "decision_reason": reason})
        except Exception:
            pass

    executor = RemediationExecutor(_guard)

    actions = ActionQueue()

    def pull_actions():
        """Intents approved at head office are pulled and verified, then wait here for the shop manager (guard/action_loop.py)."""
        pull_actions_forever(_guard, actions, hq_call)

    @api.get("/api/action-requests")
    def list_action_requests():
        return {"requests": actions.listing()}

    @api.post("/api/action-requests/{intent_id}/approve")
    def approve_action_request(intent_id: str):
        if not approve_request(_guard, executor, actions, hq_call, intent_id):
            raise HTTPException(status_code=409, detail="Request is not pending (already decided, running or expired)")
        return {"status": "running"}

    @api.post("/api/action-requests/{intent_id}/reject")
    def reject_action_request(intent_id: str, body: Optional[DecisionRequest] = None):
        if not reject_request(_guard, actions, hq_call, intent_id, (body.decision_reason if body else None) or "Declined by the shop manager"):
            raise HTTPException(status_code=409, detail="Request is not pending (already decided, running or expired)")
        return {"status": "rejected"}

    api.state.pull_actions = pull_actions
    api.state.pull_reveals = pull_reveals   # started only when run as a program (see __main__), never on import or in tests

    @api.get("/api/reveal-requests")
    def list_reveal_requests(status: Optional[str] = None):
        """Returns pending and decided reveal requests."""
        reqs = _guard.pseudonym_mgr.list_reveal_requests(status=status)
        return {"count": len(reqs), "requests": reqs}

    @api.post("/api/reveal-requests")
    def create_reveal_request(req: CreateRevealRequest):
        """Creates a new reveal request in the local reveal queue."""
        created = _guard.pseudonym_mgr.create_reveal_request(
            pseudonym=req.pseudonym,
            reason=req.reason,
        )
        return created

    @api.post("/api/reveal-requests/{req_id}/approve")
    def approve_reveal_request(req_id: str, body: Optional[DecisionRequest] = None):
        """
        Approves a reveal request locally.
        Resolves the pseudonym from local reveal.db and returns the real identifier.
        """
        reason = body.decision_reason if body else "Approved by shop operator"
        res = _guard.pseudonym_mgr.decide_reveal_request(req_id=req_id, approved=True, reason=reason)
        if not res:
            raise HTTPException(status_code=404, detail=f"Reveal request '{req_id}' not found")
        push_decision(req_id, "approved", reason)
        return res

    @api.post("/api/reveal-requests/{req_id}/reject")
    def reject_reveal_request(req_id: str, body: Optional[DecisionRequest] = None):
        """Rejects a reveal request locally."""
        reason = body.decision_reason if body else "Rejected by shop operator"
        res = _guard.pseudonym_mgr.decide_reveal_request(req_id=req_id, approved=False, reason=reason)
        if not res:
            raise HTTPException(status_code=404, detail=f"Reveal request '{req_id}' not found")
        push_decision(req_id, "rejected", reason)
        return res

    @api.get("/api/reveal/{pseudonym}")
    def reveal_pseudonym(pseudonym: str):
        """
        Local reverse lookup: resolves a pseudonym to its real raw identifier.
        Only accessible within the local environment.
        """
        real_val = _guard.pseudonym_mgr.reveal(pseudonym)
        if real_val is None:
            raise HTTPException(
                status_code=404,
                detail=f"Pseudonym '{pseudonym}' not found in local reveal table",
            )
        prefix = pseudonym.split("-")[0] if "-" in pseudonym else "unknown"
        return {
            "pseudonym": pseudonym,
            "prefix": prefix,
            "real_value": real_val,
        }

    # Mount static frontend bundle if present
    dist_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist_dir.exists() and dist_dir.is_dir():
        from starlette.staticfiles import StaticFiles
        api.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="frontend")
    else:
        @api.get("/")
        def root():
            return {
                "service": "airlock-guard-api",
                "version": _guard.config.GUARD_VERSION,
                "port": 9000,
                "docs": "/docs",
            }

    return api


app = create_guard_api_app()

if __name__ == "__main__":
    import uvicorn
    import threading
    threading.Thread(target=app.state.pull_reveals, daemon=True).start()
    threading.Thread(target=app.state.pull_actions, daemon=True).start()
    port = int(os.getenv("GUARD_PORT", "9000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
