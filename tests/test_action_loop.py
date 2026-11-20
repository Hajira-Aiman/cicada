"""Guard-side remediation loop: signature check, execute under local policy, settle check, rollback, report."""
import pytest

from guard.action_loop import handle_intent, intent_signature, verify_intent
from guard.config import GuardConfig
from guard.executor import RemediationExecutor
from guard.thin_slice import GuardThinSlice

SECRET = "sec-acme-super-secret-key-2026"


@pytest.fixture
def guard(tmp_path):
    cfg = GuardConfig()
    cfg.GUARD_DB_PATH, cfg.RAW_DB_PATH, cfg.REVEAL_DB_PATH, cfg.SHOP_LOG_PATH = (
        str(tmp_path / "g.db"), str(tmp_path / "r.db"), str(tmp_path / "v.db"), str(tmp_path / "s.log"))
    return GuardThinSlice(cfg=cfg)


def item(action="investigate", target="host-7f3a1234"):
    it = {"intent_id": "intent-1", "tenant_id": "acme", "action": action, "target": target, "created_at": "2026-11-21T04:00:00Z"}
    it["signature"] = intent_signature(SECRET, it)
    return it


def test_signature_is_checked():
    it = item()
    assert verify_intent(SECRET, it)
    assert not verify_intent("wrong-secret", it)
    assert not verify_intent(SECRET, {**it, "target": "host-deadbeef"})   # tampered after signing
    assert not verify_intent(SECRET, {**it, "signature": None})


def test_healthy_shop_reports_done_and_audits(guard):
    calls = []
    guard.probe_shop_health = lambda client=None: (1.0, 5.0)
    rep = handle_intent(guard, RemediationExecutor(guard), lambda m, p, params=None, json_body=None: calls.append((m, p, json_body)), item(), settle_s=0.3)
    assert rep["status"] == "done" and rep["health_improved"] is True
    assert calls[0][1] == "/api/actions/intent-1/result" and calls[0][2]["guard_id"] == guard.config.GUARD_ID
    with guard.pseudonym_mgr.connection() as c:
        assert c.execute("SELECT 1 FROM local_audit WHERE action = 'action_executed:investigate'").fetchone()


def test_unhealthy_shop_is_rolled_back_and_reported(guard):
    calls = []
    guard.probe_shop_health = lambda client=None: (0.0, 5.0)
    ex = RemediationExecutor(guard)
    rep = handle_intent(guard, ex, lambda m, p, params=None, json_body=None: calls.append(json_body), item(), settle_s=0.3)
    assert rep["health_improved"] is False and rep["details"].get("rolled_back") is True
    assert ex.rollback_timers["intent-1"]["status"] == "rolled_back"
