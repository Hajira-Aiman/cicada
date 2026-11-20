"""
guard/thin_slice.py
Airlock Guard Telemetry Collector & Secure Sender:
- Real probe: latency_ms = probe duration to shop-api health endpoint
- Real service_up: 1.0 if HTTP 200, else 0.0 + service_down event emitted
- Metrics in every window: cpu_pct, mem_pct, disk_pct, net_in_kbps, net_out_kbps, service_up, latency_ms
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
from guard.ledger import GuardLedger
from guard.outbox import GuardOutbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("airlock-guard")


class GuardThinSlice:
    def __init__(
        self,
        cfg=config,
        ledger: Optional[GuardLedger] = None,
        outbox: Optional[GuardOutbox] = None,
    ):
        self.config = cfg
        db_path = getattr(self.config, "GUARD_DB_PATH", "data/guard.db")
        self.ledger = ledger or GuardLedger(db_path=db_path)
        self.outbox = outbox or GuardOutbox(db_path=db_path, ledger=self.ledger)

        # Resume state from ledger: contiguous sequence with zero gaps
        last_seq, last_hash = self.ledger.get_last_seq_and_hash()
        self.seq = last_seq + 1
        self.prev_hash = last_hash

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

        # Network I/O counter baseline
        net = psutil.net_io_counters()
        self.last_net_bytes_recv = net.bytes_recv
        self.last_net_bytes_sent = net.bytes_sent
        self.last_net_time = time.perf_counter()

    def emit_change_event(
        self,
        category: str,
        source: Optional[str] = None,
        actor: Optional[str] = None,
        severity: str = "info",
    ):
        """
        Emits a change or lifecycle event with an authorized pseudonymous source.
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
        logger.info(f"Queued event: {category} for source {src} (severity={severity})")

    def _get_net_rates(self) -> Tuple[float, float]:
        """Calculates network inbound and outbound throughput in kilobits per second (kbps)."""
        now = time.perf_counter()
        dt = max(0.1, now - self.last_net_time)
        net = psutil.net_io_counters()
        bytes_recv = net.bytes_recv
        bytes_sent = net.bytes_sent

        delta_recv = max(0, bytes_recv - self.last_net_bytes_recv)
        delta_sent = max(0, bytes_sent - self.last_net_bytes_sent)

        self.last_net_bytes_recv = bytes_recv
        self.last_net_bytes_sent = bytes_sent
        self.last_net_time = now

        net_in_kbps = round((delta_recv * 8.0) / (dt * 1000.0), 2)
        net_out_kbps = round((delta_sent * 8.0) / (dt * 1000.0), 2)
        return net_in_kbps, net_out_kbps

    def _get_disk_pct(self) -> float:
        """Reads primary disk usage percentage."""
        try:
            drive = os.path.splitdrive(os.getcwd())[0]
            path = drive + "\\" if drive else "/"
            return round(psutil.disk_usage(path).percent, 2)
        except Exception:
            return 50.0

    def probe_shop_health(self, client: Optional[httpx.Client] = None) -> Tuple[float, float]:
        """
        Performs real HTTP probe to shop-api health URL.
        Returns:
            (service_up: 1.0 or 0.0, latency_ms: float)
        If status is not 200 or request fails, emits a service_down event.
        """
        start = time.perf_counter()
        health_url = getattr(
            self.config,
            "SHOP_HEALTH_URL",
            f"http://127.0.0.1:{self.config.SHOP_API_PORT}/health",
        )
        should_close = False
        if client is None:
            client = httpx.Client(timeout=1.0)
            should_close = True

        try:
            res = client.get(health_url)
            elapsed_ms = max(0.5, (time.perf_counter() - start) * 1000.0)
            if res.status_code == 200:
                return 1.0, round(elapsed_ms, 2)
            else:
                self.emit_change_event(
                    category="service_down",
                    source=self.service_pseudonyms["shop-api"],
                    severity="high",
                )
                return 0.0, round(elapsed_ms, 2)
        except Exception:
            elapsed_ms = max(1.0, (time.perf_counter() - start) * 1000.0)
            self.emit_change_event(
                category="service_down",
                source=self.service_pseudonyms["shop-api"],
                severity="high",
            )
            return 0.0, round(elapsed_ms, 2)
        finally:
            if should_close:
                client.close()

    def check_service_up(self, client: Optional[httpx.Client] = None) -> float:
        up, _ = self.probe_shop_health(client=client)
        return up

    def measure_latency(self, client: Optional[httpx.Client] = None) -> float:
        _, lat = self.probe_shop_health(client=client)
        return lat

    def collect_window(
        self,
        duration_seconds: float = 2.0,
        probe_client: Optional[httpx.Client] = None,
    ) -> Tuple[AirlockPayload, bytes]:
        """
        Gathers system and service metrics over window duration.
        Every payload includes:
        - cpu_pct (host CPU %)
        - mem_pct (host Memory %)
        - disk_pct (host Disk %)
        - net_in_kbps (Network in rate)
        - net_out_kbps (Network out rate - vital for cryptomining detection)
        - service_up (1.0 if healthy, 0.0 if down)
        - latency_ms (HTTP probe duration)
        """
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(seconds=duration_seconds)
        end_time = now

        start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        sent_iso = end_iso

        # Read host metrics
        cpu_val = float(psutil.cpu_percent(interval=None))
        mem_val = float(psutil.virtual_memory().percent)
        disk_val = self._get_disk_pct()
        net_in_kbps, net_out_kbps = self._get_net_rates()

        # Real health probe
        service_up_val, latency_val = self.probe_shop_health(client=probe_client)

        metrics = [
            MetricSample(
                name="cpu_pct",
                source=self.host_pseudonym,
                avg=round(cpu_val, 2),
                max=round(cpu_val, 2),
            ),
            MetricSample(
                name="mem_pct",
                source=self.host_pseudonym,
                avg=round(mem_val, 2),
                max=round(mem_val, 2),
            ),
            MetricSample(
                name="disk_pct",
                source=self.host_pseudonym,
                avg=round(disk_val, 2),
                max=round(disk_val, 2),
            ),
            MetricSample(
                name="net_in_kbps",
                source=self.host_pseudonym,
                avg=net_in_kbps,
                max=net_in_kbps,
            ),
            MetricSample(
                name="net_out_kbps",
                source=self.host_pseudonym,
                avg=net_out_kbps,
                max=net_out_kbps,
            ),
            MetricSample(
                name="service_up",
                source=self.service_pseudonyms["shop-api"],
                avg=service_up_val,
                max=service_up_val,
            ),
        ]
        if service_up_val == 1.0:
            metrics.append(
                MetricSample(
                    name="latency_ms",
                    source=self.host_pseudonym,
                    avg=latency_val,
                    max=latency_val,
                )
            )

        # Guard process health
        proc = psutil.Process(os.getpid())
        guard_cpu = round(proc.cpu_percent(interval=None), 2)
        guard_mem = round(proc.memory_info().rss / (1024 * 1024), 2)
        current_buffer_depth = self.outbox.get_buffer_depth()

        health = GuardHealth(
            guard_version=self.config.GUARD_VERSION,
            guard_cpu_pct=guard_cpu,
            guard_mem_mb=guard_mem,
            buffer_depth=current_buffer_depth,
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

        # Compute SHA-256 and chain
        sha256_hash = f"sha256:{hashlib.sha256(body_bytes).hexdigest()}"

        # Record to cryptographic ledger and queue in outbox (T11)
        self.ledger.record_payload(
            seq=payload.seq,
            payload_id=payload.payload_id,
            sha256=sha256_hash,
            prev_hash=payload.prev_hash,
            body=body_json,
            status="pending",
        )
        self.outbox.enqueue(
            seq=payload.seq,
            payload_id=payload.payload_id,
            sha256=sha256_hash,
            body=body_json,
        )

        self.prev_hash = sha256_hash
        self.seq += 1

        return payload, body_bytes

    def drain_outbox(
        self,
        client: Optional[httpx.Client] = None,
        ignore_backoff: bool = False,
    ) -> Tuple[int, int]:
        """
        Drains the outbox in oldest-first order (seq ASC) with backoff.
        """
        def _send(payload_id: str, body_bytes: bytes, client_obj: Optional[httpx.Client]):
            try:
                p_data = json.loads(body_bytes.decode("utf-8"))
                sent_at = p_data.get("sent_at", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            except Exception:
                sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            headers = create_auth_headers(
                guard_id=self.config.GUARD_ID,
                body_bytes=body_bytes,
                timestamp_iso=sent_at,
                secret_key=self.config.GUARD_SECRET_KEY,
            )
            should_close = False
            if client_obj is None:
                client_obj = httpx.Client(timeout=self.config.TIMEOUT_SECONDS)
                should_close = True
            try:
                resp = client_obj.post(
                    self.config.REGION_URL,
                    content=body_bytes,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return IngestReceipt.model_validate(data)
            except Exception as exc:
                logger.warning(f"Failed sending payload {payload_id} to {self.config.REGION_URL}: {exc}")
                return None
            finally:
                if should_close:
                    client_obj.close()

        return self.outbox.drain(send_fn=_send, client=client, ignore_backoff=ignore_backoff)

    def send_payload(
        self,
        payload: AirlockPayload,
        body_bytes: bytes,
        client: Optional[httpx.Client] = None,
    ) -> Optional[IngestReceipt]:
        """
        Sends payload to ingest endpoint with canonical X-Airlock-* headers,
        updates cryptographic ledger upon receipt, and returns IngestReceipt.
        """
        sha256_hash = f"sha256:{hashlib.sha256(body_bytes).hexdigest()}"
        if not self.ledger.get_row(payload.payload_id):
            self.ledger.record_payload(
                seq=payload.seq,
                payload_id=payload.payload_id,
                sha256=sha256_hash,
                prev_hash=payload.prev_hash,
                body=body_bytes.decode("utf-8"),
                status="pending",
            )
            self.outbox.enqueue(
                seq=payload.seq,
                payload_id=payload.payload_id,
                sha256=sha256_hash,
                body=body_bytes.decode("utf-8"),
            )

        # Drain outbox with provided client
        self.drain_outbox(client=client, ignore_backoff=True)

        row = self.ledger.get_row(payload.payload_id)
        if row and row["status"] in ("stored", "duplicate"):
            return IngestReceipt(
                payload_id=row["payload_id"],
                sha256=row["sha256"],
                received_at=row["receipt_at"] or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                status=row["status"],
            )
        return None


def run_loop(
    guard: Optional[GuardThinSlice] = None,
    interval: float = 2.0,
    max_iterations: Optional[int] = None,
):
    if guard is None:
        guard = GuardThinSlice()

    logger.info(
        f"Airlock Guard started [Tenant: {guard.config.TENANT_ID}, Guard: {guard.config.GUARD_ID}]"
    )
    logger.info(f"Target regional ingest: {guard.config.REGION_URL}")

    # Reusable probe client avoids ~350ms per-window TCP/TLS handshake overhead
    probe_client = httpx.Client(timeout=1.0)
    ingest_client = httpx.Client(timeout=guard.config.TIMEOUT_SECONDS)

    iteration = 0
    try:
        while max_iterations is None or iteration < max_iterations:
            time.sleep(interval)
            payload, body_bytes = guard.collect_window(
                duration_seconds=interval, probe_client=probe_client
            )
            guard.send_payload(payload, body_bytes, client=ingest_client)
            iteration += 1
    except KeyboardInterrupt:
        logger.info("Guard stopped by operator.")
    finally:
        probe_client.close()
        ingest_client.close()


if __name__ == "__main__":
    run_loop()
