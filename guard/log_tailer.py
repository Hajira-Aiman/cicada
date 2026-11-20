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
from pathlib import Path
from typing import Any, List, Optional

logger = logging.getLogger("airlock.guard.tailer")


class LogTailer:
    def __init__(self, log_path: str = "data/shop-api.log", guard: Optional[Any] = None):
        self.log_path = log_path
        self.guard = guard
        self.offset: int = 0
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)

    def read_new_lines(self) -> List[str]:
        """Reads all new lines appended since the last check."""
        if not os.path.exists(self.log_path):
            return []

        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.offset)
                lines = f.readlines()
                self.offset = f.tell()
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
            try:
                data = json.loads(line)
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

        return len(lines)
