"""
hq/aiops/baseline.py
Exponentially Weighted Moving Average (EWMA) and Variance baseline engine.
Tracks running mean and spread per (tenant_id, source, metric_name).
Flags anomalies (|z| >= 3.0) persisting for 3 consecutive windows.
Supports temporary threshold elevation via thumbs-down user feedback.
"""

import math
import time
from typing import Dict, Optional, Tuple


class MetricStreamBaseline:
    def __init__(
        self,
        alpha: float = 0.1,
        warmup_points: int = 30,
        epsilon: float = 1e-6,
    ):
        self.alpha = alpha
        self.warmup_points = warmup_points
        self.epsilon = epsilon

        self.count = 0
        self.mean: float = 0.0
        self.variance: float = 0.0
        self.consecutive_anomalies: int = 0
        self.feedback_elevated_until: float = 0.0  # Unix timestamp

    @property
    def std_dev(self) -> float:
        return math.sqrt(max(0.0, self.variance))

    @property
    def is_warmed_up(self) -> bool:
        return self.count >= self.warmup_points

    @property
    def active_z_threshold(self) -> float:
        """Returns 3.5 if thumbs-down feedback is active, else 3.0."""
        if time.time() < self.feedback_elevated_until:
            return 3.5
        return 3.0

    def apply_feedback_thumbs_down(self, duration_s: float = 1800.0):
        """Raises flag threshold from 3.0 to 3.5 for duration_s (default: 30 minutes)."""
        self.feedback_elevated_until = time.time() + duration_s

    def update(self, value: float) -> Tuple[float, float, bool]:
        """
        Updates the baseline with a new observation.
        Returns:
            (mean, z_score, is_flagged_anomaly)
        """
        self.count += 1

        if self.count == 1:
            self.mean = value
            self.variance = 1.0  # Initial baseline variance
            return self.mean, 0.0, False

        # Calculate z-score against established baseline prior to absorbing the new observation
        prior_mean = self.mean
        prior_std = self.std_dev
        z = (value - prior_mean) / (prior_std + self.epsilon)

        # Persistence check
        threshold = self.active_z_threshold
        if abs(z) >= threshold:
            self.consecutive_anomalies += 1
            # Candidate anomaly: damp absorption to prevent baseline contamination
            absorb_alpha = self.alpha * 0.1
        else:
            self.consecutive_anomalies = 0
            absorb_alpha = self.alpha

        # Welford / EWMA update
        delta = value - self.mean
        self.mean += absorb_alpha * delta
        self.variance = (1.0 - absorb_alpha) * (self.variance + absorb_alpha * (delta**2))

        # Flag anomaly if warm and persisted for >= 3 consecutive windows
        is_flagged = self.is_warmed_up and (self.consecutive_anomalies >= 3)
        return self.mean, z, is_flagged


class EWMABaselineManager:
    """Manages baseline streams across all tenants, sources, and metric names."""

    def __init__(self, alpha: float = 0.1, warmup_points: int = 30):
        self.alpha = alpha
        self.warmup_points = warmup_points
        # Key: (tenant_id, source, metric_name)
        self.streams: Dict[Tuple[str, str, str], MetricStreamBaseline] = {}

    def get_or_create(self, tenant_id: str, source: str, metric_name: str) -> MetricStreamBaseline:
        key = (tenant_id, source, metric_name)
        if key not in self.streams:
            self.streams[key] = MetricStreamBaseline(
                alpha=self.alpha,
                warmup_points=self.warmup_points,
            )
        return self.streams[key]

    def record_metric(
        self,
        tenant_id: str,
        source: str,
        metric_name: str,
        value: float,
    ) -> Tuple[float, float, bool]:
        stream = self.get_or_create(tenant_id, source, metric_name)
        return stream.update(value)

    def record_feedback_thumbs_down(self, tenant_id: str, source: str, metric_name: str):
        stream = self.get_or_create(tenant_id, source, metric_name)
        stream.apply_feedback_thumbs_down()
