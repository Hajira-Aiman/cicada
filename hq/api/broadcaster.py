"""
hq/api/broadcaster.py
Real-time broadcaster managing connected WebSocket clients for the Head-Office dashboards.
Integrates with Ingest event notifications to push live telemetry.
"""

import asyncio
from typing import Any, Callable, Coroutine, Dict, List, Optional

from hq.ingest.service import add_ingest_listener


class Broadcaster:
    def __init__(self):
        # Key: client_id, Value: async send callback
        self.active_clients: Dict[str, Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = {}
        self._incident_states: Dict[str, Dict[str, Any]] = {}
        self._incident_last_sent: Dict[str, float] = {}

    def register_client(
        self,
        client_id: str,
        send_callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]],
    ):
        self.active_clients[client_id] = send_callback

    def unregister_client(self, client_id: str):
        self.active_clients.pop(client_id, None)

    async def broadcast(self, message: Dict[str, Any]):
        """Dispatches an event to all connected clients."""
        if not self.active_clients:
            return
        tasks = []
        for client_id, send_fn in list(self.active_clients.items()):
            try:
                tasks.append(send_fn(message))
            except Exception:
                self.unregister_client(client_id)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def on_ingest_payload(self, payload_dict: Dict[str, Any]):
        """Bridge invoked synchronously from Ingest service; schedules broadcast."""
        if payload_dict.get("event_type") == "alert_opened":
            alert = payload_dict["alert"]
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self.push_alert_opened(
                        tenant_id=alert["tenant_id"],
                        alert_id=alert["alert_id"],
                        source=alert.get("source"),
                        title=alert["title"],
                        severity=alert["severity"],
                        body=alert.get("body", {}),
                        created_at=alert["created_at"],
                    )
                )
            except RuntimeError:
                pass
            return

        event = {
            "event_type": "metrics_batch",
            "tenant_id": payload_dict["tenant_id"],
            "timestamp": payload_dict["sent_at"],
            "payload": {
                "guard_id": payload_dict["guard_id"],
                "window": payload_dict["window"],
                "metrics": payload_dict.get("metrics", []),
                "events": payload_dict.get("events", []),
                "health": payload_dict.get("health", {}),
            },
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast(event))
        except RuntimeError:
            pass

    async def push_health_change(
        self, tenant_id: str, source: str, state: str, old_state: Optional[str], reasons: List[str], at: str
    ):
        event = {
            "event_type": "health_change",
            "tenant_id": tenant_id,
            "timestamp": at,
            "payload": {
                "tenant_id": tenant_id,
                "source": source,
                "state": state,
                "old_state": old_state,
                "reasons": reasons,
                "at": at,
            },
        }
        await self.broadcast(event)

    async def push_incident(
        self, event_type: str, tenant_id: str, incident_id: str, body: Dict[str, Any], status: str, timestamp: str
    ):
        if event_type == "incident_updated":
            import time
            now = time.time()
            signals = tuple(sorted(str(s) for s in body.get("signals", [])))
            changes_before = tuple(sorted(str(c) for c in body.get("changes_before", [])))
            sig = {
                "title": body.get("title"),
                "severity": body.get("severity"),
                "confidence": body.get("confidence"),
                "status": status,
                "signals": signals,
                "changes_before": changes_before,
            }
            last_sig = self._incident_states.get(incident_id)
            last_time = self._incident_last_sent.get(incident_id, 0.0)

            # Throttle if title, severity, confidence, signal set, changes_before, status unchanged AND < 10s elapsed
            if last_sig == sig and (now - last_time) < 10.0:
                return

            self._incident_states[incident_id] = sig
            self._incident_last_sent[incident_id] = now
        elif event_type == "incident_opened":
            import time
            signals = tuple(sorted(str(s) for s in body.get("signals", [])))
            changes_before = tuple(sorted(str(c) for c in body.get("changes_before", [])))
            self._incident_states[incident_id] = {
                "title": body.get("title"),
                "severity": body.get("severity"),
                "confidence": body.get("confidence"),
                "status": status,
                "signals": signals,
                "changes_before": changes_before,
            }
            self._incident_last_sent[incident_id] = time.time()

        event = {
            "event_type": event_type,  # incident_opened or incident_updated
            "tenant_id": tenant_id,
            "timestamp": timestamp,
            "payload": {
                "incident_id": incident_id,
                "tenant_id": tenant_id,
                "body": body,
                "status": status,
                "timestamp": timestamp,
            },
        }
        await self.broadcast(event)

    async def push_alert_opened(
        self,
        tenant_id: str,
        alert_id: str,
        source: Optional[str],
        title: str,
        severity: str,
        body: Any,
        created_at: str,
    ):
        import json
        parsed_body = body
        if isinstance(body, str):
            try:
                parsed_body = json.loads(body)
            except Exception:
                parsed_body = {"raw": body}
        if not isinstance(parsed_body, dict):
            parsed_body = {"raw": str(parsed_body)}

        event = {
            "event_type": "alert_opened",
            "tenant_id": tenant_id,
            "timestamp": created_at,
            "payload": {
                "alert_id": alert_id,
                "tenant_id": tenant_id,
                "source": source or (parsed_body.get("signals", [{}])[0].get("source") if parsed_body.get("signals") else None),
                "title": title,
                "severity": severity,
                "kind": parsed_body.get("kind"),
                "signals": parsed_body.get("signals", []),
                "second_opinion": parsed_body.get("second_opinion"),
                "agrees": parsed_body.get("agrees"),
                "body": parsed_body,
                "created_at": created_at,
            },
        }
        await self.broadcast(event)

    async def push_counters(
        self,
        tenant_id: str,
        raw_alerts: int,
        incidents: int,
        noise_cut_pct: float = 0.0,
        flaps_prevented: int = 0,
    ):
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        event = {
            "event_type": "counters",
            "tenant_id": tenant_id,
            "timestamp": now_iso,
            "payload": {
                "tenant_id": tenant_id,
                "raw_alerts": raw_alerts,
                "incidents": incidents,
                "noise_cut_pct": noise_cut_pct,
                "flaps_prevented": flaps_prevented,
            },
        }
        await self.broadcast(event)


broadcaster = Broadcaster()
# Wire broadcaster into ingest event stream
add_ingest_listener(broadcaster.on_ingest_payload)
