# Airlock: Sahiti's tasks (H · Head-office backend)

**Source:** *CICADA 2026 – Smart Observability Hackathon Plan* (the PRD). Every task points back to it:
- `PRD #n` = row *n* of the table "PRD: requirements to features"
- `§Section › Part` = a section of the plan

**Your role in one line:** you build the **head-office backend**. It receives guard data in two regions, checks it, stores it once, keeps customers separate, pushes live updates to the screens, and runs approvals, audit and chaos scenarios. (§Team split › Roles)

**You own:** `hq/ingest/`, `hq/api/`, `chaos/` (§Working in Antigravity › Repo layout)

**Where your code runs on demo day:**
- On **Adithya's LOQ**: `hq-api` + WebSocket :8000, `ingest-in` :8001, `ingest-eu` :8002, PostgreSQL :5432
- **Chaos agents** on each shop (:9100)

You develop on your Linux with Docker PostgreSQL and deploy to the LOQ for the demo. (§Team split › Roles note)

**Your laptop on demo day:** Linux = **Shop B "Globex" (Europe)**. It runs Hajira's guard; give her access by H8.

**Databases** (§Architecture › Machines and ports, starter prompt H):

| Database | Holds |
|---|---|
| `airlock_core` | tenants (with assigned region), guards (keys), users, audit |
| `airlock_in` | India region: metrics, events, patterns, receipts, health, incidents |
| `airlock_eu` | Europe region: same tables. **No cross-region replication, no failover** |

Tenants: `acme` (India), `globex` (Europe), `contoso` (organizer, India), `guests` (phones).

---

## Handoffs: who you depend on, who depends on you

| You need… | From | By |
|---|---|---|
| Payload schema v1 in `contracts/` | Hajira | H2 |
| Incident object shape in `contracts/` | Adithya | H2 |
| Real signed payloads from a guard | Hajira | H6 |
| Simulator posting signed payloads (for load and scenarios) | Adithya | H3 |
| PostgreSQL installed on the LOQ (his machine) | Adithya + you | H2 |

| Others need from you… | Who | By |
|---|---|---|
| Ingest endpoint, receipt format, API + WebSocket message types in `contracts/` | Everyone | H2 |
| `ingest-in` running with receipts | Hajira, Adithya | H6 |
| WebSocket push of live data | Anisa | H6 |
| Tables the AIOps worker reads and writes | Adithya | H6 |
| Chaos agent API for the console buttons | Anisa | H12 |
| Action-intent, dry-run and reveal-request APIs | Hajira, Anisa | H15 |

---

## Shared team tasks (§Team split, §Demo script)

- [ ] **H0–H2, contract:** with the team, write and freeze `contracts/`. **Your part:** ingest endpoint, receipt, API + WebSocket messages, action intent, reveal request, ports, tenant IDs.
- [ ] **Every 2 hours:** merge to `main` and run the smoke test (simulator → ingest → dashboard). Whoever breaks `main` fixes it first.
- [ ] **H12–H15, integration** on real laptops over the hotspot.
- [ ] **H15–H20:** take one 90-minute nap, staggered with the team.
- [ ] **H20–H22:** bug fixes only, and rehearse all live scenarios twice.
- [ ] **H22–H24:** be on the chaos console with the judge.

---

## Tasks by phase

### H0–H2 · Setup + contract

#### T0. Set up head office and the team basics · §Team split › phase table
- [ ] Docker PostgreSQL on your Linux for development.
- [ ] With Adithya: native PostgreSQL on the LOQ (Windows installer) + `mkcert` certificate for HTTPS. (§Open source)
- [ ] Phone hotspot set up and tested: laptops can reach each other.
- [ ] GitHub monorepo with the folders from §Repo layout and `AGENTS.md`.
- **Done when:** all 4 laptops can reach the LOQ over HTTPS on the hotspot, and the repo is cloned by everyone.

#### T1. Your part of the contract · §Working in Antigravity
- [ ] Define:
  - the ingest request (headers for signature, timestamp, payload ID)
  - the receipt `{payload_id, sha256, received_at, status: stored | duplicate}`
  - WebSocket message types
  - the action intent
  - the reveal request
- [ ] Add example JSON for each in `contracts/examples/`.
- **Done when:** frozen at H2 and Anisa can build screens from the examples.

### H2–H6 · Thin slice

#### T2. `ingest-in`: verify, store, receipt · PRD #6, #7, §Data flow steps 11–12
- [ ] One FastAPI app, run with `REGION=in`.
- [ ] Checks: known guard → valid HMAC → timestamp within ±5 min → insert by `payload_id` → return the receipt.
- **Done when:** Hajira's CPU payload is stored and she gets a receipt back.

#### T3. WebSocket push · PRD #19, §Data flow step 14
- [ ] Push new metrics and health to dashboards.
- **Done when:** Anisa's CPU tile updates live from your WebSocket.

```text
Prompt (thin slice): Read AGENTS.md and contracts/. Build hq/ingest as one FastAPI app started with REGION=in|eu.
Verify guard key (airlock_core.guards), HMAC-SHA256 signature, timestamp within ±5 min; validate the airlock.v1
contract; insert by payload_id with ON CONFLICT DO NOTHING into the region database; return a receipt
{payload_id, sha256, received_at, status}. In hq/api add a WebSocket that pushes new metrics and health.
```

### H6–H12 · Core

#### T4. Full ingest checks · PRD #4, #6, #16, §Data flow step 11, §Security controls
- [ ] Schema check (unknown field → quarantine + policy-violation alert).
- [ ] Pinned policy hash per tenant (drift alert).
- [ ] Canary and secret tripwire on the raw body.
- [ ] Seq-gap tracking and `prev_hash` chain check.
- [ ] Clock skew over 30 s → warning (§Global-ready design).
- **Done when:** each tamper case gives its own alert (see T12), and the leak badge stays at 0.

#### T5. Customer separation + logins · PRD #11
- [ ] PostgreSQL row-level security on `tenant_id`.
- [ ] Engineer login sees all tenants; customer logins (Acme, Globex) see only their own.
- **Done when:** logged in as Acme, no Globex row is returned by any API.

#### T6. `ingest-eu` + residency · PRD #18, §Global-ready design
- [ ] The same app with `REGION=eu` on :8002, writing only to `airlock_eu`.
- [ ] Each tenant has one assigned region in `airlock_core.tenants`.
- **Done when:** Globex data exists only in `airlock_eu` and Acme data only in `airlock_in`.

#### T7. Out-of-order + idempotent storage · PRD #16, #17
- [ ] Store and query by `window.start` (event time), never arrival time.
- [ ] Duplicates are no-ops but counted. A seq gap means "still buffered" until it's filled.
- **Done when:** replayed and shuffled payloads leave charts unchanged and only the duplicate counter rises.

#### T8. Reconciliation API · PRD #16, §Screens › Head office
- [ ] Per guard: sent / received / duplicates / gaps.
- **Done when:** after a forced outage and reconnect, sent = received, duplicates 0, gaps 0.

#### T9. Receipt-log checkpoint compare · PRD #29, §Security controls
- [ ] Compute the same running SHA-256 over received payload hashes in seq order every 60 s, and compare it with the guard's `{guard_id, up_to_seq, root}`.
- **Done when:** ✅ on both screens, and a mismatch names the first differing seq.

#### T10. Reveal-request API · PRD #28, §Security controls › Reveal with permission
- [ ] `POST /reveal-requests` from the head office (who is asking, and why). The guard pulls it; the decision is logged on both sides. The real value never comes back to head office.
- **Done when:** a request shows up on the shop screen and the head office audit log has the row.

#### T11. Chaos agent v1 · PRD #23, §Demo script
- [ ] An agent on each shop (:9100) for:
  - CPU spike
  - latency (Toxiproxy on Windows, `tc netem` on Linux)
  - brute force (real `sshd` on Shop B)
  - try-to-leak (post text to shop-api)
- **Done when:** each button from Anisa's console causes the real effect on the target shop.

```text
Prompt (core): Read AGENTS.md and contracts/. Extend hq/ingest: schema quarantine, per-tenant pinned policy hash,
canary/secret tripwire on the raw body, seq-gap and prev_hash chain checks, clock-skew warning over 30 s.
In PostgreSQL add row-level security on tenant_id for airlock_in and airlock_eu; logins for engineer vs customer.
In hq/api add reconciliation per guard (sent/received/duplicates/gaps), receipt-log checkpoint compare every 60 s,
and POST /reveal-requests. Store and query by window.start. Tests for duplicates and tenant isolation.
```

### H12–H15 · Integrate on real laptops

- [ ] Fix ingest issues with the real guards and measure delivery (§Team split › phase table).
- **Done when:** the round 3 evidence works live: split screen, forced outage + reconnect, reconciliation (§Roadmap).

### H15–H20 · Intelligence + extras

#### T12. Action intents, approvals, audit, dry run · PRD #20, #31, §Safe remediation
- [ ] The head office proposes an action, then checks policy:
  - the action is allowed for that tenant
  - risk is medium or lower
  - at most 3 actions per 10 min
- [ ] Phone approval records the judge's name, then a signed intent is created for the guard to pull.
- [ ] Dry-run endpoint, so the phone shows what would happen before Approve is enabled.
- [ ] Audit log for every step. Auto-rollback + escalation if health hasn't improved in 120 s.
- **Done when:** a kill-chain incident → dry run → approve → executed → audit rows on both sides.

#### T13. Region pause + tamper scenarios · PRD #23, §Demo script › Tamper
- [ ] "Pause India region" switch (ingest returns unavailable).
- [ ] Tamper cases:
  - edited payload → rejected
  - rogue guard → unauthenticated
  - policy edit → quarantined
  - ledger delete → chain break
  - clock skew → warning
  - replay + shuffle → duplicates blocked, order kept
- [ ] Extra chaos buttons: **Backup job** (CPU spike every 60 s) and **Restart app**. Also the kill-chain scenario.
- **Done when:** every tamper case shows its own alert at head office.

#### T14. Phone `/join` backend · PRD #24, §Differentiators › Judges' phones join
- [ ] Accept heartbeat + latency every 2 s from phone pages as tenant `guests`.
- **Done when:** a closed phone tab goes offline within 60 s.

```text
Prompt (actions + chaos): Read AGENTS.md and contracts/. In hq/api add action proposals with a policy check
(allowed for tenant, risk <= medium, max 3 per 10 min), a dry-run endpoint, phone approval with approver name,
signed intents for guards to pull, audit log, and auto-rollback + escalation if health doesn't improve in 120 s.
Add a region pause switch and phone /join heartbeats (tenant guests). In chaos/ build the agent (port 9100) and
tamper scripts: edited payload, rogue guard, policy edit, ledger delete, clock skew, replay + shuffle,
backup job, restart app, kill chain.
```

### H20–H24
- [ ] Bug fixes only. Rehearse twice. During the final, stand with the judge at the chaos console.

---

## Optional (P2) · §Open source
- [ ] NATS JetStream queue. Otherwise just mention it as the scale-up path.
- [ ] mTLS instead of HTTPS + HMAC (§Security controls, stretch).

## Your demo scenarios (§Demo script › Live scenarios)
- Collector loses head office (pause region)
- Duplicate or out-of-order delivery
- Remediation proposed (approval + audit)
- Tamper
- Who is behind a pseudonym
- Phones join

## Judge questions you answer (§Judge questions)
Authentication and encryption? · No loss or duplicates? · Scale to many collectors and tenants? · Regions, residency, time, ordering? · What if head office is unreachable?
