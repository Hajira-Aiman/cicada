"""
hq/api/broadcaster.py
Real-time broadcaster managing connected WebSocket clients for the Head-Office dashboards.
Integrates with Ingest event notifications to push live telemetry.
"""

import asyncio
from typing import Any, Callable, Coroutine, Dict

from hq.ingest.service import add_ingest_listener


class Broadcaster:
    def __init__(self):
        # Key: client_id, Value: async send callback
        self.active_clients: Dict[str, Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = {}

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


broadcaster = Broadcaster()
# Wire broadcaster into ingest event stream
add_ingest_listener(broadcaster.on_ingest_payload)
