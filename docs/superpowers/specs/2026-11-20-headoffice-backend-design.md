# Sahiti's Head-Office Backend Design Document (H0–H6)

**Date:** 2026-11-20  
**Owner:** Sahiti (H · Head-Office Backend)  
**Deliverables:** `hq/ingest/`, `hq/api/`, `contracts/examples/`, `scripts/init_postgres.sql`, `tests/test_headoffice_thin_slice.py`  
**Status:** Proposed for Approval  

---

## 1. Intent and Why
Provide the centralized, multi-tenant, region-aware ingestion and API tier for Airlock:
- Enforce cryptographic verification and schema conformity at the trust boundary.
- Support strict tenant data residency across two independent regional databases (`airlock_in` on :8001 and `airlock_eu` on :8002) with zero cross-region replication or failover.
- Ensure idempotent storage (zero loss, zero duplicates) and return signed receipts.
- Deliver real-time WebSocket push (`/ws/live` on :8000) so frontend dashboards reflect telemetry within sub-second latencies.

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- **T0 (H0–H2):** Setup Docker PostgreSQL 16 container (`airlock-postgres` on port 5432) initialized with three databases:
  - `airlock_core`: Tenants (`acme`, `globex`, `contoso`, `guests`), guards, credentials, audit log.
  - `airlock_in`: India region telemetry, receipts, and health states.
  - `airlock_eu`: Europe region telemetry, receipts, and health states.
- **T1 (H0–H2):** Formalize contracts & populate `contracts/examples/`:
  - `contracts/examples/payload_sample.json`
  - `contracts/examples/receipt_sample.json`
  - `contracts/examples/action_intent_sample.json`
  - `contracts/examples/reveal_request_sample.json`
  - `contracts/examples/ws_message_sample.json`
- **T2 (H2–H6):** Build `hq/ingest/main.py`:
  - Reusable parameterized FastAPI app started with `REGION=in` (port 8001) or `REGION=eu` (port 8002).
  - Validation pipeline:
    1. Known guard lookup in `airlock_core.guards`.
    2. Timestamp freshness check: $|t_{\text{sent}} - t_{\text{now}}| \le 300\text{ s}$.
    3. HMAC-SHA256 signature verification over exact payload bytes.
    4. Pydantic `AirlockPayload` schema validation (`extra="forbid"`).
    5. Deduplication insert: `ON CONFLICT (payload_id) DO NOTHING`.
    6. Return signed `IngestReceipt`: `{payload_id, sha256, received_at, status: stored | duplicate}`.
- **T3 (H2–H6):** Build `hq/api/main.py`:
  - FastAPI service on port 8000.
  - Live WebSocket `/ws/live` broadcasting new metrics, health events, and receipts to frontend dashboards.
  - PostgreSQL `LISTEN/NOTIFY` (with async memory bus fallback for testing) connecting Ingest to API.
- **Orchestration:** `scripts/run_head_office.sh` to start Postgres, `ingest-in` (8001), `ingest-eu` (8002), and `hq-api` (8000).

### Non-Goals (Deferred to H6–H12 Core & H15–H20 Actions)
- PostgreSQL Row-Level Security (RLS) enforcement and user JWT login auth (T5, H6–H12).
- Seq-gap tracking, `prev_hash` chain verification, and 60s receipt checkpoint compare (T4, T9, H6–H12).
- Action intent polling, dry-run simulation, and phone approvals (T12, H15–H20).
- Chaos agent on port 9100 (T11, H6–H12).

---

## 3. Approaches Considered

- **Approach A (Unified Configurable Ingest + Shared Core DB + Postgres LISTEN/NOTIFY):**
  A single codebase `hq/ingest/` configured via environment variables (`REGION`, `PORT`, `DB_NAME`). Uses `airlock_core` for authentication and writes to regional DBs (`airlock_in` or `airlock_eu`). Notifies `hq/api` over PostgreSQL `LISTEN/NOTIFY` (or async in-memory bus during unit tests).
  *Pros:* Zero duplicate code between India and Europe, strict regional isolation, native Postgres pub/sub with zero external broker dependencies (Ponytail mode).
  *Cons:* Requires Postgres running (Docker script provided).
  *Selected: Yes.*

- **Approach B (Separate Ingest Apps with Webhook HTTP POST to API):**
  Distinct apps for each region with HTTP webhook forwarding to `hq/api:8000`.
  *Pros:* Decoupled networking.
  *Cons:* Extra HTTP round-trip hops, higher latency, brittle failure modes if `hq/api` restarts.
  *Selected: No.*

---

## 4. Architecture & Data Flow

```
                      [ External Trust Boundary ]
                                   │
    Shop A (India)                 │              Shop B (Europe)
    POST :8001/ingest              │              POST :8002/ingest
    (HMAC + Timestamp)             │              (HMAC + Timestamp)
            │                      │                      │
            ▼                      │                      ▼
┌────────────────────────┐         │         ┌────────────────────────┐
│  ingest-in (Port 8001) │         │         │  ingest-eu (Port 8002) │
│  REGION=in             │         │         │  REGION=eu             │
└───────────┬────────────┘         │         └───────────┬────────────┘
            │                                            │
            ├───────────────┐            ┌───────────────┤
            ▼               ▼            ▼               ▼
     [airlock_core]   [airlock_in]  [airlock_eu]  [airlock_core]
     Auth lookup      Store metrics Store metrics Auth lookup
            │                                            │
            └──────────────────────┬─────────────────────┘
                                   │ pg_notify / internal bus
                                   ▼
                       ┌────────────────────────┐
                       │   hq-api (Port 8000)   │
                       │   WebSocket: /ws/live  │
                       └───────────┬────────────┘
                                   │ push JSON
                                   ▼
                         [ Frontend Dashboards ]
```

---

## 5. Verification Plan
- `tests/test_headoffice_contracts.py`: Validate sample contract examples in `contracts/examples/`.
- `tests/test_headoffice_ingest.py`:
  - Valid payload verification and receipt issuance (`status="stored"`).
  - Duplicate payload handling (`status="duplicate"`).
  - Unauthorized guard rejection (401).
  - Invalid signature rejection (401).
  - Expired timestamp rejection (400).
- `tests/test_headoffice_websocket.py`: Test WebSocket broadcast upon ingest receipt.
