"""
guard/action_loop.py
Remediation on the guard (PRD #20): pull approved action intents from head office, verify each one's signature,
run it through the local policy (RemediationExecutor), check the shop is healthy afterwards and report the result.
If the shop is not healthy after the settle time the action is rolled back and reported as such.
"""
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Set

from contracts.models import ActionIntent

logger = logging.getLogger("airlock.guard.actions")
FAILED_PROBES_TO_ROLL_BACK = 3
SETTLE_S = 15.0   # how long to watch the shop before judging a fix (the intent's own rollback window caps it)


def intent_signature(secret: str, item: Dict[str, Any]) -> str:
    """Same body head office signs in GET /api/actions/pending."""
    body = json.dumps(
        {"intent_id": item["intent_id"], "tenant_id": item["tenant_id"], "action": item["action"],
         "target": item["target"], "created_at": item["created_at"]},
        sort_keys=True,
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_intent(secret: str, item: Dict[str, Any]) -> bool:
    return hmac.compare_digest(intent_signature(secret, item), str(item.get("signature") or ""))


def handle_intent(guard, executor, call: Callable, item: Dict[str, Any], settle_s: float = SETTLE_S) -> Dict[str, Any]:
    """Execute one verified intent, watch the shop, report. Returns what was reported."""
    window = int(item.get("rollback_window_s") or 120)
    intent = ActionIntent(intent_id=item["intent_id"], tenant_id=item["tenant_id"], action=item["action"],
                          target=item["target"], timestamp=item["created_at"], signature=item["signature"],
                          rollback_window_s=max(10, window))
    result = executor.execute(intent)
    executed = result.get("status") == "executed"
    healthy, elapsed = True, 0
    if executed:
        deadline = time.time() + min(intent.rollback_window_s, settle_s)
        down = 0
        while time.time() < deadline:
            time.sleep(max(0.01, min(2.0, settle_s / 5, deadline - time.time())))
            down = 0 if guard.probe_shop_health()[0] == 1.0 else down + 1
            if down >= FAILED_PROBES_TO_ROLL_BACK:   # one dropped probe on a flaky link is not a failed fix
                healthy = False
                break
        elapsed = int(min(intent.rollback_window_s, settle_s))
        if not healthy:
            executor.rollback(intent.intent_id)
            result["rolled_back"] = True
    report = {"guard_id": guard.config.GUARD_ID, "status": "done" if executed else "failed",
              "details": {k: v for k, v in result.items() if k in ("message", "reason", "rolled_back")},
              "health_improved": healthy, "elapsed_seconds": elapsed}
    call("POST", f"/api/actions/{intent.intent_id}/result", json_body=report)
    return report


class ActionQueue:
    """Approved-at-head-office intents wait here for the shop manager. Nothing runs until the shop approves."""

    def __init__(self):
        self.items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, item: Dict[str, Any]) -> None:
        with self._lock:
            self.items.setdefault(item["intent_id"], {"item": item, "status": "pending", "result": None})

    def get(self, intent_id: str):
        with self._lock:
            return self.items.get(intent_id)

    def set(self, intent_id: str, status: str, result=None) -> None:
        with self._lock:
            if intent_id in self.items:
                self.items[intent_id].update(status=status, result=result)

    def listing(self):
        """Newest first, in the shape the shop screen shows. An expired pending request is shown as expired."""
        now = time.time()
        out = []
        with self._lock:
            for rec in self.items.values():
                it = rec["item"]
                status = rec["status"]
                exp = _epoch(it.get("expires_at"))
                if status == "pending" and exp and now > exp:
                    status = "expired"
                out.append({"intent_id": it["intent_id"], "action": it["action"], "target": it["target"], "status": status,
                            "approved_by": it.get("approved_by"), "details": it.get("details") or {}, "created_at": it.get("created_at"),
                            "expires_at": it.get("expires_at"), "result": rec["result"]})
        return sorted(out, key=lambda r: str(r["created_at"]), reverse=True)


def _epoch(value):
    from datetime import datetime, timezone
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).rstrip("Z"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()


def pull_actions_forever(guard, queue: ActionQueue, call: Callable, every_s: float = 3.0) -> None:
    """Poll head office for approved intents. A bad signature is logged and ignored; a good one waits for the shop's decision."""
    while True:
        try:
            for item in call("GET", "/api/actions/pending").json().get("intents", []):
                if not verify_intent(guard.config.GUARD_SECRET_KEY, item):
                    if not queue.get(item.get("intent_id")):
                        logger.error(f"Intent {item.get('intent_id')} has an invalid signature: ignored")
                    continue
                queue.add(item)
        except Exception as exc:
            logger.debug(f"action poll failed: {exc}")
        time.sleep(every_s)


def approve_request(guard, executor, queue: ActionQueue, call: Callable, intent_id: str, settle_s: float = SETTLE_S, wait: bool = False):
    """The shop manager said yes: run it under the local policy (in the background unless wait=True) and report the outcome."""
    rec = queue.get(intent_id)
    shown = next((r for r in queue.listing() if r["intent_id"] == intent_id), None)
    if not rec or not shown or shown["status"] != "pending":   # unknown, already decided, or past its 10-minute validity
        return None
    queue.set(intent_id, "running")

    def run():
        try:
            report = handle_intent(guard, executor, call, rec["item"], settle_s)
            ok = report["status"] == "done" and report["health_improved"]
            queue.set(intent_id, "done" if ok else ("rolled_back" if report["status"] == "done" else "failed"), report["details"])
        except Exception as exc:
            logger.warning(f"Intent {intent_id} failed: {exc}")
            queue.set(intent_id, "failed", {"reason": str(exc)})
    if wait:
        run()
    else:
        threading.Thread(target=run, daemon=True).start()
    return True


def reject_request(guard, queue: ActionQueue, call: Callable, intent_id: str, reason: str = "Declined by the shop manager"):
    """The shop manager said no: nothing runs, head office is told."""
    rec = queue.get(intent_id)
    if not rec or rec["status"] != "pending":
        return None
    queue.set(intent_id, "rejected", {"reason": reason})
    call("POST", f"/api/actions/{intent_id}/result", json_body={"guard_id": guard.config.GUARD_ID, "status": "rejected",
         "details": {"reason": reason}, "health_improved": True, "elapsed_seconds": 0})
    return True
