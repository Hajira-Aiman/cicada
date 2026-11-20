# Guard Local Shop API Specification (Port 9000)

**Service:** Airlock Guard Local Shop Screen API  
**Default Bind:** `127.0.0.1:9000` (Localhost only for shop security)  
**Version:** `0.2.0`  
**Target Consumer:** Inside the Shop Screen UI (Anisa) and Local Shop AI Assistant.

---

## 1. Overview & Security Boundaries

The Guard Local API exposes real-time local telemetry, egress logs, retention counters, and the local pseudonym reverse-mapping table to the in-store shop screen. 

### Security Rules
1. **Local Access Only:** Raw logs and reveal lookups are strictly bound to `127.0.0.1` and will return `403 Forbidden` if called across network interfaces.
2. **Secrets Visibility:** Raw logs retrieved via `GET /api/raw-logs` display the original unredacted text solely on the merchant's local screen for auditing. These lines NEVER cross the network in egress payloads.
3. **Cryptographic Integrity:** Every egress payload displays its sequence number, SHA-256 hash, and receipt confirmation status matching Head Office storage.

---

## 2. Endpoints

### 2.1 Get Status & Health
Returns Guard operational status, health, current buffer depth, retention countdown, policy version hash, and canary/secret counters.

- **Method:** `GET`
- **Path:** `/api/status`
- **Response (200 OK):**
```json
{
  "guard_id": "guard-acme-01",
  "tenant_id": "acme",
  "guard_version": "0.2.0",
  "status": "active",
  "buffer_depth": 0,
  "retention_countdown_seconds": 86342.5,
  "policy_version": "sha256:v1-default-policy",
  "canaries_planted": 8,
  "secrets_redacted": 14,
  "guard_cpu_pct": 1.25,
  "guard_mem_mb": 48.3,
  "last_seq": 142
}
```

---

### 2.2 Get Raw Logs (Secrets Visible)
Retrieves raw, unredacted log lines stored in the local 24-hour circular buffer (`raw.db`).

- **Method:** `GET`
- **Path:** `/api/raw-logs?minutes=60`
- **Query Parameters:**
  - `minutes` (optional, default: 60): Lookback window in minutes.
- **Access:** Local machine only (`127.0.0.1`). Remote IP returns `403 Forbidden`.
- **Response (200 OK):**
```json
{
  "minutes": 60,
  "count": 2,
  "logs": [
    {
      "id": 105,
      "timestamp": 1700500120.4,
      "source": "shop-api",
      "raw_text": "Authentication failed for user 'admin' password=superSecretPassword! from 198.51.100.42"
    },
    {
      "id": 104,
      "timestamp": 1700500115.1,
      "source": "shop-api",
      "raw_text": "Backup failure: AKIAIOSFODNN7EXAMPLE and card 5555 4444 3333 2222 logged"
    }
  ]
}
```

---

### 2.3 Get Egress Payloads
Returns the last 50 payloads recorded in the cryptographic outbox ledger, including the exact JSON payload sent over the wire, SHA-256 hash, and delivery receipt confirmation.

- **Method:** `GET`
- **Path:** `/api/egress`
- **Response (200 OK):**
```json
{
  "count": 1,
  "payloads": [
    {
      "seq": 142,
      "payload_id": "d4e287b3-85b4-4b53-9114-1fbc8e089201",
      "sha256": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "prev_hash": "sha256:7b502c3a1f48c8609ae212cdfb639dee39673f5e",
      "status": "stored",
      "receipt_at": "2026-11-20T15:20:01Z",
      "body": {
        "schema": "airlock.v1",
        "payload_id": "d4e287b3-85b4-4b53-9114-1fbc8e089201",
        "tenant_id": "acme",
        "guard_id": "guard-acme-01",
        "seq": 142,
        "metrics": [
          {"name": "cpu_pct", "source": "host-f3597610", "avg": 18.5, "max": 24.0},
          {"name": "service_up", "source": "proc-cfc47891", "avg": 1.0, "max": 1.0},
          {"name": "latency_ms", "source": "proc-cfc47891", "avg": 14.2, "max": 15.1},
          {"name": "packet_loss_pct", "source": "proc-cfc47891", "avg": 0.0, "max": 0.0}
        ]
      }
    }
  ]
}
```

---

### 2.4 Get Cryptographic Checkpoint
Returns the latest running SHA-256 root checkpoint covering payload sequence 1 up to `up_to_seq`.

- **Method:** `GET`
- **Path:** `/api/checkpoint`
- **Response (200 OK):**
```json
{
  "guard_id": "guard-acme-01",
  "up_to_seq": 142,
  "root": "sha256:c28f1e63a8d423984518ff94e01923485ab9230591283c847a982347bc918234",
  "timestamp": "2026-11-20T15:20:05.123456Z"
}
```

---

### 2.5 List Reveal Requests
Lists pending and historical reveal requests submitted for investigation.

- **Method:** `GET`
- **Path:** `/api/reveal-requests?status=pending`
- **Query Parameters:**
  - `status` (optional): Filter by `pending`, `approved`, or `rejected`.
- **Response (200 OK):**
```json
{
  "count": 1,
  "requests": [
    {
      "id": "req-8b3f12a0",
      "pseudonym": "src-1743a788",
      "reason": "Investigating high-volume authentication failure burst against Shop A login",
      "status": "pending",
      "requested_at": 1700500130.0,
      "decision_reason": null,
      "decided_at": null
    }
  ]
}
```

---

### 2.6 Submit Reveal Request
Submits a new reveal request to the local queue.

- **Method:** `POST`
- **Path:** `/api/reveal-requests`
- **Request Body:**
```json
{
  "pseudonym": "src-1743a788",
  "reason": "Investigating high-volume authentication failure burst against Shop A login"
}
```
- **Response (200 OK):**
```json
{
  "id": "req-8b3f12a0",
  "pseudonym": "src-1743a788",
  "reason": "Investigating high-volume authentication failure burst against Shop A login",
  "status": "pending",
  "requested_at": 1700500130.0
}
```

---

### 2.7 Approve Reveal Request
Authorizes the reveal request on the shop screen. Resolves the pseudonym to the real identifier and logs an audit entry.

- **Method:** `POST`
- **Path:** `/api/reveal-requests/{req_id}/approve`
- **Request Body:**
```json
{
  "decision_reason": "Authorized by Shop Owner for security incident investigation"
}
```
- **Response (200 OK):**
```json
{
  "id": "req-8b3f12a0",
  "pseudonym": "src-1743a788",
  "reason": "Investigating high-volume authentication failure burst against Shop A login",
  "status": "approved",
  "requested_at": 1700500130.0,
  "decision_reason": "Authorized by Shop Owner for security incident investigation",
  "decided_at": 1700500195.2,
  "revealed_value": "198.51.100.42"
}
```

---

### 2.8 Reject Reveal Request
Rejects the reveal request, declining to disclose the real identifier.

- **Method:** `POST`
- **Path:** `/api/reveal-requests/{req_id}/reject`
- **Request Body:**
```json
{
  "decision_reason": "Insufficient justification provided"
}
```
- **Response (200 OK):**
```json
{
  "id": "req-8b3f12a0",
  "pseudonym": "src-1743a788",
  "reason": "Investigating high-volume authentication failure burst against Shop A login",
  "status": "rejected",
  "requested_at": 1700500130.0,
  "decision_reason": "Insufficient justification provided",
  "decided_at": 1700500195.2
}
```

---

### 2.9 Local Pseudonym Reveal Lookup
Direct local reverse lookup for any pseudonym (`src-`, `user-`, `host-`, `proc-`).

- **Method:** `GET`
- **Path:** `/api/reveal/{pseudonym}`
- **Response (200 OK):**
```json
{
  "pseudonym": "src-1743a788",
  "prefix": "src",
  "real_value": "198.51.100.42"
}
```
- **Error (404 Not Found):**
```json
{
  "detail": "Pseudonym 'src-00000000' not found in local reveal table"
}
```
