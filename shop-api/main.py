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

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

LOG_FILE_PATH = os.getenv("SHOP_LOG_PATH", "data/shop-api.log")
Path(LOG_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Demo Shop API", version="1.0.0")


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
    uvicorn.run("shop-api.main:app", host="0.0.0.0", port=port, reload=False)
