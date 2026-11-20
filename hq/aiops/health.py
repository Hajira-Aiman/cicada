"""
hq/aiops/health.py
Airlock Four-State Health Engine with Hysteresis (Anti-Flapping) and Stale Data Handling.
Health States: Excellent (0) < Good (1) < Fair (2) < Poor (3).
Hysteresis: 6s (3 windows) bad to degrade; 20s (10 windows) good to recover.
Stale Data: 10s -> Fair; 30s -> Poor (Offline).
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from contracts.models import HealthChange, HealthState, HealthTransition

STATE_RANKS: Dict[HealthState, int] = {
    "Excellent": 0,
    "Good": 1,
    "Fair": 2,
    "Poor": 3,
}

RANK_TO_STATE: Dict[int, HealthState] = {v: k for k, v in STATE_RANKS.items()}


class SourceHealthTracker:
    def __init__(self, tenant_id: str, source: str):
        self.tenant_id = tenant_id
        self.source = source
        self.confirmed_state: HealthState = "Excellent"
        self.candidate_state: HealthState = "Excellent"
        self.candidate_duration_steps: int = 0
        self.last_seen_epoch: float = 0.0
        self.last_transition_reasons: List[str] = ["Initial baseline"]
        self.flaps_prevented: int = 0
        self.transitions: List[HealthTransition] = []

    def evaluate(
        self,
        now_epoch: float,
        metrics_by_name: Dict[str, float],
        metric_z_scores: Dict[str, float],
        flagged_anomalies: Set[str],
        event_categories: List[str],
    ) -> HealthState:
        """
        Evaluates immediate raw candidate state and applies anti-flapping hysteresis.
        Returns the confirmed health state.
        """
        raw_reasons: List[str] = []
        raw_rank = 0  # Excellent

        # 1. Stale / Offline check
        if self.last_seen_epoch > 0:
            elapsed = now_epoch - self.last_seen_epoch
            if elapsed >= 30.0:
                raw_rank = max(raw_rank, STATE_RANKS["Poor"])
                raw_reasons.append(f"Collector offline: no heartbeat for {int(elapsed)} s")
            elif elapsed >= 10.0:
                raw_rank = max(raw_rank, STATE_RANKS["Fair"])
                raw_reasons.append(f"Stale data: no heartbeat for {int(elapsed)} s")

        # 2. Critical triggers (Poor)
        if "service_down" in event_categories:
            raw_rank = max(raw_rank, STATE_RANKS["Poor"])
            raw_reasons.append("service_down event received")

        if "honeypot_hit" in event_categories:
            raw_rank = max(raw_rank, STATE_RANKS["Poor"])
            raw_reasons.append("honeypot account triggered")

        latency = metrics_by_name.get("latency_ms", 0.0)
        loss = metrics_by_name.get("packet_loss_pct", 0.0)
        if latency > 1000.0 or loss > 10.0:
            raw_rank = max(raw_rank, STATE_RANKS["Poor"])
            raw_reasons.append(f"Severe network degradation (latency={latency}ms, loss={loss}%)")

        # 3. Fair triggers
        if "auth_failure_burst" in event_categories:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append("auth_failure_burst detected")

        if flagged_anomalies:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append(f"Sustained anomalies: {', '.join(sorted(flagged_anomalies))}")

        cpu = metrics_by_name.get("cpu_pct", 0.0)
        mem = metrics_by_name.get("mem_pct", 0.0)
        disk = metrics_by_name.get("disk_pct", 0.0)

        if cpu > 85.0:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append(f"High CPU utilization: {cpu:.1f}%")
        if mem > 90.0:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append(f"High Memory utilization: {mem:.1f}%")
        if disk > 90.0:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append(f"High Disk utilization: {disk:.1f}%")
        if (latency > 200.0 or loss > 2.0) and raw_rank < STATE_RANKS["Fair"]:
            raw_rank = max(raw_rank, STATE_RANKS["Fair"])
            raw_reasons.append(f"Elevated network latency/loss (latency={latency}ms, loss={loss}%)")

        # 4. Good triggers
        if raw_rank < STATE_RANKS["Fair"]:
            elevated = [m for m, z in metric_z_scores.items() if 2.0 <= abs(z) < 3.0]
            if elevated:
                raw_rank = max(raw_rank, STATE_RANKS["Good"])
                raw_reasons.append(f"Minor metric deviation: {', '.join(elevated)}")

        if raw_rank == 0:
            raw_reasons.append("All metrics within normal baseline")

        raw_state = RANK_TO_STATE[raw_rank]

        # 5. Anti-Flapping Hysteresis Engine
        # Hysteresis steps (assuming 2s window):
        # Worse transition requires 3 steps (6s)
        # Better transition requires 10 steps (20s)
        current_rank = STATE_RANKS[self.confirmed_state]

        if raw_state == self.confirmed_state:
            self.candidate_state = raw_state
            self.candidate_duration_steps = 0
            return self.confirmed_state

        if raw_state == self.candidate_state:
            self.candidate_duration_steps += 1
        else:
            self.candidate_state = raw_state
            self.candidate_duration_steps = 1

        target_steps = 3 if raw_rank > current_rank else 10

        if self.candidate_duration_steps >= target_steps:
            # Transition accepted
            old_state = self.confirmed_state
            self.confirmed_state = raw_state
            self.last_transition_reasons = raw_reasons
            now_iso = datetime.fromtimestamp(now_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            transition = HealthChange(
                tenant_id=self.tenant_id,
                source=self.source,
                state=self.confirmed_state,
                old_state=old_state,
                reasons=raw_reasons,
                at=now_iso,
            )
            self.transitions.append(transition)
            self.candidate_duration_steps = 0
        else:
            # Flap suppressed by hysteresis
            self.flaps_prevented += 1

        return self.confirmed_state


class HealthEngine:
    """Manages health tracking across all sources and tenants."""

    def __init__(self):
        # Key: (tenant_id, source)
        self.sources: Dict[Tuple[str, str], SourceHealthTracker] = {}

    def get_or_create(self, tenant_id: str, source: str) -> SourceHealthTracker:
        key = (tenant_id, source)
        if key not in self.sources:
            self.sources[key] = SourceHealthTracker(tenant_id, source)
        return self.sources[key]

    def process_window(
        self,
        tenant_id: str,
        source: str,
        now_epoch: float,
        metrics_by_name: Dict[str, float],
        metric_z_scores: Dict[str, float],
        flagged_anomalies: Set[str],
        event_categories: List[str],
    ) -> HealthState:
        tracker = self.get_or_create(tenant_id, source)
        tracker.last_seen_epoch = now_epoch
        return tracker.evaluate(
            now_epoch=now_epoch,
            metrics_by_name=metrics_by_name,
            metric_z_scores=metric_z_scores,
            flagged_anomalies=flagged_anomalies,
            event_categories=event_categories,
        )

    def check_stale_all(self, now_epoch: float) -> List[HealthTransition]:
        """Evaluates sources for stale or offline states."""
        new_transitions = []
        for tracker in self.sources.values():
            initial_count = len(tracker.transitions)
            tracker.evaluate(
                now_epoch=now_epoch,
                metrics_by_name={},
                metric_z_scores={},
                flagged_anomalies=set(),
                event_categories=[],
            )
            if len(tracker.transitions) > initial_count:
                new_transitions.extend(tracker.transitions[initial_count:])
        return new_transitions

    @property
    def total_flaps_prevented(self) -> int:
        return sum(t.flaps_prevented for t in self.sources.values())
