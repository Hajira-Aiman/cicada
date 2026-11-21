"""
guard/log_tailer.py
Log File Tailer & Event Normalizer (T3, T16):
- Tails data/shop-api.log (and /var/log/auth.log on Linux)
- Passes each raw line into guard.process_log_line() for local raw.db storage and secret scrubbing
- Dispatches login_failure and login_success events directly into guard.record_login()
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("airlock.guard.tailer")

SSH_FAIL_PATTERN = re.compile(r"Failed password for (?:invalid user )?(\S+) from (\S+) port \d+ ssh2")
SSH_SUCCESS_PATTERN = re.compile(r"Accepted (?:password|publickey) for (\S+) from (\S+) port \d+ ssh2")


class LogTailer:
    def __init__(self, log_path: str = "data/shop-api.log", guard: Optional[Any] = None, start_at_end: bool = False):
        """The read position is saved next to the log, so a guard restart resumes instead of replaying every old line
        (which would re-raise old honeypot hits and bursts). With no saved position, start_at_end skips existing history:
        pass True when the guard has run before (its ledger is not empty)."""
        self.log_path = log_path
        self.guard = guard
        self.state_path = log_path + ".offset"
        self.offset: int = 0
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self.offset = int(Path(self.state_path).read_text().strip())
        except (OSError, ValueError):
            if start_at_end and os.path.exists(self.log_path):
                self.offset = os.path.getsize(self.log_path)
                self._save_offset()

    def _save_offset(self) -> None:
        try:
            Path(self.state_path).write_text(str(self.offset))
        except OSError as e:
            logger.warning(f"Could not save tailer position {self.state_path}: {e}")

    def read_new_lines(self) -> List[str]:
        """Reads all new lines appended since the last check."""
        if not os.path.exists(self.log_path):
            return []

        try:
            if os.path.getsize(self.log_path) < self.offset:
                self.offset = 0  # file was truncated or rotated
            with open(self.log_path, "rb") as f:
                f.seek(self.offset)
                chunk = f.read()
            end = chunk.rfind(b"\n") + 1  # only complete lines; a partial tail is read next time
            if end:
                self.offset += end
                self._save_offset()
            lines = chunk[:end].decode("utf-8", errors="replace").splitlines()
            return [line.strip() for line in lines if line.strip()]
        except Exception as e:
            logger.warning(f"Error reading log file {self.log_path}: {e}")
            return []

    def process_pending_logs(self) -> int:
        """
        Reads and processes new log lines through the guard pipeline.
        Returns count of processed lines.
        """
        lines = self.read_new_lines()
        if not lines or self.guard is None:
            return len(lines)

        for line in lines:
            # 1. Process log line through guard scrubber & store in local raw.db
            self.guard.process_log_line(line, source="shop-api")

            # 2. Parse structured events (e.g. login attempts)
            parsed_json = False
            try:
                data = json.loads(line)
                parsed_json = True
                ev = data.get("event")
                ts = data.get("timestamp")
                if ev == "login_failure":
                    username = data.get("username", "unknown")
                    ip = data.get("ip", "127.0.0.1")
                    self.guard.record_login(raw_username=username, raw_ip=ip, success=False, timestamp=ts)
                elif ev == "login_success":
                    username = data.get("username", "unknown")
                    ip = data.get("ip", "127.0.0.1")
                    self.guard.record_login(raw_username=username, raw_ip=ip, success=True, timestamp=ts)
            except Exception:
                pass

            # 3. Parse syslog / sshd auth.log lines (Linux /var/log/auth.log)
            if not parsed_json:
                m_fail = SSH_FAIL_PATTERN.search(line)
                if m_fail:
                    user, ip = m_fail.group(1), m_fail.group(2)
                    self.guard.record_login(raw_username=user, raw_ip=ip, success=False)
                else:
                    m_ok = SSH_SUCCESS_PATTERN.search(line)
                    if m_ok:
                        user, ip = m_ok.group(1), m_ok.group(2)
                        self.guard.record_login(raw_username=user, raw_ip=ip, success=True)

        return len(lines)
