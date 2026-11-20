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


def test_nothing_runs_until_the_shop_approves_and_a_rejection_is_reported(guard):
    from guard.action_loop import ActionQueue, approve_request, reject_request
    calls = []
    call = lambda method, path, params=None, json_body=None: calls.append((path, json_body))
    q = ActionQueue()
    q.add({**item(), "expires_at": "2999-01-01T00:00:00Z"})
    q.add({**item(), "intent_id": "intent-2", "expires_at": "2999-01-01T00:00:00Z"})
    assert [r["status"] for r in q.listing()] == ["pending", "pending"] and calls == []   # waiting, nothing executed or reported

    assert reject_request(guard, q, call, "intent-2", "not now")
    assert calls[-1][0] == "/api/actions/intent-2/result" and calls[-1][1]["status"] == "rejected"
    assert reject_request(guard, q, call, "intent-2") is None   # decided once

    assert approve_request(guard, RemediationExecutor(guard), q, call, "intent-1", settle_s=0.05, wait=True)
    assert calls[-1][1]["status"] == "done" and q.get("intent-1")["status"] == "done"


def test_expired_request_cannot_be_approved(guard):
    from guard.action_loop import ActionQueue, approve_request
    q = ActionQueue()
    q.add({**item(), "expires_at": "2000-01-01T00:00:00Z"})
    assert q.listing()[0]["status"] == "expired"
    assert approve_request(guard, RemediationExecutor(guard), q, lambda *a, **k: None, "intent-1", wait=True) is None
