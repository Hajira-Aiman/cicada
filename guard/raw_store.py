"""
guard/raw_store.py
Local Raw Log Store with Retention Management (T4):
- SQLite table raw_logs(id, timestamp, source, raw_text)
- 24-hour retention window with automatic pruning
- Retention countdown calculation for local shop UI
- Raw lines are stored locally only and NEVER leave the environment in payloads
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional


class RawStore:
    def __init__(self, db_path: str = "data/raw.db", retention_seconds: float = 86400.0, conn: Optional[sqlite3.Connection] = None):
        self.db_path = db_path
        self.retention_seconds = retention_seconds
        self._shared_conn = conn
        if self._shared_conn is None and self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        elif self.db_path == ":memory:" and self._shared_conn is None:
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row
        self.init_db()

    @contextmanager
    def connection(self):
        if self._shared_conn is not None:
            with self._shared_conn:
                yield self._shared_conn
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                with conn:
                    yield conn
            finally:
                conn.close()

    def init_db(self):
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    source TEXT NOT NULL,
                    raw_text TEXT NOT NULL
                )
                """
            )

    def store_raw_log(self, text: str, source: str = "shop-api", timestamp: Optional[float] = None) -> int:
        """Stores a raw log line locally."""
        ts = timestamp if timestamp is not None else time.time()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO raw_logs (timestamp, source, raw_text) VALUES (?, ?, ?)",
                (ts, source, text),
            )
            return int(cur.lastrowid)

    def prune_expired(self) -> int:
        """Prunes logs older than retention_seconds. Returns deleted count."""
        cutoff = time.time() - self.retention_seconds
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM raw_logs WHERE timestamp < ?", (cutoff,))
            return cur.rowcount

    def get_retention_countdown(self) -> float:
        """
        Returns seconds remaining until the oldest log line in the store expires.
        If store is empty, returns full retention duration (86400.0 s).
        """
        self.prune_expired()
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(timestamp) FROM raw_logs")
            row = cur.fetchone()
            if not row or row[0] is None:
                return float(self.retention_seconds)

            oldest_ts = float(row[0])
            now = time.time()
            remaining = (oldest_ts + self.retention_seconds) - now
            return max(0.0, round(remaining, 1))

    def search_raw_logs(self, query: str = "", minutes: int = 10) -> List[Dict[str, Any]]:
        """
        Searches raw logs within the last N minutes.
        Supports Shop AI and Local Shop Screen inspect operations.
        """
        cutoff = time.time() - (minutes * 60)
        with self.connection() as conn:
            cur = conn.cursor()
            if query:
                cur.execute(
                    "SELECT * FROM raw_logs WHERE timestamp >= ? AND raw_text LIKE ? ORDER BY timestamp DESC",
                    (cutoff, f"%{query}%"),
                )
            else:
                cur.execute(
                    "SELECT * FROM raw_logs WHERE timestamp >= ? ORDER BY timestamp DESC",
                    (cutoff,),
                )
            return [dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM raw_logs")
            return int(cur.fetchone()[0])
