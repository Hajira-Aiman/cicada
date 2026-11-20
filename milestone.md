# Milestones & Delivery Tracker: Tenant 1 (Shop A / Acme)

This document tracks all deliverables for **Tenant 1 (Shop A "Acme", Tier 1 Guard & Local Environment)** across all hackathon phases.

---

## Progress Overview
- **Overall Completion:** 50% (Pre-requisites, Contracts, Thin Slice, and Cross-Branch HQ Integration Complete)
- **Current Phase:** Phase 3: Core Privacy & Local Engine (T3-T16)
- **Target Branch:** `hajira`

---

## Remote Branch Integration Status
- [x] **Branch `origin/sahiti`:** Pulled shared `contracts/models.py`, sample contract payloads, `hq/` backend (`ingest`, `api`, `db.py`), `scripts/`, and integration tests.
- [x] **Branch `origin/Adithya`:** AIOps baseline & health engine (`hq/aiops/`) and multi-guard simulator (`tools/simulate.py`) pulled and integrated.
- [x] **Branch `origin/anisa`:** Checked; currently on base commit (frontend screens pending H12 handoff).
- [x] **Cross-Branch Verification:** Verified Guard delivers authentic signed payloads to Head Office Ingest with full database persistence ([test_guard_to_headoffice.py](file:///C:/Users/hajir/OneDrive/Desktop/Projects/cicada26/tests/test_guard_to_headoffice.py)). All 34 tests pass.

---

## Phase 0: Pre-requisites & Environment Setup
- [x] **Task 0.1: Python Environment & Dependencies**
  - [x] Identify Python executable (`py` / Python 3.14 / 3.11+)
  - [x] Check / Install required libraries: `fastapi`, `uvicorn`, `pydantic>=2.0`, `psutil`, `httpx`, `drain3`, `detect-secrets`, `pytest`, `python-dotenv`
  - [x] Verify test runner (`py -m pytest`)
- [x] **Task 0.2: Project Directory Structure**
  - [x] Initialize `contracts/` directory
  - [x] Initialize `guard/` and submodules (`collectors/`, `engine/`, `storage/`, `api/`)
  - [x] Initialize `shop-api/` and `shop-api/logs/`
  - [x] Initialize `chaos/`
  - [x] Initialize `tests/`
- [x] **Task 0.3: Environment Configuration**
  - [x] Create `.env.example`
  - [x] Create active `.env` for Tenant 1 (`acme`, ports 7000, 9000, 9100, local keys)
- [x] **Task 0.4: NPU Hardware & Lemonade AI Verification (T0)**
  - [x] Detect `AMD Ryzen AI 7 350` and `NPU Compute Accelerator Device`
  - [x] Connect to Lemonade Server running on port `13305`
  - [x] Install `ryzenai-llm:npu` backend
  - [x] Download & load `Qwen2.5-0.5B-Instruct-Hybrid` NPU model
  - [x] Verify chat completions inference via `/v1/chat/completions` ([shop_ai.py](file:///C:/Users/hajir/OneDrive/Desktop/Projects/cicada26/guard/shop_ai.py))

---

## Phase 1 (H0–H2): Contracts & Protocol Models
- [x] **Task 1.1: Frozen Payload JSON Schema**
  - [x] Create `contracts/payload.schema.json` according to Hackathon Plan v1
  - [x] Enforce strict allow-list: `additionalProperties: false`, fixed metric names, fixed event categories, pseudonym regex `^(host|src|user|proc)-[0-9a-f]{8}$`
- [x] **Task 1.2: Pydantic Data Contracts**
  - [x] Implement `contracts/models.py` with `ConfigDict(extra="forbid")`
  - [x] Models: `MetricItem`, `EventItem`, `LogPatternItem`, `HealthInfo`, `PayloadV1`, `SignedReceipt`, `ActionIntent`
  - [x] Unit tests in `tests/test_contracts.py` ensuring invalid fields and unredacted free text are strictly rejected

---

## Phase 2 (H2–H6): Thin Slice End-to-End
- [x] **Task 2.1: Demo Target Application (`shop-api/`)** (Scaffolded, full implementation in H6-H12 T16)
- [x] **Task 2.2: Basic Guard Telemetry Collector**
  - [x] Collect `cpu_pct` via `psutil` every 2s
  - [x] Construct valid `airlock.v1` payload with UTC + `source_tz`
- [x] **Task 2.3: Payload Builder & HMAC Signature**
  - [x] Build schema-valid payload with pseudonymous host identifier
  - [x] Sign payload with HMAC-SHA256 over body + timestamp using `GUARD_SECRET_KEY`
- [x] **Task 2.4: Egress & Ingest Receipt Handling**
  - [x] Outbound POST sender to regional ingest (`http://localhost:8001/v1/ingest`)
  - [x] Verified against `tests/mock_ingest.py`
  - [x] Receipt verification and status checking
- [x] **Task 2.5: Thin Slice Verification Test**
  - [x] Automated end-to-end integration test validating collection -> build -> sign -> dispatch -> receipt ([test_thin_slice.py](file:///C:/Users/hajir/OneDrive/Desktop/Projects/cicada26/tests/test_thin_slice.py))

---

## Phase 3 (H6–H12): Core Privacy Engine & Local Observability
- [ ] **Task 3.1: Local Raw Store (`raw_store.py`)**
  - [ ] SQLite raw telemetry & log database (`data/raw.db`)
  - [ ] Configurable 24-hour retention countdown and auto-cleanup
  - [ ] Zero egress verification
- [ ] **Task 3.2: Secret Scrubber & Canary Tripwires (`scrubber.py`)**
  - [ ] Regex & detect-secrets scrubbing for AWS keys, JWTs, passwords, card numbers
  - [ ] Canary planter inserting fake keys (`AKIACANARY...`) into raw stream every 30s
  - [ ] Pre-send tripwire check blocking any outgoing canary or leak
- [ ] **Task 3.3: Drain3 Log Pattern Mining (`pattern_miner.py`)**
  - [ ] Extract patterns and template IDs (e.g. `tpl-3fa1`) from raw log stream
  - [ ] Maintain cluster state and count pattern occurrences
  - [ ] Flag `is_new: true` for newly discovered templates
- [ ] **Task 3.4: Window Aggregation & Local Anomaly Detectors (`detectors.py`)**
  - [ ] 2-second tumbling windows with avg, max, and event counts
  - [ ] Login failure burst detector (>30 in 60s -> `auth_failure_burst`)
  - [ ] Honeypot user detector (`admin_backup` -> `honeypot_hit`)
  - [ ] Odd-hour login detector (3:00 AM shop local time)
  - [ ] Power on battery detector via `psutil.sensors_battery()`
  - [ ] Change tracker (`app_restarted`, `config_changed`)
- [ ] **Task 3.5: Pseudonymization Engine & Local Reveal Table (`pseudonymizer.py`)**
  - [ ] HMAC-SHA256 masking (`host-`, `src-`, `user-`, `proc-`)
  - [ ] Local encrypted/private SQLite reveal table (`data/reveal.db`)
- [ ] **Task 3.6: Local Shop Screen API (`guard/api.py` on Port 9000)**
  - [ ] `/api/status`: health, buffer depth, version, retention countdown
  - [ ] `/api/raw-logs`: raw logs with unmasked secrets (Shop view only)
  - [ ] `/api/egress`: live ledger view with payload hashes and receipt checks
  - [ ] `/api/reveal-requests`: approve/reject reveal requests from Head Office

---

## Phase 4 (H12–H15): Resilience, Outages & Checkpoints
- [ ] **Task 4.1: Offline Buffering & Resumption**
  - [ ] Verify guard buffers cleanly during network cut or ingest downtime
  - [ ] Verify FIFO drain upon reconnection with zero data loss and zero duplicates
- [ ] **Task 4.2: Hash-Chained Audit Ledger**
  - [ ] Sequential hash chaining: `prev_hash` validation
  - [ ] Sequence number monotonic tracking and gap detection
- [ ] **Task 4.3: 60-Second Checkpoint Generator (`checkpoints.py`)**
  - [ ] Cumulative SHA-256 calculation over sent payload hashes
  - [ ] `/api/checkpoint` endpoint for sent-vs-received tamper proofing

---

## Phase 5 (H15–H20): Safe Remediation & Chaos Agent
- [ ] **Task 5.1: Action Executor (`executor.py`)**
  - [ ] Pull signed action intents from Head Office
  - [ ] Policy gate: tenant permissions, allowed commands (`kill_process`, `restart_service`, `block_source`)
  - [ ] Dry-run endpoint support
  - [ ] Target resolution via local pseudonym table
  - [ ] Execution with 120s rollback timer and audit logging
- [ ] **Task 5.2: Local Chaos Agent (`chaos/` on Port 9100)**
  - [ ] CPU spike generator
  - [ ] Simulated latency / loss
  - [ ] Brute-force failed login generator
  - [ ] Try-to-leak payload injector
  - [ ] Battery disconnect simulation
- [ ] **Task 5.3: Shop AI Assistant Integration (`shop_ai.py`)**
  - [ ] Local OpenAI client targeting Lemonade (port 13305) or CPU fallback
  - [ ] Function calling over local SQLite raw data: `search_raw_logs`, `recent_auth_failures`

---

## Phase 6 (H20–H24): Rehearsal & Live Verification
- [ ] **Task 6.1: Full Scenario Verification**
  - [ ] Try-to-leak test (secrets masked, canaries blocked)
  - [ ] Region outage & resume test (reconciliation sent == received)
  - [ ] Brute-force login detection test
  - [ ] Chaos CPU spike & kill-process remediation test
  - [ ] Pseudonym reveal request & approval flow test
- [ ] **Task 6.2: Final Code Freeze & Documentation**
  - [ ] Run complete test suite (`py -m pytest tests/ -v`)
  - [ ] Update demo runbook in `README.md`
