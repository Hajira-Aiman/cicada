# Airlock: Round 1 Data-Flow Sketch & Trust Boundary
**CICADA 2026 – Smart Observability Hackathon · Judging Round 1 (10 Marks)**
*Presenter: Anisa Islam (F · Frontend and Demo)*

---

## 1. Executive Summary & Core Pitch
> *"Other observability tools ask you to trust that they don't leak. Airlock proves it, live."*
> *"We bring the AI to the data, never the data to the AI."*

In traditional observability, raw logs, database queries, and system traces leave customer networks and are shipped to multi-tenant cloud vendors—creating severe privacy liabilities, credential leak risks, and compliance breaches.

**Airlock solves this with a strict physical trust boundary:**
- Telemetry analysis, secret scrubbing, pattern mining, and raw storage remain strictly **inside** the customer boundary.
- **Zero raw text crosses the perimeter:** Outbound communication allows only strongly typed, allow-listed numerical aggregates, fixed categorization enums, and cryptographic pseudonyms.
- **Cryptographic Egress Proof:** Every outbound transmission is hash-chained in an immutable local ledger and reconciled with signed receipts from head office.

---

## 2. Architecture & Data-Flow Diagram

```mermaid
flowchart TD
    subgraph TIER1["TIER 1: CUSTOMER ENVIRONMENT (Shop A / Shop B / Organizer)"]
        direction TB
        APP["Local Demo Shop (shop-api :7000)<br>• Web Traffic, Auth, Checkout<br>• Local Logging (shop-api.log)"]
        SYS["Host & System<br>• psutil metrics (CPU, Mem, Disk, Net)<br>• auth.log & SSH events<br>• Battery & Probes"]
        
        subgraph GUARD["Airlock Guard Daemon (:9000)"]
            RAW_DB[("Local SQLite raw.db<br>• Full Raw Logs & Text<br>• Raw Usernames & IPs<br>• 24h Auto-Prune")]
            SCRUB["Privacy Engine<br>• Secret Scrubber (detect-secrets + regex)<br>• Canary Tripwires (AKIACANARY...)"]
            DRAIN["Drain3 Pattern Miner<br>• Raw Line -> Template ID (tpl-xxxx)<br>• Strips Variables & Free Text"]
            PSEUDO["Pseudonymizer Engine<br>• HMAC-SHA256 with Tenant Key<br>• host-*, src-*, user-*, proc-*<br>• Local Reveal Table (reveal.db)"]
            GATE["Strict Policy Gate<br>• Schema Validation (airlock.v1)<br>• Default Deny: Extra Fields Blocked<br>• Pre-Send Canary/Secret Scanner"]
            OUTBOX[("SQLite Outbox & Ledger<br>• Hash Chaining: prev_hash -> seq<br>• FIFO Buffer with Backoff")]
        end

        SHOP_UI["Inside the Shop Screen (:9000)<br>• Raw Logs & Secrets (Visible ONLY here)<br>• Egress Proof Panel (Sent JSON vs Receipt)<br>• Buffer Depth & Retention Countdown<br>• Local Reveal Approval Modal"]
    end

    subgraph TRUST_BOUNDARY["=== TRUST BOUNDARY (STRICT EGRESS ONLY) ==="]
        direction LR
        WIRE["Outbound HTTPS/HTTP POST<br>• Strictly Schema Allow-Listed JSON<br>• HMAC-SHA256 Signature Header<br>• Monotonic seq & prev_hash<br>• ZERO Raw Text, ZERO Cleartext IPs"]
    end

    subgraph TIER2["TIER 2: HEAD OFFICE & DEMO PRESENTATION"]
        direction TB
        subgraph INGEST["Regional Ingest Services"]
            IN_IN["ingest-in (:8001)<br>India Region (Shop A)"]
            IN_EU["ingest-eu (:8002)<br>Europe Region (Shop B)"]
        end
        
        DB[("PostgreSQL 16 (Native)<br>• airlock_core (Tenants, Guards, Audit)<br>• airlock_in / airlock_eu<br>• Row-Level Security on tenant_id")]
        
        AIOPS["AIOps Engine (:8000)<br>• EWMA Baselines & z-scores<br>• River HalfSpaceTrees<br>• Health States (Exc, Good, Fair, Poor)<br>• Correlation & Kill-Chain Engine"]
        
        HQ_UI["Head Office Dashboard (:8000 Projector)<br>• Tenant Switcher (Acme / Globex)<br>• Fleet Grid (4 states + reasons)<br>• Normal-Band Live Charts<br>• Incident Cards with Contribution Bars<br>• Reconciliation Panel (sent/received/dupes)<br>• Leak Tripwire Badge (0 Leaks Detected)"]
    end

    subgraph CONTROLS["MOBILE & CHAOS CONTROLS"]
        CHAOS["Chaos Console (:5173 - Laptop 4)<br>• Try-to-Leak Challenge Box<br>• Fault Buttons: CPU Spike, Auth Burst, Region Outage"]
        PHONE["Judges' Phone Pages (:8000)<br>• /join: QR Fleet Collector<br>• /approve: Remediation with Dry Run<br>• /raw vs /smart: Alert Noise Demonstration"]
    end

    %% Data flows
    APP -->|Raw Log Lines| SCRUB
    SYS -->|System Telemetry| GUARD
    SCRUB -->|Stores Raw Untruncated Data| RAW_DB
    SCRUB -->|Scrubbed Templates| DRAIN
    SYS -->|Identities| PSEUDO
    DRAIN --> GATE
    PSEUDO --> GATE
    GATE --> OUTBOX
    OUTBOX -->|Outbound Post| WIRE
    WIRE --> INGEST
    INGEST -->|Verify HMAC, Canaries & Insert| DB
    DB --> AIOPS
    AIOPS --> HQ_UI
    
    RAW_DB -.->|Local Loopback Only| SHOP_UI
    OUTBOX -.->|Proof Matching| SHOP_UI

    CHAOS -.->|Injects Faults| APP
    PHONE <-->|WebSocket Alerts & Approvals| AIOPS
```

---

## 3. Data Visibility Matrix: Who Sees What?

| Information Category | Inside the Shop Screen (`:9000`) | Head Office Dashboard (`:8000`) | Chaos Console (`:5173`) | Phone Pages |
|---|---|---|---|---|
| **Raw Log Messages** | ✅ **Full raw text** visible for local debugging | ❌ **Completely Absent** (Never sent) | ❌ Absent | ❌ Absent |
| **Passwords & API Keys** | ✅ Visible in local logs (for verification) | ❌ **0% Exposure** (Redacted + Tripwire blocked) | ⚠️ Injection test input only | ❌ Absent |
| **User Identifiers** | ✅ Real usernames (`admin`, `alice`) | 🔒 Pseudonyms only (`user-7f3a8b1c`) | ❌ Absent | 🔒 Pseudonyms |
| **Host & IP Addresses** | ✅ Real IPs (`192.168.1.50`) | 🔒 Pseudonyms only (`host-9c2e01fa`, `src-4a12be88`) | ❌ Target hostname | 🔒 Pseudonyms |
| **Log Patterns** | ✅ Template text + raw message | 📊 Drain3 Pattern ID (`tpl-3fa1`) & count only | ❌ Absent | ❌ Absent |
| **Metrics & Health** | ✅ Local buffer depth & system metrics | 📊 Aggregated 2s avg/max + Normal Bands | ❌ Absent | 📊 Health State |
| **Incident Explanations**| ❌ Local operator focuses on raw logs | 🧠 Full Incident cards, contribution %, counterfactual | ❌ Absent | 📱 Clean summary (`/smart`) |
| **Egress Proof & Ledger**| ✅ **Exact JSON sent, SHA-256, ✅ receipt** | 📊 Reconciliation table (sent vs received vs gaps) | ❌ Absent | ❌ Absent |
| **Remediation Actions** | 🔒 Local approval prompt for pseudonym reveals | ⚡ Propose remediation & review audit log | ❌ Absent | 📱 **Dry-run & Approve button** |

---

## 4. The 4 Mandatory Demo Moments (Scored in Judging)

### 1. The "Try-to-Leak" Challenge (Proof of Privacy)
- **Judge Action:** The judge enters an arbitrary secret or password into the Chaos Console's Try-to-Leak box (e.g., `AWS_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`).
- **Shop Screen:** Shows the raw log line in `raw.db` containing the key.
- **Head Office Screen:** Shows only `secret_redacted: 1` count and pattern template ID `tpl-0042`. The raw secret **never** crosses the trust boundary.
- **Leak Badge:** Egress audit confirms 0 leak occurrences.

### 2. Egress Proof Panel (Mathematical Proof)
- **What Judge Sees:** On the Shop Screen, the judge inspects the Egress Proof panel showing the exact JSON payload, its SHA-256 hash, and the cryptographically signed receipt returned by the regional ingest service.
- **Why It Matters:** Eliminates the "black-box trust" assumption. The judge can personally verify that what left the shop matches what head office received bit-for-bit.

### 3. Outage Buffer & Reconciliation (Resilience)
- **Judge Action:** Judge triggers "Pause Region Ingest" or network cable disconnect.
- **Shop Behavior:** Guard detects unreachable endpoint, holds telemetry in SQLite outbox, and applies exponential backoff (1s, 2s, 4s, 8s, 10s).
- **Head Office:** Health state marks node as `Stale` at 10s and `Poor` at 30s.
- **Resume:** Upon reconnection, outbox drains in strict FIFO sequence. Reconciliation panel proves:
  $$\text{Sent} = \text{Received}, \quad \text{Duplicates} = 0, \quad \text{Gaps} = 0$$

### 4. Noisy vs. Clean Phones (AIOps Noise Cut)
- **Demonstration:** Two phones placed side by side.
  - **Phone 1 (`/raw`):** Buzzes incessantly for every low-level alert (47 raw alerts).
  - **Phone 2 (`/smart`):** Receives **one** unified, prioritized incident ("Possible compromise: cryptomining" with 94% noise cut, root cause, and 1-tap safe rollback remediation).
