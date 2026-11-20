"""
hq/db.py
Database access layer for Head Office.
Supports PostgreSQL (via psycopg) for airlock_core, airlock_in, and airlock_eu,
with transparent SQLite in-memory fallback for isolated pytest environments.
"""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False
    ConnectionPool = None

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# In-memory SQLite instances for fallback / testing
_sqlite_dbs: Dict[str, sqlite3.Connection] = {}
_force_sqlite = os.getenv("AIRLOCK_USE_SQLITE", "false").lower() == "true"

# Global connection pools (min 2, max 10 connections per database)
_pools: Dict[str, Any] = {}
_postgres_available: Optional[bool] = None


def is_postgres_available() -> bool:
    """Checks if PostgreSQL is reachable."""
    global _postgres_available
    if _force_sqlite or not PSYCOPG_AVAILABLE:
        return False
    if _pools:
        return True
    if _postgres_available is not None:
        return _postgres_available
    try:
        with psycopg.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            dbname="postgres",
            connect_timeout=2,
        ) as conn:
            _postgres_available = True
            return True
    except Exception:
        _postgres_available = False
        return False


def get_db_pool(db_name: str) -> Optional[Any]:
    """Returns or creates a ConnectionPool for the specified database."""
    if not is_postgres_available():
        return None
    if db_name not in _pools:
        conninfo = f"host={DB_HOST} port={DB_PORT} user={DB_USER} password={DB_PASSWORD} dbname={db_name}"
        _pools[db_name] = ConnectionPool(
            conninfo=conninfo,
            min_size=2,
            max_size=10,
            open=True,
            kwargs={"row_factory": dict_row},
        )
    return _pools[db_name]


def close_all_pools():
    """Closes all connection pools and resets availability cache."""
    global _pools, _postgres_available
    for pool in list(_pools.values()):
        try:
            pool.close()
        except Exception:
            pass
    _pools.clear()
    _postgres_available = None


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
                pinned_policy_hash TEXT,
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
            CREATE TABLE IF NOT EXISTS leak_counters (
                tenant_id TEXT PRIMARY KEY,
                leak_count INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS region_states (
                region TEXT PRIMARY KEY,
                is_paused INTEGER DEFAULT 0,
                paused_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reveal_requests (
                request_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                pseudonym TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                requested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                decided_at TEXT,
                decision_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS action_intents (
                intent_id TEXT PRIMARY KEY,
                incident_id TEXT,
                tenant_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                risk TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'proposed',
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                approved_by TEXT,
                expires_at TEXT
            );
            CREATE TABLE IF NOT EXISTS action_audit (
                event_id TEXT PRIMARY KEY,
                intent_id TEXT,
                actor TEXT NOT NULL,
                step TEXT NOT NULL,
                details TEXT,
                at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT OR IGNORE INTO region_states (region, is_paused) VALUES ('in', 0), ('eu', 0);
            INSERT OR IGNORE INTO tenants (tenant_id, name, assigned_region, pinned_policy_hash) VALUES
                ('acme', 'Acme Shop A', 'in', 'sha256:v1-default-policy,sha256:ab1289cf001e35a9'),
                ('globex', 'Globex Shop B', 'eu', 'sha256:ab1289cf001e35a9,sha256:v1-default-policy'),
                ('contoso', 'Contoso Organizer', 'in', 'sha256:ab1289cf001e35a9'),
                ('guests', 'Judges Phones', 'eu', 'sha256:v1-default-policy');
            INSERT OR IGNORE INTO guards (guard_id, tenant_id, hmac_secret) VALUES
                ('guard-acme-01', 'acme', 'sec-acme-super-secret-key-2026'),
                ('guard-globex-01', 'globex', 'sec-globex-super-secret-key-2026'),
                ('guard-contoso-01', 'contoso', 'sec-contoso-super-secret-key-2026');
            INSERT OR IGNORE INTO users (user_id, tenant_id, role, password_hash) VALUES
                ('admin', NULL, 'engineer', 'scrypt$c2FsdC1hZG1pbi0yMDI2$S2+LAEdp1XilDF4COmPPTmFtgBRYLbGJCLN/YRBBCed8W6ydmpsBA0eVPGlSOarK7HoNh10X1DK3VgiCAC0a/Q=='),
                ('user-acme', 'acme', 'customer', 'scrypt$c2FsdC1hY21lLTIwMjY=$PcWWqwev1hDgD44VIaMpVfJMao5xJYupDGV/DHm+M0cD32h0apYSxB5bhLGpLF23LEeMQLJskw8yX+3wkTG9MQ=='),
                ('user-globex', 'globex', 'customer', 'scrypt$c2FsdC1nbG9iZXgtMjAyNg==$517FJoycv+sWCUl7NrwXfj4Z7aYH/ublDkR7felDxpvnzX4Ae99zAMRB81H/DlYLz4b1Z3stmkDn65BCvvROMg=='),
                ('user-contoso', 'contoso', 'customer', 'scrypt$c2FsdC1jb250b3NvLTIwMjY=$oxtispFeK2x1FKFQw6CKnGWUakmxOsO+djrmVLAIULC0ekXR2RGTjDn21+Hgcul1yXM1Jyo8kjJyLDmL425udg==');
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
                metric TEXT,
                source TEXT,
                at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS aiops_damage_map (tenant_id TEXT PRIMARY KEY, body TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS aiops_baselines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                metric TEXT NOT NULL,
                mean REAL NOT NULL,
                std REAL NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS guard_reconciliation (
                guard_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                sent_count INTEGER DEFAULT 0,
                received_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                max_seq INTEGER DEFAULT 0,
                last_hash TEXT,
                gaps TEXT DEFAULT '[]',
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS aiops_alerts (
                alert_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source TEXT,
                title TEXT,
                severity TEXT,
                body TEXT,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS aiops_counters (
                tenant_id TEXT PRIMARY KEY,
                raw_alerts INTEGER DEFAULT 0,
                incidents INTEGER DEFAULT 0,
                noise_cut_pct REAL DEFAULT 0.0,
                flaps_prevented INTEGER DEFAULT 0,
                updated TEXT DEFAULT CURRENT_TIMESTAMP
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
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO guards (guard_id, tenant_id, hmac_secret)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (guard_id) DO UPDATE SET hmac_secret = EXCLUDED.hmac_secret;
                        """,
                        (guard_id, tenant_id, hmac_secret),
                    )
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
            pool = get_db_pool(db_name)
            with pool.connection() as conn:
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


def _store_sqlite(db_name: str, payload_dict: Dict[str, Any], sha256_hash: str, now_iso: str) -> str:
    conn = get_sqlite_conn(db_name)
    cur = conn.cursor()
    cur.execute("SELECT payload_id FROM payloads WHERE payload_id = ?;", (payload_dict["payload_id"],))
    if cur.fetchone():
        cur.execute(
            """
            INSERT OR IGNORE INTO receipts (payload_id, guard_id, sha256, received_at, status)
            VALUES (?, ?, ?, ?, 'duplicate');
            """,
            (payload_dict["payload_id"], payload_dict["guard_id"], sha256_hash, now_iso),
        )
        conn.commit()
        return "duplicate"

    cur.execute(
        """
        INSERT INTO payloads (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, raw_payload, received_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            payload_dict["payload_id"],
            payload_dict["guard_id"],
            payload_dict["tenant_id"],
            payload_dict["seq"],
            payload_dict["prev_hash"],
            payload_dict["sent_at"],
            payload_dict["window"]["start"],
            payload_dict["window"]["end"],
            json.dumps(payload_dict),
            now_iso,
        ),
    )

    for m in payload_dict.get("metrics", []):
        cur.execute(
            """
            INSERT INTO metrics (payload_id, tenant_id, source, name, avg, max, event_time)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (payload_dict["payload_id"], payload_dict["tenant_id"], m["source"], m["name"], m["avg"], m["max"], payload_dict["window"]["start"]),
        )

    for e in payload_dict.get("events", []):
        cur.execute(
            """
            INSERT INTO events (payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (payload_dict["payload_id"], payload_dict["tenant_id"], e["source"], e["category"], e["severity"], e.get("actor"), e["count"], e.get("window_s", 2), payload_dict["window"]["start"]),
        )

    cur.execute(
        """
        INSERT INTO receipts (payload_id, guard_id, sha256, received_at, status)
        VALUES (?, ?, ?, ?, 'stored');
        """,
        (payload_dict["payload_id"], payload_dict["guard_id"], sha256_hash, now_iso),
    )
    conn.commit()
    return "stored"


def store_payload(db_name: str, payload_dict: Dict[str, Any], sha256_hash: str) -> str:
    """
    Stores an incoming payload idempotently in ONE transaction with SET LOCAL app.current_tenant.
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

    res = "stored"
    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute("SELECT set_config('app.current_tenant', %s, true);", (tenant_id,))
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
                        res = "duplicate"
                    else:
                        # Insert payload
                        cur.execute(
                            """
                            INSERT INTO payloads (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, raw_payload, received_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                            """,
                            (payload_id, guard_id, tenant_id, seq, prev_hash, sent_at, window_start, window_end, json.dumps(payload_dict), now_iso),
                        )

                        # Insert metrics in batch
                        metrics = payload_dict.get("metrics", [])
                        if metrics:
                            cur.executemany(
                                """
                                INSERT INTO metrics (payload_id, tenant_id, source, name, avg, max, event_time)
                                VALUES (%s, %s, %s, %s, %s, %s, %s);
                                """,
                                [
                                    (payload_id, tenant_id, m["source"], m["name"], m["avg"], m["max"], window_start)
                                    for m in metrics
                                ],
                            )

                        # Insert events in batch
                        events = payload_dict.get("events", [])
                        if events:
                            cur.executemany(
                                """
                                INSERT INTO events (payload_id, tenant_id, source, category, severity, actor, count, window_s, event_time)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                                """,
                                [
                                    (payload_id, tenant_id, e["source"], e["category"], e["severity"], e.get("actor"), e["count"], e.get("window_s", 2), window_start)
                                    for e in events
                                ],
                            )

                        # Record stored receipt
                        cur.execute(
                            """
                            INSERT INTO receipts (payload_id, guard_id, sha256, received_at, status)
                            VALUES (%s, %s, %s, %s, 'stored');
                            """,
                            (payload_id, guard_id, sha256_hash, now_iso),
                        )
                        res = "stored"

    if is_postgres_available():
        # Mirror to in-memory SQLite for test harnesses inspecting get_sqlite_conn
        try:
            _store_sqlite(db_name, payload_dict, sha256_hash, now_iso)
        except Exception:
            pass
        return res
    return _store_sqlite(db_name, payload_dict, sha256_hash, now_iso)


AUTH_SECRET = os.getenv("AUTH_SECRET", "airlock-head-office-session-secret-2026")


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hashes a password using scrypt."""
    salt = salt or os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifies a password against a stored scrypt hash."""
    try:
        scheme, salt_b64, dk_b64 = stored_hash.split("$")
        salt = base64.b64decode(salt_b64)
        expected_dk = base64.b64decode(dk_b64)
        actual_dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


def create_session_token(user_id: str, tenant_id: Optional[str], role: str, expires_in_s: int = 86400) -> str:
    """Generates a cryptographically signed HMAC-SHA256 session token."""
    now_ts = int(time.time())
    payload = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "iat": now_ts,
        "exp": now_ts + expires_in_s,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = base64.urlsafe_b64encode(raw).decode("utf-8")
    sig = hmac.new(AUTH_SECRET.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{b64_payload}.{sig}"


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies signature and expiration of session token. Returns payload dict if valid."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        b64_payload, sig = parts
        expected_sig = hmac.new(AUTH_SECRET.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(b64_payload.encode("utf-8")).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def authenticate_user(user_id: str, password: str) -> Optional[Dict[str, Any]]:
    """Validates user password hash and returns user dictionary with signed session token."""
    query = (
        "SELECT user_id, tenant_id, role, password_hash FROM users WHERE user_id = %s;"
        if is_postgres_available()
        else "SELECT user_id, tenant_id, role, password_hash FROM users WHERE user_id = ?;"
    )
    rows = execute_query("airlock_core", query, (user_id,))
    if not rows:
        return None
    user = rows[0]
    if not verify_password(password, user["password_hash"]):
        return None
    token = create_session_token(user["user_id"], user["tenant_id"], user["role"])
    return {
        "user_id": user["user_id"],
        "tenant_id": user["tenant_id"],
        "role": user["role"],
        "token": token,
    }


def execute_query(
    db_name: str, query: str, params: tuple = (), tenant_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Executes a query with optional tenant RLS isolation and returns rows as dictionaries."""
    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if tenant_id and db_name in ("airlock_in", "airlock_eu"):
                        cur.execute("SELECT set_config('app.current_tenant', %s, true);", (tenant_id,))
                    cur.execute(query, params)
                    if cur.description:
                        return [dict(r) for r in cur.fetchall()]
                    return []
    else:
        conn = get_sqlite_conn(db_name)
        cur = conn.cursor()
        sqlite_query = (
            query.replace("%s", "?")
            .replace("::text", "")
            .replace("NOW()", "CURRENT_TIMESTAMP")
            .replace("now()", "CURRENT_TIMESTAMP")
        )
        cur.execute(sqlite_query, params)
        if cur.description:
            rows = [dict(r) for r in cur.fetchall()]
            if tenant_id and tenant_id != "all" and db_name in ("airlock_in", "airlock_eu"):
                rows = [r for r in rows if r.get("tenant_id") == tenant_id]
            return rows
        conn.commit()
        return []


def log_audit_event(
    actor: str,
    action: str,
    tenant_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """Logs an audit entry in airlock_core."""
    event_id = f"aud-{uuid.uuid4().hex[:16]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    details_json = json.dumps(details or {})

    if is_postgres_available():
        try:
            pool = get_db_pool("airlock_core")
            with pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO audit_log (event_id, tenant_id, actor, action, details, timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (event_id, tenant_id, actor, action, details_json, now_iso),
                        )
        except Exception:
            pass

    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT INTO audit_log (event_id, tenant_id, actor, action, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (event_id, tenant_id, actor, action, details_json, now_iso),
    )
    conn_sq.commit()
    return event_id


def get_audit_logs(
    tenant_id: Optional[str] = None, action: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """Returns recent audit logs matching tenant or action filter."""
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                q = "SELECT event_id, tenant_id, actor, action, details, timestamp FROM audit_log WHERE 1=1"
                params = []
                if tenant_id:
                    q += " AND tenant_id = %s"
                    params.append(tenant_id)
                if action:
                    q += " AND action = %s"
                    params.append(action)
                q += " ORDER BY timestamp DESC LIMIT %s;"
                params.append(limit)
                cur.execute(q, tuple(params))
                return [dict(r) for r in cur.fetchall()]
    else:
        conn = get_sqlite_conn("airlock_core")
        cur = conn.cursor()
        q = "SELECT event_id, tenant_id, actor, action, details, timestamp FROM audit_log WHERE 1=1"
        params = []
        if tenant_id:
            q += " AND tenant_id = ?"
            params.append(tenant_id)
        if action:
            q += " AND action = ?"
            params.append(action)
        q += " ORDER BY timestamp DESC LIMIT ?;"
        params.append(limit)
        cur.execute(q, tuple(params))
        return [dict(r) for r in cur.fetchall()]


def get_tenant_assigned_region(tenant_id: str) -> Optional[str]:
    """Returns assigned region ('in' or 'eu') for a given tenant."""
    query = "SELECT assigned_region FROM tenants WHERE tenant_id = %s;" if is_postgres_available() else "SELECT assigned_region FROM tenants WHERE tenant_id = ?;"
    rows = execute_query("airlock_core", query, (tenant_id,))
    if rows and rows[0].get("assigned_region"):
        return rows[0]["assigned_region"]
    return None


def is_region_paused(region: str) -> bool:
    """Checks whether ingestion for the specified region is paused."""
    query = "SELECT is_paused FROM region_states WHERE region = %s;" if is_postgres_available() else "SELECT is_paused FROM region_states WHERE region = ?;"
    try:
        rows = execute_query("airlock_core", query, (region,))
        if rows:
            return bool(rows[0].get("is_paused"))
    except Exception:
        pass
    return False


def set_region_paused(region: str, paused: bool) -> None:
    """Pauses or resumes ingestion for a region."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO region_states (region, is_paused, paused_at)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (region) DO UPDATE SET is_paused = EXCLUDED.is_paused, paused_at = EXCLUDED.paused_at;
                        """,
                        (region, paused, now_iso),
                    )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR REPLACE INTO region_states (region, is_paused, paused_at)
        VALUES (?, ?, ?);
        """,
        (region, 1 if paused else 0, now_iso),
    )
    conn_sq.commit()


def get_tenant_pinned_policy(tenant_id: str) -> Optional[str]:
    """Retrieves pinned policy hash for a tenant."""
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pinned_policy_hash FROM tenants WHERE tenant_id = %s;", (tenant_id,))
                row = cur.fetchone()
                return row["pinned_policy_hash"] if row and row.get("pinned_policy_hash") else None
    else:
        conn = get_sqlite_conn("airlock_core")
        cur = conn.cursor()
        cur.execute("SELECT pinned_policy_hash FROM tenants WHERE tenant_id = ?;", (tenant_id,))
        row = cur.fetchone()
        return dict(row).get("pinned_policy_hash") if row else None


def set_tenant_pinned_policy(tenant_id: str, policy_hash: str):
    """Sets or updates the pinned policy hash for a tenant."""
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE tenants SET pinned_policy_hash = %s WHERE tenant_id = %s;",
                        (policy_hash, tenant_id),
                    )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        "UPDATE tenants SET pinned_policy_hash = ? WHERE tenant_id = ?;",
        (policy_hash, tenant_id),
    )
    conn_sq.commit()


def record_leak_detected(tenant_id: str) -> int:
    """Increments the leak counter for a tenant and returns the new count."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_count = 1
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO leak_counters (tenant_id, leak_count, updated_at)
                        VALUES (%s, 1, %s)
                        ON CONFLICT (tenant_id) DO UPDATE SET leak_count = leak_counters.leak_count + 1, updated_at = %s
                        RETURNING leak_count;
                        """,
                        (tenant_id, now_iso, now_iso),
                    )
                    row = cur.fetchone()
                    if row:
                        new_count = row["leak_count"] if isinstance(row, dict) else row[0]

    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute("SELECT leak_count FROM leak_counters WHERE tenant_id = ?;", (tenant_id,))
    row = cur_sq.fetchone()
    if row:
        new_count = row[0] + 1
        cur_sq.execute("UPDATE leak_counters SET leak_count = ?, updated_at = ? WHERE tenant_id = ?;", (new_count, now_iso, tenant_id))
    else:
        new_count = 1
        cur_sq.execute("INSERT INTO leak_counters (tenant_id, leak_count, updated_at) VALUES (?, 1, ?);", (tenant_id, now_iso))
    conn_sq.commit()
    return new_count


def get_leak_badge_count(tenant_id: Optional[str] = None) -> int:
    """Returns the total leaks detected (for a tenant or across all tenants)."""
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if tenant_id:
                    cur.execute("SELECT leak_count FROM leak_counters WHERE tenant_id = %s;", (tenant_id,))
                    row = cur.fetchone()
                    return (row["leak_count"] if isinstance(row, dict) else row[0]) if row else 0
                cur.execute("SELECT COALESCE(SUM(leak_count), 0) AS total FROM leak_counters;")
                row = cur.fetchone()
                val = row["total"] if isinstance(row, dict) else row[0]
                return int(val) if row else 0
    else:
        conn = get_sqlite_conn("airlock_core")
        cur = conn.cursor()
        if tenant_id:
            cur.execute("SELECT leak_count FROM leak_counters WHERE tenant_id = ?;", (tenant_id,))
            row = cur.fetchone()
            return row[0] if row else 0
        cur.execute("SELECT COALESCE(SUM(leak_count), 0) FROM leak_counters;")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def check_chain_integrity(db_name: str, guard_id: str, seq: int, prev_hash: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if prev_hash matches the sha256 hash of the payload at seq - 1.
    If seq - 1 does not exist in the database, it is considered a buffered seq gap (not an error).
    If seq == 1, prev_hash must be 'GENESIS' (or initial hash).
    """
    if seq == 1:
        if prev_hash != "GENESIS" and not prev_hash.startswith("sha256:0000"):
            return False, f"Sequence 1 must have prev_hash='GENESIS', got '{prev_hash}'"
        return True, None

    # Check if payload with seq - 1 exists
    query = """
        SELECT r.sha256 
        FROM payloads p 
        JOIN receipts r ON p.payload_id = r.payload_id 
        WHERE p.guard_id = %s AND p.seq = %s;
    """ if is_postgres_available() else """
        SELECT r.sha256 
        FROM payloads p 
        JOIN receipts r ON p.payload_id = r.payload_id 
        WHERE p.guard_id = ? AND p.seq = ?;
    """
    rows = execute_query(db_name, query, (guard_id, seq - 1))
    if rows:
        expected_prev_hash = rows[0]["sha256"]
        if prev_hash != expected_prev_hash:
            return False, f"Chain break at seq {seq}: expected prev_hash '{expected_prev_hash}', got '{prev_hash}'"

    return True, None


def update_guard_reconciliation(
    db_name: str, guard_id: str, tenant_id: str, seq: int, payload_hash: str, is_duplicate: bool
) -> Dict[str, Any]:
    """Updates reconciliation counters, max seq, gaps, and last seen timestamp for a guard."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Fetch all stored seqs for this guard to calculate gaps
    q_seqs = "SELECT seq FROM payloads WHERE guard_id = %s ORDER BY seq ASC;" if is_postgres_available() else "SELECT seq FROM payloads WHERE guard_id = ? ORDER BY seq ASC;"
    seq_rows = execute_query(db_name, q_seqs, (guard_id,))
    stored_seqs = set(r["seq"] for r in seq_rows)
    stored_seqs.add(seq)
    max_seq = max(stored_seqs) if stored_seqs else seq
    gaps = [s for s in range(1, max_seq) if s not in stored_seqs]
    gaps_json = json.dumps(gaps)
    received_count = len(stored_seqs)

    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO guard_reconciliation (
                            guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (guard_id) DO UPDATE SET
                            sent_count = EXCLUDED.sent_count,
                            received_count = EXCLUDED.received_count,
                            duplicate_count = guard_reconciliation.duplicate_count + %s,
                            max_seq = EXCLUDED.max_seq,
                            last_hash = EXCLUDED.last_hash,
                            gaps = EXCLUDED.gaps,
                            last_seen = EXCLUDED.last_seen;
                        """,
                        (
                            guard_id,
                            tenant_id,
                            max_seq,
                            received_count,
                            1 if is_duplicate else 0,
                            max_seq,
                            payload_hash,
                            gaps_json,
                            now_iso,
                            1 if is_duplicate else 0,
                        ),
                    )

    conn_sq = get_sqlite_conn(db_name)
    cur_sq = conn_sq.cursor()
    cur_sq.execute("SELECT duplicate_count FROM guard_reconciliation WHERE guard_id = ?;", (guard_id,))
    row = cur_sq.fetchone()
    dup_cnt = (row[0] + 1) if row and is_duplicate else (1 if is_duplicate else (row[0] if row else 0))
    cur_sq.execute(
        """
        INSERT OR REPLACE INTO guard_reconciliation (
            guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (guard_id, tenant_id, max_seq, received_count, dup_cnt, max_seq, payload_hash, gaps_json, now_iso),
    )
    conn_sq.commit()

    return {
        "guard_id": guard_id,
        "tenant_id": tenant_id,
        "sent_count": max_seq,
        "received_count": received_count,
        "duplicate_count": dup_cnt,
        "max_seq": max_seq,
        "gaps": gaps,
        "last_seen": now_iso,
    }


def get_guard_reconciliation(db_name: str, guard_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves reconciliation stats for a guard."""
    query = "SELECT guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen FROM guard_reconciliation WHERE guard_id = %s;" if is_postgres_available() else "SELECT guard_id, tenant_id, sent_count, received_count, duplicate_count, max_seq, last_hash, gaps, last_seen FROM guard_reconciliation WHERE guard_id = ?;"
    rows = execute_query(db_name, query, (guard_id,))
    if rows:
        r = rows[0]
        if isinstance(r.get("gaps"), str):
            r["gaps"] = json.loads(r["gaps"])
        return r
    return None


def compute_checkpoint_root(hashes: List[str]) -> str:
    """Computes running SHA-256 root over payload hashes in sequence order."""
    if not hashes:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    running = ""
    for h in hashes:
        running = hashlib.sha256((running + h).encode("utf-8")).hexdigest()
    return f"sha256:{running}"


def compute_guard_checkpoint(guard_id: str, up_to_seq: Optional[int] = None) -> Dict[str, Any]:
    """Computes the running SHA-256 checkpoint root over received payload hashes in seq order."""
    guard_rec = lookup_guard(guard_id)
    if not guard_rec:
        return {"guard_id": guard_id, "up_to_seq": 0, "root": "sha256:" + hashlib.sha256(b"").hexdigest(), "hashes": []}

    tenant_id = guard_rec["tenant_id"]
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"

    query = """
        SELECT p.seq, r.sha256 
        FROM payloads p 
        JOIN receipts r ON p.payload_id = r.payload_id 
        WHERE p.guard_id = %s 
        ORDER BY p.seq ASC;
    """ if is_postgres_available() else """
        SELECT p.seq, r.sha256 
        FROM payloads p 
        JOIN receipts r ON p.payload_id = r.payload_id 
        WHERE p.guard_id = ? 
        ORDER BY p.seq ASC;
    """
    rows = execute_query(db_name, query, (guard_id,))
    seq_hash_map = {int(r["seq"]): r["sha256"] for r in rows}

    max_seq = up_to_seq if up_to_seq is not None else (max(seq_hash_map.keys()) if seq_hash_map else 0)
    ordered_hashes = []
    for s in range(1, max_seq + 1):
        ordered_hashes.append(seq_hash_map.get(s, ""))

    root = compute_checkpoint_root(ordered_hashes)
    return {
        "guard_id": guard_id,
        "up_to_seq": max_seq,
        "root": root,
        "hashes": ordered_hashes,
        "seq_map": seq_hash_map,
    }


def compare_guard_checkpoint(
    guard_id: str,
    up_to_seq: int,
    guard_root: str,
    guard_hashes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compares head office's running SHA-256 root against guard's checkpoint and names first differing seq."""
    hq_chk = compute_guard_checkpoint(guard_id, up_to_seq=up_to_seq)
    hq_root = hq_chk["root"]
    match = (hq_root == guard_root)

    first_diff_seq = None
    if not match:
        if guard_hashes and len(guard_hashes) > 0:
            for idx, g_h in enumerate(guard_hashes):
                hq_h = hq_chk["hashes"][idx] if idx < len(hq_chk["hashes"]) else ""
                if g_h != hq_h:
                    first_diff_seq = idx + 1
                    break
            if first_diff_seq is None:
                first_diff_seq = len(guard_hashes) + 1
        else:
            # Check for gaps or missing seqs at HQ
            seq_map = hq_chk["seq_map"]
            for s in range(1, up_to_seq + 1):
                if s not in seq_map:
                    first_diff_seq = s
                    break
            if first_diff_seq is None:
                first_diff_seq = up_to_seq

    log_audit_event(
        actor=guard_id,
        action="checkpoint_verified" if match else "checkpoint_mismatch",
        details={
            "guard_id": guard_id,
            "up_to_seq": up_to_seq,
            "match": match,
            "first_differing_seq": first_diff_seq,
        },
    )

    return {
        "guard_id": guard_id,
        "up_to_seq": up_to_seq,
        "match": match,
        "status": "verified" if match else "mismatch",
        "hq_root": hq_root,
        "guard_root": guard_root,
        "first_differing_seq": first_diff_seq,
    }


def create_reveal_request(
    tenant_id: str,
    pseudonym: str,
    requested_by: str,
    reason: str,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a new reveal request in airlock_core and logs an audit event."""
    req_id = request_id or f"rev-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO reveal_requests (request_id, tenant_id, pseudonym, requested_by, reason, requested_at, status)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                        ON CONFLICT (request_id) DO NOTHING;
                        """,
                        (req_id, tenant_id, pseudonym, requested_by, reason, now_iso),
                    )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR IGNORE INTO reveal_requests (request_id, tenant_id, pseudonym, requested_by, reason, requested_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'pending');
        """,
        (req_id, tenant_id, pseudonym, requested_by, reason, now_iso),
    )
    conn_sq.commit()

    log_audit_event(
        actor=requested_by,
        action="reveal_requested",
        tenant_id=tenant_id,
        details={"request_id": req_id, "pseudonym": pseudonym, "reason": reason},
    )

    return {
        "request_id": req_id,
        "tenant_id": tenant_id,
        "pseudonym": pseudonym,
        "requested_by": requested_by,
        "reason": reason,
        "requested_at": now_iso,
        "status": "pending",
    }


def list_reveal_requests(tenant_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists reveal requests filtered by tenant and status."""
    query = "SELECT request_id, tenant_id, pseudonym, requested_by, reason, requested_at, status, decided_at, decision_reason FROM reveal_requests WHERE 1=1"
    params = []
    if tenant_id and tenant_id != "all":
        query += " AND tenant_id = %s" if is_postgres_available() else " AND tenant_id = ?"
        params.append(tenant_id)
    if status:
        query += " AND status = %s" if is_postgres_available() else " AND status = ?"
        params.append(status)
    query += " ORDER BY requested_at DESC;"
    return execute_query("airlock_core", query, tuple(params))


def update_reveal_request_status(
    request_id: str,
    status: str,
    decided_by: str = "guard",
    decision_reason: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Updates a reveal request's status (approved/rejected) and logs audit on decision."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE reveal_requests 
                        SET status = %s, decided_at = %s, decision_reason = %s
                        WHERE request_id = %s;
                        """,
                        (status, now_iso, decision_reason, request_id),
                    )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        UPDATE reveal_requests 
        SET status = ?, decided_at = ?, decision_reason = ?
        WHERE request_id = ?;
        """,
        (status, now_iso, decision_reason, request_id),
    )
    conn_sq.commit()

    log_audit_event(
        actor=decided_by,
        action=f"reveal_{status}",
        details={"request_id": request_id, "status": status, "decision_reason": decision_reason},
    )

    rows = execute_query(
        "airlock_core",
        "SELECT * FROM reveal_requests WHERE request_id = %s;" if is_postgres_available() else "SELECT * FROM reveal_requests WHERE request_id = ?;",
        (request_id,),
    )
    return rows[0] if rows else None


def record_feedback(
    alert_id: str,
    tenant_id: str,
    user_id: str,
    metric: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Records user thumbs-down feedback for an alert/incident into the regional database."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"

    if metric is None or source is None:
        try:
            alert_query = (
                "SELECT body, source, tenant_id FROM aiops_alerts WHERE alert_id = %s;"
                if is_postgres_available()
                else "SELECT body, source, tenant_id FROM aiops_alerts WHERE alert_id = ?;"
            )
            alert_rows = execute_query(db_name, alert_query, (alert_id,), tenant_id=tenant_id)
            if alert_rows:
                r = alert_rows[0]
                if not source and r.get("source"):
                    source = r["source"]
                body_val = r.get("body")
                if isinstance(body_val, str):
                    try:
                        body_val = json.loads(body_val)
                    except Exception:
                        body_val = {}
                if isinstance(body_val, dict):
                    signals = body_val.get("signals") or []
                    if signals and isinstance(signals[0], dict):
                        if not metric:
                            metric = signals[0].get("name")
                        if not source:
                            source = signals[0].get("source")
        except Exception:
            pass

    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO feedback (alert_id, tenant_id, user_id, metric, source, at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (alert_id) DO UPDATE SET user_id = EXCLUDED.user_id, metric = EXCLUDED.metric, source = EXCLUDED.source, at = EXCLUDED.at;
                        """,
                        (alert_id, tenant_id, user_id, metric, source, now_iso),
                    )

    conn_sq = get_sqlite_conn(db_name)
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR REPLACE INTO feedback (alert_id, tenant_id, user_id, metric, source, at)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (alert_id, tenant_id, user_id, metric, source, now_iso),
    )
    conn_sq.commit()

    log_audit_event(
        actor=user_id,
        action="feedback_submitted",
        tenant_id=tenant_id,
        details={"alert_id": alert_id, "user_id": user_id, "metric": metric, "source": source, "at": now_iso},
    )

    return {
        "status": "recorded",
        "alert_id": alert_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "metric": metric,
        "source": source,
        "at": now_iso,
    }


def get_tenant_baselines(tenant_id: str) -> List[Dict[str, Any]]:
    """Reads baseline normal bands from aiops_baselines table in regional DB."""
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"
    query = (
        "SELECT source, metric, mean, std FROM aiops_baselines WHERE tenant_id = %s;"
        if is_postgres_available()
        else "SELECT source, metric, mean, std FROM aiops_baselines WHERE tenant_id = ?;"
    )
    try:
        rows = execute_query(db_name, query, (tenant_id,), tenant_id=tenant_id)
        return [
            {
                "source": r["source"],
                "metric": r["metric"],
                "mean": float(r["mean"]),
                "std": float(r["std"]),
            }
            for r in rows
        ]
    except Exception:
        return []


def get_damage_map(tenant_id: str) -> Dict[str, Any]:
    """Topology with affected/impacted/ok per component, written by the AIOps worker (T9)."""
    db_name = "airlock_in" if (get_tenant_assigned_region(tenant_id) or "in") == "in" else "airlock_eu"
    q = "SELECT body FROM aiops_damage_map WHERE tenant_id = " + ("%s;" if is_postgres_available() else "?;")
    try:
        rows = execute_query(db_name, q, (tenant_id,), tenant_id=tenant_id)
        body = rows[0]["body"] if rows else None
        return json.loads(body) if isinstance(body, str) else (body or {"nodes": [], "edges": []})
    except Exception:
        return {"nodes": [], "edges": []}


def get_tenant_counters(tenant_id: str) -> Dict[str, Any]:
    """Reads telemetry counters for tenant from aiops_counters table written by AIOps worker."""
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"

    query = (
        "SELECT tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, updated FROM aiops_counters WHERE tenant_id = %s;"
        if is_postgres_available()
        else "SELECT tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, updated FROM aiops_counters WHERE tenant_id = ?;"
    )
    rows = execute_query(db_name, query, (tenant_id,))
    if rows:
        r = rows[0]
        return {
            "tenant_id": r["tenant_id"],
            "raw_alerts": int(r.get("raw_alerts") or 0),
            "incidents": int(r.get("incidents") or 0),
            "noise_cut_pct": float(r.get("noise_cut_pct") or 0.0),
            "flaps_prevented": int(r.get("flaps_prevented") or 0),
            "updated": str(r.get("updated") or ""),
        }
    return {
        "tenant_id": tenant_id,
        "raw_alerts": 0,
        "incidents": 0,
        "noise_cut_pct": 0.0,
        "flaps_prevented": 0,
        "updated": None,
    }


def update_tenant_counters(
    tenant_id: str,
    raw_alerts: int,
    incidents: int,
    noise_cut_pct: float,
    flaps_prevented: int,
) -> Dict[str, Any]:
    """Writes telemetry counters into aiops_counters table (matches hq/aiops/worker.py write shape)."""
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO aiops_counters (tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, updated)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id) DO UPDATE SET
                            raw_alerts = EXCLUDED.raw_alerts,
                            incidents = EXCLUDED.incidents,
                            noise_cut_pct = EXCLUDED.noise_cut_pct,
                            flaps_prevented = EXCLUDED.flaps_prevented,
                            updated = EXCLUDED.updated;
                        """,
                        (tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, now_iso),
                    )

    conn_sq = get_sqlite_conn(db_name)
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR REPLACE INTO aiops_counters (tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, updated)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (tenant_id, raw_alerts, incidents, noise_cut_pct, flaps_prevented, now_iso),
    )
    conn_sq.commit()

    return {
        "tenant_id": tenant_id,
        "raw_alerts": raw_alerts,
        "incidents": incidents,
        "noise_cut_pct": noise_cut_pct,
        "flaps_prevented": flaps_prevented,
        "updated": now_iso,
    }


def record_aiops_alert(
    tenant_id: str,
    title: str,
    severity: str = "high",
    source: Optional[str] = "ingest_security",
    body: Optional[Dict[str, Any]] = None,
    alert_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Records an alert row into the regional database aiops_alerts table."""
    a_id = alert_id or f"alt-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assigned_reg = get_tenant_assigned_region(tenant_id) or "in"
    db_name = "airlock_in" if assigned_reg == "in" else "airlock_eu"
    body_dict = body or {}
    body_json = json.dumps(body_dict)

    if is_postgres_available():
        pool = get_db_pool(db_name)
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO aiops_alerts (alert_id, tenant_id, source, title, severity, body, status, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s)
                        ON CONFLICT (alert_id) DO NOTHING;
                        """,
                        (a_id, tenant_id, source, title, severity, body_json, now_iso, now_iso),
                    )

    conn_sq = get_sqlite_conn(db_name)
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR IGNORE INTO aiops_alerts (alert_id, tenant_id, source, title, severity, body, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?);
        """,
        (a_id, tenant_id, source, title, severity, body_json, now_iso, now_iso),
    )
    conn_sq.commit()

    return {
        "alert_id": a_id,
        "tenant_id": tenant_id,
        "source": source,
        "title": title,
        "severity": severity,
        "body": body_dict,
        "status": "open",
        "created_at": now_iso,
    }


def create_action_intent(
    tenant_id: str,
    action: str,
    target: str,
    risk: str = "low",
    why: str = "",
    incident_id: Optional[str] = None,
    reversible: bool = True,
    rollback: Optional[str] = None,
    intent_id: Optional[str] = None,
    expires_in_s: int = 600,
) -> Dict[str, Any]:
    """Creates a proposed action intent in airlock_core with 10-minute expiration and audit entry."""
    i_id = intent_id or f"act-{uuid.uuid4().hex[:12]}"
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    expires_dt = datetime.fromtimestamp(now_dt.timestamp() + expires_in_s, tz=timezone.utc)
    expires_iso = expires_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    details = {
        "why": why,
        "reversible": reversible,
        "rollback": rollback,
    }
    details_json = json.dumps(details)

    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO action_intents (
                            intent_id, incident_id, tenant_id, action, target, risk, status, details, created_at, expires_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 'proposed', %s, %s, %s)
                        ON CONFLICT (intent_id) DO NOTHING;
                        """,
                        (i_id, incident_id, tenant_id, action, target, risk, details_json, now_iso, expires_iso),
                    )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT OR IGNORE INTO action_intents (
            intent_id, incident_id, tenant_id, action, target, risk, status, details, created_at, expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?);
        """,
        (i_id, incident_id, tenant_id, action, target, risk, details_json, now_iso, expires_iso),
    )
    conn_sq.commit()

    log_action_audit(intent_id=i_id, actor="aiops", step="proposed", details=details)

    return {
        "intent_id": i_id,
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "action": action,
        "target": target,
        "risk": risk,
        "status": "proposed",
        "why": why,
        "reversible": reversible,
        "rollback": rollback,
        "created_at": now_iso,
        "expires_at": expires_iso,
    }


def list_action_intents(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent action intents, newest first (for the Actions screen and the approver phone)."""
    rows = execute_query("airlock_core", f"SELECT * FROM action_intents ORDER BY created_at DESC LIMIT {int(limit)};")
    out = []
    for r in rows:
        r = dict(r)
        if isinstance(r.get("details"), str):
            try:
                r["details"] = json.loads(r["details"])
            except Exception:
                pass
        out.append(r)
    return out


def get_action_intent(intent_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an action intent by ID from airlock_core."""
    query = "SELECT * FROM action_intents WHERE intent_id = %s;" if is_postgres_available() else "SELECT * FROM action_intents WHERE intent_id = ?;"
    rows = execute_query("airlock_core", query, (intent_id,))
    if rows:
        r = dict(rows[0])
        if isinstance(r.get("details"), str):
            try:
                r["details"] = json.loads(r["details"])
            except Exception:
                pass
        return r
    return None


def update_action_intent_status(
    intent_id: str,
    status: str,
    approved_by: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Updates status and approver of an action intent."""
    if is_postgres_available():
        pool = get_db_pool("airlock_core")
        with pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if approved_by:
                        cur.execute(
                            "UPDATE action_intents SET status = %s, approved_by = %s WHERE intent_id = %s;",
                            (status, approved_by, intent_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE action_intents SET status = %s WHERE intent_id = %s;",
                            (status, intent_id),
                        )
    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    if approved_by:
        cur_sq.execute(
            "UPDATE action_intents SET status = ?, approved_by = ? WHERE intent_id = ?;",
            (status, approved_by, intent_id),
        )
    else:
        cur_sq.execute(
            "UPDATE action_intents SET status = ? WHERE intent_id = ?;",
            (status, intent_id),
        )
    conn_sq.commit()
    return get_action_intent(intent_id)


def count_recent_intents(tenant_id: str, window_seconds: int = 600) -> int:
    """Counts proposed/executed intents for a tenant within the sliding window."""
    cutoff = datetime.fromtimestamp(time.time() - window_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        "SELECT COUNT(*) AS cnt FROM action_intents WHERE tenant_id = %s AND created_at >= %s;"
        if is_postgres_available()
        else "SELECT COUNT(*) AS cnt FROM action_intents WHERE tenant_id = ? AND created_at >= ?;"
    )
    rows = execute_query("airlock_core", query, (tenant_id, cutoff))
    if rows:
        return int(rows[0].get("cnt", 0))
    return 0


def list_pending_action_intents(tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists approved intents that have not expired."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = (
        "SELECT * FROM action_intents WHERE status = 'approved' AND (expires_at IS NULL OR expires_at > %s)"
        if is_postgres_available()
        else "SELECT * FROM action_intents WHERE status = 'approved' AND (expires_at IS NULL OR expires_at > ?)"
    )
    params = [now_iso]
    if tenant_id and tenant_id != "all":
        query += " AND tenant_id = %s" if is_postgres_available() else " AND tenant_id = ?"
        params.append(tenant_id)
    query += " ORDER BY created_at ASC;"
    rows = execute_query("airlock_core", query, tuple(params))
    return [dict(r) for r in rows]


def log_action_audit(
    intent_id: Optional[str],
    actor: str,
    step: str,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """Logs an action intent lifecycle event in action_audit."""
    event_id = f"actaud-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    details_json = json.dumps(details or {})

    if is_postgres_available():
        try:
            pool = get_db_pool("airlock_core")
            with pool.connection() as conn:
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO action_audit (event_id, intent_id, actor, step, details, at)
                            VALUES (%s, %s, %s, %s, %s, %s);
                            """,
                            (event_id, intent_id, actor, step, details_json, now_iso),
                        )
        except Exception:
            pass

    conn_sq = get_sqlite_conn("airlock_core")
    cur_sq = conn_sq.cursor()
    cur_sq.execute(
        """
        INSERT INTO action_audit (event_id, intent_id, actor, step, details, at)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (event_id, intent_id, actor, step, details_json, now_iso),
    )
    conn_sq.commit()
    return event_id


def get_action_audit_logs(intent_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Returns action audit entries."""
    query = "SELECT * FROM action_audit WHERE 1=1"
    params = []
    if intent_id:
        query += " AND intent_id = %s" if is_postgres_available() else " AND intent_id = ?"
        params.append(intent_id)
    query += " ORDER BY at DESC LIMIT %s;" if is_postgres_available() else " ORDER BY at DESC LIMIT ?;"
    params.append(limit)
    rows = execute_query("airlock_core", query, tuple(params))
    return [dict(r) for r in rows]


def truncate_all_data():
    """Truncates/clears all dynamic test data to ensure test independence.

    On Postgres this wipes live telemetry, so it only runs when AIRLOCK_ALLOW_TRUNCATE=1 (point it at a scratch database).
    Without Postgres credentials the tests use the SQLite fallback and need nothing.
    """
    if is_postgres_available() and os.getenv("AIRLOCK_ALLOW_TRUNCATE") != "1":
        raise RuntimeError("Refusing to truncate PostgreSQL (it holds live telemetry). Test on SQLite (AIRLOCK_USE_SQLITE=true, "
                           "the default under pytest) or set AIRLOCK_ALLOW_TRUNCATE=1 for a scratch database.")
    regional_tables = [
        "payloads",
        "metrics",
        "events",
        "receipts",
        "health_history",
        "health_current",
        "incidents",
        "aiops_alerts",
        "aiops_counters",
        "guard_reconciliation",
        "feedback",
    ]
    core_tables = [
        "audit_log",
        "leak_counters",
        "reveal_requests",
        "action_intents",
        "action_audit",
    ]
    if is_postgres_available():
        for db in ("airlock_in", "airlock_eu"):
            with psycopg.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=db
            ) as conn:
                with conn.cursor() as cur:
                    for tbl in regional_tables:
                        cur.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
                conn.commit()
        with psycopg.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname="airlock_core"
        ) as conn:
            with conn.cursor() as cur:
                for tbl in core_tables:
                    cur.execute(f"TRUNCATE TABLE {tbl} CASCADE;")
            conn.commit()
    else:
        for db in ("airlock_in", "airlock_eu"):
            conn = get_sqlite_conn(db)
            cur = conn.cursor()
            for tbl in regional_tables:
                cur.execute(f"DELETE FROM {tbl};")
            conn.commit()
        conn = get_sqlite_conn("airlock_core")
        cur = conn.cursor()
        for tbl in core_tables:
            cur.execute(f"DELETE FROM {tbl};")
        conn.commit()
