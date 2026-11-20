"""
hq/ingest/service.py
Ingestion verification and processing logic.
Verifies guard authentication, HMAC signature, timestamp freshness, and schema compliance.
Inserts into the regional database and returns a cryptographic IngestReceipt.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from contracts.models import AirlockPayload, IngestReceipt
from hq.db import lookup_guard, store_payload

# Global event listeners for in-memory WebSocket pub/sub
_ingest_listeners: List[Callable[[Dict[str, Any]], Any]] = []


def add_ingest_listener(listener: Callable[[Dict[str, Any]], Any]):
    """Registers an event callback when a new payload is ingested."""
    if listener not in _ingest_listeners:
        _ingest_listeners.append(listener)


def notify_listeners(payload_dict: Dict[str, Any]):
    for listener in _ingest_listeners:
        try:
            listener(payload_dict)
        except Exception:
            pass


def parse_iso8601_z(ts_str: str) -> datetime:
    """Parses UTC ISO-8601 timestamp ending with Z."""
    clean_ts = ts_str.rstrip("Z")
    dt = datetime.fromisoformat(clean_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def process_ingest_payload(
    region: str,
    raw_body: bytes,
    guard_id: Optional[str],
    signature: Optional[str],
    timestamp_str: Optional[str],
) -> Tuple[int, Dict[str, Any]]:
    """
    Validates and stores incoming telemetry payload.
    Returns: (HTTP status code, response dictionary).
    """
    if not guard_id or not signature or not timestamp_str:
        return 400, {"error": "Missing required security headers (Guard-ID, Signature, Timestamp)"}

    # 1. Timestamp freshness check (+/- 300s)
    try:
        sent_dt = parse_iso8601_z(timestamp_str)
        now_dt = datetime.now(timezone.utc)
        skew_seconds = abs((now_dt - sent_dt).total_seconds())
        if skew_seconds > 300.0:
            return 400, {"error": f"Timestamp skewed by {int(skew_seconds)}s (> 300s window allowed)"}
    except Exception as exc:
        return 400, {"error": f"Invalid ISO-8601 timestamp format: {exc}"}

    # 2. Guard authentication lookup
    guard_record = lookup_guard(guard_id)
    if not guard_record:
        return 401, {"error": f"Guard '{guard_id}' is not registered in airlock_core"}

    secret = guard_record["hmac_secret"]

    # 3. HMAC-SHA256 signature verification
    expected_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        return 401, {"error": "Invalid HMAC-SHA256 payload signature"}

    # 4. JSON parsing and schema validation
    try:
        payload_json = json.loads(raw_body.decode("utf-8"))
        validated = AirlockPayload.model_validate(payload_json)
        payload_dict = validated.model_dump(by_alias=True)
    except (json.JSONDecodeError, ValidationError) as exc:
        return 422, {"error": f"Schema contract violation: {exc}"}

    # 5. Compute SHA-256 hash of payload
    sha256_hash = "sha256:" + hashlib.sha256(raw_body).hexdigest()

    # 6. Idempotent storage in regional database
    db_name = "airlock_in" if region == "in" else "airlock_eu"
    storage_status = store_payload(db_name=db_name, payload_dict=payload_dict, sha256_hash=sha256_hash)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt = IngestReceipt(
        payload_id=payload_dict["payload_id"],
        sha256=sha256_hash,
        received_at=now_iso,
        status=storage_status,
    )

    # 7. Notify real-time WebSocket subscribers
    if storage_status == "stored":
        notify_listeners(payload_dict)

    return 200, receipt.model_dump()
