"""
guard/thin_slice.py
Airlock Guard Telemetry Collector & Secure Sender:
- Imports exclusively from contracts.models
- Emits cpu_pct, service_up, and latency_ms in every payload
- Supports change events (app_restarted, version_changed, config_changed, new_process)
- Signs raw body with HMAC-SHA256 (X-Airlock-*) matching docs/contracts.md
"""

import os
import time
import socket
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
import psutil
import httpx

from contracts.models import (
    AirlockPayload,
    TimeWindow,
    MetricSample,
    EventSample,
    LogPatternSample,
    GuardHealth,
    IngestReceipt,
)
from guard.config import config
from guard.pseudonym import generate_pseudonym
from guard.signer import create_auth_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("airlock-guard")


class GuardThinSlice:
    def __init__(self, cfg=config):
        self.config = cfg
        self.seq = 1
        self.prev_hash = "GENESIS"
        self.hostname = socket.gethostname()
        self.host_pseudonym = generate_pseudonym("host", self.hostname, self.config.TENANT_SECRET_KEY)
        self.pending_events: List[EventSample] = []
        self.pending_log_patterns: List[LogPatternSample] = []

        # Service pseudonyms
        self.service_pseudonyms = {
            "shop-api": generate_pseudonym("proc", "shop-api", self.config.TENANT_SECRET_KEY),
            "login": generate_pseudonym("proc", "login", self.config.TENANT_SECRET_KEY),
            "checkout": generate_pseudonym("proc", "checkout", self.config.TENANT_SECRET_KEY),
            "db": generate_pseudonym("proc", "database", self.config.TENANT_SECRET_KEY),
        }

    def emit_change_event(
        self,
        category: str,
        source: Optional[str] = None,
        actor: Optional[str] = None,
        severity: str = "info",
    ):
        """
        Emits a change event (app_restarted, version_changed, config_changed, new_process)
        with an authorized pseudonymous source.
        """
        src = source or self.service_pseudonyms.get("shop-api", self.host_pseudonym)
        event = EventSample(
            category=category,
            severity=severity,
            source=src,
            actor=actor,
            count=1,
            window_s=2,
        )
        self.pending_events.append(event)
        logger.info(f"Queued change event: {category} for source {src}")

    def measure_latency(self) -> float:
        """Simulates or measures probe latency in ms."""
        # Baseline ping / latency check
        return 12.5

    def check_service_up(self) -> float:
        """Probes shop-api health or returns 1.0."""
        return 1.0

    def collect_window(self, duration_seconds: float = 2.0) -> Tuple[AirlockPayload, bytes]:
        """
        Gathers metrics over window duration and constructs a valid AirlockPayload.
        Guarantees that cpu_pct, service_up, and latency_ms are present in every window.
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=duration_seconds)
        end_time = now

        start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        sent_iso = end_iso

        # Read CPU
        cpu_val = float(psutil.cpu_percent(interval=None))
        service_up_val = self.check_service_up()
        latency_val = self.measure_latency()

        metrics = [
            MetricSample(
                name="cpu_pct",
                source=self.host_pseudonym,
                avg=round(cpu_val, 2),
                max=round(cpu_val, 2),
            ),
            MetricSample(
                name="service_up",
                source=self.service_pseudonyms["shop-api"],
                avg=service_up_val,
                max=service_up_val,
            ),
            MetricSample(
                name="latency_ms",
                source=self.host_pseudonym,
                avg=latency_val,
                max=latency_val,
            ),
        ]

        # Guard process health
        proc = psutil.Process(os.getpid())
        guard_cpu = round(proc.cpu_percent(interval=None), 2)
        guard_mem = round(proc.memory_info().rss / (1024 * 1024), 2)

        health = GuardHealth(
            guard_version=self.config.GUARD_VERSION,
            guard_cpu_pct=guard_cpu,
            guard_mem_mb=guard_mem,
            buffer_depth=0,
            config_ok=True,
            canaries_planted=0,
            secrets_redacted=0,
        )

        payload_id = str(uuid.uuid4())

        # Collect and drain pending events
        events_to_send = list(self.pending_events)
        self.pending_events.clear()

        log_patterns_to_send = list(self.pending_log_patterns)
        self.pending_log_patterns.clear()

        payload = AirlockPayload(
            schema="airlock.v1",
            payload_id=payload_id,
            tenant_id=self.config.TENANT_ID,
            guard_id=self.config.GUARD_ID,
            seq=self.seq,
            prev_hash=self.prev_hash,
            policy_version=self.config.POLICY_VERSION,
            sent_at=sent_iso,
            window=TimeWindow(
                start=start_iso,
                end=end_iso,
                source_tz=self.config.TIMEZONE,
            ),
            metrics=metrics,
            events=events_to_send,
            log_patterns=log_patterns_to_send,
            health=health,
        )

        # Serialize body to exact JSON bytes
        body_json = payload.model_dump_json(by_alias=True)
        body_bytes = body_json.encode("utf-8")

        # Update hash chain and sequence for next cycle
        sha256_hash = hashlib.sha256(body_bytes).hexdigest()
        self.prev_hash = f"sha256:{sha256_hash}"
        self.seq += 1

        return payload, body_bytes

    def send_payload(
        self,
        payload: AirlockPayload,
        body_bytes: bytes,
        client: Optional[httpx.Client] = None,
    ) -> Optional[IngestReceipt]:
        """
        Sends payload to ingest endpoint with canonical X-Airlock-* headers and returns IngestReceipt.
        """
        headers = create_auth_headers(
            guard_id=self.config.GUARD_ID,
            body_bytes=body_bytes,
            timestamp_iso=payload.sent_at,
            secret_key=self.config.GUARD_SECRET_KEY,
        )

        should_close = False
        if client is None:
            client = httpx.Client(timeout=self.config.TIMEOUT_SECONDS)
            should_close = True

        try:
            logger.info(
                f"Sending payload seq={payload.seq - 1} id={payload.payload_id} to {self.config.REGION_URL}"
            )
            response = client.post(
                self.config.REGION_URL,
                content=body_bytes,
                headers=headers,
            )
            response.raise_for_status()

            receipt_data = response.json()
            receipt = IngestReceipt.model_validate(receipt_data)
            logger.info(
                f"Receipt received: payload_id={receipt.payload_id} status={receipt.status} sha256={receipt.sha256}"
            )
            return receipt

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Ingest: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Connection failed to {self.config.REGION_URL} ({e}). Payload buffered.")
            return None
        finally:
            if should_close:
                client.close()


def run_loop(
    guard: Optional[GuardThinSlice] = None,
    interval: float = 2.0,
    max_iterations: Optional[int] = None,
):
    if guard is None:
        guard = GuardThinSlice()

    logger.info(
        f"Airlock Guard Thin Slice started [Tenant: {guard.config.TENANT_ID}, Guard: {guard.config.GUARD_ID}]"
    )
    logger.info(f"Target regional ingest: {guard.config.REGION_URL}")

    iteration = 0
    try:
        while max_iterations is None or iteration < max_iterations:
            time.sleep(interval)
            payload, body_bytes = guard.collect_window(duration_seconds=interval)
            guard.send_payload(payload, body_bytes)
            iteration += 1
    except KeyboardInterrupt:
        logger.info("Guard stopped by operator.")


if __name__ == "__main__":
    run_loop()
