"""
guard/signer.py
HMAC-SHA256 payload signing and verification for guard-to-ingest transport security.
"""

import hmac
import hashlib
from typing import Dict, Tuple


def sign_payload(body_bytes: bytes, timestamp_iso: str, secret_key: str) -> str:
    """
    Signs body + timestamp with HMAC-SHA256.
    Message format: f"{timestamp_iso}.{body_bytes.decode('utf-8')}"
    """
    mac = hmac.new(
        secret_key.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    mac.update(timestamp_iso.encode("utf-8"))
    mac.update(b".")
    mac.update(body_bytes)
    return mac.hexdigest()


def create_auth_headers(
    guard_id: str,
    payload_id: str,
    body_bytes: bytes,
    timestamp_iso: str,
    secret_key: str,
) -> Dict[str, str]:
    """
    Constructs HTTP headers for authenticating guard payloads.
    """
    signature = sign_payload(body_bytes, timestamp_iso, secret_key)
    return {
        "Content-Type": "application/json",
        "X-Guard-ID": guard_id,
        "X-Payload-ID": payload_id,
        "X-Timestamp": timestamp_iso,
        "X-Signature": signature,
    }


def verify_payload_signature(
    body_bytes: bytes,
    timestamp_iso: str,
    signature: str,
    secret_key: str,
) -> bool:
    """
    Verifies the HMAC-SHA256 signature using constant-time comparison.
    """
    expected = sign_payload(body_bytes, timestamp_iso, secret_key)
    return hmac.compare_digest(expected, signature)
