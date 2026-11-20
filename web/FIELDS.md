# Airlock Frontend Data Consumption Schema (web/FIELDS.md)

This document specifies the exact fields consumed by each widget across all entry points (`hq`, `shop`, `chaos`, `phone`) and notes any pending endpoints requested from backend owners (Adithya, Sahiti, Hajira).

---

## 1. Head-Office Dashboard (`hq` / Projector)

### 1.1 Fleet Grid & Guard Health (`GET /api/health`, WS `health_change`, WS `guard_heartbeat`)
- **`tenant_id`**: string (`"acme"`, `"globex"`, `"contoso"`)
- **`source` / `guard_id`**: Pseudonym (`"host-7f3a1234"`, `"guard-acme-01"`)
- **`state`**: `"Excellent" | "Good" | "Fair" | "Poor"`
- **`reasons`**: `string[]` (e.g. `["no data for 14 s"]`, `"Elevated CPU > 85% for 3 windows"`)
- **`since` / `at`**: ISO-8601 UTC string (`"2026-11-21T04:12:06Z"`)
- **`flaps_prevented`**: integer (`3`)
- **`guard_version`**: string (`"0.3.1"`)
- **`guard_cpu_pct`**: float (`12.4`)
- **`guard_mem_mb`**: float (`48.2`)
- **`buffer_depth`**: integer (`0`)
- **`config_ok`**: boolean (`true`)
- **`canaries_planted`**: integer (`12`)
- **`secrets_redacted`**: integer (`3`)

### 1.2 Live Metric Charts (`GET /api/metrics`, WS `metrics_batch`)
- **`id`**: integer
- **`payload_id`**: string
- **`tenant_id`**: string
- **`source`**: Pseudonym
- **`name`**: `"cpu_pct" | "mem_pct" | "latency_ms" | "net_out_kbps" | "packet_loss_pct"`
- **`avg`**: float
- **`max`**: float
- **`event_time`**: ISO-8601 UTC string (ordered by event_time, never arrival time)
- **`window`**: `{ "start": ISO-8601 UTC, "end": ISO-8601 UTC, "source_tz": string }`
- **Normal Band**: Baseline $\pm 2\sigma$.
  *Pending backend endpoint from Adithya:* `GET /api/baseline/{tenant_id}`.
  *UI Fallback implementation:* Calculated dynamically from a 30-point rolling window $(\mu \pm 2\sigma)$.

### 1.3 Incident Feed & Cards (`GET /api/incidents`, WS `incident_opened`, WS `incident_updated`)
- **`incident_id`**: string (`"inc-0042"`)
- **`tenant_id`**: string (`"acme"`)
- **`title`**: string (`"Possible compromise: cryptomining"`)
- **`severity`**: `"critical" | "high" | "medium" | "low" | "info"`
- **`confidence`**: float (`0.85` $\to 85\%$)
  - Hover formula: `0.4 + 0.15 * agreeing_signals + 0.1 * rule_match (capped at 0.95)`
- **`started_at`**: ISO-8601 UTC string
- **`affected`**: `string[]` (e.g. `["host-7f3a1b2c", "shop-api", "checkout"]`)
- **`signals`**: Array of signal objects:
  - `evidence_id`: string (`"ev-1"`, `"ev-2"`)
  - `name`: string (`"cpu_pct"`, `"auth_failure_burst"`)
  - `value`: float
  - `baseline`: float
  - `z`: float or null
  - `contribution_pct`: float (`40.0`)
- **`reasoning_path`**: `string[]` (sequential timeline)
- **`counterfactual`**: string or null (`"Without the outbound spike this would be a High security incident, not Critical"`)
- **`recommendation`**: Object containing:
  - `action`: `"kill_process" | "restart_service" | "block_source" | "block_ip" | "dry_run"`
  - `target`: string (`"proc-1a2b3c4d"`)
  - `why`: string
  - `risk`: `"low" | "medium" | "high"`
  - `reversible`: boolean
  - `rollback`: string
- **`changes_before`**: `string[]` (e.g. `["proc-1a2b3c4d started"]`)
- **`suppressed_reason`**: string or null
- **`repeat_count`**: integer (`1` $\to$ badge `"x1"`)
- **`narrative`**: string

### 1.4 Header Counters & Privacy KPI Strip (`GET /api/counters/{tenant_id}`, WS `counters`)
- **`raw_alerts`**: integer (`47`)
- **`incidents`**: integer (`3`)
- **`noise_cut_pct`**: calculated as `((raw_alerts - incidents) / raw_alerts) * 100` (`94%`)
- **`flaps_prevented`**: integer (`12`)
- **`canaries_planted`**: integer (`1240`)
- **`leaks_detected`**: integer (`0` — strictly zero, privacy tripwire)

### 1.5 Reconciliation Table (`GET /api/reconciliation`, `GET /api/reconciliation/{guard_id}`)
- **`guard_id`**: string
- **`tenant_id`**: string
- **`sent_count`**: integer
- **`received_count`**: integer
- **`duplicate_count`**: integer
- **`max_seq`**: integer
- **`last_hash`**: string (sha256 hex)
- **`gaps`**: `string[]` or `int[]`
- **`last_seen`**: ISO-8601 UTC string

### 1.6 AI Operations Copilot Drawer (`POST /api/ai/chat`)
- **Request**: `{ "question": string }`
- **Response**:
  - `answer`: string
  - `evidence_ids`: `string[]` (e.g. `["ev-1", "ev-2"]` — clickable chips that link to signals)

---

## 2. Inside the Shop Screen (`shop` / Port 9000 Local View)

### 2.1 Local Status & Raw Logs (`GET /api/status`, `GET /api/raw-logs` on guard :9000)
- **`status`**: `"active" | "degraded" | "paused"`
- **`buffer_depth`**: integer
- **`retention_countdown_s`**: integer (`86400` $\to$ formatted as `23h 59m`)
- **`canaries_planted`**: integer
- **`secrets_redacted`**: integer
- **`raw_logs`**: Array of local log lines with unredacted credentials (highlighted in crimson on-screen).

### 2.2 Egress Proof Panel (`GET /api/egress` local vs `GET /api/payloads` Head Office)
- **`payload_id`**: UUID string
- **`seq`**: integer
- **`sha256`**: hex string
- **`raw_payload`**: Full JSON object of allow-listed telemetry
- **Receipt Verification**:
  - Local emitted `sha256` vs Head Office stored `sha256`
  - Match badge: `✓ MATCH` (Emerald) or `✕ MISMATCH` (Crimson)

### 2.3 Reveal Request Decider (`GET /reveal-requests`, `POST /reveal-requests/{request_id}/decision`)
- **`request_id`**: string
- **`pseudonym`**: string (`"user-7f3a1234"`)
- **`reason`**: string
- **`requested_by`**: string
- **`status`**: `"pending" | "approved" | "rejected"`
- **`decision_reason`**: string

---

## 3. Chaos Console (`chaos` / Laptop 4 Port 5173)

### 3.1 Scenarios (`POST /scenarios/{scenario_name}` on :9100)
- `cpu_spike`, `latency`, `brute_force`, `leak`, `region_outage`, `replay_shuffle`, `tamper`, `kill_chain`, `backup_job`, `restart_app`
- **Parameters**: `{ "target_guard": string, "duration_s": int, "intensity": int }`

### 3.2 Region Outage Control (`POST /api/regions/{in|eu}/pause` & `unpause`)
- `is_paused`: boolean
- `paused_at`: ISO-8601 UTC string

### 3.3 Try-to-Leak Box (`POST /chaos/inject-log`)
- `payload`: arbitrary string containing canary or dummy password.
- Dashboard proof: Tripwire captures the attempt, increments `secrets_redacted`, never emits to Head Office.

---

## 4. Phone Pages (`phone` / Port 8000 `/m/*`)

### 4.1 `/m/join` (Guest Device Collector)
- **Heartbeat Payload**: `{ "device_id": string, "tenant_id": string, "latency_ms": float, "battery_pct": float }`

### 4.2 `/m/approve` (Action Intent One-Tap Remediation)
- **`intent_id`**: UUID string
- **`action`**: `"kill_process" | "restart_service" | "block_source"`
- **`target`**: string (`"proc-1a2b3c4d"`)
- **`rollback_window_s`**: integer (`120`)
- **Buttons**: `DRY RUN` $\to$ `APPROVE` / `REJECT`

### 4.3 `/m/raw` vs `/m/smart`
- `/m/raw`: Emits audio/vibration triggers on every `alert_opened` WS event.
- `/m/smart`: Filtered, incident-only cards (`incident_opened`).

---

## 5. Fields & Endpoints Requested from Backend Owners

1. **To Adithya (`hq/aiops`, `incidents`, `baseline`):**
   - **`GET /api/baseline/{tenant_id}`**: Baseline values and standard deviation per metric (`{ "cpu_pct": { "mean": 21.0, "stddev": 4.5 }, ... }`). *(Until delivered, the UI calculates moving 30-sample $\mu \pm 2\sigma$ dynamically).*
   - **Topology JSON for Damage Map**: Node connection graph (`{ "nodes": [...], "edges": [...] }`) for `host-7f3a` $\to$ `shop-api` $\to$ `checkout` $\to$ `db`.
2. **To Sahiti (`contracts`, `hq/api`):**
   - **`GET /api/checkpoints/{guard_id}`**: Verified working! Returns current checkpoint root hash and verified seq.
   - **`aiops_counters` Table Fix**: Verified fixed in commit `3b5d0a5`!
3. **To Hajira (`guard` local API :9000):**
   - **`/api/status` & `/api/egress`**: Exact JSON structure matching `contracts/examples/payload.json` and `receipt_sample.json`.
