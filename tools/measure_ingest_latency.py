"""
tools/measure_ingest_latency.py
Measures ingestion latency across 3 parallel clients sending 200 payloads to real PostgreSQL.
Reports p50 and p95 per request. Target: p95 < 100 ms.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contracts.models import AirlockPayload, EventItem, GuardHealth, MetricItem, TimeWindow
from hq.db import (
    close_all_pools,
    get_db_pool,
    init_all_databases,
    is_postgres_available,
    register_guard,
    truncate_all_data,
)
from hq.ingest.main import create_ingest_app

HMAC_SECRET = "sec-perf-secret-key-2026"
TENANT_ID = "acme"  # Routes to airlock_in


def make_payload_and_sig(
    guard_id: str, seq: int, prev_hash: str
) -> Tuple[bytes, str, str, str]:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = AirlockPayload(
        payload_id=f"perf-{uuid.uuid4().hex[:12]}",
        guard_id=guard_id,
        tenant_id=TENANT_ID,
        seq=seq,
        prev_hash=prev_hash,
        policy_version="sha256:v1-default-policy",
        sent_at=now_iso,
        window=TimeWindow(start=now_iso, end=now_iso, source_tz="UTC"),
        metrics=[
            MetricItem(source="host-7f3a1b2c", name="cpu_pct", avg=34.2, max=58.1),
            MetricItem(source="host-7f3a1b2c", name="mem_pct", avg=45.0, max=60.0),
        ],
        events=[
            EventItem(
                source="host-7f3a1b2c",
                category="auth_failure_burst",
                severity="low",
                actor="src-9c2e0011",
                count=1,
                window_s=2,
            ),
        ],
        health=GuardHealth(
            guard_version="0.3.1",
            guard_cpu_pct=1.2,
            guard_mem_mb=80.0,
            buffer_depth=0,
            config_ok=True,
            canaries_planted=12,
            secrets_redacted=3,
        ),
    )
    raw_body = payload.model_dump_json(by_alias=True).encode("utf-8")
    sig = hmac.new(HMAC_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    cur_hash = "sha256:" + hashlib.sha256(raw_body).hexdigest()
    return raw_body, sig, now_iso, cur_hash


async def client_worker(
    client: AsyncClient,
    guard_id: str,
    count: int,
    latencies: List[float],
):
    prev_hash = "GENESIS"
    for seq in range(1, count + 1):
        raw_body, sig, ts_iso, cur_hash = make_payload_and_sig(guard_id, seq, prev_hash)
        prev_hash = cur_hash
        headers = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": guard_id,
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": ts_iso,
        }
        t0 = time.perf_counter()
        resp = await client.post("/ingest", content=raw_body, headers=headers)
        duration_ms = (time.perf_counter() - t0) * 1000.0
        assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
        receipt = resp.json()
        assert receipt["status"] == "stored"
        latencies.append(duration_ms)


async def run_benchmark():
    assert is_postgres_available(), "PostgreSQL must be reachable for benchmark!"
    print("✅ Verified PostgreSQL is reachable.")

    # Register 3 performance test guards in airlock_core
    guard_ids = ["guard-perf-01", "guard-perf-02", "guard-perf-03"]
    for gid in guard_ids:
        register_guard(guard_id=gid, tenant_id=TENANT_ID, hmac_secret=HMAC_SECRET)

    # Initialize app and client
    app = create_ingest_app(region="in")
    counts = [67, 67, 66]  # Total 200 payloads
    total_expected = sum(counts)

    print(f"🚀 Starting benchmark: {total_expected} payloads across {len(guard_ids)} parallel clients...")
    all_latencies: List[float] = []

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Warmup connection pool
        raw_body, sig, ts_iso, _ = make_payload_and_sig("guard-perf-01", 1, "GENESIS")
        headers = {
            "Content-Type": "application/json",
            "X-Airlock-Guard-ID": "guard-perf-01",
            "X-Airlock-Signature": sig,
            "X-Airlock-Timestamp": ts_iso,
        }
        await client.post("/ingest", content=raw_body, headers=headers)
        # Clear dynamic data after warmup
        truncate_all_data()

        t_start = time.perf_counter()
        worker_latencies: List[List[float]] = [[], [], []]
        tasks = [
            client_worker(client, guard_ids[i], counts[i], worker_latencies[i])
            for i in range(3)
        ]
        await asyncio.gather(*tasks)
        total_time_s = time.perf_counter() - t_start

        for wl in worker_latencies:
            all_latencies.extend(wl)

        # Query GET /health for server-side latency histogram
        h_resp = await client.get("/health")
        h_data = h_resp.json()

    sorted_lats = sorted(all_latencies)
    n = len(sorted_lats)
    p50 = sorted_lats[int(round((n - 1) * 0.50))]
    p95 = sorted_lats[int(round((n - 1) * 0.95))]
    p99 = sorted_lats[int(round((n - 1) * 0.99))]
    min_lat = sorted_lats[0]
    max_lat = sorted_lats[-1]
    avg_lat = sum(sorted_lats) / n
    rps = n / total_time_s

    print("\n" + "=" * 50)
    print("INGEST BENCHMARK RESULTS (Real PostgreSQL):")
    print(f"Total Requests:      {n}")
    print(f"Total Duration:      {total_time_s:.2f} s")
    print(f"Throughput:          {rps:.1f} req/s")
    print(f"Min Latency:         {min_lat:.2f} ms")
    print(f"Avg Latency:         {avg_lat:.2f} ms")
    print(f"p50 Latency:         {p50:.2f} ms")
    print(f"p95 Latency:         {p95:.2f} ms")
    print(f"p99 Latency:         {p99:.2f} ms")
    print(f"Max Latency:         {max_lat:.2f} ms")
    print("=" * 50)
    print(f"GET /health server histogram: {h_data}")
    print("=" * 50)

    assert p95 < 100.0, f"Target failed! p95 was {p95:.2f} ms (expected < 100 ms)"
    print(f"🎯 SUCCESS: p95 latency {p95:.2f} ms is well under target 100 ms!")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
