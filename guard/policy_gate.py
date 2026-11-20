"""
guard/policy_gate.py
Egress Policy Gate & Strict Validation (T10):
- Verifies every payload through the official AirlockPayload schema model
- Forbids unknown/extra fields, raw IPs, raw usernames, and unapproved metric names
- Scans serialised payload text for canaries (AKIACANARY...) and unmasked secrets
- Blocks egress and logs violations locally if validation fails
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from pydantic import ValidationError
from contracts.models import AirlockPayload
from guard.scrubber import Scrubber

logger = logging.getLogger("airlock.guard.policy")


class PolicyGate:
    def __init__(self, scrubber: Optional[Scrubber] = None):
        self.scrubber = scrubber or Scrubber()
        self.blocked_count: int = 0

    def inspect_payload(
        self,
        payload_obj: AirlockPayload,
        body_json_str: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Runs comprehensive policy check on the payload before it enters egress.
        Returns:
            (True, None) if payload passes all checks.
            (False, violation_reason) if blocked.
        """
        # 1. Pydantic contract re-validation (checks extra fields, bounds, enum allow-lists)
        try:
            dumped = payload_obj.model_dump(by_alias=True)
            AirlockPayload.model_validate(dumped)
        except ValidationError as exc:
            self.blocked_count += 1
            reason = f"Contract schema violation: {exc}"
            logger.critical(f"POLICY GATE BLOCKED: {reason}")
            return False, reason

        # 2. Canary and secret leak detection in serialized JSON
        serialized = body_json_str or payload_obj.model_dump_json(by_alias=True)
        leak, leak_reason = self.scrubber.contains_canary_or_secret(serialized)
        if leak:
            self.blocked_count += 1
            logger.critical(f"POLICY GATE BLOCKED: {leak_reason}")
            return False, leak_reason

        return True, None
