"""
guard/pseudonym.py
Deterministic pseudonymization using HMAC-SHA256 with tenant secret salt (T8):
- Produces pseudonyms matching: ^(host|src|user|proc)-[0-9a-f]{8}$
- Local reveal table in SQLite: answers "who is src-xxxx" locally only
- Raw identifiers (IPs, usernames, hostnames) NEVER cross the trust boundary
"""

import hashlib
import hmac
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

PSEUDONYM_REGEX = r"^(host|src|user|proc)-[0-9a-f]{8}$"


def generate_pseudonym(prefix: str, value: str, tenant_secret: str) -> str:
    """
    Generate an 8-character hex pseudonym with the given prefix:
    prefix: 'host', 'src', 'user', or 'proc'
    value: raw hostname, IP, username, or process identifier
    tenant_secret: local secret salt held by the tenant
    """
    if prefix not in {"host", "src", "user", "proc"}:
        raise ValueError(f"Invalid prefix: {prefix}. Allowed: host, src, user, proc")

    digest = hmac.new(
        tenant_secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # First 4 bytes = 8 hex characters
    return f"{prefix}-{digest[:8]}"


class PseudonymManager:
    """
    Local pseudonym service managing generation and local-only reverse mapping.
    Keeps the reveal table in local SQLite (data/reveal.db).
    """

    def __init__(
        self,
        tenant_secret: str,
        db_path: str = "data/reveal.db",
        conn: Optional[sqlite3.Connection] = None,
    ):
        self.tenant_secret = tenant_secret
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
                CREATE TABLE IF NOT EXISTS reveal (
                    pseudonym TEXT PRIMARY KEY,
                    prefix TEXT NOT NULL,
                    raw_value TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reveal_requests (
                    id TEXT PRIMARY KEY,
                    pseudonym TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_at REAL NOT NULL,
                    decision_reason TEXT,
                    decided_at REAL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS local_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                """
            )

    def get_or_create(self, prefix: str, raw_value: str) -> str:
        """
        Computes the deterministic pseudonym and stores the mapping locally.
        Returns the pseudonym.
        """
        pseudonym = generate_pseudonym(prefix, raw_value, self.tenant_secret)
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO reveal (pseudonym, prefix, raw_value, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (pseudonym, prefix, raw_value, now),
            )
        return pseudonym

    def reveal(self, pseudonym: str) -> Optional[str]:
        """
        Answers 'who is src-xxxx' locally only.
        Returns the real raw value, or None if unknown.
        """
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT raw_value FROM reveal WHERE pseudonym = ?", (pseudonym,))
            row = cur.fetchone()
            return str(row[0]) if row else None

    def get_all_reveals(self) -> List[Dict[str, Any]]:
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM reveal ORDER BY created_at ASC")
            return [dict(r) for r in cur.fetchall()]

    def create_reveal_request(self, pseudonym: str, reason: str, req_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a pending reveal request and writes to local audit log."""
        r_id = req_id or f"req-{uuid.uuid4().hex[:8]}"
        now = time.time()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO reveal_requests (id, pseudonym, reason, status, requested_at)
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (r_id, pseudonym, reason, now),
            )
            conn.execute(
                "INSERT INTO local_audit (timestamp, action, details) VALUES (?, ?, ?)",
                (now, "reveal_requested", f"Requested reveal for {pseudonym}: {reason}"),
            )
        return {
            "id": r_id,
            "pseudonym": pseudonym,
            "reason": reason,
            "status": "pending",
            "requested_at": now,
        }

    def list_reveal_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lists reveal requests, optionally filtered by status ('pending', 'approved', 'rejected')."""
        with self.connection() as conn:
            cur = conn.cursor()
            if status:
                cur.execute("SELECT * FROM reveal_requests WHERE status = ? ORDER BY requested_at DESC", (status,))
            else:
                cur.execute("SELECT * FROM reveal_requests ORDER BY requested_at DESC")
            return [dict(r) for r in cur.fetchall()]

    def decide_reveal_request(self, req_id: str, approved: bool, reason: str = "") -> Optional[Dict[str, Any]]:
        """Decides a reveal request locally, records audit log, and returns resolved details."""
        now = time.time()
        new_status = "approved" if approved else "rejected"
        action = "reveal_approved" if approved else "reveal_rejected"
        with self.connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM reveal_requests WHERE id = ?", (req_id,))
            row = cur.fetchone()
            if not row:
                return None
            req = dict(row)
            cur.execute(
                """
                UPDATE reveal_requests
                SET status = ?, decision_reason = ?, decided_at = ?
                WHERE id = ?
                """,
                (new_status, reason, now, req_id),
            )
            cur.execute(
                "INSERT INTO local_audit (timestamp, action, details) VALUES (?, ?, ?)",
                (now, action, f"{action} for {req['pseudonym']}: {reason}"),
            )
            req["status"] = new_status
            req["decision_reason"] = reason
            req["decided_at"] = now
            if approved:
                req["revealed_value"] = self.reveal(req["pseudonym"])
            return req
