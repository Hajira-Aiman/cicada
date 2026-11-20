"""
hq/api/main.py
Head-Office Core API & Real-Time Dashboard WebSocket Server.
Runs on port 8000.
"""

import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from hq.api.broadcaster import broadcaster
from hq.db import execute_query, init_all_databases

init_all_databases()

app = FastAPI(title="Airlock Head-Office API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "hq-api"}


@app.get("/api/tenants")
def list_tenants():
    rows = execute_query("airlock_core", "SELECT tenant_id, name, assigned_region FROM tenants;")
    return {"tenants": rows}


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(uuid.uuid4())

    async def send_json(message: dict):
        await websocket.send_json(message)

    broadcaster.register_client(client_id, send_json)
    try:
        while True:
            # Keep connection open; receive client pings/messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        broadcaster.unregister_client(client_id)
    except Exception:
        broadcaster.unregister_client(client_id)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("hq.api.main:app", host="0.0.0.0", port=port, reload=False)
