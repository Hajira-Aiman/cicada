"""Tests run on the SQLite fallback unless told otherwise: .env carries live Postgres credentials, and several test
fixtures truncate every table. To test against a scratch Postgres: AIRLOCK_USE_SQLITE=false AIRLOCK_ALLOW_TRUNCATE=1."""
import os

os.environ.setdefault("AIRLOCK_USE_SQLITE", "true")   # must be set before hq.db is imported
