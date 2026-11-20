"""
contracts/payload.py
Airlock v1 Data Contracts.
Re-exports and provides aliases for models in contracts/models.py
ensuring 100% interoperability across Guard, Head Office, and AIOps engines.
"""

from contracts.models import (
    PSEUDONYM_REGEX,
    Pseudonym,
    MetricName,
    EventCategory,
    SeverityLevel,
    LogLevel,
    HealthState,
    TimeWindow,
    MetricSample,
    EventSample,
    LogPatternSample,
    GuardHealth,
    AirlockPayload,
    IngestReceipt,
    ActionIntent,
    Checkpoint,
    SignalEvidence,
    ActionRecommendation,
    Incident,
    HealthTransition,
    RevealRequest,
    WSMessage,
)

from enum import Enum

class ActionType(str, Enum):
    KILL_PROCESS = "kill_process"
    BLOCK_IP = "block_ip"
    RESTART_SERVICE = "restart_service"
    INVESTIGATE = "investigate"

# Semantic Aliases for Guard modules
PayloadV1 = AirlockPayload
SignedReceipt = IngestReceipt
MetricItem = MetricSample
EventItem = EventSample
LogPatternItem = LogPatternSample
HealthInfo = GuardHealth
WindowInfo = TimeWindow
Severity = SeverityLevel

__all__ = [
    "PSEUDONYM_REGEX",
    "Pseudonym",
    "MetricName",
    "EventCategory",
    "SeverityLevel",
    "Severity",
    "LogLevel",
    "HealthState",
    "TimeWindow",
    "WindowInfo",
    "MetricSample",
    "MetricItem",
    "EventSample",
    "EventItem",
    "LogPatternSample",
    "LogPatternItem",
    "GuardHealth",
    "HealthInfo",
    "AirlockPayload",
    "PayloadV1",
    "IngestReceipt",
    "SignedReceipt",
    "ActionIntent",
    "Checkpoint",
    "SignalEvidence",
    "ActionRecommendation",
    "Incident",
    "HealthTransition",
    "RevealRequest",
    "WSMessage",
]
