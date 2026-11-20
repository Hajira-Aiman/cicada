"""Airlock contract v1: payload (guard->hq), incident + health messages (aiops->everyone). Frozen at H2."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

PSEUDO = r"^(host|src|user|proc)-[0-9a-f]{8}$"
METRIC_NAMES = ["cpu_pct", "mem_pct", "disk_pct", "net_in_kbps", "net_out_kbps", "latency_ms",
                "packet_loss_pct", "service_up", "battery_pct", "on_battery", "battery_min_left"]
EVENT_CATEGORIES = ["auth_failure_burst", "login_after_failures", "honeypot_hit", "odd_hour_login",
                    "service_down", "new_log_pattern", "log_pattern_spike", "power_on_battery",
                    "secret_redacted", "app_restarted", "version_changed", "config_changed", "new_process"]
Severity = Literal["info", "low", "medium", "high", "critical"]
State = Literal["excellent", "good", "fair", "poor"]
MetricName = Literal[tuple(METRIC_NAMES)]
EventCategory = Literal[tuple(EVENT_CATEGORIES)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- payload airlock.v1 (the allow-list) ----
class Window(Strict):
    start: str
    end: str
    source_tz: str

class Metric(Strict):
    name: MetricName
    source: str = Field(pattern=PSEUDO)
    avg: float
    max: float

class Event(Strict):
    category: EventCategory
    severity: Severity
    source: str = Field(pattern=PSEUDO)
    actor: str | None = Field(default=None, pattern=PSEUDO)
    count: int = 1
    window_s: int = 2

class LogPattern(Strict):
    pattern_id: str = Field(pattern=r"^tpl-[0-9a-f]{4}$")
    level: Literal["DEBUG", "INFO", "WARN", "ERROR"]
    count: int
    is_new: bool = False

class GuardHealth(Strict):
    guard_version: str
    guard_cpu_pct: float
    guard_mem_mb: float
    buffer_depth: int
    config_ok: bool
    canaries_planted: int = 0
    secrets_redacted: int = 0

class Payload(Strict):
    schema_: Literal["airlock.v1"] = Field(alias="schema")
    payload_id: str
    tenant_id: str
    guard_id: str
    seq: int
    prev_hash: str
    policy_version: str
    sent_at: str
    window: Window
    metrics: list[Metric] = []
    events: list[Event] = []
    log_patterns: list[LogPattern] = []
    health: GuardHealth


# ---- incident object ----
class Signal(Strict):
    evidence_id: str
    name: str
    value: float
    baseline: float
    z: float | None = None
    contribution_pct: float

class Recommendation(Strict):
    action: Literal["kill_process", "block_source", "restart_service", "investigate"]
    target: str | None = None
    why: str
    risk: Literal["low", "medium", "high"]
    reversible: bool
    rollback: str | None = None

class Incident(Strict):
    incident_id: str
    tenant_id: str
    title: str
    severity: Severity
    confidence: float
    started_at: str
    affected: list[str]
    signals: list[Signal]
    reasoning_path: list[str]
    counterfactual: str | None = None
    recommendation: Recommendation | None = None
    changes_before: list[str] = []
    suppressed_reason: str | None = None
    repeat_count: int = 1
    narrative: str | None = None

# ---- health-state message (WebSocket "health" + history rows) ----
class HealthChange(Strict):
    tenant_id: str
    source: str
    state: State
    old_state: State | None
    reasons: list[str]
    at: str  # UTC ISO-8601 Z
