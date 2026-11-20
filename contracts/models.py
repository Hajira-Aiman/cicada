"""
contracts/models.py
Shared contract models for Airlock (airlock.v1).
Strict allow-list schema: extra fields are forbidden.
Free text and unapproved identifiers cannot cross the trust boundary.
"""

from typing import Annotated, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PSEUDONYM_REGEX = r"^(host|src|user|proc)-[0-9a-f]{8}$"
Pseudonym = Annotated[str, StringConstraints(pattern=PSEUDONYM_REGEX)]

MetricName = Literal[
    "cpu_pct",
    "mem_pct",
    "disk_pct",
    "net_in_kbps",
    "net_out_kbps",
    "latency_ms",
    "packet_loss_pct",
    "service_up",
    "battery_pct",
    "on_battery",
    "battery_min_left",
]

EventCategory = Literal[
    "auth_failure_burst",
    "login_after_failures",
    "honeypot_hit",
    "odd_hour_login",
    "service_down",
    "new_log_pattern",
    "log_pattern_spike",
    "power_on_battery",
    "secret_redacted",
    "app_restarted",
    "version_changed",
    "config_changed",
    "new_process",
]

SeverityLevel = Literal["info", "low", "medium", "high", "critical"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
HealthState = Literal["Excellent", "Good", "Fair", "Poor"]


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str  # ISO-8601 UTC with Z (e.g. 2026-11-21T04:12:04Z)
    end: str    # ISO-8601 UTC with Z
    source_tz: str  # e.g. Europe/Berlin or Asia/Kolkata


class MetricSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: MetricName
    source: Pseudonym
    avg: float
    max: float


class EventSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: EventCategory
    severity: SeverityLevel
    source: Pseudonym
    actor: Optional[Pseudonym] = None
    count: int = Field(ge=1)
    window_s: Optional[int] = Field(default=None, ge=1)


class LogPatternSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern_id: str = Field(pattern=r"^tpl-[0-9a-fA-F]+$")
    level: LogLevel
    count: int = Field(ge=1)
    is_new: bool = False


class GuardHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guard_version: str
    guard_cpu_pct: float
    guard_mem_mb: float
    buffer_depth: int = Field(ge=0)
    config_ok: bool
    canaries_planted: int = Field(ge=0)
    secrets_redacted: int = Field(ge=0)


class AirlockPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    schema_version: Literal["airlock.v1"] = Field(
        default="airlock.v1",
        alias="schema",
        serialization_alias="schema",
    )
    payload_id: str
    tenant_id: str
    guard_id: str
    seq: int = Field(ge=0)
    prev_hash: str
    policy_version: str
    sent_at: str  # ISO-8601 UTC with Z
    window: TimeWindow
    metrics: List[MetricSample] = Field(default_factory=list)
    events: List[EventSample] = Field(default_factory=list)
    log_patterns: List[LogPatternSample] = Field(default_factory=list)
    health: GuardHealth


class IngestReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload_id: str
    sha256: str
    received_at: str  # ISO-8601 UTC with Z
    status: Literal["stored", "duplicate"]


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent_id: str
    tenant_id: str
    action: Literal["kill_process", "block_ip", "restart_service"]
    target: str
    timestamp: str  # ISO-8601 UTC with Z
    signature: str
    rollback_window_s: int = Field(default=120, ge=10)


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guard_id: str
    up_to_seq: int = Field(ge=0)
    root: str


class SignalEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    name: str
    value: float
    baseline: float
    z: Optional[float] = None
    contribution_pct: float = Field(ge=0.0, le=100.0)


class ActionRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["kill_process", "block_ip", "restart_service", "investigate"]
    target: Optional[str] = None
    why: str
    risk: Literal["low", "medium", "high"]
    reversible: bool
    rollback: Optional[str] = None


class Incident(BaseModel):
    model_config = ConfigDict(extra="forbid")
    incident_id: str
    tenant_id: str
    title: str
    severity: SeverityLevel
    confidence: float = Field(ge=0.0, le=1.0)
    started_at: str  # ISO-8601 UTC with Z
    affected: List[str] = Field(default_factory=list)
    signals: List[SignalEvidence] = Field(default_factory=list)
    reasoning_path: List[str] = Field(default_factory=list)
    counterfactual: Optional[str] = None
    recommendation: Optional[ActionRecommendation] = None
    narrative: Optional[str] = None


class HealthTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str
    source: Pseudonym
    old_state: HealthState
    new_state: HealthState
    reasons: List[str]
    transition_at: str  # ISO-8601 UTC with Z


class RevealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str
    tenant_id: str
    pseudonym: Pseudonym
    requested_by: str
    reason: str
    requested_at: str  # ISO-8601 UTC with Z
    status: Literal["pending", "approved", "rejected"] = "pending"


class WSMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["metrics_batch", "health_change", "incident_alert", "receipt_ack"]
    tenant_id: str
    timestamp: str  # ISO-8601 UTC with Z
    payload: dict
