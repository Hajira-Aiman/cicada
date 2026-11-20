"""
hq/ingest/main.py
FastAPI Regional Ingestion Service.
Run with REGION=in on port 8001 or REGION=eu on port 8002.
"""

import os
import threading
import time
from collections import deque
from typing import Any, Dict
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from hq.ingest.service import process_ingest_payload


class LatencyTracker:
    """Thread-safe latency tracker computing count, p50, and p95 percentiles."""

    def __init__(self, max_samples: int = 5000):
        self.samples: deque = deque(maxlen=max_samples)
        self.lock = threading.Lock()
        self.total_count = 0

    def record(self, duration_ms: float):
        with self.lock:
            self.samples.append(duration_ms)
            self.total_count += 1

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            if not self.samples:
                return {
                    "count": self.total_count,
                    "p50": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                }
            sorted_samples = sorted(self.samples)

            def percentile(p: float) -> float:
                idx = int(round((len(sorted_samples) - 1) * p))
                return round(sorted_samples[idx], 2)

            return {
                "count": self.total_count,
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "p99": percentile(0.99),
                "min": round(sorted_samples[0], 2),
                "max": round(sorted_samples[-1], 2),
            }


def create_ingest_app(region: str = "eu") -> FastAPI:
    app = FastAPI(title=f"Airlock Ingest ({region.upper()})")
    tracker = LatencyTracker()
    app.state.latency_tracker = tracker

    @app.get("/health")
    def health_check():
        stats = tracker.get_stats()
        return {
            "status": "ok",
            "region": region,
            "count": stats["count"],
            "p50": stats["p50"],
            "p95": stats["p95"],
            "latency": stats,
        }

    @app.post("/ingest")
    async def ingest_payload(
        request: Request,
        x_airlock_guard_id: str = Header(None, alias="X-Airlock-Guard-ID"),
        x_airlock_signature: str = Header(None, alias="X-Airlock-Signature"),
        x_airlock_timestamp: str = Header(None, alias="X-Airlock-Timestamp"),
    ):
        t0 = time.perf_counter()
        raw_body = await request.body()
        status_code, result = process_ingest_payload(
            region=region,
            raw_body=raw_body,
            guard_id=x_airlock_guard_id,
            signature=x_airlock_signature,
            timestamp_str=x_airlock_timestamp,
        )
        duration_ms = (time.perf_counter() - t0) * 1000.0
        tracker.record(duration_ms)

        if status_code != 200:
            err_msg = result.get("error", "Ingest error")
            return JSONResponse(status_code=status_code, content={"error": err_msg, "detail": err_msg})
        return JSONResponse(status_code=200, content=result)

    return app


# Default app instance loaded by uvicorn
default_region = os.getenv("REGION", "eu")
app = create_ingest_app(region=default_region)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002" if default_region == "eu" else "8001"))
    uvicorn.run("hq.ingest.main:app", host="0.0.0.0", port=port, reload=False)
