# Requirements: Tenant 1 (Shop A "Acme" - Tier 1 Guard & Local Environment)

## 1. System Identity & Context
- **Role:** Tier 1 Tenant Environment & Guard Engineer (**Role G**)
- **Tenant ID:** `acme`
- **Shop Name:** Shop A ("Acme")
- **Region:** India (`ingest-in`, primary endpoint `http://localhost:8001`)
- **Timezone:** `Asia/Kolkata`
- **Host Machine:** Windows (Ryzen AI 7 350 / Local PC)
- **Primary Ports:**
  - `shop-api`: Port `7000`
  - `guard` + Local UI API: Port `9000`
  - `chaos agent`: Port `9100`
  - `toxiproxy`: Port `8474` (optional network simulation)
  - `lemonade` (Shop AI): Port `13305` (or local CPU fallback)

---

## 2. Shared Contracts (`contracts/`)
Tenant 1 adheres strictly to frozen protocol contracts shared across Tier 1 and Tier 2:
- **`contracts/payload.schema.json`**: Strict JSON Schema for `airlock.v1` telemetry payloads (`additionalProperties: false`).
- **`contracts/models.py`**: Pydantic v2 data models with `model_config = ConfigDict(extra="forbid")`:
  - `MetricItem`: `name` (enum of allowed metrics), `source` (`host-*` pseudonym), `avg`, `max`.
  - `EventItem`: `category` (enum of allowed events), `severity` (`info|low|medium|high|critical`), `source`, `actor`, `count`, `window_s`.
  - `LogPatternItem`: `pattern_id`, `level`, `count`, `is_new`.
  - `HealthInfo`: `guard_version`, `guard_cpu_pct`, `guard_mem_mb`, `buffer_depth`, `config_ok`, `canaries_planted`, `secrets_redacted`.
  - `PayloadV1`: Root envelope with `schema="airlock.v1"`, `payload_id`, `tenant_id="acme"`, `guard_id`, `seq`, `prev_hash`, `policy_version`, `sent_at`, `window`, metrics, events, log_patterns, health.
  - `SignedReceipt`: `payload_id`, `sha256`, `received_at`, `status` (`stored|duplicate`).
  - `ActionIntent`: Remediation payload (`action_id`, `tenant_id`, `action`, `target`, `dry_run`, `signature`).

---

## 3. Target Application: `shop-api/` (Port 7000)
A realistic demo e-commerce service designed to simulate real customer operations and generate telemetry:
1. **API Endpoints:**
   - `GET /health`: Service health status and uptime.
   - `POST /auth/login`: User authentication with failure tracking (records source IP, username, latency).
   - `GET /catalog`: Fetch product list.
   - `POST /cart/checkout`: Process purchase, logs transaction IDs, billing metadata, simulated credit card/auth tokens.
   - `POST /chaos/inject-log`: Receives arbitrary strings to demonstrate secret redaction and pattern mining.
2. **Local Logging:**
   - Writes rich structured logs to `shop-api/logs/shop.log`.
   - Generates realistic logs with sensitive tokens, passwords, and raw customer data intended to test local scrubbing.

---

## 4. Privacy Guard: `guard/` (Port 9000)
The heart of Tenant 1. A standalone, outbound-only observability daemon.

### 4.1 Telemetry Collection Pipeline
- **Frequency:** Every 2.0 seconds window.
- **Metrics Collected (`psutil` & local probes):**
  - Host CPU usage (`cpu_pct`), memory usage (`mem_pct`), disk usage (`disk_pct`).
  - Network I/O rate (`net_in_kbps`, `net_out_kbps`).
  - TCP latency & packet loss probes to local gateway / head-office endpoint.
  - HTTP probe to `shop-api` health endpoint (`service_up`).
  - Battery status via `psutil.sensors_battery()`: `battery_pct`, `on_battery`, `battery_min_left`.
- **Log Collection:**
  - Tailing `shop-api/logs/shop.log`.

### 4.2 Local Raw Store (`raw_store.py`)
- SQLite database (`data/raw.db`).
- Stores raw log entries and un-aggregated metrics locally for 24 hours.
- Strict retention policy: automatic deletion after 24 hours with active countdown.
- **Zero Raw Data Egress:** Raw lines NEVER leave `raw.db` across the trust boundary.

### 4.3 Redaction & Canary Tripwires (`scrubber.py`)
- Regex and pattern scrubbers masking AWS keys (`AKIA...`), JWT tokens, basic auth passwords, and bearer tokens.
- **Canary Planter:** Every 30 seconds, injects synthetic canary secrets (`AKIACANARY...`) into the local raw stream.
- **Pre-send Verifier:** Verifies that no payload contains any canary string or unmasked secret pattern before transmission.

### 4.4 Pattern Mining (`pattern_miner.py`)
- Integrated **Drain3** algorithm to parse free-text log messages into structured pattern templates (e.g. `tpl-3fa1`) and track frequency counts.
- Flags `is_new: true` when a previously unseen pattern appears.

### 4.5 Local Anomaly & Behavioral Detectors (`detectors.py`)
- **Login Burst Detector:** Triggers `auth_failure_burst` event if >30 failed attempts occur within 60s.
- **Honeypot Trap:** Instant `honeypot_hit` critical event if authentication is attempted for trap user `admin_backup`.
- **Odd-Hour Login:** Detects logins at 3:00 AM shop local time (`Asia/Kolkata`).
- **Power Failure:** Triggers `power_on_battery` event on charger disconnection.
- **Change Tracker:** Emits `app_restarted`, `config_changed`, or `new_process` metadata events.

### 4.6 Pseudonymization Engine (`pseudonymizer.py`)
- Deterministic HMAC-SHA256 keyed with tenant secret `TENANT_SECRET_KEY`.
- Formats:
  - Hostnames -> `host-[0-9a-f]{8}`
  - Source IPs / Actors -> `src-[0-9a-f]{8}`
  - Usernames -> `user-[0-9a-f]{8}`
  - Process PIDs / names -> `proc-[0-9a-f]{8}`
- Stores bidirectional mapping exclusively in local SQLite table (`reveal.db`) for permissioned reveal requests.

### 4.7 Hash-Chained Egress Ledger & Outbox (`ledger.py`)
- Hash chain integrity: Each payload references `prev_hash: "sha256:..."` and calculates its own SHA-256.
- Monotonically increasing sequence number `seq`.
- Persistent SQLite Outbox queue:
  - If network or regional ingest is unreachable, buffers payloads locally in FIFO sequence.
  - Zero loss, zero duplicate transmission.
  - Exponential backoff retry (1s, 2s, 4s, 8s, max 10s).
- Receipt reconciliation: Updates local ledger row status to `CONFIRMED` upon receiving valid signed receipt from Head Office.

### 4.8 Receipt-Log Checkpoint Generator (`checkpoints.py`)
- Every 60 seconds, calculates cumulative SHA-256 root over all transmitted payload hashes up to sequence `N`.
- Exposes `{guard_id, up_to_seq, root}` for sent-vs-received matching against Head Office.

### 4.9 Remediation Executor (`executor.py`)
- Pulls signed action intents from Head Office (`GET /actions/pending` or webhook).
- **Policy Gate:** Enforces tenant permission rules:
  - Allowed actions: `kill_process`, `restart_service`, `block_source`, `dry_run`.
  - Rate limiting (max 3 actions per 10 minutes).
- Resolves pseudonyms (`proc-1a2b3c4d`) to real local targets via local reveal table.
- **Dry-run Mode:** Returns exact projected impact without making changes.
- **Execution & Rollback:**
  - Kills runaway processes or restarts `shop-api`.
  - Starts 120s rollback timer; escalates or rolls back if service does not return to healthy state.
  - Logs all actions to local audit table.

### 4.10 Local Shop Screen API (`api.py` on Port 9000)
- `GET /api/status`: Guard health, buffer depth, version, retention countdown.
- `GET /api/raw-logs`: Displays raw logs with secrets and raw data visible (Shop only!).
- `GET /api/egress`: Egress proof panel displaying exact JSON sent, SHA-256, and receipt status.
- `GET /api/reveal-requests`: View pending pseudonym reveal requests from Head Office.
- `POST /api/reveal-requests/{id}/approve`: Shop admin approves reveal; value displayed only on local screen.
- `GET /api/checkpoint`: Running 60-second checkpoint root hash.

### 4.11 Shop AI Assistant (`shop_ai.py`)
- Connects to local Lemonade server on port 13305 (or CPU fallback).
- Implements OpenAI tool-calling interface with tools:
  - `search_raw_logs(query, minutes)`
  - `recent_auth_failures(minutes)`
- Answers tenant operator queries based on local raw logs without exposing data to Head Office.

---

## 5. Local Chaos Agent: `chaos/` (Port 9100)
Allows triggerable scenarios for live hackathon evaluation:
- `POST /chaos/cpu-spike`: Consumes high CPU to simulate cryptominer or runaway process.
- `POST /chaos/latency`: Injects artificial network latency.
- `POST /chaos/brute-force`: Simulates 50 failed login attempts.
- `POST /chaos/inject-secret`: Injects passwords and API keys into the raw shop log.
- `POST /chaos/power-cut`: Simulates battery operation.
- `POST /chaos/restart-shop`: Restarts `shop-api` to trigger change event correlation.

---

## 6. Pre-requisites & Environment
- **Python:** 3.11+ / 3.14 via `py` launcher.
- **Dependencies:** `fastapi`, `uvicorn`, `pydantic>=2.0`, `psutil`, `httpx`, `drain3`, `detect-secrets`, `pytest`, `python-dotenv`.
- **Environment Configuration (`.env`):**
  - `TENANT_ID=acme`
  - `GUARD_ID=guard-acme-01`
  - `SHOP_API_PORT=7000`
  - `GUARD_PORT=9000`
  - `CHAOS_PORT=9100`
  - `INGEST_URL=http://localhost:8001/v1/ingest`
  - `GUARD_SECRET_KEY=secret-guard-acme-key-350`
  - `TENANT_SECRET_KEY=tenant-acme-hmac-salt-99`
  - `TIMEZONE=Asia/Kolkata`
