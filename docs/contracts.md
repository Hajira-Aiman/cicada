# Airlock Official System Contracts

This document specifies the official API, Ingest, Database, and Messaging contracts across Guard, Head Office, AIOps, and Frontend components.

---

## 1. Telemetry Ingest Contract

### Endpoints
- **India Region (IN):** `POST http://<host>:8001/ingest` (writes strictly to `airlock_in`)
- **Europe Region (EU):** `POST http://<host>:8002/ingest` (writes strictly to `airlock_eu`)

### Request Headers
| Header | Description | Example / Format |
|---|---|---|
| `X-Airlock-Guard-ID` | Registered Guard identifier | `guard-acme-01` |
| `X-Airlock-Timestamp` | Request UTC timestamp (ISO-8601 with `Z`) | `2026-11-21T04:12:00Z` ($\le 300\text{ s}$ skew) |
| `X-Airlock-Signature` | Hex-encoded HMAC-SHA256 signature | `hmac_sha256(secret, raw_body_bytes)` |

> **Note:** Signature is computed strictly over the **raw body bytes** only using the pre-shared per-guard HMAC secret.

### Validation Pipeline & Status Codes
1. **Known Guard:** Guard registered in `airlock_core.guards` (`401` if unknown/rogue).
2. **Residency Check:** Guard's tenant assigned region must match ingest endpoint (`403` if mismatch).
3. **Region Pause Check:** If region is paused, returns `503 Service Unavailable` with no failover forwarding.
4. **Valid HMAC:** Raw body signature check (`401` if invalid).
5. **Timestamp Window:** Within $\pm 300\text{ s}$ (`400` if stale/skewed; audit warning if $> 30\text{ s}$).
6. **Schema Contract:** Validates against `AirlockPayload` (`422` if extra fields, raw IPs, or invalid format).
7. **Pinned Policy Hash:** Tenant policy hash matches approved hashes (`422` if mismatch).
8. **Canary & Secret Tripwire:** Scans raw body for leaked credentials or canaries (`422` if detected; increments leak counter).
9. **Hash Chain & Idempotency:** Validates `prev_hash` chain (`422` if chain broken; gaps treated as buffered). Stored idempotently by `payload_id` (`ON CONFLICT DO NOTHING`).

### Response Receipt (HTTP 200)
```json
{
  "payload_id": "9f1d0b1a-4f5e-4c7b-8c7a-5b1e4f5e4c7b",
  "sha256": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "received_at": "2026-11-21T04:12:01Z",
  "status": "stored"
}
```
*`status` values:* `"stored"` (fresh payload) or `"duplicate"` (idempotent replay).

---

## 2. Official PostgreSQL Database Schema

### 2.1 Core Database (`airlock_core`)
- **`tenants`**: `(tenant_id PRIMARY KEY, name, assigned_region, pinned_policy_hash)`
- **`guards`**: `(guard_id PRIMARY KEY, tenant_id, hmac_secret, status, registered_at)`
- **`users`**: `(user_id PRIMARY KEY, tenant_id, role, password_hash, created_at)`
- **`audit_log`**: `(event_id PRIMARY KEY, tenant_id, actor, action, details, timestamp)`
- **`leak_counters`**: `(tenant_id PRIMARY KEY, leak_count, updated_at)`
- **`region_states`**: `(region PRIMARY KEY, is_paused, paused_at)`
- **`reveal_requests`**: `(request_id PRIMARY KEY, tenant_id, pseudonym, requested_by, reason, requested_at, status, decided_at, decision_reason)`

### 2.2 Regional Databases (`airlock_in`, `airlock_eu`)
- **`payloads`**: `(payload_id VARCHAR(64) PRIMARY KEY, guard_id VARCHAR(64), tenant_id VARCHAR(64), seq BIGINT, prev_hash VARCHAR(64), sent_at TIMESTAMPTZ, window_start TIMESTAMPTZ, window_end TIMESTAMPTZ, raw_payload JSONB, received_at TIMESTAMPTZ)`
- **`metrics`**: `(id BIGSERIAL PRIMARY KEY, payload_id VARCHAR(64), tenant_id VARCHAR(64), source VARCHAR(64), name VARCHAR(64), avg REAL, max REAL, event_time TIMESTAMPTZ)`
- **`events`**: `(id BIGSERIAL PRIMARY KEY, payload_id VARCHAR(64), tenant_id VARCHAR(64), source VARCHAR(64), category VARCHAR(64), severity VARCHAR(32), actor VARCHAR(64), count INT, window_s INT DEFAULT 2, event_time TIMESTAMPTZ)`
- **`receipts`**: `(payload_id VARCHAR(64) PRIMARY KEY, guard_id VARCHAR(64), sha256 VARCHAR(64), received_at TIMESTAMPTZ, status VARCHAR(32))`
- **`guard_reconciliation`**: `(guard_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), sent_count INT, received_count INT, duplicate_count INT, max_seq BIGINT, last_hash VARCHAR(64), gaps JSONB, last_seen TIMESTAMPTZ)`
- **`health_history`**: `(id BIGSERIAL PRIMARY KEY, tenant_id VARCHAR(64), source VARCHAR(64), state VARCHAR(32), old_state VARCHAR(32), reasons JSONB, at TIMESTAMPTZ)`
- **`health_current`**: `(tenant_id VARCHAR(64), source VARCHAR(64), state VARCHAR(32), reasons JSONB, since TIMESTAMPTZ, flaps_prevented INT DEFAULT 0, updated TIMESTAMPTZ DEFAULT NOW(), PRIMARY KEY(tenant_id, source))`
- **`incidents`**: `(incident_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), body JSONB, status VARCHAR(32) DEFAULT 'open', started_at TIMESTAMPTZ, updated_at TIMESTAMPTZ DEFAULT NOW())`
- **`aiops_alerts`**: `(alert_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), source VARCHAR(64), title VARCHAR(128), severity VARCHAR(32), body TEXT, status VARCHAR(32) DEFAULT 'open', created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)`
- **`tenant_thresholds`**: `(tenant_id VARCHAR(64) PRIMARY KEY, config JSONB)`
- **`feedback`**: `(alert_id VARCHAR(64) PRIMARY KEY, tenant_id VARCHAR(64), user_id VARCHAR(64), at TIMESTAMPTZ DEFAULT NOW())`

### 2.3 Row-Level Security (RLS) & AIOps Role
- Row-Level Security enabled on all regional tables: `current_setting('app.current_tenant', true)`.
- **AIOps Worker Role (`aiops_worker`):**
  - Host: `localhost:5432`, User: `aiops_worker`, Password: `aiops_secret_2026`.
  - Permissions: Read `payloads`, `metrics`, `events`; Read/Write `health_history`, `health_current`, `incidents`, `aiops_alerts`, `tenant_thresholds`, `feedback`.

---

## 3. WebSocket Message Contracts (`/ws/live`)

All streaming messages follow the envelope `{ "event_type": "<type>", "tenant_id": "<tenant>", "timestamp": "<iso>", "payload": { ... } }`:

### 3.1 `metrics_batch`
```json
{
  "event_type": "metrics_batch",
  "tenant_id": "acme",
  "timestamp": "2026-11-21T04:12:00Z",
  "payload": {
    "guard_id": "guard-acme-01",
    "window": {"start": "2026-11-21T04:12:00Z", "end": "2026-11-21T04:12:02Z", "source_tz": "Asia/Kolkata"},
    "metrics": [{"name": "cpu_pct", "source": "host-7f3a1234", "avg": 30.5, "max": 45.0}]
  }
}
```

### 3.2 `health_change`
```json
{
  "event_type": "health_change",
  "tenant_id": "acme",
  "timestamp": "2026-11-21T04:12:06Z",
  "payload": {
    "tenant_id": "acme",
    "source": "host-7f3a1234",
    "state": "Poor",
    "old_state": "Fair",
    "reasons": ["Elevated CPU > 85% for 3 windows"],
    "at": "2026-11-21T04:12:06Z"
  }
}
```

### 3.3 `incident_opened` & `incident_updated`
```json
{
  "event_type": "incident_opened",
  "tenant_id": "acme",
  "timestamp": "2026-11-21T04:12:12Z",
  "payload": {
    "incident_id": "inc-acme-1001",
    "tenant_id": "acme",
    "body": {
      "title": "Cryptomining attack",
      "severity": "critical",
      "repeat_count": 1,
      "changes_before": ["proc-1a2b3c4d started"],
      "suppressed_reason": null
    },
    "status": "open",
    "timestamp": "2026-11-21T04:12:12Z"
  }
}
```

### 3.4 `alert_opened`
```json
{
  "event_type": "alert_opened",
  "tenant_id": "acme",
  "timestamp": "2026-11-21T04:12:02Z",
  "payload": {
    "alert_id": "alt-acme-5001",
    "tenant_id": "acme",
    "source": "host-7f3a1234",
    "title": "SSH login failure burst",
    "severity": "high",
    "body": "50 failed logins in 2s",
    "created_at": "2026-11-21T04:12:02Z"
  }
}
```

### 3.5 `counters`
```json
{
  "event_type": "counters",
  "tenant_id": "acme",
  "timestamp": "2026-11-21T04:12:15Z",
  "payload": {
    "tenant_id": "acme",
    "raw_alerts": 14,
    "incidents": 2,
    "flaps_prevented": 3
  }
}
```

---

## 4. REST API Endpoints

### 4.1 Authentication: `POST /api/login`
- **Request:** `{"username": "user-acme", "password": "..."}`
- **Response:** `200 OK`
  ```json
  {
    "token": "eyJhbGciOi...",
    "user_id": "user-acme",
    "tenant_id": "acme",
    "role": "customer"
  }
  ```

### 4.2 Stream Reconciliation: `GET /api/reconciliation/{guard_id}`
- **Response:** `200 OK`
  ```json
  {
    "guard_id": "guard-acme-01",
    "tenant_id": "acme",
    "sent_count": 150,
    "received_count": 150,
    "duplicate_count": 4,
    "max_seq": 150,
    "gaps": [],
    "last_seen": "2026-11-21T04:12:01Z"
  }
  ```

### 4.3 60s Checkpoints: `POST /api/checkpoints/compare`
- **Request:**
  ```json
  {
    "guard_id": "guard-acme-01",
    "up_to_seq": 100,
    "root": "sha256:4f3a...9c",
    "hashes": ["sha256:1a...", "sha256:2b..."]
  }
  ```
- **Response:** `200 OK`
  ```json
  {
    "guard_id": "guard-acme-01",
    "up_to_seq": 100,
    "match": true,
    "status": "verified",
    "first_differing_seq": null
  }
  ```
  *(On mismatch, `match: false`, `status: "mismatch"`, and `first_differing_seq: <seq_num>`)*.

### 4.4 Reveal Requests
- **Create:** `POST /reveal-requests`
  ```json
  {
    "pseudonym": "user-7f3a1234",
    "reason": "Investigating unauthorized sudo escalation",
    "tenant_id": "acme"
  }
  ```
- **List Pending:** `GET /reveal-requests?status=pending`
- **Decision:** `POST /reveal-requests/{request_id}/decision`
  ```json
  {
    "status": "approved",
    "decision_reason": "Approved by security team"
  }
  ```
  *(Audit rows written on both sides; raw secret/value never returned to Head Office)*.

### 4.5 Regional Outage / Pause Switch
- `POST /api/regions/{region}/pause` (sets paused state, reject ingest with 503)
- `POST /api/regions/{region}/unpause`
- `GET /api/regions/{region}/status`

### 4.6 Action Intents & Guard Remediations
- **Propose Intent:** `POST /api/actions/propose`
  ```json
  {
    "action": "kill_process",
    "target": "proc-7f3a1234",
    "why": "Uncontrolled CPU loop detected by AIOps",
    "risk": "medium",
    "incident_id": "inc-acme-1001",
    "tenant_id": "acme"
  }
  ```
  *Response:* `{"status": "proposed", "intent_id": "act-4f9e12...", "intent": {...}}`
- **Dry Run Simulation:** `POST /api/actions/{intent_id}/dry-run`
  *Response:* `{"status": "dry_run_done", "simulation": {"would_affect": "proc-7f3a1234", "estimated_risk": "medium"}}`
- **Human Approval:** `POST /api/actions/{intent_id}/approve`
  ```json
  {
    "approved_by": "Adithya"
  }
  ```
  *Response:* `{"status": "approved", "intent_id": "act-4f9e12...", "approved_by": "Adithya"}`
- **Guard Poll Pending (HMAC-signed):** `GET /api/actions/pending?guard_id=guard-acme-01`
  *Response:* `{"intents": [{"intent_id": "act-4f9e12...", "action": "kill_process", "target": "proc-7f3a1234", "signature": "..."}]}`
- **Post Result & Automated Rollback:** `POST /api/actions/{intent_id}/result`
  ```json
  {
    "guard_id": "guard-acme-01",
    "status": "done",
    "health_improved": true,
    "elapsed_seconds": 25
  }
  ```
  *(If `health_improved: false` or `elapsed_seconds > 120`, automated rollback status `rolled_back` is assigned)*.
- **Audit Trail:** `GET /api/actions/audit`

### 4.7 Guest Judges Phone Join
- **Phone Heartbeat:** `POST /api/phones/heartbeat`
  ```json
  {
    "phone_id": "phone-judge-01",
    "latency_ms": 42.5
  }
  ```
  *Response:* `{"status": "ok", "phone_id": "phone-judge-01", "tenant_id": "guests", "color": "green", "latency_ms": 42.5}`
  *(Color turns `"red"` if latency > 150 ms)*.
- **List Active Phones:** `GET /api/phones`
  *Response:* `{"phones": [{"phone_id": "phone-judge-01", "status": "online", "color": "green", "latency_ms": 42.5, "last_seen_s_ago": 1.2}]}`
  *(Phones with no heartbeat for > 60 s transition to `status: "offline", color: "red"`)*.

### 4.8 Metric Baselines Normal Band: `GET /api/baselines/{tenant_id}`
- **Response:** `200 OK`
  ```json
  [
    {
      "source": "host-7f3a1234",
      "metric": "cpu_pct",
      "mean": 35.2,
      "std": 4.8
    }
  ]
  ```
  *(Returns `[]` if no baseline rows are recorded yet for the tenant)*.

### 4.9 Thumbs-Down Feedback: `POST /feedback`
- **Request:**
  ```json
  {
    "alert_id": "alt-acme-5001",
    "user_id": "user-ops-1",
    "tenant_id": "acme",
    "metric": "cpu_pct",
    "source": "host-7f3a1234"
  }
  ```
  *(If `metric` or `source` is omitted, Head Office automatically resolves them from `aiops_alerts.body.signals`)*.
- **Response:** `200 OK`
  ```json
  {
    "status": "recorded",
    "alert_id": "alt-acme-5001",
    "tenant_id": "acme",
    "user_id": "user-ops-1",
    "metric": "cpu_pct",
    "source": "host-7f3a1234",
    "at": "2026-11-21T04:12:30Z"
  }
  ```

### 4.10 AI Assistant Chat: `POST /ai/chat`
- **Request:** `{"question": "What caused the incident on host-7f3a1234?"}`
- Proxies with a **20-second timeout** to `http://localhost:8010/chat`.
- **Response (Normal upstream):** `200 OK`
  ```json
  {
    "answer": "A rogue process spiked CPU to 95% after 50 failed SSH authentication attempts.",
    "evidence_ids": ["ev-1", "ev-2"]
  }
  ```
- **Fallback Response (Upstream timeout or offline):** `200 OK`
  ```json
  {
    "answer": "AI Assistant is currently unavailable. Telemetry indicates normal operation within region for tenant 'acme'.",
    "evidence_ids": []
  }
  ```

---

## 5. Chaos Agent Contracts (Port 9100)

Exposes REST endpoints matching `tools/simulate_timeline.py` scenario names:
- `POST /scenarios/cpu_spike`
- `POST /scenarios/latency`
- `POST /scenarios/brute_force` (alias `/scenarios/login_burst`)
- `POST /scenarios/leak` (alias `/scenarios/try_to_leak`)
- `POST /scenarios/region_outage` (alias `/scenarios/outage`)
- `POST /scenarios/replay_shuffle` (alias `/scenarios/duplicates`, `/scenarios/out_of_order`)
- `POST /scenarios/tamper`
- `POST /scenarios/kill_chain`
- `POST /scenarios/backup_job`
- `POST /scenarios/restart_app`
- `GET /chaos/active` & `POST /chaos/reset`
