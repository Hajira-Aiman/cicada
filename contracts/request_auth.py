"""Guard -> head-office request signing (shared by both sides so they cannot drift).

Every guard request that is not an ingest payload (pulling actions or reveal requests, posting results or
decisions) carries X-Airlock-Guard-ID / -Timestamp / -Signature, where the signature is
HMAC-SHA256(guard secret, "<timestamp>\\n<METHOD>\\n<path?query>\\n" + body). Ingest keeps its own
body-only signature from docs/contracts.md.
"""
from datetime import datetime, timezone
from typing import Dict, Optional
import hashlib
import hmac

# Browsers on localhost or a private network (hotspot / LAN) only. The bearer token is not a cookie, so no wildcard needed.
PRIVATE_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
)


def request_signature(secret: str, timestamp: str, method: str, path_qs: str, body: bytes = b"") -> str:
    msg = f"{timestamp}\n{method.upper()}\n{path_qs}\n".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def guard_request_headers(guard_id: str, secret: str, method: str, path_qs: str, body: bytes = b"",
                          now: Optional[datetime] = None) -> Dict[str, str]:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "X-Airlock-Guard-ID": guard_id,
        "X-Airlock-Timestamp": ts,
        "X-Airlock-Signature": request_signature(secret, ts, method, path_qs, body),
    }
