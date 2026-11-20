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
from urllib.parse import urlparse
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
from guard.pseudonym import generate_pseudonym, PseudonymManager
from guard.signer import create_auth_headers
from guard.ledger import GuardLedger
from guard.outbox import GuardOutbox
from guard.raw_store import RawStore
from guard.scrubber import Scrubber
from guard.detectors import AuthDetector, PowerDetector, ChangeDetector
from guard.log_tailer import LogTailer
from guard.policy_gate import PolicyGate
from contracts.models import Checkpoint

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("airlock-guard")


class GuardThinSlice:
    def __init__(
        self,
        cfg=config,
        ledger: Optional[GuardLedger] = None,
        outbox: Optional[GuardOutbox] = None,
        raw_store: Optional[RawStore] = None,
        scrubber: Optional[Scrubber] = None,
        pseudonym_mgr: Optional[PseudonymManager] = None,
    ):
        self.config = cfg
        db_path = getattr(self.config, "GUARD_DB_PATH", "data/guard.db")
        raw_db_path = getattr(self.config, "RAW_DB_PATH", "data/raw.db")
        reveal_db_path = getattr(self.config, "REVEAL_DB_PATH", "data/reveal.db")

        self.ledger = ledger or GuardLedger(db_path=db_path)
        self.outbox = outbox or GuardOutbox(db_path=db_path, ledger=self.ledger)
        self.raw_store = raw_store or RawStore(db_path=raw_db_path)
        self.scrubber = scrubber or Scrubber()
        self.pseudonym_mgr = pseudonym_mgr or PseudonymManager(
            tenant_secret=self.config.TENANT_SECRET_KEY,
            db_path=reveal_db_path,
        )

        # Resume state from ledger: contiguous sequence with zero gaps
        last_seq, last_hash = self.ledger.get_last_seq_and_hash()
        self.seq = last_seq + 1
        self.prev_hash = last_hash

        self.hostname = socket.gethostname()
        self.host_pseudonym = self.pseudonym_mgr.get_or_create("host", self.hostname)
        self.pending_events: List[EventSample] = []
        self.pending_log_patterns: List[LogPatternSample] = []

        # Service pseudonyms registered in local reveal table
        self.service_pseudonyms = {
            "shop-api": self.pseudonym_mgr.get_or_create("proc", "shop-api"),
            "login": self.pseudonym_mgr.get_or_create("proc", "login"),
            "checkout": self.pseudonym_mgr.get_or_create("proc", "checkout"),
            "db": self.pseudonym_mgr.get_or_create("proc", "db"),
        }

        # Local AIOps Detectors (T9, T13, T19)
        self.auth_detector = AuthDetector(
            pseudonym_mgr=self.pseudonym_mgr,
            tenant_tz_str=self.config.TIMEZONE,
        )
        self.power_detector = PowerDetector(host_pseudonym=self.host_pseudonym)
        self.change_detector = ChangeDetector(
            pseudonym_mgr=self.pseudonym_mgr,
            host_pseudonym=self.host_pseudonym,
        )
        shop_log_path = getattr(self.config, "SHOP_LOG_PATH", "data/shop-api.log")
        self.log_tailer = LogTailer(log_path=shop_log_path, guard=self)
        self.policy_gate = PolicyGate(scrubber=self.scrubber)
        self.last_checkpoint_time: float = 0.0
        self.last_checkpoint: Optional[Checkpoint] = None

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

    def process_log_line(self, raw_line: str, source: str = "shop-api") -> Tuple[str, int]:
        """
        Processes an incoming log line:
        1. Stores raw line locally in raw.db (never sent over the wire).
        2. Masks secrets (AWS keys, JWTs, bearer tokens, passwords, cards).
        3. Returns (scrubbed_line, redactions_count).
        """
        # Store in local raw.db with 24h retention
        self.raw_store.store_raw_log(text=raw_line, source=source)

        # Mask secrets in pipeline
        scrubbed_line, count = self.scrubber.scrub_text(raw_line)
        if count > 0:
            self.emit_change_event(
                category="secret_redacted",
                source=self.service_pseudonyms.get(source, self.host_pseudonym),
                severity="medium",
            )
        return scrubbed_line, count

    def record_login(
        self,
        raw_username: str,
        raw_ip: str,
        success: bool,
        timestamp: Optional[float] = None,
    ) -> List[EventSample]:
        """
        Records a login attempt and enqueues triggered security events (honeypot, odd_hour, login_after_failures).
        """
        events = self.auth_detector.record_login(
            raw_username=raw_username,
            raw_ip=raw_ip,
            success=success,
            service_pseudonym=self.service_pseudonyms["login"],
            timestamp=timestamp,
        )
        self.pending_events.extend(events)
        return events

    def notify_shop_process(self, pid: int, create_time: float) -> Optional[EventSample]:
        """Notifies guard of shop-api process identity to detect app_restarted events."""
        event = self.change_detector.update_shop_process(
            pid=pid,
            create_time=create_time,
            service_pseudonym=self.service_pseudonyms["shop-api"],
        )
        if event:
            self.pending_events.append(event)
        return event

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

    def _get_ingest_host_port(self) -> Tuple[str, int]:
        """Extracts head-office ingest host and port for packet loss probes."""
        url = getattr(self.config, "REGION_URL", "") or os.getenv("INGEST_URL", "http://127.0.0.1:8001")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://127.0.0.1:8001" + url
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 8001)
        return host, port

    def measure_packet_loss(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        count: int = 10,
        timeout: float = 0.05,
    ) -> float:
        """
        Sends 10 small TCP connection attempts to the head-office ingest host:port.
        Reports failed share as a percent (0.0 to 100.0).
        """
        override = getattr(self, "_packet_loss_override", None)
        if override is not None:
            return float(override)

        if host is None or port is None:
            h, p = self._get_ingest_host_port()
            host = host or h
            port = port or p

        failed = 0
        for _ in range(count):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                err = s.connect_ex((host, port))
                if err != 0:
                    failed += 1
                s.close()
            except Exception:
                failed += 1

        return round((failed / float(count)) * 100.0, 1)

    def set_packet_loss_override(self, val: Optional[float]):
        self._packet_loss_override = val

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

        # Tail and process new logs from shop-api (T3, T16)
        self.log_tailer.process_pending_logs()

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
                    source=self.service_pseudonyms["shop-api"],
                    avg=latency_val,
                    max=latency_val,
                )
            )

        # Real packet loss probe to head-office ingest host:port
        packet_loss_val = self.measure_packet_loss()
        metrics.append(
            MetricSample(
                name="packet_loss_pct",
                source=self.service_pseudonyms["shop-api"],
                avg=packet_loss_val,
                max=packet_loss_val,
            )
        )

        # Evaluate power & battery state (T19)
        power_metrics, power_events = self.power_detector.check_power()
        metrics.extend(power_metrics)
        self.pending_events.extend(power_events)

        # Evaluate auth bursts (30+ failures in 60s) (T9)
        burst_events = self.auth_detector.evaluate_bursts(service_pseudonym=self.service_pseudonyms["login"])
        self.pending_events.extend(burst_events)

        # Evaluate configuration changes (.env hash) (T13)
        cfg_event = self.change_detector.check_config_changed()
        if cfg_event:
            self.pending_events.append(cfg_event)

        # Plant canary every 30s into raw store (T5)
        self.scrubber.maybe_plant_canary(raw_store=self.raw_store)

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
            canaries_planted=self.scrubber.canaries_planted,
            secrets_redacted=self.scrubber.secrets_redacted,
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

        # Policy gate inspection: schema contract + canary/secret check (T4, T10)
        valid, reason = self.policy_gate.inspect_payload(payload, body_json_str=body_json)
        if not valid:
            logger.critical(f"POLICY GATE VIOLATION: {reason}. Egress payload BLOCKED.")
            raise ValueError(f"Pre-send policy violation: {reason}")

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

    def maybe_publish_checkpoint(self, now: Optional[float] = None) -> Optional[Checkpoint]:
        """
        Every 60s computes and publishes running SHA-256 checkpoint {guard_id, up_to_seq, root} (T14).
        """
        current_time = now if now is not None else time.time()
        if self.last_checkpoint_time == 0.0 or (current_time - self.last_checkpoint_time) >= 60.0:
            cp = self.ledger.compute_checkpoint(guard_id=self.config.GUARD_ID)
            self.last_checkpoint_time = current_time
            self.last_checkpoint = cp
            logger.info(f"Published Checkpoint: guard_id={cp.guard_id} up_to_seq={cp.up_to_seq} root={cp.root}")
            return cp
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
            guard.maybe_publish_checkpoint()
            iteration += 1
    except KeyboardInterrupt:
        logger.info("Guard stopped by operator.")
    finally:
        probe_client.close()
        ingest_client.close()


if __name__ == "__main__":
    run_loop()
