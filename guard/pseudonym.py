"""
guard/pseudonym.py
Deterministic pseudonymization using HMAC-SHA256 with tenant secret salt.
Produces pseudonyms matching: ^(host|src|user|proc)-[0-9a-f]{8}$
"""

import hmac
import hashlib


def generate_pseudonym(prefix: str, value: str, tenant_secret: str) -> str:
    """
    Generate an 8-character hex pseudonym with the given prefix:
    prefix: 'host', 'src', 'user', or 'proc'
    value: raw hostname, IP, username, or process identifier
    tenant_secret: local secret salt held by the tenant
    """
    if prefix not in {"host", "src", "user", "proc"}:
        raise ValueError(f"Invalid prefix: {prefix}. Allowed: host, src, user, proc")

    digest = hmac.new(
        tenant_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # First 4 bytes = 8 hex characters
    return f"{prefix}-{digest[:8]}"
