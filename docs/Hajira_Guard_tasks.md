# Airlock: Hajira's tasks (G · Guard engineer)

**Source:** *CICADA 2026 – Smart Observability Hackathon Plan* (the PRD). Every task points back to it:
- `PRD #n` = row *n* of the table "PRD: requirements to features"
- `§Section › Part` = a section of the plan

**Your role in one line:** you build the **guard**, the program that runs inside every customer environment. It collects everything, keeps raw data local, and sends only signed, allow-listed metadata. You also build the small demo shop app and the shop AI. (§Team split › Roles)

**You own:** `guard/`, `shop-api/` (§Working in Antigravity › Repo layout)

**Your laptop on demo day:** Ryzen = **Shop A "Acme" (India)**.

**Your guard runs on 3 machines** (§Architecture › Machines and ports):

| Machine | Tenant | Region endpoint | Time zone | Extra |
|---|---|---|---|---|
| Your Ryzen (Windows) | `acme` | India `ingest-in` :8001 | Asia/Kolkata | shop-api :7000, Toxiproxy :8474, guard :9000, Lemonade :13305 |
| Sahiti's Linux | `globex` | Europe `ingest-eu` :8002 | Europe/Berlin | shop-api :7000, real `sshd` + `auth.log`, guard :9000 |
| Anisa's laptop 4 (Windows) | `contoso` | India `ingest-in` :8001 | Asia/Kolkata | guard with organizer adapter :9000 |

> Same code everywhere. Only the per-machine `.env` changes (AGENTS.md rule: no hard-coded IPs).

---

## Handoffs: who you depend on, who depends on you

| You need… | From | By |
|---|---|---|
| Ingest endpoint + receipt format (in `contracts/`) | Sahiti | H2 |
| A running `ingest-in` to send to | Sahiti | H6 |
| Action-intent, dry-run and reveal-request APIs | Sahiti | H15 |
| Shop screen web bundle (your guard serves it) | Anisa | H12 |
| Access to the Linux laptop to install and test the guard | Sahiti | H8 |

| Others need from you… | Who | By |
|---|---|---|
| Payload schema v1 in `contracts/` | Everyone | H2 |
| Real signed payloads reaching `ingest-in` | Sahiti, Adithya | H6 |
| Guard local API (raw logs, ledger, buffer, reveal) | Anisa | H12 |
| Change events in payloads | Adithya | H12 |
| Guards running on all 3 machines | Everyone | H15 |

---

## Shared team tasks (§Team split, §Demo script)

- [ ] **H0–H2, contract:** with the team, write and freeze `contracts/`: payload schema, enums, API + WebSocket messages, action intent, ports, tenant IDs. **Your part: the payload schema** (T1).
- [ ] **Every 2 hours:** merge to `main` (H4, H6, H8, …) and run the smoke test (simulator → ingest → dashboard). Whoever breaks `main` fixes it first.
- [ ] **H12–H15, integration** on real laptops over the hotspot.
- [ ] **H15–H20:** take one 90-minute nap, staggered with the team.
- [ ] **H20–H22:** bug fixes only, and rehearse all live scenarios twice.
- [ ] **H22–H24:** be on Shop A + B during the demo.

---

## Tasks by phase

### H0–H2 · Setup + contract

#### T0. Set up the shop machines · PRD #22, §Team split
- [ ] Install Python 3.11+ on Ryzen, Linux and laptop 4.
- [ ] Install **Lemonade** on the Ryzen and test a Qwen model on the NPU. Fall back to CPU if the NPU fails. (§AI assistants)
- [ ] Turn on `sshd` on Sahiti's Linux laptop so `auth.log` records real failed logins.
- [ ] Create a `.env` template: tenant, region URL, guard key, source timezone, log sources.
- **Done when:** Lemonade answers a test prompt on the Ryzen; a wrong SSH password shows up in `auth.log`; the `.env` template is in the repo.

#### T1. Write the payload schema v1 in `contracts/` · PRD #4, §Architecture › Payload schema v1
- [ ] Turn the JSON example and the "allowed values" table into a pydantic v2 model with `extra="forbid"` + a JSON Schema file.
- [ ] Enums:
  - **Metrics:** `cpu_pct`, `mem_pct`, `disk_pct`, `net_in_kbps`, `net_out_kbps`, `latency_ms`, `packet_loss_pct`, `service_up`, `battery_pct`, `on_battery`, `battery_min_left`
  - **Event categories:** `auth_failure_burst`, `login_after_failures`, `honeypot_hit`, `odd_hour_login`, `service_down`, `new_log_pattern`, `log_pattern_spike`, `power_on_battery`, `secret_redacted`, `app_restarted`, `version_changed`, `config_changed`, `new_process`
  - **Severity:** `info`, `low`, `medium`, `high`, `critical`
  - **Identifiers:** must match `^(host|src|user|proc)-[0-9a-f]{8}$`
- [ ] Put 3 example payloads in `contracts/examples/` for Anisa and Adithya.
- **Done when:** the team agrees and the schema is frozen at H2. A payload with an extra field or a free-text string fails validation.

```text
Prompt: Read AGENTS.md. Create contracts/payload.py (pydantic v2, extra="forbid") and contracts/payload.schema.json
for schema "airlock.v1" exactly as in the plan's "Payload schema v1": payload_id, tenant_id, guard_id, seq,
prev_hash, policy_version, sent_at, window{start,end,source_tz}, metrics[], events[], log_patterns[], health{}.
Use enums for metric names, event categories and severity; identifiers must match ^(host|src|user|proc)-[0-9a-f]{8}$.
Add 3 valid example payloads in contracts/examples/ and a test that rejects unknown fields and free text.
```

### H2–H6 · Thin slice

#### T2. psutil → payload → sign → send · PRD #1, #6, §Data flow steps 1, 10
- [ ] Collect CPU every 2 s with psutil.
- [ ] Build a schema-valid payload.
- [ ] Sign it: HMAC-SHA256 over body + timestamp, with the payload ID as nonce.
- [ ] POST it over HTTPS to `ingest-in` and read the receipt.
- **Done when:** a CPU number from the Ryzen shows up in Sahiti's ingest and you get back `{payload_id, sha256, received_at, status}`.

```text
Prompt: Read AGENTS.md and contracts/. In guard/, build the thin slice: every 2 s read cpu_pct with psutil,
build a valid airlock.v1 payload (2 s window, UTC + source_tz from .env), sign it with HMAC-SHA256 over body +
timestamp using GUARD_KEY, POST over HTTPS to REGION_URL with a timeout, and log the receipt. Config from .env only.
```

### H6–H12 · Core

#### T3. All collectors · PRD #1, #8, §Data flow step 1
- [ ] psutil every 2 s: CPU, memory, disk, network in/out, battery (`battery_pct`, `on_battery`, `battery_min_left`).
- [ ] TCP probes for `latency_ms` and `packet_loss_pct`.
- [ ] HTTP health check of shop-api → `service_up`.
- [ ] Tail the shop-api log, plus `/var/log/auth.log` on Linux.
- [ ] Normalise everything to `{event_time UTC, source_tz, source, kind, fields}`.
- **Done when:** every metric name in the schema has live values on Ryzen and Linux.

#### T4. Raw store with 24 h retention · PRD #2, §Data flow step 2
- [ ] SQLite `raw.db` holds the raw lines, deletes anything older than 24 h (configurable), and exposes a retention countdown.
- **Done when:** raw lines (including secrets) are readable locally, and nothing from `raw.db` is ever placed in a payload.

#### T5. Secret scrubbing + canaries · PRD #3, §Data flow step 3, §Differentiators › Canary tripwire
- [ ] Use detect-secrets + regex to mask keys, passwords, tokens and card numbers. Count what was found (→ `secret_redacted` event + `health.secrets_redacted`).
- [ ] Every 30 s, plant a fake key (`AKIACANARY…`) in your own raw stream and count it in `health.canaries_planted`.
- **Done when:** a log line with an AWS key is masked in the pipeline, and the canary counter keeps going up.

#### T6. Log patterns with Drain3 · PRD #3, §Data flow step 4
- [ ] Each log line becomes a `pattern_id` + `level` + `count` + `is_new`. The pattern text never leaves.
- **Done when:** 50 similar login lines become one pattern with count 50.

#### T7. 2-second windows · PRD #3, #17, §Data flow step 5
- [ ] Every window has avg, max and counts, with UTC `start`/`end` + `source_tz`.
- **Done when:** payloads carry correct windows on both India and Europe time zones.

#### T8. Pseudonyms + reveal table · PRD #5, §Data flow step 7
- [ ] Build pseudonyms as `host-` / `src-` / `user-` / `proc-` + the first 4 bytes (8 hex digits) of HMAC-SHA256(tenant key, value).
- [ ] Keep the pseudonym-to-real-value mapping in a local table only.
- **Done when:** no hostname, IP or username appears in any payload, and the local lookup returns the real value.

#### T9. Local login-failure detection · PRD #9, §Data flow step 6
- [ ] Leaky-bucket detector → `auth_failure_burst` (count, window, attacker pseudonym, risk), plus `login_after_failures`.
- [ ] 3 AM shop-time login → `odd_hour_login`.
- **Done when:** 50 wrong passwords produce one `auth_failure_burst` with count 50 and severity high, with no usernames or IPs.

#### T10. Policy gate · PRD #4, §Data flow step 8, §Security controls › Defence in depth
- [ ] Validate every payload against the contract model (an unknown field is blocked).
- [ ] Scan the serialised payload for canaries before sending.
- **Done when:** a payload with an extra field or a canary is blocked and logged locally.

#### T11. Ledger + outbox + sender · PRD #7, #15, §Data flow steps 9–12
- [ ] Store the exact JSON, SHA-256, `prev_hash` and `seq` in the hash-chained ledger.
- [ ] SQLite outbox, sent oldest first, with backoff 1, 2, 4, 8, 10 s while the endpoint is unreachable.
- [ ] Verify the receipt hash and mark the ledger row ✅ (or ❌ on mismatch).
- **Done when:** with ingest stopped, the buffer grows. When it's back, the buffer drains, and the reconciliation shows sent = received with zero duplicates and zero gaps.

#### T12. Heartbeat in every payload · PRD #10
- [ ] `health` block: `guard_version`, `guard_cpu_pct`, `guard_mem_mb`, `buffer_depth`, `config_ok`, `canaries_planted`, `secrets_redacted`.
- **Done when:** Sahiti's fleet panel data shows all fields for each guard.

#### T13. Change events · PRD #27, §Correlation › What changed just before
- [ ] Send `app_restarted`, `version_changed`, `config_changed`, `new_process` as events.
- **Done when:** restarting shop-api produces an `app_restarted` event in the next payload.

#### T14. Receipt-log checkpoints · PRD #29, §Security controls › Receipt-log checkpoints
- [ ] Every 60 s, compute a running SHA-256 over all payload hashes in seq order and publish `{guard_id, up_to_seq, root}`.
- **Done when:** your root matches the head office root (✅). A mismatch names the first differing seq.

#### T15. Guard local API for the shop screen · §Screens › Inside the shop
- [ ] Endpoints for:
  - raw logs (secrets visible, local only)
  - egress ledger (exact JSON, hash, ✅/❌)
  - buffer depth
  - retention countdown
  - reveal lookup
- [ ] Serve Anisa's shop screen bundle from the guard (port 9000).
- **Done when:** Anisa's shop screen shows live data from your API.

#### T16. Demo shop app · §Team split › Roles (G owns `shop-api/`)
- [ ] A tiny shop API on port 7000 with login, products and checkout. It writes JSON-line logs that the guard tails.
- [ ] Text sent from the chaos console's try-to-leak box ends up in this log (§Differentiators › Try-to-leak challenge).
- **Done when:** wrong logins and leak text appear in the log and flow through the guard pipeline.

```text
Prompt (pipeline core): Read AGENTS.md and contracts/. In guard/, add one module per concern:
collectors (psutil 2 s, TCP probes, HTTP health, log tail incl. /var/log/auth.log), raw.db with 24 h retention,
scrubber (detect-secrets + regex) with canary planting every 30 s, Drain3 patterns, 2 s window aggregation,
HMAC pseudonyms with a local reveal table, policy gate (contract validation + canary scan), hash-chained ledger,
SQLite outbox and sender (backoff 1,2,4,8,10 s, receipt hash check). Write tests for the privacy and no-duplicate rules.
```

### H12–H15 · Integrate on real laptops

#### T17. Run guards on all 3 machines · §Team split › phase table
- [ ] Ryzen = `acme`/India, Linux = `globex`/Europe, laptop 4 = `contoso`/India, all over the hotspot.
- **Done when:** all three appear on the head-office fleet grid with live data, and the round 3 split screen works (§Roadmap).

### H15–H20 · Intelligence + extras

#### T18. Action executor + dry run · PRD #20, #31, §Safe remediation
- [ ] Pull signed intents (the guard is outbound-only) and re-check local policy.
- [ ] Execute:
  - `kill_process` (resolve the pseudonym to the real PID locally)
  - block source for 15 min (`iptables` on Linux, logged simulation on Windows)
  - restart shop-api
- [ ] Answer dry runs with exactly what would happen, without changing anything.
- [ ] Report results, auto-rollback if asked, and log every step.
- **Done when:** the judge approves on the phone, the fake miner is killed, and audit rows appear on both sides.

#### T19. Honeypot + power cut · PRD #9, #24, §Differentiators
- [ ] A login with `admin_backup` → `honeypot_hit` (critical).
- [ ] Charger pulled → `power_on_battery` + `battery_min_left`.
- **Done when:** both show at head office within one payload cycle.

#### T20. Shop AI · PRD #22, §AI assistants
- [ ] Lemonade on the NPU (CPU fallback) via the OpenAI Python client.
- [ ] Tools `search_raw_logs(query, minutes)` and `recent_auth_failures(minutes)` over local SQLite. Reachable only on that laptop.
- **Done when:** asked "show me the failed logins from the last 10 minutes", it lists the real lines.

#### T21. Organizer-stream adapter · PRD #1
- [ ] A pluggable source on laptop 4 that turns the organizer stream into normal guard events.
- **Done when:** organizer events flow as tenant `contoso` and the judges' latency checks use them.

#### T22. Reveal-request pull + local approve · PRD #28, §Security controls › Reveal with permission
- [ ] Pull head-office reveal requests. The shop admin approves or rejects on the shop screen; the answer is shown only there. Both sides log it.
- **Done when:** head office still shows `src-9c2e` while the shop screen shows the real IP.

```text
Prompt (actions): Read AGENTS.md and contracts/. In guard/, add an executor that polls head office for signed
action intents and reveal requests (outbound only). Re-check local policy, support dry_run, kill_process (resolve
proc- pseudonym locally), block source 15 min (iptables on Linux, logged simulation on Windows), restart shop-api.
Report results and log every step. Reveal requests wait for local approval and are answered only on the shop screen.
```

### H20–H24
- [ ] Bug fixes only. Rehearse your scenarios twice. During the final, stay on Shop A + B.

---

## Optional (P2, only if time allows) · §Open source
- [ ] Microsoft Presidio as an extra check for the try-to-leak box.

## If time runs short (§Summary › cut order)
Shop AI on the NPU falls back to CPU. Never cut: guard, redaction, egress proof, buffering (§Summary › MVP).

## Your demo scenarios (§Demo script › Live scenarios)
- Raw log with a secret
- Collector loses head office (Wi-Fi off on Shop A)
- Repeated failed logins (real `sshd` on Shop B)
- Power cut (pull Shop A's charger)
- Tamper on the guard side (ledger delete, policy edit)
- Change caused it (restart app)
- Who is behind a pseudonym (reveal)

## Judge questions you answer (§Judge questions)
What leaves the environment? · How does the guard decide what's allowed? · How do you stop accidental secret leaks? · What if head office is unreachable?
