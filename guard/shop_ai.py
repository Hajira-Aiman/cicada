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
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from guard.config import config


class ShopAIAssistant:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:13305/v1",
        model_name: str = "Qwen2.5-0.5B-Instruct-Hybrid",
        raw_db_path: str = "data/raw.db",
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.raw_db_path = raw_db_path

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_raw_logs",
                    "description": "Searches local raw un-redacted logs from the demo shop application for a given query string within the last N minutes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Keyword or pattern to search for in local raw logs (e.g., error, password, secret, checkout).",
                            },
                            "minutes": {
                                "type": "integer",
                                "description": "Lookback window in minutes (default 10).",
                                "default": 10,
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
                    "description": "Returns recent failed login attempts including raw usernames, source IPs, and timestamps within the last N minutes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes": {
                                "type": "integer",
                                "description": "Lookback window in minutes (default 10).",
                                "default": 10,
                            }
                        },
                    },
                },
            },
        ]

    def search_raw_logs(self, query: str, minutes: int = 10) -> List[Dict[str, Any]]:
        """Queries local SQLite raw.db for log lines matching query."""
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        cutoff_epoch = time.time() - (minutes * 60)
        try:
            with sqlite3.connect(self.raw_db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(raw_logs)")
                cols = {row["name"] for row in cursor.fetchall()}
                if "raw_text" in cols:
                    cursor.execute(
                        "SELECT * FROM raw_logs WHERE timestamp >= ? AND raw_text LIKE ? ORDER BY id DESC LIMIT 50",
                        (cutoff_epoch, f"%{query}%"),
                    )
                    return [dict(r) for r in cursor.fetchall()]
                else:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS raw_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            level TEXT NOT NULL,
                            source_ip TEXT,
                            username TEXT,
                            message TEXT NOT NULL
                        )
                        """
                    )
                    cursor.execute(
                        """
                        SELECT timestamp, level, source_ip, username, message
                        FROM raw_logs
                        WHERE timestamp >= ? AND message LIKE ?
                        ORDER BY id DESC LIMIT 50
                        """,
                        (cutoff_iso, f"%{query}%"),
                    )
                    return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return [{"error": f"Failed to query local raw store: {e}"}]

    def recent_auth_failures(self, minutes: int = 10) -> List[Dict[str, Any]]:
        """Queries local raw.db for failed login events."""
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
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
                        SELECT * FROM raw_logs 
                        WHERE timestamp >= ? AND (raw_text LIKE '%login_failure%' OR raw_text LIKE '%Failed password%' OR raw_text LIKE '%invalid password%')
                        ORDER BY id DESC LIMIT 50
                        """,
                        (cutoff_epoch,),
                    )
                    return [dict(r) for r in cursor.fetchall()]
                else:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS raw_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            level TEXT NOT NULL,
                            source_ip TEXT,
                            username TEXT,
                            message TEXT NOT NULL
                        )
                        """
                    )
                    cursor.execute(
                        """
                        SELECT timestamp, source_ip, username, message
                        FROM raw_logs
                        WHERE timestamp >= ? AND (message LIKE '%login failed%' OR message LIKE '%invalid password%' OR level = 'WARNING')
                        ORDER BY id DESC LIMIT 50
                        """,
                        (cutoff_iso,),
                    )
                    return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            return [{"error": f"Failed to query auth failures: {e}"}]

    def execute_tool(self, name: str, args: Dict[str, Any]) -> Any:
        if name == "search_raw_logs":
            return self.search_raw_logs(
                query=args.get("query", ""),
                minutes=args.get("minutes", 10),
            )
        elif name == "recent_auth_failures":
            return self.recent_auth_failures(
                minutes=args.get("minutes", 10),
            )
        return {"error": f"Unknown tool: {name}"}

    def chat(self, user_prompt: str) -> str:
        """
        Sends user prompt to Lemonade OpenAI-compatible endpoint.
        Handles function calling if model requests tools.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Airlock Shop AI, the local observability assistant running on the customer's "
                    "Ryzen AI NPU. You have access to local un-redacted raw logs via tools. "
                    "You answer the shop admin's questions with specific facts from the local logs. "
                    "Raw logs never leave this machine."
                ),
            },
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "tools": self.get_tool_definitions(),
            "tool_choice": "auto",
            "temperature": 0.2,
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(f"{self.base_url}/chat/completions", json=payload)
                res.raise_for_status()
                data = res.json()
                choice = data["choices"][0]["message"]

                # If model requested a tool call
                if choice.get("tool_calls"):
                    tool_call = choice["tool_calls"][0]
                    func_name = tool_call["function"]["name"]
                    func_args = json.loads(tool_call["function"].get("arguments", "{}"))

                    # Execute local tool
                    tool_result = self.execute_tool(func_name, func_args)

                    # Append assistant message and tool response
                    messages.append(choice)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.get("id", "call_1"),
                        "name": func_name,
                        "content": json.dumps(tool_result),
                    })

                    # Second turn for final synthesis
                    second_payload = {
                        "model": self.model_name,
                        "messages": messages,
                        "temperature": 0.2,
                    }
                    res2 = client.post(f"{self.base_url}/chat/completions", json=second_payload)
                    res2.raise_for_status()
                    return res2.json()["choices"][0]["message"]["content"]

                return choice.get("content", "")

        except Exception as e:
            return f"Shop AI (Lemonade NPU) connection error: {e}"
