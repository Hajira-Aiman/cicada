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


def pull_actions_forever(guard, executor, call: Callable, every_s: float = 3.0) -> None:
    """Poll head office for approved intents. Each intent id is handled once; a bad signature is logged and ignored."""
    seen: Set[str] = set()
    while True:
        try:
            for item in call("GET", "/api/actions/pending").json().get("intents", []):
                iid = item.get("intent_id")
                if iid in seen:
                    continue
                seen.add(iid)
                if not verify_intent(guard.config.GUARD_SECRET_KEY, item):
                    logger.error(f"Intent {iid} has an invalid signature: ignored")
                    continue
                threading.Thread(target=_safe_handle, args=(guard, executor, call, item), daemon=True).start()
        except Exception as exc:
            logger.debug(f"action poll failed: {exc}")
        time.sleep(every_s)


def _safe_handle(guard, executor, call, item) -> None:
    try:
        handle_intent(guard, executor, call, item)
    except Exception as exc:
        logger.warning(f"Intent {item.get('intent_id')} failed: {exc}")
