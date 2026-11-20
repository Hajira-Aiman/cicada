"""
guard/scrubber.py
Secret Scrubber & Canary Tripwire (T5):
- Detects and masks AWS keys, JWTs, bearer tokens, passwords, card numbers
- Tracks redaction counts for GuardHealth.secrets_redacted
- Plants an AKIACANARY... every 30s into raw stream (GuardHealth.canaries_planted)
- Pre-send gate: blocks any payload that contains a canary or unmasked secret
"""

import re
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

AWS_KEY_PATTERN = re.compile(r"\b(AKIA[0-9A-Z]{16,20})\b")
AWS_SECRET_PATTERN = re.compile(r"(?i)(aws_secret_access_key\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{40})(['\"]?)")
JWT_PATTERN = re.compile(r"\b(eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+)\b")
BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9\-._~+/]{16,}=*)")
PASSWORD_JSON_PATTERN = re.compile(r'(?i)("?(?:password|passwd|pwd)"?\s*[:=]\s*)"[^"]+"')
PASSWORD_KV_PATTERN = re.compile(r'(?i)("?(?:password|passwd|pwd)"?\s*[:=]\s*)[^\s,;]+')
CARD_PATTERN = re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b")
SECRET_KV_PATTERN = re.compile(r'(?i)("?(?:api_key|apikey|secret_key|client_secret)"?\s*[:=]\s*)"[^"]+"')

# Canary detector
CANARY_SUBSTRING = "AKIACANARY"


class Scrubber:
    def __init__(self, canary_interval_s: float = 30.0):
        self.canary_interval_s = canary_interval_s
        self.secrets_redacted: int = 0
        self.canaries_planted: int = 0
        self.last_canary_time: float = 0.0

    def scrub_text(self, text: str) -> Tuple[str, int]:
        """
        Masks all sensitive tokens with standard redaction placeholders.
        Returns: (scrubbed_text, redactions_count)
        """
        redactions = 0
        scrubbed = text

        # 1. AWS Access Keys
        matches = list(AWS_KEY_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = AWS_KEY_PATTERN.sub("[REDACTED_AWS_KEY]", scrubbed)

        # 2. AWS Secret Access Keys
        matches = list(AWS_SECRET_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = AWS_SECRET_PATTERN.sub(r"\1[REDACTED_AWS_SECRET]\3", scrubbed)

        # 3. JWTs
        matches = list(JWT_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = JWT_PATTERN.sub("[REDACTED_JWT]", scrubbed)

        # 4. Bearer tokens
        matches = list(BEARER_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = BEARER_PATTERN.sub(r"\1[REDACTED_BEARER_TOKEN]", scrubbed)

        # 5. Passwords
        m_json = list(PASSWORD_JSON_PATTERN.finditer(scrubbed))
        if m_json:
            redactions += len(m_json)
            scrubbed = PASSWORD_JSON_PATTERN.sub(r'\1"[REDACTED_PASSWORD]"', scrubbed)
        else:
            m_kv = list(PASSWORD_KV_PATTERN.finditer(scrubbed))
            if m_kv:
                redactions += len(m_kv)
                scrubbed = PASSWORD_KV_PATTERN.sub(r"\1[REDACTED_PASSWORD]", scrubbed)

        # 6. Credit Card Numbers
        matches = list(CARD_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = CARD_PATTERN.sub("[REDACTED_CARD_NUMBER]", scrubbed)

        # 7. Generic API keys
        matches = list(SECRET_KV_PATTERN.finditer(scrubbed))
        if matches:
            redactions += len(matches)
            scrubbed = SECRET_KV_PATTERN.sub(r'\1"[REDACTED_SECRET]"', scrubbed)

        self.secrets_redacted += redactions
        return scrubbed, redactions

    def maybe_plant_canary(self, raw_store: Optional[Any] = None, now: Optional[float] = None) -> Optional[str]:
        """
        Plants an AKIACANARY... every 30 seconds into the local raw store.
        Returns the canary string if planted, otherwise None.
        """
        current_time = now if now is not None else time.time()
        if self.last_canary_time == 0.0 or (current_time - self.last_canary_time) >= self.canary_interval_s:
            suffix = secrets.token_hex(8).upper()
            canary = f"AKIACANARY{suffix}"
            self.canaries_planted += 1
            self.last_canary_time = current_time

            if raw_store is not None and hasattr(raw_store, "store_raw_log"):
                raw_store.store_raw_log(
                    text=f"System credential validation: access_key={canary}",
                    source="canary-tripwire",
                    timestamp=current_time,
                )
            return canary
        return None

    def contains_canary_or_secret(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Pre-send policy check: scans serialized payload text.
        Blocks any payload containing an unmasked secret or canary tripwire.
        Returns: (True, violation_reason) if blocked; (False, None) if clean.
        """
        # Canary tripwire check
        if CANARY_SUBSTRING in text:
            return True, "Canary tripwire detected in payload (AKIACANARY)"

        # Unmasked AWS key check
        if AWS_KEY_PATTERN.search(text):
            return True, "Unmasked AWS Access Key detected in payload"

        # Unmasked JWT check
        if JWT_PATTERN.search(text):
            return True, "Unmasked JWT detected in payload"

        # Unmasked Bearer token check
        if BEARER_PATTERN.search(text):
            return True, "Unmasked Bearer token detected in payload"

        # Unmasked Credit Card check
        if CARD_PATTERN.search(text):
            return True, "Unmasked Credit Card Number detected in payload"

        return False, None
