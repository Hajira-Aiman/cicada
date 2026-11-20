# Head-Office Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the multi-database setup, frozen contract examples, regional ingest services (`ingest-in` :8001, `ingest-eu` :8002), and live WebSocket API (:8000) for Sahiti's Head-Office Backend.

**Architecture:** Multi-database tier (`airlock_core`, `airlock_in`, `airlock_eu`) running on Docker PostgreSQL 16 (with SQLite/memory fallback), parameter-driven FastAPI regional ingest validating HMAC signatures and strict `airlock.v1` schemas with idempotent inserts, and `hq/api` broadcasting live telemetry updates to frontend WebSocket subscribers.

**Tech Stack:** Python 3.13/3.14, FastAPI, Uvicorn, Pydantic v2, Psycopg 3 (with binary and connection pool), Docker PostgreSQL 16, HTTPX, Pytest.

**Spec:** [docs/superpowers/specs/2026-11-20-headoffice-backend-design.md](file:///data/Projects/cicada/docs/superpowers/specs/2026-11-20-headoffice-backend-design.md)

## Global Constraints

- Python 3.11+ using FastAPI, Pydantic v2 with `extra="forbid"` on every contract model.
- Port allocations: `hq-api` on 8000, `ingest-in` on 8001, `ingest-eu` on 8002, PostgreSQL on 5432.
- All timestamps MUST be ISO-8601 UTC ending with `Z`.
- HMAC-SHA256 signature calculated over exact payload JSON bytes using the guard secret.
- Strict data residency: India data (`acme`, `contoso`) lives only in `airlock_in`; Europe data (`globex`) lives only in `airlock_eu`. Zero cross-region replication.
- Ingest insertion is strictly idempotent via `payload_id`.

## Review Focus

1. **Replayed Payload:** Ingesting a previously stored `payload_id` MUST return 200 with `status: "duplicate"` and NOT create duplicate metric rows.
2. **Clock Skew:** A payload with timestamp difference $> 300\text{ s}$ from server UTC time MUST be rejected with HTTP 400.
3. **Signature Mismatch:** A payload with an invalid or tampered HMAC signature MUST be rejected with HTTP 401.
4. **Unknown Guard:** A payload citing a `guard_id` not registered in `airlock_core.guards` MUST be rejected with HTTP 401.
5. **Schema Violation:** A payload containing unexpected or unauthorized fields MUST be rejected with HTTP 422.

---

### Task 1: Multi-Database Provisioning & Schema Initialization (T0)

**Files:**
- Create: `scripts/init_postgres.sql`
- Create: `scripts/init_postgres.sh`
- Create: `hq/db.py`
- Test: `tests/test_db_provisioning.py`

**Interfaces:**
- Consumes: PostgreSQL connection credentials from `.env` (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`).
- Produces: `get_db_connection(db_name: str)`, `init_all_databases()`, `register_guard(...)`, `lookup_guard(guard_id: str) -> Optional[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_provisioning.py
import pytest
from hq.db import init_all_databases, lookup_guard, register_guard, execute_query

def test_database_initialization_and_guard_lookup():
    init_all_databases()
    register_guard("airlock_core", "guard-test-01", "globex", "secret-test-key")
    guard = lookup_guard("guard-test-01")
    assert guard is not None
    assert guard["tenant_id"] == "globex"
    assert guard["hmac_secret"] == "secret-test-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_db_provisioning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hq.db'`

- [ ] **Step 3: Implement SQL schema, Docker provisioning script, and `hq/db.py`**

- In `scripts/init_postgres.sql`, write DDL for:
  - `airlock_core`: tables `tenants`, `guards`, `users`, `audit_log`.
  - `airlock_in` & `airlock_eu`: tables `payloads`, `metrics`, `events`, `receipts`.
- In `scripts/init_postgres.sh`, start docker container `airlock-postgres` (if not running) and execute `init_postgres.sql`.
- In `hq/db.py`, implement connection pooling with Psycopg 3 and transparent SQLite in-memory fallback for isolated pytest environments.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_db_provisioning.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/init_postgres.sql scripts/init_postgres.sh hq/db.py tests/test_db_provisioning.py
git commit -m "feat(hq): add multi-database schema and db helper with fallback"
```

---

### Task 2: Contract Deliverables & Frozen JSON Examples (T1)

**Files:**
- Modify: `contracts/models.py`
- Create: `contracts/examples/payload_sample.json`
- Create: `contracts/examples/receipt_sample.json`
- Create: `contracts/examples/action_intent_sample.json`
- Create: `contracts/examples/reveal_request_sample.json`
- Create: `contracts/examples/ws_message_sample.json`
- Test: `tests/test_contract_examples.py`

**Interfaces:**
- Consumes: Pydantic models from `contracts/models.py`.
- Produces: `RevealRequest`, `WSMessage` models and frozen JSON mock examples.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contract_examples.py
import json
from pathlib import Path
from contracts.models import AirlockPayload, IngestReceipt, ActionIntent, RevealRequest, WSMessage

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_contract_examples.py -v`
Expected: FAIL with `cannot import name 'RevealRequest'`

- [ ] **Step 3: Implement models and JSON example fixtures**

- Add `RevealRequest` and `WSMessage` to `contracts/models.py`.
- Write valid JSON fixtures in `contracts/examples/` with realistic sample data for Shop A (Acme) and Shop B (Globex).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_contract_examples.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contracts/models.py contracts/examples/ tests/test_contract_examples.py
git commit -m "feat(contracts): add reveal request, ws models and frozen json fixtures"
```

---

### Task 3: Regional Ingest Service (T2)

**Files:**
- Create: `hq/ingest/main.py`
- Create: `hq/ingest/service.py`
- Test: `tests/test_headoffice_ingest.py`

**Interfaces:**
- Consumes: `hq/db.py` (`lookup_guard`, `store_payload_and_metrics`), `contracts/models.py` (`AirlockPayload`, `IngestReceipt`).
- Produces: `POST /ingest` endpoint on port 8001 (`REGION=in`) and port 8002 (`REGION=eu`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_headoffice_ingest.py
import json, hmac, hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from hq.ingest.main import create_ingest_app

@pytest.mark.anyio
async def test_ingest_verification_and_receipt():
    app = create_ingest_app(region="eu")
    transport = ASGITransport(app=app)
    # create valid payload dict for globex guard
    # compute HMAC signature and headers
    # post to /ingest
    # assert status == 200, status == "stored"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_headoffice_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hq.ingest'`

- [ ] **Step 3: Implement Ingest Service in `hq/ingest/main.py` & `hq/ingest/service.py`**

- Read `X-Airlock-Guard-ID`, `X-Airlock-Signature`, `X-Airlock-Timestamp`.
- Lookup guard secret; verify HMAC-SHA256 signature.
- Check timestamp freshness ($|t - \text{now}| \le 300\text{ s}$).
- Validate `AirlockPayload` schema.
- Insert payload with `ON CONFLICT DO NOTHING`.
- Store metric and event rows.
- Publish notification payload to pub/sub broadcaster.
- Return `IngestReceipt`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_headoffice_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hq/ingest/ tests/test_headoffice_ingest.py
git commit -m "feat(hq/ingest): implement regional ingest service with hmac and schema validation"
```

---

### Task 4: Head-Office API & WebSocket Broadcaster (T3)

**Files:**
- Create: `hq/api/main.py`
- Create: `hq/api/broadcaster.py`
- Test: `tests/test_headoffice_websocket.py`

**Interfaces:**
- Consumes: Pub/sub notification events from `hq/ingest/service.py`.
- Produces: `GET /health`, `WebSocket /ws/live` on port 8000.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_headoffice_websocket.py
import pytest
from httpx import AsyncClient, ASGITransport
from hq.api.main import app
from hq.api.broadcaster import broadcaster

@pytest.mark.anyio
async def test_hq_api_health_and_websocket_broadcast():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_headoffice_websocket.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hq.api'`

- [ ] **Step 3: Implement `hq/api/main.py` and `broadcaster.py`**

- Build `Broadcaster` managing connected WebSocket clients.
- Implement `/ws/live` accepting WebSocket connections.
- Broadcast new metrics and events to all connected clients.
- Provide `/api/tenants` and `/health` endpoints.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_headoffice_websocket.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add hq/api/ tests/test_headoffice_websocket.py
git commit -m "feat(hq/api): implement hq api and live websocket broadcaster"
```

---

### Task 5: Orchestration Script & End-to-End Integration Verification

**Files:**
- Create: `scripts/run_head_office.sh`
- Test: `tests/test_headoffice_integration.py`

**Interfaces:**
- Consumes: `tools/simulate.py`, `hq/ingest/main.py`, `hq/api/main.py`.
- Produces: Full working Head-Office stack (:8000, :8001, :8002).

- [ ] **Step 1: Write the failing end-to-end integration test**

```python
# tests/test_headoffice_integration.py
import pytest
from tools.simulate import SimulatedGuardState, compute_hmac_signature

@pytest.mark.anyio
async def test_end_to_end_head_office_pipeline():
    # 1. Start simulated guard for Globex
    # 2. Post to ingest-eu (:8002)
    # 3. Assert receipt status is "stored"
    # 4. Re-post same payload -> Assert status is "duplicate"
    # 5. Verify live websocket received the telemetry update
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_headoffice_integration.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `scripts/run_head_office.sh` and ensure E2E integration works**

- Provide clean launcher script starting Postgres, `ingest-in`, `ingest-eu`, and `hq-api`.
- Run complete test cycle.

- [ ] **Step 4: Run all tests to verify 100% pass rate**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_head_office.sh tests/test_headoffice_integration.py
git commit -m "feat(hq): complete head office end-to-end pipeline and runner script"
```
