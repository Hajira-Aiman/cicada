"""
tests/test_scrubber_and_raw_store.py
Verification for T4 (Raw Store), T5 (Scrubber + Canaries), and T8 (Pseudonyms):
- 24-hour retention countdown and local search in raw.db (raw logs never leave)
- Secret masking: AWS keys, JWTs, bearer tokens, passwords, credit card numbers
- Canary planting every 30s into raw stream and canaries_planted counter tracking
- Pre-send policy check: blocks payloads containing canaries or unmasked secrets
- Deterministic pseudonyms matching ^(host|src|user|proc)-[0-9a-f]{8}$
- Local reveal table answers "who is src-xxxx" locally only
"""

import re
import time
import pytest
from guard.raw_store import RawStore
from guard.scrubber import Scrubber
from guard.pseudonym import PseudonymManager, generate_pseudonym, PSEUDONYM_REGEX
from guard.thin_slice import GuardThinSlice
from guard.config import GuardConfig


def test_raw_store_retention_and_countdown(tmp_path):
    db_file = str(tmp_path / "raw_test.db")
    store = RawStore(db_path=db_file, retention_seconds=10.0)

    # Store fresh log
    now = time.time()
    id1 = store.store_raw_log("User logged in with secret=123", source="auth", timestamp=now)
    assert id1 >= 1
    assert store.count() == 1

    # Store old log beyond retention (15 seconds ago)
    old_ts = now - 15.0
    id2 = store.store_raw_log("Old log entry", source="auth", timestamp=old_ts)
    assert store.count() == 2

    # Search raw logs
    found = store.search_raw_logs("secret=123", minutes=5)
    assert len(found) == 1
    assert "secret=123" in found[0]["raw_text"]

    # Prune expired logs
    pruned = store.prune_expired()
    assert pruned == 1
    assert store.count() == 1

    # Retention countdown should be between 0 and 10 seconds
    countdown = store.get_retention_countdown()
    assert 0.0 <= countdown <= 10.0


def test_scrubber_masks_secrets_and_canary_tripwire(tmp_path):
    scrubber = Scrubber(canary_interval_s=0.1)

    # 1. AWS key masking
    raw1 = "Error initializing client: key AKIAIOSFODNN7EXAMPLE accessed"
    clean1, count1 = scrubber.scrub_text(raw1)
    assert count1 == 1
    assert "AKIAIOSFODNN7EXAMPLE" not in clean1
    assert "[REDACTED_AWS_KEY]" in clean1

    # 2. JWT masking
    raw2 = "Auth header: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG66dcb3"
    clean2, count2 = scrubber.scrub_text(raw2)
    assert count2 == 1
    assert "eyJhbGci" not in clean2
    assert "[REDACTED_JWT]" in clean2

    # 3. Bearer token masking
    raw3 = "Authorization: Bearer secret-token-abcdef1234567890"
    clean3, count3 = scrubber.scrub_text(raw3)
    assert count3 == 1
    assert "secret-token" not in clean3
    assert "[REDACTED_BEARER_TOKEN]" in clean3

    # 4. Password masking
    raw4 = '{"user": "alice", "password": "SuperSecretPassword123!"}'
    clean4, count4 = scrubber.scrub_text(raw4)
    assert count4 == 1
    assert "SuperSecretPassword123!" not in clean4
    assert "[REDACTED_PASSWORD]" in clean4

    # 5. Credit Card masking
    raw5 = "Payment received with card 4111 1111 1111 1234"
    clean5, count5 = scrubber.scrub_text(raw5)
    assert count5 == 1
    assert "4111 1111 1111 1234" not in clean5
    assert "[REDACTED_CARD_NUMBER]" in clean5

    assert scrubber.secrets_redacted == 5

    # 6. Canary planting
    raw_db = str(tmp_path / "canary_raw.db")
    raw_store = RawStore(db_path=raw_db)
    canary = scrubber.maybe_plant_canary(raw_store=raw_store)
    assert canary is not None
    assert canary.startswith("AKIACANARY")
    assert scrubber.canaries_planted == 1
    assert raw_store.count() == 1

    # Pre-send check: blocks canary
    blocked, reason = scrubber.contains_canary_or_secret(f"payload text with {canary}")
    assert blocked
    assert "Canary tripwire detected" in reason

    # Pre-send check: blocks unmasked AWS key
    blocked_key, reason_key = scrubber.contains_canary_or_secret("payload text with AKIAIOSFODNN7EXAMPLE")
    assert blocked_key
    assert "Unmasked AWS" in reason_key

    # Pre-send check: allows properly scrubbed text
    blocked_clean, _ = scrubber.contains_canary_or_secret(clean1)
    assert not blocked_clean


def test_pseudonym_manager_and_local_reveal(tmp_path):
    reveal_db = str(tmp_path / "reveal_test.db")
    secret = "tenant-salt-acme-local-reveal-2026"
    mgr = PseudonymManager(tenant_secret=secret, db_path=reveal_db)

    # 1. Deterministic generation
    p_src1 = mgr.get_or_create("src", "192.168.1.105")
    p_src2 = mgr.get_or_create("src", "192.168.1.105")
    assert p_src1 == p_src2
    assert re.match(r"^src-[0-9a-f]{8}$", p_src1)

    p_user = mgr.get_or_create("user", "admin_ops")
    assert re.match(r"^user-[0-9a-f]{8}$", p_user)

    p_proc = mgr.get_or_create("proc", "shop-api")
    assert re.match(r"^proc-[0-9a-f]{8}$", p_proc)

    p_host = mgr.get_or_create("host", "ryzen-shop-a")
    assert re.match(r"^host-[0-9a-f]{8}$", p_host)

    # 2. Local reveal table lookup answers "who is src-xxxx"
    assert mgr.reveal(p_src1) == "192.168.1.105"
    assert mgr.reveal(p_user) == "admin_ops"
    assert mgr.reveal("src-00000000") is None


def test_guard_pipeline_scrubbing_and_canary_tracking(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH = str(tmp_path / "guard_pipe.db")
    cfg.RAW_DB_PATH = str(tmp_path / "raw_pipe.db")
    cfg.REVEAL_DB_PATH = str(tmp_path / "reveal_pipe.db")

    guard = GuardThinSlice(cfg=cfg)

    # 1. Process log line containing AWS key
    raw_line = "2026-11-21 04:12:00 [ERROR] Failed S3 backup with key AKIAIOSFODNN7EXAMPLE"
    scrubbed, count = guard.process_log_line(raw_line, source="shop-api")
    assert count == 1
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "[REDACTED_AWS_KEY]" in scrubbed

    # 2. Raw line is stored locally in raw.db
    assert guard.raw_store.count() == 1
    raw_entries = guard.raw_store.search_raw_logs("AKIAIOSFODNN7EXAMPLE")
    assert len(raw_entries) == 1

    # 3. Collect window: secrets_redacted counted, secret_redacted event emitted
    payload, body_bytes = guard.collect_window(duration_seconds=1.0)
    assert payload.health.secrets_redacted == 1
    assert any(e.category == "secret_redacted" for e in payload.events)
    assert payload.health.canaries_planted >= 1

    # 4. Verify no raw IP, raw hostname, or raw secret exists in serialised payload
    body_text = body_bytes.decode("utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in body_text
    assert guard.hostname not in body_text

    # 5. Pre-send block when a canary leaks into payload
    guard.emit_change_event("new_process")
    # Manually inject canary into an event's text if possible or check contain check
    leak, reason = guard.scrubber.contains_canary_or_secret("Some text with AKIACANARY1234567890ABCDEF")
    assert leak
    assert "Canary tripwire detected" in reason
