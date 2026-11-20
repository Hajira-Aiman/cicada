# Milestone 1 Design Doc: Thin Slice Telemetry & Transmission

**Date:** 2026-11-20  
**Machine:** Linux Laptop (Shop B · Globex · Europe Region)  
**Status:** Proposed for Approval  

---

## 1. Intent and Why
Establish the first working end-to-end slice of Airlock telemetry from the Linux environment:
- Target web shop (`shop-api`) emits logs and provides a health check on port 7000.
- Guard agent collects real host metrics (`psutil`) and probe data every 2s, aggregates into 2s tumbling windows, formats into strict `airlock.v1` schema payloads, signs them with HMAC-SHA256, and posts them to the regional ingest endpoint (port 8002).
- E2E verification proves telemetry flows across the trust boundary with zero raw data leaks and receives cryptographically verifiable receipts.

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- Run `shop-api` on port 7000 with `/health`, `/products`, `/checkout`.
- Implement `guard/collector.py` polling `psutil` host metrics, TCP latency/loss probe, and `shop-api` HTTP health probe.
- Implement `guard/aggregator.py` bundling metrics into 2s tumbling windows with UTC ISO-8601 timestamps and `source_tz`.
- Implement `guard/signer.py` generating HMAC-SHA256 signatures using `GUARD_SECRET`.
- Implement `guard/sender.py` asynchronously posting payloads to `HQ_INGEST_URL` and parsing `IngestReceipt`.
- Provide `tools/mock_ingest.py` on port 8002 to enable immediate standalone verification on Linux.
- Provide `scripts/dev.sh` to run the stack cleanly.
- 100% test coverage on telemetry aggregation, payload signing, and transmission.

### Non-Goals (Deferred to Milestone 2 & 4)
- Drain3 log mining and full regex secret scrubbing (Milestone 2).
- SQLite outbox offline buffering and 24h `raw.db` retention (Milestone 2).
- Linux `iptables` remediation and chaos agent (Milestone 4).

### Anti-Goals
- Never send raw hostnames, raw IP addresses, raw usernames, or free-form text across the wire.
- Never add unnecessary abstraction layers or external queue dependencies.

---

## 3. Approaches Considered

- **Approach A (Direct In-Memory Pipeline + Mock Ingest Harness):**
  A clean, modular Python pipeline inside `guard/` with dedicated modules: `collector.py`, `aggregator.py`, `signer.py`, `sender.py`, orchestrated by `guard/main.py` (FastAPI). Tested against a local mock ingest server (`tools/mock_ingest.py`) validating HMAC signatures and returning signed receipts.
  *Pros:* Smallest complete change, zero bloated dependencies, 100% testable in isolation, directly reusable when SQLite outbox is added in M2.
  *Cons:* Relies on in-memory queue until SQLite outbox is wired in M2.
  *Selected: Yes.*

- **Approach B (All-in-one Single File Script):**
  Putting the collector, signer, sender, and shop-api into a single monolithic script.
  *Pros:* Fast to draft.
  *Cons:* Violates single-concern architecture, hard to test, messy to expand into M2 (Drain3, outbox, raw store, remediation).
  *Selected: No.*

---

## 4. Architecture & Components

```
[ Linux Laptop: Shop B (Europe) ]
┌───────────────────────────────┐
│  shop-api (FastAPI: 7000)     │ <── HTTP probe every 2s
│  /health, /products, checkout │
└───────────────────────────────┘
              ▲
              │ polls
┌─────────────┴────────────────────────────────────────────────┐
│  guard (FastAPI: 9000)                                       │
│  ├── collector.py   (psutil host stats, TCP probe, HTTP probe│
│  ├── aggregator.py  (2s tumbling window, pseudonym mapping)  │
│  ├── signer.py      (HMAC-SHA256 signature generator)        │
│  ├── sender.py      (async HTTP transmitter with backoff)    │
│  └── main.py        (FastAPI lifecycle & background loops)   │
└─────────────────────────────┬────────────────────────────────┘
                              │
                              │ POST /ingest (HMAC signed JSON)
                              ▼
┌──────────────────────────────────────────────────────────────┐
│  tools/mock_ingest.py (Port 8002, Europe Ingest Simulator)   │
│  Validates: guard_key, HMAC, airlock.v1 schema, returns      │
│  { payload_id, sha256, received_at, status: "stored" }      │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Verification Plan
- Unit tests (`tests/test_collector.py`, `tests/test_aggregator.py`, `tests/test_signer.py`).
- Integration test (`tests/test_e2e_thin_slice.py`): Starts `shop-api`, `mock_ingest`, triggers guard transmission, and asserts payload was accepted with a valid receipt and 0 schema violations.
