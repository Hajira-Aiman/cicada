# tests/test_contract_examples.py
import json
from pathlib import Path
from contracts.models import (
    AirlockPayload,
    IngestReceipt,
    ActionIntent,
    RevealRequest,
    WSMessage,
)

def test_frozen_json_examples_conform_to_contracts():
    examples_dir = Path("contracts/examples")
    payload = AirlockPayload.model_validate_json((examples_dir / "payload_sample.json").read_text())
    receipt = IngestReceipt.model_validate_json((examples_dir / "receipt_sample.json").read_text())
    intent = ActionIntent.model_validate_json((examples_dir / "action_intent_sample.json").read_text())
    reveal = RevealRequest.model_validate_json((examples_dir / "reveal_request_sample.json").read_text())
    ws_msg = WSMessage.model_validate_json((examples_dir / "ws_message_sample.json").read_text())

    assert payload.schema_version == "airlock.v1"
    assert receipt.status in ("stored", "duplicate")
    assert intent.action in ("kill_process", "block_ip", "restart_service")
    assert reveal.pseudonym.startswith("src-")
    assert ws_msg.event_type in ("metrics_batch", "health_change", "incident_alert")
