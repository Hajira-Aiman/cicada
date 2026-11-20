"""
contracts/payload.py: Airlock v1 Data Contracts
Strict allow-list telemetry envelopes, receipts, and remediation intents.
Extra fields are strictly forbidden to ensure zero accidental leaks.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MetricName(str, Enum):
    CPU_PCT = "cpu_pct"
    MEM_PCT = "mem_pct"
    DISK_PCT = "disk_pct"
    NET_IN_KBPS = "net_in_kbps"
    NET_OUT_KBPS = "net_out_kbps"
    LATENCY_MS = "latency_ms"
    PACKET_LOSS_PCT = "packet_loss_pct"
    SERVICE_UP = "service_up"
    BATTERY_PCT = "battery_pct"
    ON_BATTERY = "on_battery"
    BATTERY_MIN_LEFT = "battery_min_left"


class EventCategory(str, Enum):
    AUTH_FAILURE_BURST = "auth_failure_burst"
    LOGIN_AFTER_FAILURES = "login_after_failures"
    HONEYPOT_HIT = "honeypot_hit"
    ODD_HOUR_LOGIN = "odd_hour_login"
    SERVICE_DOWN = "service_down"
    NEW_LOG_PATTERN = "new_log_pattern"
    LOG_PATTERN_SPIKE = "log_pattern_spike"
    POWER_ON_BATTERY = "power_on_battery"
    SECRET_REDACTED = "secret_redacted"
    APP_RESTARTED = "app_restarted"
    VERSION_CHANGED = "version_changed"
    CONFIG_CHANGED = "config_changed"
    NEW_PROCESS = "new_process"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class WindowInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str = Field(description="ISO 8601 UTC timestamp")
    end: str = Field(description="ISO 8601 UTC timestamp")
    source_tz: str = Field(default="Asia/Kolkata", description="Source timezone name")


class MetricItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: MetricName
    source: str = Field(pattern=r"^(host|src|user|proc)-[0-9a-f]{8}$")
    avg: float
    max: float


class EventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: EventCategory
    severity: Severity
    source: str = Field(pattern=r"^(host|src|user|proc)-[0-9a-f]{8}$")
    actor: Optional[str] = Field(default=None, pattern=r"^(host|src|user|proc)-[0-9a-f]{8}$")
    count: int = Field(ge=1)
    window_s: int = Field(ge=1)


class LogPatternItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern_id: str = Field(pattern=r"^tpl-[0-9a-f]{4,16}$")
    level: LogLevel
    count: int = Field(ge=1)
    is_new: bool = False


class HealthInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    guard_version: str
    guard_cpu_pct: float
    guard_mem_mb: float
    buffer_depth: int = Field(ge=0)
    config_ok: bool
    canaries_planted: int = Field(ge=0)
    secrets_redacted: int = Field(ge=0)


class PayloadV1(BaseModel):
    """
    Airlock v1 telemetry envelope.
    Strict allow-list: extra='forbid' prevents unlisted fields from leaving the environment.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="airlock.v1", alias="schema")
    payload_id: str = Field(description="UUID v4 identifier")
    tenant_id: str
    guard_id: str
    seq: int = Field(ge=1)
    prev_hash: str = Field(description="SHA-256 of preceding payload or 'GENESIS'")
    policy_version: str
    sent_at: str = Field(description="ISO 8601 UTC timestamp")
    window: WindowInfo
    metrics: List[MetricItem] = Field(default_factory=list)
    events: List[EventItem] = Field(default_factory=list)
    log_patterns: List[LogPatternItem] = Field(default_factory=list)
    health: HealthInfo


class SignedReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload_id: str
    sha256: str
    received_at: str
    status: str = Field(description="'stored' or 'duplicate'")


class ActionType(str, Enum):
    KILL_PROCESS = "kill_process"
    RESTART_SERVICE = "restart_service"
    BLOCK_SOURCE = "block_source"
    DRY_RUN = "dry_run"


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    tenant_id: str
    action: ActionType
    target: str = Field(pattern=r"^(host|src|user|proc)-[0-9a-f]{8}$|^shop-api$")
    why: str
    risk: Severity = Severity.LOW
    reversible: bool = True
    rollback: str
    dry_run: bool = False
    issued_at: str
    signature: str
