"""
guard/signer.py
HMAC-SHA256 payload signing and verification for guard-to-ingest transport security.
Aligned with hq/ingest/service.py and tools/simulate.py.
"""

import hmac
import hashlib
from typing import Dict


def sign_payload(body_bytes: bytes, secret_key: str) -> str:
    """
    Signs body bytes directly with HMAC-SHA256.
    """
    return hmac.new(
        secret_key.encode("utf-8"),
        body_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()


def create_auth_headers(
    guard_id: str,
    payload_id: str,
    body_bytes: bytes,
    timestamp_iso: str,
    secret_key: str,
) -> Dict[str, str]:
    """
    Constructs HTTP headers for authenticating guard payloads.
    Includes canonical X-Airlock-* headers used by HQ Ingest and aliases.
    """
    signature = sign_payload(body_bytes, secret_key)
    return {
        "Content-Type": "application/json",
        "X-Airlock-Guard-ID": guard_id,
        "X-Airlock-Signature": signature,
        "X-Airlock-Timestamp": timestamp_iso,
        # Backward compatibility aliases
        "X-Guard-ID": guard_id,
        "X-Payload-ID": payload_id,
        "X-Timestamp": timestamp_iso,
        "X-Signature": signature,
    }


def verify_payload_signature(
    body_bytes: bytes,
    signature: str,
    secret_key: str,
) -> bool:
    """
    Verifies the HMAC-SHA256 signature using constant-time comparison.
    """
    expected = sign_payload(body_bytes, secret_key)
    return hmac.compare_digest(expected, signature)
