import json
from pathlib import Path
import pytest
import jsonschema
from pydantic import ValidationError

from contracts.payload import (
    PayloadV1,
    MetricItem,
    EventItem,
    LogPatternItem,
    HealthInfo,
    WindowInfo,
    MetricName,
    EventCategory,
    Severity,
    LogLevel,
    SignedReceipt,
    ActionIntent,
    ActionType,
)

SCHEMA_PATH = Path("contracts/payload.schema.json")
EXAMPLES_DIR = Path("contracts/examples")


@pytest.fixture(scope="module")
def json_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_file_exists_and_is_valid(json_schema):
    assert json_schema["title"] == "AirlockPayloadV1"
    assert json_schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "filename",
    [
        "01_normal_window.json",
        "02_auth_failure_burst.json",
        "03_battery_power_alert.json",
    ],
)
def test_examples_against_jsonschema_and_pydantic(filename, json_schema):
    filepath = EXAMPLES_DIR / filename
    assert filepath.exists(), f"Missing example file: {filename}"
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Validate against JSON schema
    jsonschema.validate(instance=data, schema=json_schema)

    # 2. Validate against Pydantic model
    payload = PayloadV1.model_validate(data)
    assert payload.schema_version == "airlock.v1"
    dumped = payload.model_dump(by_alias=True)
    assert dumped["schema"] == "airlock.v1"


def test_reject_unknown_extra_fields():
    with open(EXAMPLES_DIR / "01_normal_window.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["leak_secret"] = "password123"
    with pytest.raises(ValidationError):
        PayloadV1.model_validate(data)


def test_reject_free_text_or_raw_ip():
    with open(EXAMPLES_DIR / "01_normal_window.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["metrics"][0]["source"] = "192.168.1.50"
    with pytest.raises(ValidationError):
        PayloadV1.model_validate(data)


def test_reject_unlisted_metric_name():
    with open(EXAMPLES_DIR / "01_normal_window.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["metrics"][0]["name"] = "unapproved_speed"
    with pytest.raises(ValidationError):
        PayloadV1.model_validate(data)


def test_reject_raw_username_in_actor():
    with open(EXAMPLES_DIR / "02_auth_failure_burst.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    data["events"][0]["actor"] = "root_admin"
    with pytest.raises(ValidationError):
        PayloadV1.model_validate(data)


def test_signed_receipt_model():
    receipt = SignedReceipt(
        payload_id="0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
        sha256="sha256:112233445566",
        received_at="2026-11-21T04:12:09Z",
        status="stored",
    )
    assert receipt.status == "stored"


def test_action_intent_model():
    intent = ActionIntent(
        intent_id="act-1234",
        tenant_id="acme",
        action="kill_process",
        target="proc-1a2b3c4d",
        timestamp="2026-11-21T04:12:10Z",
        signature="sig-hmac-test",
        rollback_window_s=120,
    )
    assert intent.action == "kill_process"
    assert intent.rollback_window_s == 120
