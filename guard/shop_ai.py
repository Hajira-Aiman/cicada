"""
guard/shop_ai.py
Shop AI Assistant running locally on Ryzen AI NPU via Lemonade Server (port 13305).
Reachable only on this machine.
Exposes tools over local SQLite raw data:
- search_raw_logs(query, minutes)
- recent_auth_failures(minutes)
Never exposes raw logs outside the customer environment.
"""

import json
import time
import re
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import httpx
from guard.config import config


class ShopAIAssistant:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:13305/v1",
        model_name: Optional[str] = None,
        raw_db_path: str = "data/raw.db",
        guard_db_path: str = "data/guard.db",
    ):
        self.base_url = base_url.rstrip("/")
        if model_name is None:
            import os
            model_name = os.getenv("LEMONADE_MODEL")
            if not model_name:
                try:
                    with httpx.Client(timeout=2.0) as client:
                        r = client.get(f"{self.base_url}/models")
                        if r.status_code == 200:
                            data = r.json().get("data", [])
                            # Prioritize Qwen2.5-3B-Instruct-NPU as requested by user
                            for m in data:
                                m_id = m.get("id", "")
                                if "3B" in m_id or "3b" in m_id:
                                    model_name = m_id
                                    break
                            if not model_name and data:
                                model_name = data[0].get("id")
                except Exception:
                    pass
            if not model_name:
                model_name = "Qwen2.5-3B-Instruct-NPU"
        self.model_name = model_name
        self.raw_db_path = raw_db_path
        self.guard_db_path = guard_db_path

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_raw_logs",
                    "description": "Searches local raw un-redacted logs from the demo shop application for a given query string within the last N minutes. Returns log records including numeric id, timestamp, source, and raw_text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Keyword or pattern to search for in local raw logs (e.g., error, password, secret, checkout, tripwire, canary, access_key).",
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "Lookback window in minutes (default 60).",
                                "default": 60,
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "recent_auth_failures",
                    "description": "Returns recent failed login attempts including raw usernames, source IPs, log id, and timestamps within the last N minutes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes": {
                                "type": "integer",
                                "description": "Lookback window in minutes (default 60).",
                                "default": 60,
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_guard_status",
                    "description": "Returns current local guard buffer depth and outbox queue status from local guard ledger.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recent_egress",
                    "description": "Returns the most recent egress payloads sent to head office, including sequence number, payload ID, SHA-256 hash, and receipt status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of recent payloads to return (default 5).",
                                "default": 5,
                            }
                        },
                    },
                },
            },
        ]

    def search_raw_logs(self, query: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Queries local SQLite raw.db for log lines matching query or relevant keywords."""
        cutoff_epoch = time.time() - (minutes * 60)
        try:
            with sqlite3.connect(self.raw_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(raw_logs)")
                cols = {row["name"] for row in cursor.fetchall()}
                if "raw_text" in cols:
                    # 1. Exact substring match
                    cursor.execute(
                        "SELECT id, timestamp, source, raw_text FROM raw_logs WHERE timestamp >= ? AND (raw_text LIKE ? OR source LIKE ?) ORDER BY id DESC LIMIT 50",
                        (cutoff_epoch, f"%{query}%", f"%{query}%"),
                    )
                    rows = [dict(r) for r in cursor.fetchall()]
                    if rows:
                        return rows
                    
                    # 2. Keyword fallback for compound queries
                    keywords = [w for w in query.split() if len(w) > 2 and w.lower() not in ("the", "and", "for", "with", "any", "were")]
                    synonyms = []
                    q_lower = query.lower()
                    if any(w in q_lower for w in ["key", "credential", "tripwire", "canary", "secret"]):
                        synonyms.extend(["canary", "access_key", "credential", "tripwire"])
                    search_terms = keywords + synonyms
                    if search_terms:
                        clauses = " OR ".join(["raw_text LIKE ? OR source LIKE ?" for _ in search_terms])
                        params = [cutoff_epoch]
                        for term in search_terms:
                            params.extend([f"%{term}%", f"%{term}%"])
                        cursor.execute(
                            f"SELECT id, timestamp, source, raw_text FROM raw_logs WHERE timestamp >= ? AND ({clauses}) ORDER BY id DESC LIMIT 50",
                            params,
                        )
                        return [dict(r) for r in cursor.fetchall()]
                    return []
                else:
                    cursor.execute(
                        """
                        SELECT id, timestamp, level, source_ip, username, message
                        FROM raw_logs
                        WHERE timestamp >= ? AND message LIKE ?
                        ORDER BY id DESC LIMIT 50
                        """,
                        (cutoff_epoch, f"%{query}%"),
                    )
                    return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return [{"error": f"Failed to query local raw store: {e}"}]

    def recent_auth_failures(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """Queries local raw.db for failed login events."""
        cutoff_epoch = time.time() - (minutes * 60)
        try:
            with sqlite3.connect(self.raw_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(raw_logs)")
                cols = {row["name"] for row in cursor.fetchall()}
                if "raw_text" in cols:
                    cursor.execute(
                        """
                        SELECT id, timestamp, source, raw_text 
                        FROM raw_logs 
                        WHERE timestamp >= ? AND (raw_text LIKE '%login_failure%' OR raw_text LIKE '%Failed password%' OR raw_text LIKE '%invalid password%')
                        ORDER BY id DESC LIMIT 50
                        """,
                        (cutoff_epoch,),
                    )
                    rows = [dict(r) for r in cursor.fetchall()]
                    if not rows:
                        # Fallback to wider window if no recent failures in last N minutes
                        cursor.execute(
                            """
                            SELECT id, timestamp, source, raw_text 
                            FROM raw_logs 
                            WHERE raw_text LIKE '%login_failure%' OR raw_text LIKE '%Failed password%'
                            ORDER BY id DESC LIMIT 20
                            """
                        )
                        rows = [dict(r) for r in cursor.fetchall()]
                    return rows
                else:
                    cursor.execute(
                        """
                        SELECT timestamp, source_ip, username, message
                        FROM raw_logs
                        WHERE message LIKE '%login failed%' OR message LIKE '%invalid password%' OR level = 'WARNING'
                        ORDER BY id DESC LIMIT 50
                        """
                    )
                    return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return [{"error": f"Failed to query auth failures: {e}"}]

    def get_guard_status(self) -> Dict[str, Any]:
        """Queries local guard database for buffer depth and queue health."""
        try:
            with sqlite3.connect(self.guard_db_path) as conn:
                cursor = conn.cursor()
                buffer_depth = cursor.execute("SELECT count(1) FROM outbox").fetchone()[0]
                latest_seq = cursor.execute("SELECT max(seq) FROM ledger").fetchone()[0] or 0
                return {
                    "buffer_depth": buffer_depth,
                    "last_seq": latest_seq,
                    "status": "active" if buffer_depth == 0 else "buffering",
                }
        except Exception as e:
            return {"error": f"Failed to read guard status: {e}"}

    def get_recent_egress(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Queries local guard ledger for recent cryptographic egress records."""
        try:
            with sqlite3.connect(self.guard_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT seq, payload_id, sha256, status, receipt_at FROM ledger ORDER BY seq DESC LIMIT ?",
                    (limit,),
                )
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return [{"error": f"Failed to read egress ledger: {e}"}]

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "search_raw_logs":
            return self.search_raw_logs(
                query=args.get("query", ""),
                minutes=args.get("minutes", 60),
            )
        elif name == "recent_auth_failures":
            return self.recent_auth_failures(
                minutes=args.get("minutes", 60),
            )
        elif name == "get_guard_status":
            return self.get_guard_status()
        elif name == "get_recent_egress":
            return self.get_recent_egress(
                limit=args.get("limit", 5),
            )
        return {"error": f"Unknown tool: {name}"}

    def clean_log_text(self, raw_text: str) -> str:
        """Formats raw log line into clean, human-readable key-value summary for NPU context."""
        try:
            data = json.loads(raw_text)
            ev = data.get("event", "")
            user = data.get("username", "")
            ip = data.get("ip", "")
            msg = data.get("message", "")
            pwd = data.get("password", "")
            parts = []
            if ev:
                parts.append(f"event={ev}")
            if user:
                parts.append(f"user={user}")
            if pwd:
                parts.append(f"password={pwd}")
            if ip:
                parts.append(f"ip={ip}")
            if msg:
                parts.append(f"msg='{msg}'")
            return " ".join(parts) if parts else raw_text
        except Exception:
            return raw_text

    def clean_output(self, text: str) -> str:
        """Removes markdown bold asterisks, emojis, and bullet points from model output."""
        # 1. Strip markdown bold and italic asterisks
        text = text.replace("**", "").replace("*", "")
        # 2. Strip emojis and unicode symbols
        emoji_pattern = re.compile(
            r"[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f]",
            flags=re.UNICODE,
        )
        text = emoji_pattern.sub("", text)
        # 3. Strip leading bullet points
        lines = [re.sub(r"^[\s\-\*•\d\.]+\s*", "", line) for line in text.splitlines() if line.strip()]
        text = " ".join(lines)
        # 4. Collapse whitespace
        text = re.sub(r" +", " ", text).strip()
        return text

    def gather_context(self, user_prompt: str) -> Tuple[str, List[int], List[int], bool]:
        """
        Direct ground-truth context injection: queries local SQLite databases (data/raw.db and data/guard.db).
        Returns (evidence_text, matched_log_ids, matched_seq_ids, is_buffer_query).
        """
        p_lower = user_prompt.lower()
        lines = []
        matched_log_ids: List[int] = []
        matched_seq_ids: List[int] = []
        is_buffer_query = any(w in p_lower for w in ["buffer", "outbox", "queue", "depth", "countdown"])

        # 1. Local Guard Buffer & Outbox state
        st = self.get_guard_status()
        if is_buffer_query or any(w in p_lower for w in ["status", "health", "state"]):
            if "buffer_depth" in st:
                lines.append(
                    f"[Guard Status] Buffer Depth: {st['buffer_depth']} (status: {st['status']}), Last Egress Seq: {st.get('last_seq', 'N/A')}"
                )

        # 2. Egress ledger records
        if any(w in p_lower for w in ["egress", "payload", "hash", "sent", "cloud", "hq", "head office"]):
            egress = self.get_recent_egress(limit=3)
            for e in egress:
                matched_seq_ids.append(e["seq"])
                lines.append(
                    f"[Egress Receipt] Seq #{e['seq']}: sha256={e['sha256']} status={e['status']} receipt_at={e.get('receipt_at', 'pending')}"
                )

        # 3. Failed auth attempts
        if any(w in p_lower for w in ["auth", "login", "password", "fail", "attack", "error"]):
            failures = self.recent_auth_failures(minutes=60)
            if failures:
                lines.append("[Failed Auth Logs]")
                for f in failures[:5]:
                    matched_log_ids.append(f["id"])
                    clean = self.clean_log_text(f["raw_text"])
                    lines.append(f"Log #{f['id']}: {clean}")

        # 4. Tripwire & canary credential detections
        if any(w in p_lower for w in ["tripwire", "canary", "secret", "key", "credential", "cleartext", "leak"]):
            canaries = self.search_raw_logs(query="canary", minutes=60)
            if canaries:
                lines.append("[Tripwire & Canary Logs]")
                for c in canaries[:4]:
                    matched_log_ids.append(c["id"])
                    clean = self.clean_log_text(c["raw_text"])
                    lines.append(f"Log #{c['id']}: source={c['source']} {clean}")

        # 5. Generic log search fallback
        if not matched_log_ids and not matched_seq_ids and not is_buffer_query:
            words = [
                w for w in user_prompt.split()
                if len(w) > 3 and w.lower() not in ("what", "were", "this", "from", "with", "about", "show", "tell", "summarize", "anyone", "admin", "have", "there")
            ]
            if words:
                matches = self.search_raw_logs(query=" ".join(words[:2]), minutes=60)
                if matches:
                    lines.append("[Matching Local Logs]")
                    for m in matches[:4]:
                        matched_log_ids.append(m["id"])
                        clean = self.clean_log_text(m["raw_text"])
                        lines.append(f"Log #{m['id']}: {clean}")

        return "\n".join(lines), matched_log_ids, matched_seq_ids, is_buffer_query

    def chat(self, user_prompt: str) -> str:
        """
        Answers user prompt via direct context injection (RAG) on the Ryzen AI NPU.
        Avoids multi-turn tool loops, enforces strict ground-truth, and removes asterisks/emojis.
        """
        evidence_text, matched_log_ids, matched_seq_ids, is_buffer_query = self.gather_context(user_prompt)

        # Strict RAG: if no matching records found and not asking about buffer status
        if not matched_log_ids and not matched_seq_ids and not is_buffer_query:
            return "No matching records found in local logs."

        system_msg = (
            "You are the Airlock Local Guard AI assistant running on this device.\n"
            "Strict rules:\n"
            "1. Base your answer strictly on the provided local evidence.\n"
            "2. Answer the question in 1 or 2 concise, factual sentences.\n"
            "3. Never use markdown bold asterisks (**) or bullet points.\n"
            "4. Never use emojis.\n"
            "5. Do not invent any facts not present in the evidence."
        )
        user_msg = f"LOCAL EVIDENCE:\n{evidence_text}\n\nQUESTION: {user_prompt}"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.2,
            "max_tokens": 120,
        }

        try:
            with httpx.Client(timeout=45.0) as client:
                res = client.post(f"{self.base_url}/chat/completions", json=payload)
                res.raise_for_status()
                data = res.json()
                choice = data["choices"][0]["message"]
                reply = self.clean_output(choice.get("content", ""))

                # Ensure exact citations are included for UI spotlighting
                citations = []
                for lid in matched_log_ids[:3]:
                    if f"Log #{lid}" not in reply and str(lid) not in reply:
                        citations.append(f"Log #{lid}")
                for sid in matched_seq_ids[:2]:
                    if f"Seq #{sid}" not in reply and str(sid) not in reply:
                        citations.append(f"Seq #{sid}")
                if citations:
                    reply += " (Evidence: " + ", ".join(citations) + ")"

                return reply

        except Exception as e:
            return f"Shop AI (Lemonade NPU) connection error: {e}"
