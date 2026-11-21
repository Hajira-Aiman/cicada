# Airlock: Round 2 Architecture & Security Slide
**CICADA 2026 – Smart Observability Hackathon · Judging Round 2 (25 Marks)**
*Presenter: Anisa Islam (F · Frontend and Demo)*

---

## 1. High-Level Architecture (2 Tiers, 4 Laptops, 1 Trust Boundary)

```mermaid
graph TB
    subgraph TIER1["TIER 1: ISOLATED CUSTOMER ENVIRONMENTS (Edge Guards)"]
        direction TB
        subgraph SHOP_A["Shop A 'Acme' (Ryzen AI Laptop · India)"]
            SA_APP["shop-api (:7000)"]
            SA_GUARD["Airlock Guard (:9000)<br>• SQLite raw.db (24h)<br>• detect-secrets + Drain3<br>• Outbox & Chained Ledger"]
        end

        subgraph SHOP_B["Shop B 'Globex' (Linux Laptop · Europe)"]
            SB_APP["shop-api (:7000)"]
            SB_GUARD["Airlock Guard (:9000)<br>• Real sshd & auth.log<br>• Local Pseudonyms (HMAC)<br>• Outbox & Chained Ledger"]
        end

        subgraph ORG["Organizer Stream (Laptop 4 · India)"]
            ORG_GUARD["Airlock Guard (:9000)<br>• Contoso stream adapter"]
        end

        subgraph GUESTS["Judges' Phone Fleet"]
            PHONE_GUARD["Browser Lite Collector<br>• Heartbeat & Latency (2s)"]
        end
    end

    subgraph BOUNDARY["=== ZERO-TRUST EGRESS PERIMETER (Outbound HTTPS Only) ==="]
        direction LR
        PAYLOAD["Allow-Listed Payload airlock.v1<br>• HMAC-SHA256 Signature Header<br>• Nonce / Payload UUID<br>• prev_hash & Monotonic seq<br>• ZERO Free Text / Raw IPs"]
    end

    subgraph TIER2["TIER 2: HEAD OFFICE HEADQUARTERS (Lenovo LOQ Projector)"]
        direction TB
        subgraph INGEST_SERVICES["Regional Ingest Services"]
            INGEST_IN["ingest-in (:8001)<br>India Data Residency"]
            INGEST_EU["ingest-eu (:8002)<br>Europe Data Residency"]
        end

        subgraph STORAGE["PostgreSQL 16 (Multi-Tenant Native)"]
            PG_CORE[("airlock_core<br>Tenants, Guards, Policies, Audit")]
            PG_IN[("airlock_in<br>India Metrics & Receipts")]
            PG_EU[("airlock_eu<br>Europe Metrics & Receipts")]
        end

        subgraph INTELLIGENCE["AIOps & Core Engine (:8000)"]
            AIOPS["AIOps Engine<br>• EWMA Baselines & z-scores (3 windows)<br>• River HalfSpaceTrees<br>• 4 Health States (Exc, Good, Fair, Poor)<br>• Correlation & Kill-Chain Engine"]
            AI_ASSIST["Head Office AI Assistant<br>• Ollama Qwen 3.5:4B (evidence-only)"]
        end

        subgraph PROJECTOR["Presentation Dashboards"]
            HQ_UI["Head Office Projector UI (:8000)<br>• Fleet Grid & Normal-Band Charts<br>• Incident Cards & Counterfactuals<br>• Reconciliation & Egress Proof"]
        end
    end

    SA_GUARD -->|POST :8001 (India)| INGEST_IN
    ORG_GUARD -->|POST :8001 (India)| INGEST_IN
    PHONE_GUARD -->|POST :8000 (Direct)| INTELLIGENCE
    SB_GUARD -->|POST :8002 (Europe)| INGEST_EU

    INGEST_IN --> PG_IN
    INGEST_EU --> PG_EU
    INGEST_IN --> PG_CORE
    INGEST_EU --> PG_CORE

    PG_IN --> AIOPS
    PG_EU --> AIOPS
    AIOPS --> HQ_UI
    AI_ASSIST --> HQ_UI
```

---

## 2. Payload Schema v1 & Strict Allow-List

Every payload emitted across the boundary must conform strictly to `airlock.v1`. Pydantic models on both Guard and Ingest enforce `extra="forbid"`. Any unlisted key causes immediate rejection.

```json
{
  "schema": "airlock.v1",
  "payload_id": "0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
  "tenant_id": "globex",
  "guard_id": "guard-globex-01",
  "seq": 1042,
  "prev_hash": "sha256:9c1e457f0a91e523bf4c01d98a2e4b3c7f1a92e850d64389efb21c4078a9c3b1",
  "policy_version": "sha256:ab12ef45cd890123456789abcdef0123456789abcdef0123456789abcdef0123",
  "sent_at": "2026-11-20T12:00:02Z",
  "window": {
    "start": "2026-11-20T12:00:00Z",
    "end": "2026-11-20T12:00:02Z",
    "source_tz": "Europe/Berlin"
  },
  "metrics": [
    {"name": "cpu_pct", "source": "host-7f3a1234", "avg": 88.5, "max": 96.0},
    {"name": "latency_ms", "source": "host-7f3a1234", "avg": 240.5, "max": 310.0}
  ],
  "events": [
    {"category": "auth_failure_burst", "severity": "high", "source": "host-7f3a1234", "actor": "src-9c2e5678", "count": 50, "window_s": 60}
  ],
  "log_patterns": [
    {"pattern_id": "tpl-0001", "level": "ERROR", "count": 40, "is_new": true}
  ],
  "health": {
    "guard_version": "0.3.1",
    "guard_cpu_pct": 1.4,
    "guard_mem_mb": 62.5,
    "buffer_depth": 0,
    "config_ok": true,
    "canaries_planted": 48,
    "secrets_redacted": 12
  }
}
```

### The Strict Allow-List

| Field Group | Permitted Items | Validation & Boundary Enforcement |
|---|---|---|
| **Metric Names** | `cpu_pct`, `mem_pct`, `disk_pct`, `net_in_kbps`, `net_out_kbps`, `latency_ms`, `packet_loss_pct`, `service_up`, `battery_pct`, `on_battery`, `battery_min_left` | Fixed Enum; non-matching names rejected |
| **Event Categories** | `auth_failure_burst`, `login_after_failures`, `honeypot_hit`, `odd_hour_login`, `service_down`, `new_log_pattern`, `log_pattern_spike`, `power_on_battery`, `secret_redacted`, `app_restarted`, `version_changed`, `config_changed`, `new_process` | Fixed Enum; structured event counters only |
| **Severity Enums** | `info`, `low`, `medium`, `high`, `critical` | Fixed Enum |
| **Identifiers** | Pseudonyms strictly matching `^(host\|src\|user\|proc)-[0-9a-f]{8}$` | HMAC-SHA256 with tenant key; raw IPs/users forbidden |
| **Log Patterns** | Drain3 template hashes `^tpl-[0-9a-f]{4,8}$` + count | Freeform log text, query strings, and arguments stripped |
| **Forbidden Fields** | Raw log text, passwords, usernames, cleartext IPs, file paths, SQL queries | Blocked by schema `extra="forbid"` and pre-send tripwires |

---

## 3. Four Core Security Controls

1. **Guard Authentication & Request Signing**:
   - Every guard has a unique secret registered in `airlock_core`.
   - Outgoing payloads are signed via HMAC-SHA256 over `timestamp.payload_id.payload_json`.
   - Headers: `X-Airlock-Signature`, `X-Airlock-Timestamp`, `X-Airlock-Payload-Id`, `X-Airlock-Guard-Id`. Replays and clock skews (>5 min) are rejected.
2. **Pre-Send Canary Tripwire**:
   - Guards inject synthetic canaries (`AKIACANARY[0-9A-Z]{16}`) into local raw streams every 30s.
   - The Pre-Send Gatekeeper scans outgoing payloads. If any canary or unmasked secret pattern appears, the transmission is aborted.
3. **Outbound-Only Architecture**:
   - Guards never open inbound listening ports to the public network or Head Office.
   - Remediation intents are polled outbound by the guard (`GET /tenants/{id}/actions/pending`).
4. **Local Reverse Reveal Table**:
   - The mapping of pseudonyms (`src-9c2e5678`) to raw IPs (`192.168.1.55`) is stored in local SQLite (`reveal.db`).
   - Head Office can only *request* a reveal; authorization occurs strictly on the local shop screen.

---

## 4. Global-Ready Architecture: Residency, Outages & Idempotency

### A. Strict Regional Data Residency (No Failover by Design)
- **Shop A (Acme)** is assigned to region `in` (`http://...:8001`). Its data resides exclusively in `airlock_in`.
- **Shop B (Globex)** is assigned to region `eu` (`http://...:8002`). Its data resides exclusively in `airlock_eu`.
- **Zero Cross-Region Spill:** If Europe ingest (:8002) is partitioned, Shop B's guard buffers locally. It will **never** failover to India (:8001). Data residency supersedes temporary cloud availability.

### B. Outage Buffering & Zero Loss (SQLite Outbox)
- During an outage, payloads accumulate in SQLite `outbox.db` in monotonic `seq` order.
- The worker executes exponential backoff (1s, 2s, 4s, 8s, max 10s).
- When the endpoint recovers, buffered payloads drain in strict FIFO sequence.

### C. Cryptographic Deduplication & Reconciliation
- Regional ingest uses `ON CONFLICT (payload_id) DO NOTHING` in PostgreSQL. Replayed payloads return the original receipt with `status: "duplicate"`.
- Monotonic sequence tracking highlights sequence gaps (`seq_n - seq_{n-1} > 1`) as un-drained buffer items.
- The Reconciliation Panel guarantees:
  $$\text{Sent} = \text{Received}, \quad \text{Duplicates} = 0, \quad \text{Gaps} = 0$$
