"""
guard/detectors.py
Local Security & Change Detectors for AIOps (T9, T13, T19):
- AuthDetector:
  * 30+ failed logins in 60s -> auth_failure_burst (severity high, count N, actor = src-xxxx)
  * Successful login after failures -> login_after_failures (severity medium, actor = src-xxxx)
  * Login at 03:00 shop time -> odd_hour_login (severity medium, actor = src-xxxx)
  * Login with trap user 'admin_backup' -> honeypot_hit (severity critical, actor = src-xxxx)
- PowerDetector:
  * Charger unplugged -> power_on_battery event + battery_pct, on_battery, battery_min_left metrics
- ChangeDetector:
  * Watches shop-api PID/start time -> app_restarted
  * Watches .env/policy hash -> config_changed
  * Detects new top CPU processes -> new_process
- Strict pseudonymization: no raw IPs, hostnames, or usernames leave the environment
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import psutil

from contracts.models import EventSample, MetricSample
from guard.pseudonym import PseudonymManager

logger = logging.getLogger("airlock.guard.detectors")


class AuthDetector:
    """
    T9 Local login failure and attack detector.
    Tracks failure bursts, odd-hour access, honeypots, and account recovery after failures.
    """

    def __init__(self, pseudonym_mgr: PseudonymManager, tenant_tz_str: str = "Asia/Kolkata"):
        self.pseudonym_mgr = pseudonym_mgr
        self.tenant_tz_str = tenant_tz_str
        # map: raw_ip -> list of failure timestamps
        self.failure_history: Dict[str, List[float]] = {}
        # map: raw_ip -> count seen during previous check (to detect when growth stops)
        self.last_failure_counts: Dict[str, int] = {}
        # map: raw_ip -> bool indicating if IP had failures before success
        self.had_failures: Set[str] = set()

    def record_login(
        self,
        raw_username: str,
        raw_ip: str,
        success: bool,
        service_pseudonym: str,
        timestamp: Optional[float] = None,
    ) -> List[EventSample]:
        """
        Records a login attempt and returns any triggered security events.
        """
        now = timestamp if timestamp is not None else time.time()
        events: List[EventSample] = []

        actor_pseudonym = self.pseudonym_mgr.get_or_create("src", raw_ip)
        self.pseudonym_mgr.get_or_create("user", raw_username)

        # 1. Honeypot check: trap user 'admin_backup'
        if raw_username == "admin_backup":
            events.append(
                EventSample(
                    category="honeypot_hit",
                    severity="critical",
                    source=service_pseudonym,
                    actor=actor_pseudonym,
                    count=1,
                    window_s=2,
                )
            )
            logger.warning(f"Honeypot hit detected from actor {actor_pseudonym}")

        # 2. Odd-hour login check (03:00 shop time)
        if success:
            try:
                tz = ZoneInfo(self.tenant_tz_str)
                dt = datetime.fromtimestamp(now, tz=tz)
                if dt.hour == 3:
                    events.append(
                        EventSample(
                            category="odd_hour_login",
                            severity="medium",
                            source=service_pseudonym,
                            actor=actor_pseudonym,
                            count=1,
                            window_s=2,
                        )
                    )
            except Exception as e:
                logger.error(f"Timezone error calculating odd_hour_login: {e}")

        # 3. Failure & Burst tracking
        if not success:
            if raw_ip not in self.failure_history:
                self.failure_history[raw_ip] = []
            self.failure_history[raw_ip].append(now)
            self.had_failures.add(raw_ip)
        else:
            # Successful login after failures from the same actor
            if raw_ip in self.had_failures:
                events.append(
                    EventSample(
                        category="login_after_failures",
                        severity="medium",
                        source=service_pseudonym,
                        actor=actor_pseudonym,
                        count=1,
                        window_s=2,
                    )
                )
                self.had_failures.discard(raw_ip)
                self.failure_history.pop(raw_ip, None)

        return events

    def evaluate_bursts(
        self,
        service_pseudonym: str,
        now: Optional[float] = None,
        force: bool = False,
    ) -> List[EventSample]:
        """
        Evaluates sliding 60-second window for auth_failure_bursts (30+ failures).
        Emits once at the end of the burst (or when it stops growing) with the real total count.
        """
        current_time = now if now is not None else time.time()
        cutoff = current_time - 60.0
        events: List[EventSample] = []

        for raw_ip, timestamps in list(self.failure_history.items()):
            # Keep only failures within last 60 seconds up to current_time
            valid_fails = [t for t in timestamps if cutoff <= t <= current_time]
            if len(valid_fails) >= 30:
                last_fail_ts = max(valid_fails) if valid_fails else current_time
                prev_count = self.last_failure_counts.get(raw_ip, 0)
                curr_count = len(valid_fails)

                quiet_time = current_time - last_fail_ts
                # Burst has stopped if:
                # - forced
                # - quiet period >= 0.5s has elapsed since the last failure
                # - OR the count hasn't grown since the previous evaluation check
                burst_stopped = (
                    force
                    or (quiet_time >= 0.5)
                    or (prev_count > 0 and curr_count == prev_count)
                )

                if burst_stopped:
                    actor_pseudonym = self.pseudonym_mgr.get_or_create("src", raw_ip)
                    events.append(
                        EventSample(
                            category="auth_failure_burst",
                            severity="high",
                            source=service_pseudonym,
                            actor=actor_pseudonym,
                            count=curr_count,
                            window_s=60,
                        )
                    )
                    logger.warning(
                        f"Auth failure burst detected: {curr_count} failures from actor {actor_pseudonym}"
                    )
                    # Clear counted failures after emitting
                    self.failure_history[raw_ip] = [t for t in timestamps if t > current_time]
                    self.last_failure_counts.pop(raw_ip, None)
                else:
                    self.last_failure_counts[raw_ip] = curr_count
                    self.failure_history[raw_ip] = valid_fails + [t for t in timestamps if t > current_time]
            else:
                self.failure_history[raw_ip] = valid_fails + [t for t in timestamps if t > current_time]
                self.last_failure_counts.pop(raw_ip, None)

        return events


class PowerDetector:
    """
    T19 Charger and battery status detector.
    Reports battery metrics and emits power_on_battery when unplugged.
    """

    def __init__(self, host_pseudonym: str):
        self.host_pseudonym = host_pseudonym
        self.was_on_battery: bool = False
        # Optional override for testing or headless environments
        self.override_state: Optional[Dict[str, Any]] = None

    def set_override(
        self,
        percent: float,
        power_plugged: bool,
        secsleft: int = 3600,
    ):
        self.override_state = {
            "percent": percent,
            "power_plugged": power_plugged,
            "secsleft": secsleft,
        }

    def clear_override(self):
        self.override_state = None

    def check_power(self) -> Tuple[List[MetricSample], List[EventSample]]:
        metrics: List[MetricSample] = []
        events: List[EventSample] = []

        battery = None
        if self.override_state is not None:
            class MockBattery:
                pass
            battery = MockBattery()
            battery.percent = self.override_state["percent"]
            battery.power_plugged = self.override_state["power_plugged"]
            battery.secsleft = self.override_state["secsleft"]
        else:
            try:
                battery = psutil.sensors_battery()
            except Exception:
                battery = None

        if battery is not None:
            pct = round(float(battery.percent), 1)
            plugged = bool(battery.power_plugged)
            on_battery = 0.0 if plugged else 1.0

            if battery.secsleft > 0 and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
                min_left = round(battery.secsleft / 60.0, 1)
            else:
                min_left = 0.0 if on_battery == 1.0 else 180.0

            metrics.extend([
                MetricSample(name="battery_pct", source=self.host_pseudonym, avg=pct, max=pct),
                MetricSample(name="on_battery", source=self.host_pseudonym, avg=on_battery, max=on_battery),
                MetricSample(name="battery_min_left", source=self.host_pseudonym, avg=min_left, max=min_left),
            ])

            # Transition check: charger unplugged
            if on_battery == 1.0 and not self.was_on_battery:
                events.append(
                    EventSample(
                        category="power_on_battery",
                        severity="high",
                        source=self.host_pseudonym,
                        count=1,
                        window_s=2,
                    )
                )

            self.was_on_battery = (on_battery == 1.0)

        return metrics, events


class ChangeDetector:
    """
    T13 Real change detection:
    - Watches shop-api PID / start time -> app_restarted
    - Watches .env / policy file hash -> config_changed
    - Discovers new top-CPU processes -> new_process
    """

    def __init__(
        self,
        pseudonym_mgr: PseudonymManager,
        host_pseudonym: str,
        env_path: str = ".env",
    ):
        self.pseudonym_mgr = pseudonym_mgr
        self.host_pseudonym = host_pseudonym
        self.env_path = env_path
        self.last_shop_pid: Optional[int] = None
        self.last_shop_create_time: Optional[float] = None
        self.last_env_hash: Optional[str] = self._compute_env_hash()
        self.known_pids: Set[int] = set(p.pid for p in psutil.process_iter())

    def _compute_env_hash(self) -> Optional[str]:
        p = Path(self.env_path)
        if p.exists():
            try:
                return hashlib.sha256(p.read_bytes()).hexdigest()
            except Exception:
                return None
        return None

    def update_shop_process(
        self,
        pid: int,
        create_time: float,
        service_pseudonym: str,
    ) -> Optional[EventSample]:
        """Checks if shop-api restarted based on PID or process creation time."""
        if self.last_shop_pid is not None:
            if pid != self.last_shop_pid or create_time != self.last_shop_create_time:
                self.last_shop_pid = pid
                self.last_shop_create_time = create_time
                return EventSample(
                    category="app_restarted",
                    severity="info",
                    source=service_pseudonym,
                    count=1,
                    window_s=2,
                )
        self.last_shop_pid = pid
        self.last_shop_create_time = create_time
        return None

    def check_config_changed(self) -> Optional[EventSample]:
        """Checks if the .env configuration hash changed."""
        current_hash = self._compute_env_hash()
        if self.last_env_hash is not None and current_hash is not None:
            if current_hash != self.last_env_hash:
                self.last_env_hash = current_hash
                return EventSample(
                    category="config_changed",
                    severity="info",
                    source=self.host_pseudonym,
                    count=1,
                    window_s=2,
                )
        if self.last_env_hash is None and current_hash is not None:
            self.last_env_hash = current_hash
        return None

    def scan_for_new_processes(self) -> List[EventSample]:
        """Detects new processes and emits new_process events with pseudonyms."""
        events: List[EventSample] = []
        try:
            current_procs = list(psutil.process_iter(["pid", "name"]))
            for p in current_procs:
                pid = p.info["pid"]
                if pid not in self.known_pids:
                    self.known_pids.add(pid)
                    p_name = p.info.get("name") or f"proc_{pid}"
                    proc_pseudonym = self.pseudonym_mgr.get_or_create("proc", f"{p_name}_{pid}")
                    events.append(
                        EventSample(
                            category="new_process",
                            severity="info",
                            source=proc_pseudonym,
                            count=1,
                            window_s=2,
                        )
                    )
        except Exception as e:
            logger.debug(f"Process scan exception: {e}")
        return events
