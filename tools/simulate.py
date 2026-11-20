"""
tools/simulate.py
Multi-guard chaos simulator for Airlock.
Generates valid, cryptographically signed airlock.v1 payloads with scenario switches.
Can be run via CLI or used programmatically in tests and AIOps development.
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from contracts.models import (
    AirlockPayload,
    EventSample,
    GuardHealth,
    MetricSample,
    TimeWindow,
)

DEFAULT_POLICY_VERSION = "sha256:ab1289cf001e35a9"


def compute_hmac_signature(payload_json_bytes: bytes, secret: str) -> str:
    """Computes HMAC-SHA256 over exact payload JSON bytes."""
    return hmac.new(secret.encode("utf-8"), payload_json_bytes, hashlib.sha256).hexdigest()


class SimulatedGuardState:
    def __init__(
        self,
        tenant_id: str,
        guard_id: str,
        secret: str,
        source_id: str = "host-7f3a1234",
        source_tz: str = "Europe/Berlin",
    ):
        self.tenant_id = tenant_id
        self.guard_id = guard_id
        self.secret = secret
        self.source_id = source_id
        self.source_tz = source_tz
        self.seq = 0
        self.prev_hash = "sha256:0000000000000000"
        self.last_payload: Optional[Dict[str, Any]] = None
        self.kill_chain_step = 0
        self.step_counter = 0

    def generate_payload(
        self,
        scenario: str = "normal",
        window_duration_s: int = 2,
    ) -> Dict[str, Any]:
        """Generates an airlock.v1 payload dictionary according to the chosen scenario."""
        self.step_counter += 1
        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        start_iso = datetime.fromtimestamp(now_dt.timestamp() - window_duration_s, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        end_iso = now_iso

        # Base normal values
        cpu_avg = round(random.uniform(20.0, 35.0), 1)
        cpu_max = round(cpu_avg + random.uniform(2.0, 8.0), 1)
        mem_avg = round(random.uniform(42.0, 48.0), 1)
        disk_avg = 32.5
        net_in = round(random.uniform(150.0, 300.0), 1)
        net_out = round(random.uniform(80.0, 160.0), 1)
        latency_ms = round(random.uniform(12.0, 25.0), 1)
        packet_loss = 0.0
        service_up = 1.0

        events: List[Dict[str, Any]] = []

        # Scenario injections
        if scenario == "cpu_spike":
            cpu_avg = round(random.uniform(93.0, 97.5), 1)
            cpu_max = 99.0
        elif scenario == "latency":
            latency_ms = round(random.uniform(450.0, 850.0), 1)
            packet_loss = round(random.uniform(4.0, 12.0), 1)
        elif scenario == "login_burst":
            events.append(
                {
                    "category": "auth_failure_burst",
                    "severity": "high",
                    "source": self.source_id,
                    "actor": "src-9c2e0011",
                    "count": 50,
                    "window_s": 60,
                }
            )
        elif scenario == "honeypot":
            events.append(
                {
                    "category": "honeypot_hit",
                    "severity": "critical",
                    "source": self.source_id,
                    "actor": "src-bad0001",
                    "count": 1,
                    "window_s": 2,
                }
            )
        elif scenario == "kill_chain":
            self.kill_chain_step = (self.kill_chain_step + 1) % 5
            if self.kill_chain_step == 1:
                events.append(
                    {
                        "category": "auth_failure_burst",
                        "severity": "high",
                        "source": self.source_id,
                        "actor": "src-9c2e0011",
                        "count": 50,
                        "window_s": 60,
                    }
                )
            elif self.kill_chain_step == 2:
                events.append(
                    {
                        "category": "login_after_failures",
                        "severity": "medium",
                        "source": self.source_id,
                        "actor": "src-9c2e0011",
                        "count": 1,
                        "window_s": 10,
                    }
                )
            elif self.kill_chain_step == 3:
                cpu_avg = 96.5
                cpu_max = 99.0
            elif self.kill_chain_step == 4:
                cpu_avg = 96.0
                cpu_max = 98.5
                net_out = 920.0
        elif scenario == "scheduled_job":
            # Spikes every 30 steps (60s)
            if self.step_counter % 30 in (1, 2):
                cpu_avg = 95.0
                cpu_max = 98.0

        # Build metrics list
        metrics = [
            {"name": "cpu_pct", "source": self.source_id, "avg": cpu_avg, "max": cpu_max},
            {"name": "mem_pct", "source": self.source_id, "avg": mem_avg, "max": mem_avg + 2.0},
            {"name": "disk_pct", "source": self.source_id, "avg": disk_avg, "max": disk_avg},
            {"name": "net_in_kbps", "source": self.source_id, "avg": net_in, "max": net_in + 50.0},
            {"name": "net_out_kbps", "source": self.source_id, "avg": net_out, "max": net_out + 40.0},
            {"name": "latency_ms", "source": self.source_id, "avg": latency_ms, "max": latency_ms + 10.0},
            {"name": "packet_loss_pct", "source": self.source_id, "avg": packet_loss, "max": packet_loss},
            {"name": "service_up", "source": self.source_id, "avg": service_up, "max": service_up},
        ]

        payload_id = str(uuid.uuid4())

        # Handle duplicate scenario
        if scenario == "duplicates" and self.last_payload is not None:
            return self.last_payload

        # Handle out_of_order scenario
        if scenario == "out_of_order":
            stale_timestamp = datetime.fromtimestamp(now_dt.timestamp() - 60, timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            start_iso = stale_timestamp
            end_iso = stale_timestamp

        raw_payload = {
            "schema": "airlock.v1",
            "payload_id": payload_id,
            "tenant_id": self.tenant_id,
            "guard_id": self.guard_id,
            "seq": self.seq,
            "prev_hash": self.prev_hash,
            "policy_version": DEFAULT_POLICY_VERSION,
            "sent_at": now_iso,
            "window": {
                "start": start_iso,
                "end": end_iso,
                "source_tz": self.source_tz,
            },
            "metrics": metrics,
            "events": events,
            "log_patterns": [],
            "health": {
                "guard_version": "0.1.0",
                "guard_cpu_pct": 0.8,
                "guard_mem_mb": 42.0,
                "buffer_depth": 0,
                "config_ok": True,
                "canaries_planted": 1,
                "secrets_redacted": 0,
            },
        }

        # Validate with contract model
        validated = AirlockPayload.model_validate(raw_payload)
        dumped = validated.model_dump(by_alias=True)

        # Update chain state
        payload_bytes = json.dumps(dumped, sort_keys=True).encode("utf-8")
        current_hash = "sha256:" + hashlib.sha256(payload_bytes).hexdigest()
        self.prev_hash = current_hash
        self.seq += 1
        self.last_payload = dumped

        return dumped


class MultiGuardSimulator:
    def __init__(
        self,
        tenants: List[str],
        guards_per_tenant: int = 1,
        secret: str = "sec-globex-super-secret-key-2026",
    ):
        self.guards: List[SimulatedGuardState] = []
        for t in tenants:
            for g_idx in range(1, guards_per_tenant + 1):
                guard_id = f"guard-{t}-{g_idx:02d}"
                source_id = f"host-{hashlib.md5(guard_id.encode()).hexdigest()[:8]}"
                self.guards.append(
                    SimulatedGuardState(
                        tenant_id=t,
                        guard_id=guard_id,
                        secret=secret,
                        source_id=source_id,
                        source_tz="Europe/Berlin" if t == "globex" else "Asia/Kolkata",
                    )
                )

    async def run_loop(
        self,
        endpoint_url: str,
        scenario: str = "normal",
        interval_s: float = 2.0,
        max_iterations: Optional[int] = None,
    ):
        """Asynchronously posts generated payloads to endpoint_url."""
        iteration = 0
        async with httpx.AsyncClient(timeout=5.0) as client:
            while True:
                if max_iterations is not None and iteration >= max_iterations:
                    break
                iteration += 1

                for guard in self.guards:
                    # In outage scenario, simulate silence
                    if scenario == "outage" and iteration > 2:
                        continue

                    payload_dict = guard.generate_payload(scenario=scenario)
                    payload_bytes = json.dumps(payload_dict, sort_keys=True).encode("utf-8")
                    signature = compute_hmac_signature(payload_bytes, guard.secret)

                    headers = {
                        "Content-Type": "application/json",
                        "X-Airlock-Guard-ID": guard.guard_id,
                        "X-Airlock-Signature": signature,
                        "X-Airlock-Timestamp": payload_dict["sent_at"],
                    }

                    try:
                        resp = await client.post(endpoint_url, content=payload_bytes, headers=headers)
                        print(f"[{payload_dict['sent_at']}] {guard.guard_id} seq={payload_dict['seq']} -> {resp.status_code}")
                    except Exception as exc:
                        print(f"[{guard.guard_id}] Ingest post error: {exc}")

                await asyncio.sleep(interval_s)


def main():
    parser = argparse.ArgumentParser(description="Airlock Multi-Guard Telemetry Simulator")
    parser.add_argument("--tenants", type=str, default="globex,acme", help="Comma-separated tenant IDs")
    parser.add_argument("--guards", type=int, default=1, help="Guards per tenant")
    parser.add_argument("--endpoint", type=str, default="http://localhost:8002/ingest", help="Ingest URL")
    parser.add_argument("--scenario", type=str, default="normal", choices=[
        "normal", "cpu_spike", "latency", "login_burst", "honeypot", "outage", "duplicates", "out_of_order", "kill_chain", "scheduled_job"
    ], help="Chaos scenario to inject")
    parser.add_argument("--interval", type=float, default=2.0, help="Interval in seconds")
    parser.add_argument("--count", type=int, default=None, help="Number of payloads to emit before stopping")
    parser.add_argument("--secret", type=str, default="sec-globex-super-secret-key-2026", help="HMAC signing secret")
    args = parser.parse_args()

    tenant_list = [t.strip() for t in args.tenants.split(",") if t.strip()]
    simulator = MultiGuardSimulator(tenants=tenant_list, guards_per_tenant=args.guards, secret=args.secret)
    print(f"Starting Airlock Simulator with {len(simulator.guards)} guards across {tenant_list} (Scenario: {args.scenario})")
    asyncio.run(simulator.run_loop(
        endpoint_url=args.endpoint,
        scenario=args.scenario,
        interval_s=args.interval,
        max_iterations=args.count,
    ))


if __name__ == "__main__":
    main()
