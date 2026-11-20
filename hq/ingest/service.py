"""
hq/ingest/service.py
Ingestion verification and processing logic.
Enforces the 8-step security verification order:
1. Known guard (airlock_core.guards) -> 401
2. Valid HMAC-SHA256 signature over raw body -> 401
3. Timestamp freshness within +/-300s -> 400 (clock skew >30s logs audit warning)
4. Schema contract validation (AirlockPayload strict allow-list) -> 422
5. Pinned policy hash per tenant -> 422
6. Canary and secret tripwire on raw body -> 422 (increments leak badge)
7. Insert once by payload_id (ON CONFLICT DO NOTHING) -> duplicate return status
8. Seq gap and prev_hash chain tracking -> 422 on chain break; gaps buffered
"""

import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import ValidationError

from contracts.models import AirlockPayload, IngestReceipt
from hq.db import (
    check_chain_integrity,
    get_tenant_assigned_region,
    get_tenant_pinned_policy,
    is_region_paused,
    log_audit_event,
    lookup_guard,
    record_leak_detected,
    store_payload,
    update_guard_reconciliation,
)

# Global event listeners for in-memory WebSocket pub/sub
_ingest_listeners: List[Callable[[Dict[str, Any]], Any]] = []

# Tripwire regex patterns
CANARY_REGEX = re.compile(r"AKIACANARY[A-Z0-9]*", re.IGNORECASE)
AWS_KEY_REGEX = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
PRIVATE_KEY_REGEX = re.compile(r"-----BEGIN\s+[A-Z\s]+PRIVATE\s+KEY-----", re.IGNORECASE)


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


def scan_for_secrets(raw_body_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Scans the raw body string for canaries or unmasked secrets."""
    if match := CANARY_REGEX.search(raw_body_str):
        return True, "canary", match.group(0)
    if match := AWS_KEY_REGEX.search(raw_body_str):
        return True, "aws_secret_key", match.group(0)
    if match := PRIVATE_KEY_REGEX.search(raw_body_str):
        return True, "private_key", match.group(0)
    return False, None, None


def process_ingest_payload(
    region: str,
    raw_body: bytes,
    guard_id: Optional[str],
    signature: Optional[str],
    timestamp_str: Optional[str],
) -> Tuple[int, Dict[str, Any]]:
    """
    Validates and stores incoming telemetry payload enforcing strict order:
    1. Known guard -> 401
    2. Valid HMAC -> 401
    3. Timestamp within +/-5 min -> 400 (clock skew >30s audit warning)
    4. Schema contract -> 422
    5. Pinned policy hash -> 422
    6. Canary and secret tripwire -> 422
    7. Insert once by payload_id (idempotent)
    8. Seq gap and prev_hash chain tracking -> 422 on chain break
    """
    # 0. Region pause check (503 Service Unavailable, no failover forwarding)
    if is_region_paused(region):
        log_audit_event(actor=guard_id or "unknown", action="region_paused_reject", details={"region": region})
        return 503, {"error": f"Region '{region}' is paused", "detail": f"Region '{region}' is paused"}

    # 1. Known guard check
    if not guard_id:
        log_audit_event(actor="unknown", action="missing_guard_header", details={"region": region})
        return 400, {"error": "Missing required security header: X-Airlock-Guard-ID"}

    guard_record = lookup_guard(guard_id)
    if not guard_record:
        log_audit_event(actor=guard_id, action="rogue_guard", details={"guard_id": guard_id, "region": region})
        return 401, {"error": f"Rogue guard '{guard_id}' is not registered in airlock_core"}

    tenant_id = guard_record["tenant_id"]
    secret = guard_record["hmac_secret"]

    # Data residency check
    assigned_region = get_tenant_assigned_region(tenant_id)
    if assigned_region and assigned_region != region:
        log_audit_event(
            actor=guard_id,
            action="residency_violation",
            tenant_id=tenant_id,
            details={"region": region, "assigned_region": assigned_region},
        )
        return 403, {"error": f"Data residency violation: tenant '{tenant_id}' is assigned to region '{assigned_region}', not '{region}'"}

    # 2. Valid HMAC (raw body) check
    if not signature:
        log_audit_event(actor=guard_id, action="missing_signature", tenant_id=tenant_id)
        return 400, {"error": "Missing required security header: X-Airlock-Signature"}

    expected_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, signature):
        log_audit_event(actor=guard_id, action="bad_signature", tenant_id=tenant_id, details={"guard_id": guard_id})
        return 401, {"error": "Invalid HMAC-SHA256 payload signature"}

    # 3. Timestamp within +/- 5 min (+/- 300s)
    if not timestamp_str:
        log_audit_event(actor=guard_id, action="missing_timestamp", tenant_id=tenant_id)
        return 400, {"error": "Missing required security header: X-Airlock-Timestamp"}

    try:
        sent_dt = parse_iso8601_z(timestamp_str)
        now_dt = datetime.now(timezone.utc)
        skew_seconds = abs((now_dt - sent_dt).total_seconds())
        if skew_seconds > 300.0:
            log_audit_event(
                actor=guard_id, action="stale_timestamp", tenant_id=tenant_id, details={"skew_s": skew_seconds}
            )
            return 400, {"error": f"Timestamp skewed by {int(skew_seconds)}s (> 300s window allowed)"}
        if skew_seconds > 30.0:
            log_audit_event(
                actor=guard_id, action="clock_skew_warning", tenant_id=tenant_id, details={"skew_s": skew_seconds}
            )
    except Exception as exc:
        log_audit_event(
            actor=guard_id, action="invalid_timestamp", tenant_id=tenant_id, details={"timestamp": timestamp_str}
        )
        return 400, {"error": f"Invalid ISO-8601 timestamp format: {exc}"}

    # 4. Schema contract validation (strict allow-list)
    try:
        raw_str = raw_body.decode("utf-8")
        payload_json = json.loads(raw_str)
        validated = AirlockPayload.model_validate(payload_json)
        payload_dict = validated.model_dump(by_alias=True)
    except (json.JSONDecodeError, ValidationError) as exc:
        log_audit_event(
            actor=guard_id, action="schema_violation", tenant_id=tenant_id, details={"error": str(exc)}
        )
        return 422, {"error": f"Schema contract violation: {exc}"}

    # 5. Pinned policy hash per tenant
    expected_policy = get_tenant_pinned_policy(validated.tenant_id)
    if expected_policy:
        approved = [p.strip() for p in expected_policy.split(",")]
        if validated.policy_version not in approved:
            log_audit_event(
                actor=guard_id,
                action="policy_mismatch",
                tenant_id=validated.tenant_id,
                details={"expected": expected_policy, "received": validated.policy_version},
            )
            return 422, {"error": f"Policy mismatch: expected {expected_policy}, got {validated.policy_version}"}

    # 6. Canary and secret tripwire on the raw body
    is_leak, leak_type, match_preview = scan_for_secrets(raw_str)
    if is_leak:
        record_leak_detected(validated.tenant_id)
        log_audit_event(
            actor=guard_id,
            action="tripwire_triggered",
            tenant_id=validated.tenant_id,
            details={"leak_type": leak_type, "match": match_preview},
        )
        return 422, {"error": f"Tripwire triggered: {leak_type} detected in raw payload"}

    # 7. Insert once by payload_id (ON CONFLICT DO NOTHING)
    sha256_hash = "sha256:" + hashlib.sha256(raw_body).hexdigest()
    db_name = "airlock_in" if region == "in" else "airlock_eu"

    # Pre-check hash chain integrity before inserting new payload
    chain_ok, chain_err = check_chain_integrity(
        db_name=db_name, guard_id=guard_id, seq=validated.seq, prev_hash=validated.prev_hash
    )
    if not chain_ok:
        log_audit_event(
            actor=guard_id,
            action="chain_break",
            tenant_id=validated.tenant_id,
            details={"seq": validated.seq, "error": chain_err},
        )
        return 422, {"error": f"Hash chain break: {chain_err}"}

    storage_status = store_payload(db_name=db_name, payload_dict=payload_dict, sha256_hash=sha256_hash)

    # 8. Seq gap and prev_hash chain tracking
    is_dup = (storage_status == "duplicate")
    update_guard_reconciliation(
        db_name=db_name,
        guard_id=guard_id,
        tenant_id=validated.tenant_id,
        seq=validated.seq,
        payload_hash=sha256_hash,
        is_duplicate=is_dup,
    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt = IngestReceipt(
        payload_id=payload_dict["payload_id"],
        sha256=sha256_hash,
        received_at=now_iso,
        status=storage_status,
    )

    # 9. Notify WebSocket subscribers on new payload
    if storage_status == "stored":
        notify_listeners(payload_dict)

    return 200, receipt.model_dump()
