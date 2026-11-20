"""
guard/outbox.py
Outbox buffer and sender with backoff (T11):
- SQLite table outbox(seq, payload_id, sha256, body, created_at, attempts, next_retry_at, status)
- Oldest-first sending order (ORDER BY seq ASC)
- Exponential backoff: [1, 2, 4, 8, 10] seconds while ingest is unreachable
- Receipt validation: marks done only when receipt has matching payload_id + sha256
- Real buffer depth tracking for GuardHealth.buffer_depth
"""

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from guard.ledger import GuardLedger

logger = logging.getLogger("airlock.guard.outbox")

BACKOFF_STEPS = [1.0, 2.0, 4.0, 8.0, 10.0]


class GuardOutbox:
    def __init__(
        self,
        db_path: str = "data/guard.db",
        ledger: Optional[GuardLedger] = None,
        conn: Optional[sqlite3.Connection] = None,
    ):
        self.db_path = db_path
        self._shared_conn = conn
        self.ledger = ledger or GuardLedger(db_path=db_path, conn=conn)
        if self._shared_conn is None and self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        elif self.db_path == ":memory:" and self._shared_conn is None:
            if self.ledger._shared_conn is not None:
                self._shared_conn = self.ledger._shared_conn
            else:
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
                CREATE TABLE IF NOT EXISTS outbox (
                    seq INTEGER PRIMARY KEY,
                    payload_id TEXT UNIQUE NOT NULL,
                    sha256 TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    next_retry_at REAL DEFAULT 0,
                    status TEXT DEFAULT 'queued'
                )
                """
            )

    def enqueue(self, seq: int, payload_id: str, sha256: str, body: str) -> None:
        """Enqueues a payload into the outbox."""
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO outbox (seq, payload_id, sha256, body, created_at, attempts, next_retry_at, status)
                VALUES (?, ?, ?, ?, ?, 0, 0, 'queued')
                """,
                (seq, payload_id, sha256, body, now),
            )

    def get_buffer_depth(self) -> int:
        """Returns the number of queued/unsent items in the buffer."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM outbox WHERE status = 'queued'")
            return int(cur.fetchone()[0])

    def get_queued_items(self) -> List[Dict[str, Any]]:
        """Returns all queued items in ascending seq order (oldest first)."""
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM outbox WHERE status = 'queued' ORDER BY seq ASC")
            return [dict(r) for r in cur.fetchall()]

    def drain(
        self,
        send_fn: Callable[[str, bytes, Optional[Any]], Optional[Any]],
        client: Optional[Any] = None,
        ignore_backoff: bool = False,
    ) -> Tuple[int, int]:
        """
        Drains the outbox in oldest-first order (seq ASC).
        send_fn(payload_id, body_bytes, client) -> IngestReceipt or None
        Returns: (sent_count, failure_count).
        """
        queued = self.get_queued_items()
        if not queued:
            return 0, 0

        now = time.time()
        sent_count = 0
        failure_count = 0

        for item in queued:
            seq = item["seq"]
            payload_id = item["payload_id"]
            sha256 = item["sha256"]
            body = item["body"]
            attempts = item["attempts"]
            next_retry_at = item["next_retry_at"]

            # Backoff check
            if not ignore_backoff and now < next_retry_at:
                logger.debug(f"Seq {seq} is backing off until {next_retry_at:.1f} (now={now:.1f})")
                break

            # Check if ledger already marked this row done
            ledger_row = self.ledger.get_row(payload_id)
            if ledger_row and ledger_row["status"] in ("stored", "duplicate"):
                # Already received; do not resend
                with self.connection() as conn:
                    conn.execute("DELETE FROM outbox WHERE payload_id = ?", (payload_id,))
                continue

            # Attempt transmission
            body_bytes = body.encode("utf-8")
            try:
                receipt = send_fn(payload_id, body_bytes, client)
            except Exception as e:
                logger.warning(f"Error sending payload seq {seq}: {e}")
                receipt = None

            if receipt is not None:
                receipt_payload_id = getattr(receipt, "payload_id", None) or receipt.get("payload_id")
                receipt_sha = getattr(receipt, "sha256", None) or receipt.get("sha256")
                receipt_status = getattr(receipt, "status", None) or receipt.get("status")
                receipt_at = getattr(receipt, "received_at", None) or receipt.get("received_at", "")

                # Validate receipt
                clean_item_sha = sha256.replace("sha256:", "")
                clean_rec_sha = str(receipt_sha).replace("sha256:", "")

                if receipt_payload_id == payload_id and clean_item_sha == clean_rec_sha:
                    # Successfully confirmed by Head Office Ingest
                    self.ledger.mark_receipt(
                        payload_id=payload_id,
                        sha256=receipt_sha,
                        status=receipt_status,
                        receipt_at=receipt_at,
                    )
                    with self.connection() as conn:
                        conn.execute("DELETE FROM outbox WHERE payload_id = ?", (payload_id,))
                    sent_count += 1
                else:
                    logger.error(
                        f"Receipt verification failed for seq {seq}: id={receipt_payload_id} vs {payload_id}, sha={clean_rec_sha} vs {clean_item_sha}"
                    )
                    self.ledger.mark_receipt(
                        payload_id=payload_id,
                        sha256=receipt_sha or "INVALID",
                        status="mismatch",
                        receipt_at=receipt_at,
                    )
                    failure_count += 1
                    break
            else:
                # Transmission failed: apply backoff
                attempts += 1
                backoff_s = BACKOFF_STEPS[min(attempts - 1, len(BACKOFF_STEPS) - 1)]
                next_retry = time.time() + backoff_s

                with self.connection() as conn:
                    conn.execute(
                        "UPDATE outbox SET attempts = ?, next_retry_at = ? WHERE payload_id = ?",
                        (attempts, next_retry, payload_id),
                    )

                logger.warning(
                    f"Payload seq {seq} failed (attempt {attempts}). Backing off for {backoff_s}s."
                )
                failure_count += 1
                # Must stop draining to maintain strict FIFO delivery
                break

        return sent_count, failure_count
