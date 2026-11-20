"""
tests/mock_ingest.py
Lightweight mock regional ingest service (representing Tier 2 ingest-in/eu).
Strictly adheres to docs/contracts.md:
- Headers: X-Airlock-Guard-ID, X-Airlock-Signature, X-Airlock-Timestamp
- HMAC-SHA256 signature verification over raw body
"""

import hashlib
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Request
from contracts.models import AirlockPayload, IngestReceipt
from guard.signer import verify_payload_signature
from guard.config import config

mock_ingest_app = FastAPI(title="Mock Regional Ingest")

received_payloads = []


@mock_ingest_app.post("/ingest", response_model=IngestReceipt)
@mock_ingest_app.post("/v1/ingest", response_model=IngestReceipt)
async def ingest_payload(
    request: Request,
    x_airlock_guard_id: str = Header(None, alias="X-Airlock-Guard-ID"),
    x_airlock_signature: str = Header(None, alias="X-Airlock-Signature"),
    x_airlock_timestamp: str = Header(None, alias="X-Airlock-Timestamp"),
):
    body = await request.body()

    if not x_airlock_guard_id or not x_airlock_signature or not x_airlock_timestamp:
        raise HTTPException(status_code=400, detail="Missing required X-Airlock security headers")

    # 1. Verify HMAC Signature over raw body bytes
    is_valid = verify_payload_signature(
        body_bytes=body,
        signature=x_airlock_signature,
        secret_key=config.GUARD_SECRET_KEY,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid HMAC payload signature")

    # 2. Verify Payload Schema (Strict allow-list)
    try:
        payload = AirlockPayload.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Schema violation: {str(e)}")

    # 3. Calculate SHA-256 digest
    body_sha256 = "sha256:" + hashlib.sha256(body).hexdigest()

    status = "stored"
    if any(p["payload_id"] == payload.payload_id for p in received_payloads):
        status = "duplicate"
    else:
        received_payloads.append({
            "payload_id": payload.payload_id,
            "seq": payload.seq,
            "prev_hash": payload.prev_hash,
            "sha256": body_sha256,
            "metrics": payload.metrics,
            "tenant_id": payload.tenant_id,
        })

    receipt = IngestReceipt(
        payload_id=payload.payload_id,
        sha256=body_sha256,
        received_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        status=status,
    )
    return receipt
