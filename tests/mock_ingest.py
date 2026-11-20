"""
tests/mock_ingest.py
Lightweight mock regional ingest service (representing Tier 2 ingest-in/eu).
Verifies:
1. X-Guard-ID and secret key association
2. HMAC-SHA256 signature over body + timestamp
3. Payload schema validation (extra='forbid')
4. Returns SignedReceipt
"""

import hashlib
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException, Request, Response
from contracts.payload import PayloadV1, SignedReceipt
from guard.signer import verify_payload_signature
from guard.config import config

mock_ingest_app = FastAPI(title="Mock Regional Ingest")

# In-memory storage for received payloads to verify reconciliation
received_payloads = []


@mock_ingest_app.post("/v1/ingest", response_model=SignedReceipt)
@mock_ingest_app.post("/ingest", response_model=SignedReceipt)
async def ingest_payload(
    request: Request,
    x_guard_id: str = Header(..., alias="X-Guard-ID"),
    x_payload_id: str = Header(..., alias="X-Payload-ID"),
    x_timestamp: str = Header(..., alias="X-Timestamp"),
    x_signature: str = Header(..., alias="X-Signature"),
):
    body = await request.body()

    # 1. Verify HMAC Signature
    is_valid = verify_payload_signature(
        body_bytes=body,
        signature=x_signature,
        secret_key=config.GUARD_SECRET_KEY,
    )
    if not is_valid:
        raise HTTPException(status_code=401, detail="Invalid HMAC payload signature")

    # 2. Verify Payload Schema (Strict allow-list)
    try:
        payload = PayloadV1.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Schema violation: {str(e)}")

    if payload.payload_id != x_payload_id:
        raise HTTPException(status_code=400, detail="Mismatched X-Payload-ID header")

    # 3. Calculate SHA-256 digest
    body_sha256 = f"sha256:{hashlib.sha256(body).hexdigest()}"

    # Check for duplicates
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

    receipt = SignedReceipt(
        payload_id=payload.payload_id,
        sha256=body_sha256,
        received_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        status=status,
    )
    return receipt
