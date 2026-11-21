# Airlock Defense & Judging Q&A Guide (docs/QA.md)

This document contains authoritative, mathematically grounded answers to the 12 most critical questions judges will ask during evaluations.

---

### Q1: How do you guarantee cleartext passwords or PII never cross the trust boundary?
**Answer:**
We implement a 3-layer defense-in-depth architecture at Tier 1 (inside the customer's machine):
1. **Strict Contract Allow-Listing (`contracts/models.py`):** The schema forbids extra fields (`extra="forbid"`). Only pre-approved metric names, Drain3 cluster IDs, and pseudonyms can exist in serialized JSON.
2. **Regex & Detect-Secrets Scrubbing:** All raw logs pass through token scrubbing patterns (Bearer tokens, AWS keys, passwords, database URIs) before ingestion.
3. **Synthetic Tripwires & Canaries:** We plant known synthetic canary tokens into local logs. The Ingest server has tripwire detection; if a canary ever crosses the wire, ingest immediately rejects the payload and raises an audit alert.

---

### Q2: What happens if the network drops between Guard and Head Office?
**Answer:**
The Guard maintains an in-memory and disk-backed circular ring buffer (`buffer_depth`). When ingest is unreachable:
1. Payloads accumulate in local queue with exponential backoff retry (1s to 10s ceiling).
2. No data is dropped up to the retention limit (24 hours).
3. Upon network reconnection, payloads are transmitted in strict sequence order (`seq`).
4. Ingest receives payloads idempotently (`ON CONFLICT (payload_id) DO NOTHING`) and reconciles sequence gaps.

---

### Q3: What happens if an entire regional cloud datacenter (e.g., India) experiences an outage?
**Answer:**
Data residency rules are strictly maintained even under catastrophic failure:
- Acme (India) is legally pinned to India Ingest (`airlock_in`).
- If India Ingest fails (simulated via `POST /api/regions/in/pause`), the endpoint returns `503 Service Unavailable`.
- The Guard **never fails over to Europe (`airlock_eu`)**, as cross-border forwarding would violate statutory data residency boundaries.
- Payloads buffer safely at Tier 1 until India recovers.

---

### Q4: How does your AIOps AI explain incidents without hallucinating?
**Answer:**
Our AI assistant does not invent facts or guess causes. It operates strictly over structured telemetry evidence:
- Every incident card contains an explicit `signals` array with `evidence_id`, `baseline`, standard deviation multiplier ($z$-score), and percentage contribution.
- The confidence score is computed via a transparent deterministic formula:  
  $$\text{Confidence} = \min(0.95,\, 0.4 + 0.15 \times N_{\text{agreeing signals}} + 0.1 \times \mathbb{I}_{\text{rule match}})$$
- Every Copilot response cites clickable evidence chips (e.g., `[ev-1]`, `[ev-2]`) that highlight the exact anomaly chart.

---

### Q5: How does noise reduction work without suppressing critical alerts?
**Answer:**
We utilize temporal clustering, log template clustering (Drain3), and deterministic kill-chain correlation:
- 50 failed logins in 2 seconds are collapsed at Tier 1 into a single `auth_failure_burst` event count.
- If a high-CPU spike occurs within 60 seconds on the same host, the AIOps engine correlates them into a single `Possible compromise` incident rather than two disparate tickets.
- Known periodic batch jobs (e.g., backups running every 60s) are matched against suppression rules and marked `SUPPRESSED · scheduled job` without waking on-call engineers.

---

### Q6: Can a rogue guard spoof another customer's telemetry or tamper with metrics?
**Answer:**
No. Every Guard must authenticate cryptographically:
1. Every ingest request requires headers `X-Airlock-Guard-ID`, `X-Airlock-Timestamp`, and `X-Airlock-Signature`.
2. The signature is computed as $\text{HMAC-SHA256}(\text{pre-shared guard secret}, \text{raw body bytes})$.
3. Timestamp skew is enforced within $\pm 300\text{ s}$ to prevent replay attacks.
4. Each payload contains `prev_hash`, creating an unalterable cryptographic hash chain ($H_n = \text{SHA256}(H_{n-1} \,\|\, \text{payload}_n)$).

---

### Q7: What happens if an attacker tampers with a payload in transit?
**Answer:**
If even a single byte is altered in transit:
1. The HMAC signature check fails at Ingest $\to$ returns `401 Unauthorized`.
2. The `sha256` hash mismatch is detected $\to$ marked `REJECTED · SIGNATURE`.
3. In the 3D Live Fleet Bridge, the particle bursts crimson at the Trust Boundary and never enters Head Office storage.

---

### Q8: What is the 60-second rolling checkpoint?
**Answer:**
Every 60 seconds, the Guard computes a Merkle root over all sequence hashes emitted during that window. It sends this root to `/api/checkpoints/compare`. Head Office independently computes the Merkle root over the payloads it received and stored.
- If the roots match: `✓ ROOT MATCH` (verified stream integrity).
- If they differ: `✕ MISMATCH` with `first_differing_seq`, instantly pinpointing the exact dropped or tampered packet.

---

### Q9: Why did you build with React 19, TypeScript, and Tailwind instead of standard Grafana?
**Answer:**
1. **Interactive Proofs:** Grafana cannot render our side-by-side Cryptographic Egress Proof, interactive Try-To-Leak challenge, or 1-tap dry-run remediation workflow with countdown timers.
2. **Hybrid 2D/3D Live Fleet Bridge:** Our custom WebGL / 2D SVG bridge visually proves data residency and particle flows across the trust boundary in real time.
3. **Multi-Surface Architecture:** One unified codebase provides distinct entry points for the Projector (`hq`), Local Customer Machine (`shop`), Adversarial Console (`chaos`), and Mobile On-Call (`phone`).

---

### Q10: How is customer data isolated inside the Head Office database?
**Answer:**
1. **Physical Regional Separation:** Data resides in separate databases: `airlock_core` (tenants, guards, users), `airlock_in` (India payloads, metrics, incidents), and `airlock_eu` (Europe payloads).
2. **PostgreSQL Row-Level Security (RLS):** Every table has RLS enabled with `current_setting('app.current_tenant')`.
3. **Role-Enforced Queries:** Customer tokens for Acme can only ever query `airlock_in` with tenant set to `acme`. Attempting to access Globex rows yields empty sets directly at the SQL engine level.

---

### Q11: How do you handle clock skew across global time zones?
**Answer:**
1. All database timestamps and contract payloads strictly use UTC ISO-8601 with `Z` suffix (`2026-11-21T04:12:00Z`).
2. Each payload window carries `source_tz` (`Asia/Kolkata` or `Europe/Berlin`).
3. In the UI, toggling between `UTC`, `VIEWER`, and `SHOP` changes the human-readable formatting labels, but never alters the chronological sorting order of events.

---

### Q12: What is the end-to-end latency from an event occurring to screen render?
**Answer:**
- Guard collection window: 2.0 s.
- Ingest validation + HMAC verification: 8–15 ms.
- AIOps anomaly evaluation + WebSocket broadcast: 12–25 ms.
- Browser WebSocket receipt to DOM update: 4–10 ms.
- **Total P95 Latency:** $\sim 2.3\text{ seconds}$ (well within our 10-second SLA limit).
