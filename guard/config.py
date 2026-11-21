"""
guard/config.py
Configuration loader reading environment variables with .env support.
Zero hardcoded IPs. Pinned to registered secrets from contracts/models.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class GuardConfig:
    TENANT_ID: str = os.getenv("TENANT_ID", "acme")
    GUARD_ID: str = os.getenv("GUARD_ID", "guard-acme-01")
    REGION_URL: str = os.getenv("INGEST_URL", "http://localhost:8001/ingest")
    GUARD_SECRET_KEY: str = os.getenv("GUARD_SECRET_KEY", "sec-acme-super-secret-key-2026")
    TENANT_SECRET_KEY: str = os.getenv("TENANT_SECRET_KEY", "tenant-salt-acme-local-reveal-2026")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    POLICY_VERSION: str = os.getenv("POLICY_VERSION", "sha256:v1-default-policy")
    GUARD_VERSION: str = "0.2.0"
    GUARD_PORT: int = int(os.getenv("GUARD_PORT", "9000"))
    SHOP_API_PORT: int = int(os.getenv("SHOP_API_PORT", "7000"))
    SHOP_HEALTH_URL: str = os.getenv("SHOP_HEALTH_URL", f"http://127.0.0.1:{os.getenv('SHOP_API_PORT', '7000')}/health")
    GUARD_DB_PATH: str = os.getenv("GUARD_DB_PATH", "data/guard.db")
    RAW_DB_PATH: str = os.getenv("RAW_DB_PATH", "data/raw.db")
    REVEAL_DB_PATH: str = os.getenv("REVEAL_DB_PATH", "data/reveal.db")
    SHOP_LOG_PATH: str = os.getenv("SHOP_LOG_PATH", "data/shop-api.log")
    TIMEOUT_SECONDS: float = 5.0
    # path to the CA / self-signed cert that signed head office's TLS cert; unset = system CAs (https) or plain http
    TLS_VERIFY = os.getenv("INGEST_CA_CERT") or True


config = GuardConfig()
