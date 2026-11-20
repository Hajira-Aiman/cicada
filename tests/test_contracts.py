import json
import pytest
from pydantic import ValidationError
from contracts.models import (
    AirlockPayload,
    TimeWindow,
    MetricSample,
    EventSample,
    LogPatternSample,
    GuardHealth,
    IngestReceipt,
    ActionIntent,
)


def sample_valid_payload_dict():
    return {
        "schema": "airlock.v1",
        "payload_id": "0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
        "tenant_id": "globex",
        "guard_id": "guard-globex-01",
        "seq": 1042,
        "prev_hash": "sha256:9c1e7a08b3c",
        "policy_version": "sha256:ab1289cf001",
        "sent_at": "2026-11-21T04:12:08Z",
        "window": {
            "start": "2026-11-21T04:12:04Z",
            "end": "2026-11-21T04:12:06Z",
            "source_tz": "Europe/Berlin",
        },
        "metrics": [
            {
                "name": "cpu_pct",
                "source": "host-7f3a1234",
                "avg": 34.2,
                "max": 51.0,
            }
        ],
        "events": [
            {
                "category": "auth_failure_burst",
                "severity": "high",
                "source": "host-7f3a1234",
                "actor": "src-9c2e0011",
                "count": 50,
                "window_s": 60,
            }
        ],
        "log_patterns": [
            {
                "pattern_id": "tpl-3fa1",
                "level": "ERROR",
                "count": 40,
                "is_new": True,
            }
        ],
        "health": {
            "guard_version": "0.1.0",
            "guard_cpu_pct": 1.2,
            "guard_mem_mb": 80.0,
            "buffer_depth": 0,
            "config_ok": True,
            "canaries_planted": 12,
            "secrets_redacted": 3,
        },
    }


def test_valid_payload():
    data = sample_valid_payload_dict()
    payload = AirlockPayload.model_validate(data)
    dumped = payload.model_dump(by_alias=True)
    assert dumped["schema"] == "airlock.v1"
    assert dumped["tenant_id"] == "globex"
    assert dumped["metrics"][0]["name"] == "cpu_pct"
    assert dumped["events"][0]["actor"] == "src-9c2e0011"


def test_reject_extra_fields_in_payload():
    data = sample_valid_payload_dict()
    data["unauthorized_free_text"] = "password=supersecret"
    with pytest.raises(ValidationError):
        AirlockPayload.model_validate(data)


def test_reject_extra_fields_in_nested_metrics():
    data = sample_valid_payload_dict()
    data["metrics"][0]["raw_command"] = "rm -rf /"
    with pytest.raises(ValidationError):
        AirlockPayload.model_validate(data)


def test_reject_raw_ip_as_source():
    data = sample_valid_payload_dict()
    data["metrics"][0]["source"] = "192.168.1.50"
    with pytest.raises(ValidationError):
        AirlockPayload.model_validate(data)


def test_reject_raw_username_as_actor():
    data = sample_valid_payload_dict()
    data["events"][0]["actor"] = "root"
    with pytest.raises(ValidationError):
        AirlockPayload.model_validate(data)


def test_reject_unauthorized_metric_name():
    data = sample_valid_payload_dict()
    data["metrics"][0]["name"] = "custom_unapproved_metric"
    with pytest.raises(ValidationError):
        AirlockPayload.model_validate(data)


def test_receipt_model():
    receipt = IngestReceipt(
        payload_id="0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
        sha256="sha256:abc12345",
        received_at="2026-11-21T04:12:09Z",
        status="stored",
    )
    assert receipt.status == "stored"


def test_action_intent_model():
    intent = ActionIntent(
        intent_id="act-001",
        tenant_id="globex",
        action="block_ip",
        target="src-9c2e0011",
        timestamp="2026-11-21T04:13:00Z",
        signature="hmac-sha256-mock",
        rollback_window_s=900,
    )
    assert intent.action == "block_ip"
