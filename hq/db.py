"""
hq/db.py
Database access layer for Head Office.
Supports PostgreSQL (via psycopg) for airlock_core, airlock_in, and airlock_eu,
with transparent SQLite in-memory fallback for isolated pytest environments.
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# In-memory SQLite instances for fallback / testing
_sqlite_dbs: Dict[str, sqlite3.Connection] = {}
_force_sqlite = os.getenv("AIRLOCK_USE_SQLITE", "false").lower() == "true"


def is_postgres_available() -> bool:
    """Checks if PostgreSQL is reachable."""
    if _force_sqlite or not PSYCOPG_AVAILABLE:
        return False
    try:
        with psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres",
            connect_timeout=1,
        ) as conn:
            return True
    except Exception:
        return False


def get_sqlite_conn(db_name: str) -> sqlite3.Connection:
    if db_name not in _sqlite_dbs:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _sqlite_dbs[db_name] = conn
        _init_sqlite_schema(conn, db_name)
    return _sqlite_dbs[db_name]


def _init_sqlite_schema(conn: sqlite3.Connection, db_name: str):
    cur = conn.cursor()
    if db_name == "airlock_core":
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                assigned_region TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS guards (
                guard_id TEXT PRIMARY KEY,
                tenant_id TEXT,
                hmac_secret TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                tenant_id TEXT,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT OR IGNORE INTO tenants (tenant_id, name, assigned_region) VALUES
                ('acme', 'Acme Shop A', 'in'),
                ('globex', 'Globex Shop B', 'eu'),
                ('contoso', 'Contoso Organizer', 'in'),
                ('guests', 'Judges Phones', 'eu');
            INSERT OR IGNORE INTO guards (guard_id, tenant_id, hmac_secret) VALUES
                ('guard-acme-01', 'acme', 'sec-acme-super-secret-key-2026'),
                ('guard-globex-01', 'globex', 'sec-globex-super-secret-key-2026'),
                ('guard-contoso-01', 'contoso', 'sec-contoso-super-secret-key-2026');
        """)
    else:  # airlock_in or airlock_eu
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS payloads (
                payload_id TEXT PRIMARY KEY,
                guard_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                prev_hash TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                received_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                name TEXT NOT NULL,
                avg REAL NOT NULL,
                max REAL NOT NULL,
                event_time TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                severity TEXT NOT NULL,
                actor TEXT,
                count INTEGER NOT NULL,
                window_s INTEGER DEFAULT 2,
                event_time TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS receipts (
                payload_id TEXT PRIMARY KEY,
                guard_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                received_at TEXT NOT NULL,
                status TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS health_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT,
                source TEXT,
                state TEXT,
                old_state TEXT,
                reasons TEXT,
                at TEXT
            );
            CREATE TABLE IF NOT EXISTS health_current (
                tenant_id TEXT,
                source TEXT,
                state TEXT,
                reasons TEXT,
                since TEXT,
                flaps_prevented INTEGER DEFAULT 0,
                updated TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(tenant_id, source)
            );
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                started_at TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tenant_thresholds (
                tenant_id TEXT PRIMARY KEY,
                config TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                alert_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
    conn.commit()


def init_all_databases():
    """Initializes schema on all three databases."""
    if is_postgres_available():
        # Schema already initialized by init_postgres.sql in Postgres container
        return
    # Initialize SQLite in-memory fallbacks
    for db in ("airlock_core", "airlock_in", "airlock_eu"):
        get_sqlite_conn(db)


def register_guard(guard_id: str, tenant_id: str, hmac_secret: str, db_name: str = "airlock_core"):
    """Registers or updates a guard credential in airlock_core."""
    if is_postgres_available():
        with psycopg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=db_name
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO guards (guard_id, tenant_id, hmac_secret)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (guard_id) DO UPDATE SET hmac_secret = EXCLUDED.hmac_secret;
                    """,
                    (guard_id, tenant_id, hmac_secret),
                )
            conn.commit()
    else:
        conn = get_sqlite_conn(db_name)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO guards (guard_id, tenant_id, hmac_secret)
            VALUES (?, ?, ?);
            """,
            (guard_id, tenant_id, hmac_secret),
        )
        conn.commit()


def lookup_guard(guard_id: str, db_name: str = "airlock_core") -> Optional[Dict[str, Any]]:
    """Looks up guard details by guard_id."""
    if is_postgres_available():
        try:
            with psycopg.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=db_name, row_factory=dict_row
            ) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT guard_id, tenant_id, hmac_secret, status FROM guards WHERE guard_id = %s;", (guard_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception:
            return None
    else:
        conn = get_sqlite_conn(db_name)
        cur = conn.cursor()
        cur.execute("SELECT guard_id, tenant_id, hmac_secret, status FROM guards WHERE guard_id = ?;", (guard_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def store_payload(db_name: str, payload_dict: Dict[str, Any], sha256_hash: str) -> str:
    """
    Stores an incoming payload idempotently.
    Returns: 'stored' if newly inserted, 'duplicate' if already present.
    """
    payload_id = payload_dict["payload_id"]
    guard_id = payload_dict["guard_id"]
    tenant_id = payload_dict["tenant_id"]
    seq = payload_dict["seq"]
    prev_hash = payload_dict["prev_hash"]
    sent_at = payload_dict["sent_at"]
    window_start = payload_dict["window"]["start"]
    window_end = payload_dict["window"]["end"]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_postgres_available():
        with psycopg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=db_name
        ) as conn:
            with conn.cursor() as cur:
                # Check for duplicate
                cur.execute("SELECT payload_id FROM payloads WHERE payload_id = %s;", (payload_id,))
                if cur.fetchone():
                    # Record duplicate receipt
                    cur.execute(
                        """
                        INSERT INTO receipts (payload_id, guard_id, sha256, received_at, status)
                        VALUES (%s, %s, %s, %s, 'duplicate')
                        ON CONFLICT (payload_id) DO NOTHING;
                        """,
                        (payload_id, guard_id, sha256_hash, now_iso),
                    )
                    conn.commit()
                    return "duplicate"

                # Insert payload
                cur.execute(
                    """
                    INSERT INTO payloads (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, raw_payload, received_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, json.dumps(payload_dict), now_iso),
                )

                # Insert metrics
                for m in payload_dict.get("metrics", []):
                    cur.execute(
                        """
                        INSERT INTO metrics (payload_id, tenant_id, source, name, avg, max, event_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s);
                        """,
                        (payload_id, tenant_id, m["source"], m["name"], m["avg"], m["max"], window_start),
                    )

                # Insert events
                for e in payload_dict.get("events", []):
                    cur.execute(
                        """
                        INSERT INTO events (payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (payload_id, tenant_id, e["source"], e["category"], e["severity"], e.get("actor"), e["count"], e.get("window_s", 2), window_start),
                    )

                # Record stored receipt
                cur.execute(
                    """
                    INSERT INTO receipts (payload_id, guard_id, sha256, received_at, status)
                    VALUES (%s, %s, %s, %s, 'stored');
                    """,
                    (payload_id, guard_id, sha256_hash, now_iso),
                )
            conn.commit()
            return "stored"
    else:
        conn = get_sqlite_conn(db_name)
        cur = conn.cursor()
        cur.execute("SELECT payload_id FROM payloads WHERE payload_id = ?;", (payload_id,))
        if cur.fetchone():
            cur.execute(
                """
                INSERT OR IGNORE INTO receipts (payload_id, guard_id, sha256, received_at, status)
                VALUES (?, ?, ?, ?, 'duplicate');
                """,
                (payload_id, guard_id, sha256_hash, now_iso),
            )
            conn.commit()
            return "duplicate"

        cur.execute(
            """
            INSERT INTO payloads (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, raw_payload, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, json.dumps(payload_dict), now_iso),
        )

        for m in payload_dict.get("metrics", []):
            cur.execute(
                """
                INSERT INTO metrics (payload_id, tenant_id, source, name, avg, max, event_time)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (payload_id, tenant_id, m["source"], m["name"], m["avg"], m["max"], window_start),
            )

        for e in payload_dict.get("events", []):
            cur.execute(
                """
                INSERT INTO events (payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (payload_id, tenant_id, e["source"], e["category"], e["severity"], e.get("actor"), e["count"], e.get("window_s", 2), window_start),
            )

        cur.execute(
            """
            INSERT INTO receipts (payload_id, guard_id, sha256, received_at, status)
            VALUES (?, ?, ?, ?, 'stored');
            """,
            (payload_id, guard_id, sha256_hash, now_iso),
        )
        conn.commit()
        return "stored"


def execute_query(db_name: str, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Executes a SELECT query and returns rows as dictionaries."""
    if is_postgres_available():
        with psycopg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=db_name, row_factory=dict_row
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
    else:
        conn = get_sqlite_conn(db_name)
        cur = conn.cursor()
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
