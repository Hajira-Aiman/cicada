import hashlib
import json
import pytest
from contracts.models import AirlockPayload
from tools.simulate import SimulatedGuardState, compute_hmac_signature


def test_simulate_normal_payload():
    guard = SimulatedGuardState(
        tenant_id="globex",
        guard_id="guard-globex-01",
        secret="test-secret-1234",
    )
    p1 = guard.generate_payload(scenario="normal")
    assert p1["schema"] == "airlock.v1"
    assert p1["tenant_id"] == "globex"
    assert p1["seq"] == 0
    assert p1["prev_hash"] == "sha256:0000000000000000"

    # Verify validity with Pydantic contract
    validated = AirlockPayload.model_validate(p1)
    assert validated.tenant_id == "globex"

    # Verify signature
    p_bytes = json.dumps(p1, sort_keys=True).encode("utf-8")
    sig = compute_hmac_signature(p_bytes, "test-secret-1234")
    assert isinstance(sig, str) and len(sig) == 64


def test_simulate_hash_chain():
    guard = SimulatedGuardState(
        tenant_id="globex",
        guard_id="guard-globex-01",
        secret="test-secret-1234",
    )
    p1 = guard.generate_payload(scenario="normal")
    p2 = guard.generate_payload(scenario="normal")

    assert p2["seq"] == 1
    # p2's prev_hash should match SHA-256 of p1
    p1_bytes = json.dumps(p1, sort_keys=True).encode("utf-8")
    expected_p1_hash = "sha256:" + hashlib.sha256(p1_bytes).hexdigest()
    assert p2["prev_hash"] == expected_p1_hash


def test_simulate_cpu_spike_scenario():
    guard = SimulatedGuardState("globex", "guard-01", "sec")
    payload = guard.generate_payload(scenario="cpu_spike")
    cpu_sample = next(m for m in payload["metrics"] if m["name"] == "cpu_pct")
    assert cpu_sample["avg"] >= 90.0


def test_simulate_latency_scenario():
    guard = SimulatedGuardState("globex", "guard-01", "sec")
    payload = guard.generate_payload(scenario="latency")
    lat_sample = next(m for m in payload["metrics"] if m["name"] == "latency_ms")
    assert lat_sample["avg"] >= 400.0


def test_simulate_login_burst_scenario():
    guard = SimulatedGuardState("globex", "guard-01", "sec")
    payload = guard.generate_payload(scenario="login_burst")
    assert len(payload["events"]) == 1
    assert payload["events"][0]["category"] == "auth_failure_burst"
    assert payload["events"][0]["count"] == 50


def test_simulate_kill_chain_progression():
    guard = SimulatedGuardState("globex", "guard-01", "sec")
    p1 = guard.generate_payload(scenario="kill_chain")
    p2 = guard.generate_payload(scenario="kill_chain")
    p3 = guard.generate_payload(scenario="kill_chain")
    p4 = guard.generate_payload(scenario="kill_chain")

    assert p1["events"][0]["category"] == "auth_failure_burst"
    assert p2["events"][0]["category"] == "login_after_failures"
    cpu_p3 = next(m for m in p3["metrics"] if m["name"] == "cpu_pct")
    assert cpu_p3["avg"] >= 95.0
    net_p4 = next(m for m in p4["metrics"] if m["name"] == "net_out_kbps")
    assert net_p4["avg"] >= 900.0
