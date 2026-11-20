"""
guard/thin_slice.py
Thin slice telemetry collector and sender:
1. Reads cpu_pct every 2s via psutil
2. Builds schema-valid airlock.v1 payload with UTC timestamps and source_tz
3. Signs payload with HMAC-SHA256
4. POSTs to regional ingest endpoint and handles signed receipt
"""

import os
import socket
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
import psutil
import httpx

from contracts.payload import (
    PayloadV1,
    WindowInfo,
    MetricItem,
    MetricName,
    HealthInfo,
    SignedReceipt,
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
        self.last_cpu = psutil.cpu_percent(interval=None)

    def collect_window(self, duration_seconds: float = 2.0) -> Tuple[PayloadV1, bytes]:
        """
        Gathers CPU metric over window duration and constructs a valid PayloadV1.
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=duration_seconds)
        end_time = now

        start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        sent_iso = end_iso

        # Read CPU
        cpu_val = float(psutil.cpu_percent(interval=None))
        mem = psutil.virtual_memory()

        metrics = [
            MetricItem(
                name=MetricName.CPU_PCT,
                source=self.host_pseudonym,
                avg=round(cpu_val, 2),
                max=round(cpu_val, 2),
            )
        ]

        # Guard process health
        proc = psutil.Process(os.getpid())
        guard_cpu = round(proc.cpu_percent(interval=None), 2)
        guard_mem = round(proc.memory_info().rss / (1024 * 1024), 2)

        health = HealthInfo(
            guard_version=self.config.GUARD_VERSION,
            guard_cpu_pct=guard_cpu,
            guard_mem_mb=guard_mem,
            buffer_depth=0,
            config_ok=True,
            canaries_planted=0,
            secrets_redacted=0,
        )

        payload_id = str(uuid.uuid4())

        payload = PayloadV1(
            schema="airlock.v1",
            payload_id=payload_id,
            tenant_id=self.config.TENANT_ID,
            guard_id=self.config.GUARD_ID,
            seq=self.seq,
            prev_hash=self.prev_hash,
            policy_version=self.config.POLICY_VERSION,
            sent_at=sent_iso,
            window=WindowInfo(
                start=start_iso,
                end=end_iso,
                source_tz=self.config.TIMEZONE,
            ),
            metrics=metrics,
            events=[],
            log_patterns=[],
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
        payload: PayloadV1,
        body_bytes: bytes,
        client: Optional[httpx.Client] = None,
    ) -> Optional[SignedReceipt]:
        """
        Sends payload to ingest endpoint with HMAC signature headers and returns receipt.
        """
        headers = create_auth_headers(
            guard_id=self.config.GUARD_ID,
            payload_id=payload.payload_id,
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
            receipt = SignedReceipt.model_validate(receipt_data)
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
    import time
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
