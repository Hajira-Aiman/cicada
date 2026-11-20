"""
guard/ledger.py
Cryptographic hash-chained egress ledger (T11):
- SQLite table ledger(seq, payload_id, sha256, prev_hash, body, status, receipt_at)
- Contiguous sequence numbers (no gaps)
- Hash chain integrity: row[k].prev_hash == row[k-1].sha256
- Tracks receipt status ("pending", "stored", "duplicate", "mismatch")
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class GuardLedger:
    def __init__(self, db_path: str = "data/guard.db", conn: Optional[sqlite3.Connection] = None):
        self.db_path = db_path
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
                CREATE TABLE IF NOT EXISTS ledger (
                    seq INTEGER PRIMARY KEY,
                    payload_id TEXT UNIQUE NOT NULL,
                    sha256 TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    body TEXT NOT NULL,
                    status TEXT NOT NULL,
                    receipt_at TEXT
                )
                """
            )

    def get_last_seq_and_hash(self) -> Tuple[int, str]:
        """Returns (highest seq, highest sha256) or (0, 'GENESIS')."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT seq, sha256 FROM ledger ORDER BY seq DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return int(row["seq"]), str(row["sha256"])
            return 0, "GENESIS"

    def record_payload(
        self,
        seq: int,
        payload_id: str,
        sha256: str,
        prev_hash: str,
        body: str,
        status: str = "pending",
    ) -> None:
        """
        Records a new payload into the ledger.
        Ensures sequence number has no gaps.
        """
        last_seq, expected_prev_hash = self.get_last_seq_and_hash()
        expected_next_seq = last_seq + 1

        if seq != expected_next_seq:
            raise ValueError(
                f"Ledger sequence gap detected: expected seq {expected_next_seq}, got {seq}"
            )
        if prev_hash != expected_prev_hash:
            raise ValueError(
                f"Ledger hash chain mismatch: expected prev_hash '{expected_prev_hash}', got '{prev_hash}'"
            )

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO ledger (seq, payload_id, sha256, prev_hash, body, status, receipt_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (seq, payload_id, sha256, prev_hash, body, status),
            )

    def mark_receipt(
        self,
        payload_id: str,
        sha256: str,
        status: str,
        receipt_at: str,
    ) -> bool:
        """
        Marks a ledger row as done with receipt confirmation.
        Verifies that sha256 in receipt matches the recorded sha256.
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT seq, sha256, status FROM ledger WHERE payload_id = ?", (payload_id,))
            row = cur.fetchone()
            if not row:
                return False

            expected_sha = str(row["sha256"])
            clean_expected = expected_sha.replace("sha256:", "")
            clean_receipt = sha256.replace("sha256:", "")

            if clean_expected != clean_receipt:
                cur.execute(
                    "UPDATE ledger SET status = 'mismatch' WHERE payload_id = ?",
                    (payload_id,),
                )
                return False

            new_status = status if status in ("stored", "duplicate") else "done"
            cur.execute(
                "UPDATE ledger SET status = ?, receipt_at = ? WHERE payload_id = ?",
                (new_status, receipt_at, payload_id),
            )
            return True

    def get_row(self, payload_id: str) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ledger WHERE payload_id = ?", (payload_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_row_by_seq(self, seq: int) -> Optional[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ledger WHERE seq = ?", (seq,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_rows(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ledger ORDER BY seq ASC")
            return [dict(r) for r in cur.fetchall()]

    def verify_chain(self) -> Tuple[bool, Optional[str]]:
        """
        Verifies the full cryptographic hash chain of the ledger:
        - Sequence numbers are contiguous (no gaps, 1..N)
        - prev_hash matches prior row's sha256
        - sha256 matches sha256(body)
        """
        rows = self.get_all_rows()
        if not rows:
            return True, None

        expected_seq = 1
        expected_prev_hash = "GENESIS"

        for row in rows:
            seq = row["seq"]
            payload_id = row["payload_id"]
            sha256 = row["sha256"]
            prev_hash = row["prev_hash"]
            body = row["body"]

            if seq != expected_seq:
                return False, f"Sequence gap at row {seq}: expected {expected_seq}"

            if prev_hash != expected_prev_hash:
                return False, f"Hash chain break at seq {seq}: expected prev_hash '{expected_prev_hash}', found '{prev_hash}'"

            computed_sha = "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()
            clean_computed = computed_sha.replace("sha256:", "")
            clean_sha = sha256.replace("sha256:", "")
            if clean_computed != clean_sha:
                return False, f"Body hash mismatch at seq {seq} (payload {payload_id})"

            expected_prev_hash = sha256
            expected_seq += 1

        return True, None
