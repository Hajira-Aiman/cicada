"""Shared by simulator + mock ingest: guard registry, signing, region routing."""
import hashlib, hmac, os
from dotenv import load_dotenv
load_dotenv()

# tenant -> (guard_id, region, source tz). ponytail: dev secrets derived from guard_id; real keys come from airlock_core.
TENANTS = {
    "acme":    ("guard-acme-01",    "in", "Asia/Kolkata"),
    "globex":  ("guard-globex-01",  "eu", "Europe/Berlin"),
    "contoso": ("guard-contoso-01", "in", "Asia/Kolkata"),
}
PORTS = {"in": int(os.getenv("INGEST_IN_PORT", 8001)), "eu": int(os.getenv("INGEST_EU_PORT", 8002))}

def secret(guard_id: str) -> bytes:
    return os.getenv("GUARD_SECRET_" + guard_id.upper().replace("-", "_"), "dev-secret-" + guard_id).encode()

def sign(guard_id: str, ts: str, body: bytes) -> str:
    return hmac.new(secret(guard_id), ts.encode() + b"." + body, hashlib.sha256).hexdigest()

def pseudo(kind: str, value: str) -> str:  # same shape as the guard's HMAC pseudonyms
    return f"{kind}-{hashlib.sha256(value.encode()).hexdigest()[:8]}"

def dsn(db: str) -> str:
    g = os.getenv
    return f"postgresql://{g('DB_USER','postgres')}:{g('DB_PASSWORD','airlock_dev')}@{g('DB_HOST','localhost')}:{g('DB_PORT',5432)}/{db}"
