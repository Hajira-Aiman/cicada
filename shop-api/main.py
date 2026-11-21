"""
shop-api/main.py
Demo E-Commerce Shop Service on port 7000 (T16):
- Endpoints:
  * GET /health: Health probe with PID and uptime
  * POST /auth/login: Login verification, logs success/failure with raw details for scrubber
  * GET /catalog: Product catalog listing
  * POST /cart/checkout: Order checkout logging realistic card numbers
  * POST /chaos/inject-log: Arbitrary text injection from Chaos Console / Try-to-leak box
- Writes JSON-line logs to data/shop-api.log for the Guard log tailer
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from contracts.request_auth import PRIVATE_ORIGIN_REGEX
except ImportError:
    PRIVATE_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"

LOG_FILE_PATH = os.getenv("SHOP_LOG_PATH", "data/shop-api.log")
Path(LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Demo Shop API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=PRIVATE_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_delay = {"until": 0.0, "ms": 0}   # chaos: every non-chaos request waits `ms` until `until`


@app.middleware("http")
async def artificial_latency(request: Request, call_next):
    if time.time() < _delay["until"] and not request.url.path.startswith("/chaos"):
        await asyncio.sleep(_delay["ms"] / 1000.0)
    return await call_next(request)


def log_shop_event(event_dict: Dict[str, Any]):
    """Appends structured JSON-line log to shop log file."""
    event_dict["timestamp"] = time.time()
    event_dict["service"] = "shop-api"
    line = json.dumps(event_dict)
    with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class LoginRequest(BaseModel):
    username: str
    password: str


class CheckoutRequest(BaseModel):
    card_number: str
    amount: float
    items: List[Dict[str, Any]] = Field(default_factory=list)


class InjectLogRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "shop-api",
        "version": "1.0.0",
        "pid": os.getpid(),
        "time": time.time(),
    }


@app.post("/auth/login")
def login(req: LoginRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    
    # Credential validation (standard demo user: admin / securepass2026)
    if req.username == "admin" and req.password == "securepass2026":
        log_shop_event({
            "level": "INFO",
            "event": "login_success",
            "username": req.username,
            "ip": client_ip,
            "message": f"User '{req.username}' logged in successfully from {client_ip}",
        })
        return {
            "status": "success",
            "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyIjoiYWRtaW4ifQ.demoSignature123",
            "username": req.username,
        }
    else:
        # Intentionally log failed credentials so the scrubber can verify password masking
        log_shop_event({
            "level": "WARNING",
            "event": "login_failure",
            "username": req.username,
            "password": req.password,
            "ip": client_ip,
            "message": f"Authentication failed for user '{req.username}' password={req.password} from {client_ip}",
        })
        raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/catalog")
def catalog():
    log_shop_event({
        "level": "INFO",
        "event": "catalog_view",
        "message": "Customer browsed security appliances catalog",
    })
    return [
        {"id": "prod-101", "name": "Airlock Security Appliance Edge-1", "price": 499.0},
        {"id": "prod-102", "name": "Quantum HSM Keycard", "price": 89.0},
        {"id": "prod-103", "name": "Ryzen AI NPU Accelerator Kit", "price": 249.0},
    ]


@app.post("/cart/checkout")
def checkout(req: CheckoutRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    receipt_id = f"rcpt_{int(time.time())}"
    
    # Realistic sensitive card number logged for scrubber redaction verification
    log_shop_event({
        "level": "INFO",
        "event": "checkout_processed",
        "card_number": req.card_number,
        "amount": req.amount,
        "ip": client_ip,
        "receipt_id": receipt_id,
        "message": f"Order processed for amount ${req.amount:.2f} using card {req.card_number}",
    })
    return {
        "status": "completed",
        "receipt_id": receipt_id,
        "amount": req.amount,
    }


class LatencyRequest(BaseModel):
    delay_ms: int = Field(default=450, ge=0, le=5000)
    duration_s: int = Field(default=20, ge=1, le=300)


@app.post("/chaos/latency")
def chaos_latency(req: LatencyRequest):
    """Slows every shop request by delay_ms for duration_s: the guard's health probe then reports real latency."""
    _delay["ms"], _delay["until"] = req.delay_ms, time.time() + req.duration_s
    return {"status": "slow", "delay_ms": req.delay_ms, "duration_s": req.duration_s}


@app.post("/chaos/inject-log")
def inject_log(req: InjectLogRequest):
    """
    Accepts arbitrary text (e.g. from the Chaos Console / Try-to-leak challenge)
    and writes it directly to the shop log file.
    """
    log_shop_event({
        "level": "INFO",
        "event": "chaos_injection",
        "raw_injection": req.text,
        "message": req.text,
    })
    return {
        "status": "injected",
        "bytes": len(req.text),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("SHOP_API_PORT", "7000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
