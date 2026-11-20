# Airlock Official System Contracts

This document specifies the official API, Ingest, Database, and Messaging contracts across Guard, Head Office, AIOps, and Frontend components.

---

## 1. Telemetry Ingest Contract

### Endpoints
- **India Region (IN):** `POST http://<host>:8001/ingest` (writes to `airlock_in`)
- **Europe Region (EU):** `POST http://<host>:8002/ingest` (writes to `airlock_eu`)

### Request Headers
| Header | Description | Example / Format |
|---|---|---|
| `X-Airlock-Guard-ID` | Registered Guard identifier | `guard-acme-01` |
| `X-Airlock-Timestamp` | Request UTC timestamp (ISO-8601 with `Z`) | `2026-11-21T04:12:00Z` (clock skew $\le 300\text{ s}$) |
| `X-Airlock-Signature` | Hex-encoded HMAC-SHA256 signature | `hmac_sha256(secret, raw_body_bytes)` |

> **Note:** Signature is computed strictly over the **raw body bytes** only using the pre-shared per-guard HMAC secret.

### Response Receipt (HTTP 200)
```json
{
  "payload_id": "9f1d0b1a-4f5e-4c7b-8c7a-5b1e4f5e4c7b",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "received_at": "2026-11-21T04:12:01Z",
  "status": "stored"
}
```
*`status` values:* `"stored"` (fresh payload) or `"duplicate"` (idempotent replay).

---

## 2. Official PostgreSQL Database Schema

Applicable to both `airlock_in` and `airlock_eu` regional databases:

### Ingest Tables
- **`payloads`**: `(payload_id VARCHAR(64) PRIMARY KEY, guard_id VARCHAR(64), tenant_id VARCHAR(64), seq BIGINT, prev_hash VARCHAR(64), sent_at TIMESTAMPTZ, window_start TIMESTAMPTZ, window_end TIMESTAMPTZ, raw_payload JSONB, received_at TIMESTAMPTZ)`
- **`metrics`**: `(id BIGSERIAL PRIMARY KEY, payload_id VARCHAR(64), tenant_id VARCHAR(64), source VARCHAR(64), name VARCHAR(64), avg REAL, max REAL, event_time TIMESTAMPTZ)`
- **`events`**: `(id BIGSERIAL PRIMARY KEY, payload_id VARCHAR(64), tenant_id VARCHAR(64), source VARCHAR(64), category VARCHAR(64), severity VARCHAR(32), actor VARCHAR(64), count INT, window_s INT DEFAULT 2, event_time TIMESTAMPTZ)`
- **`receipts`**: `(payload_id VARCHAR(64) PRIMARY KEY, guard_id VARCHAR(64), sha256 VARCHAR(64), received_at TIMESTAMPTZ, status VARCHAR(32))`

### AIOps & Analytic Tables
- **`health_history`**: `(id BIGSERIAL PRIMARY KEY, tenant_id VARCHAR(64), source VARCHAR(64), state VARCHAR(32), old_state VARCHAR(32), reasons JSONB, at TIMESTAMPTZ)`
- **`health_current`**: `(tenant_id VARCHAR(64), source VARCHAR(64), state VARCHAR(32), reasons JSONB, since TIMESTAMPTZ, flaps_prevented INT DEFAULT 0, updated TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY(tenant_id, source))`
- **`incidents`**: `(incident_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), body JSONB, status VARCHAR(32) DEFAULT 'open', started_at TIMESTAMPTZ, updated_at TIMESTAMPTZ DEFAULT NOW())`
- **`tenant_thresholds`**: `(tenant_id VARCHAR(64) PRIMARY KEY, config JSONB)`
- **`feedback`**: `(alert_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), user_id VARCHAR(64), at TIMESTAMPTZ DEFAULT NOW())`

---

## 3. WebSocket Message Contracts (`/ws`)

All streaming messages follow the envelope `{ "type": "<event_type>", "payload": { ... } }`:

| Message Type | Description | Key Payload Fields |
|---|---|---|
| `metrics_batch` | Streaming metrics per window | `tenant_id`, `window_start`, `metrics: [{source, name, avg, max}]` |
| `health_change` | Source health transitions | `tenant_id`, `source`, `state`, `old_state`, `reasons`, `at` |
| `incident_opened` | High/Critical incident detection | `incident_id`, `tenant_id`, `title`, `severity`, `confidence`, `signals`, `recommendation` |
| `incident_updated`| Incident status/suppression updates | `incident_id`, `status`, `repeat_count`, `suppressed_reason`, `narrative` |
| `counters` | Aggregate telemetry & flap counters | `raw_alerts`, `incidents`, `flaps_prevented` |

---

## 4. API Endpoints

### 4.1 Thumbs-Down Feedback
- **Method & Route:** `POST /feedback`
- **Request Body:**
  ```json
  {
    "alert_id": "inc-0042",
    "tenant_id": "acme",
    "user_id": "user-ops-1",
    "at": "2026-11-21T04:15:00Z"
  }
  ```
- **Response:** `200 OK` `{ "status": "recorded", "alert_id": "inc-0042" }`

### 4.2 AI Assistant Chat
- **Method & Route:** `POST /ai/chat`
- **Authentication:** Tenant context derived directly from authenticated user login session.
- **Request Body:**
  ```json
  {
    "question": "What caused the high CPU and outbound network spike on host-7f3a1b2c?"
  }
  ```
- **Response:** `200 OK`
  ```json
  {
    "answer": "A rogue cryptomining process (proc-1a2b3c4d) was launched following multiple failed login attempts.",
    "evidence_ids": ["ev-1", "ev-2", "ev-3"]
  }
  ```
