"""
guard/signer.py
HMAC-SHA256 payload signing and verification for guard-to-ingest transport security.
Strictly adheres to docs/contracts.md:
- HMAC-SHA256 computed over raw body bytes
- Headers: X-Airlock-Guard-ID, X-Airlock-Signature, X-Airlock-Timestamp
"""

import hmac
import hashlib
from typing import Dict


def sign_payload(body_bytes: bytes, secret_key: str) -> str:
    """
    Signs raw body bytes directly with HMAC-SHA256.
    """
    return hmac.new(
        secret_key.encode("utf-8"),
        body_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()


def create_auth_headers(
    guard_id: str,
    body_bytes: bytes,
    timestamp_iso: str,
    secret_key: str,
) -> Dict[str, str]:
    """
    Constructs HTTP headers for authenticating guard payloads strictly matching docs/contracts.md.
    No legacy alias headers.
    """
    signature = sign_payload(body_bytes, secret_key)
    return {
        "Content-Type": "application/json",
        "X-Airlock-Guard-ID": guard_id,
        "X-Airlock-Signature": signature,
        "X-Airlock-Timestamp": timestamp_iso,
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
