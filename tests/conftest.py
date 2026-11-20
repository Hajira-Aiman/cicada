"""Tests run on the SQLite fallback unless told otherwise: .env carries live Postgres credentials, and several test
fixtures truncate every table. To test against a scratch Postgres: AIRLOCK_USE_SQLITE=false AIRLOCK_ALLOW_TRUNCATE=1."""
import os

os.environ.setdefault("AIRLOCK_USE_SQLITE", "true")   # must be set before hq.db is imported


import pytest


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch, tmp_path):
    """A real AI service on :8010 or a guard.db left by another test must not change results."""
    monkeypatch.setenv("AI_SERVICE_URL", "http://127.0.0.1:9/chat")   # unreachable: the tests expect the offline fallback
    from guard.config import config
    monkeypatch.setattr(config, "GUARD_DB_PATH", str(tmp_path / "guard.db"), raising=False)
