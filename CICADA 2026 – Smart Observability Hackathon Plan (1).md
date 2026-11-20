# CICADA 2026 – Smart Observability Hackathon Plan

Nov 20, 2026 · @Adithya

## Summary and MVP

We are building **Airlock**: a guard inside each customer's environment collects and analyses everything locally, and sends only allow-listed numbers and labels to a multi-customer head office. The head office turns those into explained incidents and safe, human-approved fixes. Pitch: *"Other tools ask you to trust that they don't leak. Airlock proves it, live."* Second line: *"We bring the AI to the data, never the data to the AI."*

**Minimum viable demo (never cut):**

1. A guard on 2 real laptops plus the organizer stream, sending metadata only.
2. Secrets and raw logs visible on the shop screen, absent at head office.
3. Egress proof panel with sent-vs-received matching.
4. Offline buffer, retry and resume with zero loss and zero duplicates.
5. Four health states with reasons and stale-data handling.
6. Anomalies grouped into incidents with signal contributions, confidence and a recommended action.
7. The head-office AI assistant answering from evidence only.

**Picked extras:** judges' phones join the fleet (1), try-to-leak challenge (2), phone approval of fixes (3), noisy vs clean phones (4), kill-chain attack story (5), charger-pull power cut (7), honeypot account (9), thumbs up/down on alerts (11), damage map (14), and two AI assistants (shop + head office). Innovation adds: reveal with permission, receipt-log checkpoints, "what changed just before" incidents, no flapping, and learned scheduled jobs. A time-zone switch and a dry-run button make the bonus challenges visible.

**Assumptions to confirm** (questions not yet answered):

| Topic | Assumed | Change if |
| --- | --- | --- |
| Name | Airlock | You prefer another |
| Network | Our own phone hotspot | Venue Wi-Fi lets laptops talk |
| Code | One GitHub monorepo, branch per person | — |
| Security | HTTPS + per-guard key + signature on every payload; mTLS only if time allows | — |
| Database | PostgreSQL installed natively on the LOQ (Docker exists only on Linux) | — |
| Presenter | One speaker + slides | Everyone presents |
| Cut order | Talking alerts → damage map → phone fleet → thumbs feedback → NPU (CPU fallback) | You reorder |
| Team roles | 4 roles below; names to be mapped | — |
| Timing | Judging at roughly H2, H6, H15 and H23 | Organizers publish real times |

## PRD: requirements to features

Every item the judges check maps to one feature with a priority and one owner. **P0** = never cut (MVP), **P1** = planned, **P2** = only if time allows. Owners: **G** = Guard engineer, **H** = Head-office backend, **A** = AIOps and AI, **F** = Frontend and demo.

| # | Requirement (from the guide) | Airlock feature | Priority | Owner |
| --- | --- | --- | --- | --- |
| 1 | Collect infra, app, network, security telemetry | psutil host metrics every 2 s; TCP probes for latency and packet loss; HTTP health check of shop API; tail shop-API log and Linux `auth.log`; organizer-stream adapter | P0 | G |
| 2 | Raw data stays local | Raw store in local SQLite with 24 h retention, shown only on the shop screen | P0 | G |
| 3 | Filter, redact, aggregate, summarise | Secret scrubbing (detect-secrets + regex), Drain3 log patterns, 2 s windows (avg, max, counts) | P0 | G |
| 4 | Allow-listed metadata only | Strict payload schema: unknown fields rejected; strings only from fixed lists or pseudonyms. Free text can't leave | P0 | G |
| 5 | Pseudonymous source IDs | HMAC of hostname, IP and user with a tenant-held key (`host-7f3a`); mapping kept local for "reveal locally" | P0 | G |
| 6 | Collector auth + encrypted transport | HTTPS + per-guard secret + HMAC signature + timestamp on every payload; guard is outbound-only | P0 | G + H |
| 7 | Auditable transfer records + egress proof panel | Hash-chained egress ledger (payload, SHA-256, previous hash, seq); signed receipt from head office; sent vs received matching | P0 | G + H |
| 8 | Monitor CPU, memory, disk, availability, bandwidth, latency, loss, connectivity | Metric set in the schema; charts with a normal-range band | P0 | G + F |
| 9 | Repeated failed logins, suspicious activity | Local leaky-bucket detector, honeypot account, 3 AM shop-time login rule; only counts and a risk level leave | P0 | G |
| 10 | Collector online/offline, last seen, version, resource use, config status | Heartbeat inside every payload; guard CPU and memory, buffer depth, policy hash; fleet panel | P0 | G + H + F |
| 11 | Multi-tenant separation | PostgreSQL row-level security on `tenant_id`; customer logins see only their tenant; engineer login sees all | P0 | H |
| 12 | Four health states with configurable thresholds, reasons, stale handling | Health engine; stale at 10 s, offline at 30 s; every transition logged in UTC | P0 | A |
| 13 | Anomaly detection beyond thresholds | Rolling baseline (mean and spread) per metric, z-score for 3 points in a row, River anomaly score as second opinion; "signals must agree" rule | P0 | A |
| 14 | Correlate, prioritise, explain, recommend | Incident grouping (same tenant, related component, 120 s window), kill-chain rule, contribution bars, confidence, counterfactual, runbook action | P0 | A |
| 15 | Outage detection, buffering, retry, resume | SQLite outbox, oldest-first, backoff up to 10 s, receipts; region pause button | P0 | G + H |
| 16 | No loss, no duplicates | Unique `payload_id` in PostgreSQL + seq gap tracking; reconciliation panel | P0 | H |
| 17 | UTC + source timezone, out-of-order | Every window carries UTC start/end + `source_tz`; storage and charts ordered by event time | P0 | G + H |
| 18 | Regional ingest, tenant data residency | Two ingest services (India 8001, Europe 8002) writing to separate databases; no failover to the other region | P1 | H |
| 19 | Real-time targets measured | Live latency meter (event time to render, p50/p95); alert-delay and offline-delay stamps | P0 | F + A |
| 20 | Safe remediation: policy, approval, audit, rollback | Action intents pulled by the guard, local policy check, phone approval page, audit log, auto-rollback timer | P1 | H + G + F |
| 21 | Head-office AI assistant | Ollama Qwen, evidence-only answers with clickable evidence tags, pre-written incident narratives | P0 | A |
| 22 | Shop AI assistant | Lemonade on the Ryzen NPU (CPU fallback), reads local raw logs | P1 | G |
| 23 | Live chaos and tamper scenarios | Chaos console: CPU spike, latency, brute force, leak, region outage, duplicates/out-of-order, tamper, kill chain | P0 | H + F |
| 24 | Picked extras | Phone fleet join, noisy vs clean phones, power cut, thumbs feedback, damage map | P2 | F + A + G |
| 25 | Bonus: alert-noise reduction (made visible) | No flapping: a source turns Fair only after 6 s bad and returns only after 20 s good; "flaps prevented" counter | P1 | A + F |
| 26 | Real anomaly vs normal spike | Learned scheduled jobs: the same spike at a steady interval 3 times is labelled "scheduled job" and suppressed, with the reason shown | P1 | A |
| 27 | Correlate and highlight likely causes | What changed just before: guard sends change events (app restarted, version changed, config changed, new process); incidents show "started 40 s after shop-api restarted" | P1 | G + A |
| 28 | Who can see what | Reveal with permission: head office requests the real value behind a pseudonym; the shop admin approves on the shop screen; the value appears only there; both sides log it | P1 | G + H + F |
| 29 | Auditable transfer records | Receipt-log checkpoints: every 60 s guard and head office each publish a running hash of all payloads sent and received; ✅ badge when equal | P1 | G + H |
| 30 | Bonus: global-ready delivery (made visible) | Time-zone switch (UTC / viewer / shop time); Shop A runs on India time, Shop B on Europe time, both line up on one UTC timeline | P1 | F |
| 31 | Bonus: safe remediation simulation | Dry-run button: shows exactly what the fix would change before Approve is enabled | P1 | H + F |

**Out of scope:** real SNMP or flow devices, Kubernetes, fully autonomous fixes, production-grade key management.

## Differentiators and demo moments

Our edge is provable privacy plus explained AIOps, shown live on 4 real laptops, with judges pressing the buttons themselves.

| Idea | What the judge sees | How it works | Owner |
| --- | --- | --- | --- |
| Leak impossible by design | Free text never appears at head office | Schema only allows numbers, fixed labels and pseudonyms | G |
| Canary tripwire | "Canaries planted 1,240 · leaks detected 0" badge | Guard plants fake keys (`AKIACANARY…`) in its own raw stream every 30 s; head office scans every payload for them | G + H |
| Try-to-leak challenge (2) | Judge types any password into a box; head office shows only `pattern #12 count 1` | Chaos console posts the text to the shop API, which logs it; the guard pipeline does the rest | F + G |
| Signed receipts + hash chain | Egress panel shows ✅ per payload, or ❌ on any mismatch | Head office returns payload ID + SHA-256; guard compares | G + H |
| Two AI assistants | Shop AI quotes real log lines; head-office AI says "I don't have that, raw data never leaves Shop A" | Shop AI reads local SQLite; head-office AI only gets evidence JSON | G + A |
| Kill-chain story (5) | 4 alerts merge into one "Possible compromise: cryptomining" incident | Rule: login failures → success → CPU anomaly → outbound spike within 10 min | A |
| Signals must agree | CPU spike alone = "usage spike, info"; with latency + errors = incident | Multi-signal rule, inspired by Netdata's consensus approach | A |
| Counterfactual | "If latency had stayed normal, this would be Fair, not Poor" | Re-run the health rule without each signal | A |
| Phone approval (3) | Judge taps Approve on a phone page; fix runs, rollback timer starts, audit row appears | Guard pulls the signed intent and checks local policy before acting | H + G + F |
| Noisy vs clean phones (4) | Phone 1 buzzes for every raw alert; phone 2 gets one incident | Two phone pages fed by the same WebSocket | F |
| Judges' phones join (1) | Scan QR → phone appears as a collector; close tab → offline within 60 s | Browser page sends heartbeat + latency every 2 s | F + H |
| Power cut (7) | Pull Shop A's charger: "Site on backup power, \~45 min left" | psutil battery status and time left | G |
| Honeypot (9) | Login with `admin_backup` = instant critical alert, zero false alarms | Trap username list in the guard | G |
| Thumbs feedback (11) | 👎 on an alert stops repeats of that pattern | Raises that signal's threshold for 30 min, logged | A + F |
| Damage map (14) | Database slows → website, login and checkout light up | Small topology map per tenant | A + F |
| No failover on purpose | Kill India region: guards buffer, don't send to Europe | Residency beats availability; the dashboard explains why | H |
| Real-world precedent | "CrowdSec and Netdata ship metadata-only designs in production" | Slide + Q&A answer | F |
| Reveal with permission | Engineer asks "who is src-9c2e?"; the request pops up on the shop screen; after approval the real IP shows there, never at head office | Reveal request queue on the guard; the local reveal table answers; audit row on both sides | G + H + F |
| Receipt-log checkpoints | Matching fingerprints on both screens every minute: proof head office never got more than was sent | Running SHA-256 over payload hashes in seq order, published every 60 s; same idea as certificate transparency logs | G + H |
| What changed just before | Incident card: "started 40 s after shop-api restarted" | Change events as metadata; any change within 5 min before the first signal is linked and raises confidence | G + A |
| No flapping | Calm status colours plus a "flaps prevented: 12" counter | Different enter and exit thresholds (6 s bad to enter, 20 s good to exit) | A + F |
| Learns repeating jobs | Backup job spikes CPU every 60 s: alerts 3 times, then "scheduled job, suppressed" | Track gaps between spikes per source and metric; 3 gaps within ±10 % = learned interval; a spike off-schedule still alerts | A |

## Architecture

Two tiers on one hotspot. Each guard only ever makes outbound HTTPS calls to its assigned regional endpoint, so nothing can connect into a customer environment. Raw data stops at the trust boundary; signed, allow-listed payloads cross it.

&#91;embedded content: Airlock architecture · 2 tiers, 4 laptops + phones, 1 trust boundary\]

Shop A and the organizer guard send to the India endpoint, Shop B to Europe, and phones send heartbeats straight to hq-api; nothing crosses the dashed line except signed metadata, receipts and action intents.

### Machines and ports

| Machine | Tier and role | Runs (port) |
| --- | --- | --- |
| Lenovo LOQ, RTX 4060, Windows | Tier 2: head office, on the projector | `hq-api` + WebSocket (8000), `ingest-in` India (8001), `ingest-eu` Europe (8002), AIOps worker, PostgreSQL native (5432: `airlock_core`, `airlock_in`, `airlock_eu`), Ollama (11434), head-office web + phone pages |
| Ryzen AI 7 350, Windows | Tier 1: Shop A "Acme", India | `shop-api` (7000), Toxiproxy (8474), guard + local UI (9000), chaos agent (9100), Lemonade (13305) |
| Linux laptop | Tier 1: Shop B "Globex", Europe | `shop-api` (7000), real `sshd` + `auth.log`, guard (9000), chaos agent (9100), `tc netem` |
| Windows laptop 4 | Tier 1: organizer-stream guard (tenant "Contoso", India) + chaos console | guard with organizer adapter (9000), chaos console web (5173) |
| Judges' phones | Tier 1 lite collectors (tenant "Guests") | Browser page only |

No Docker is needed on Windows: PostgreSQL, Toxiproxy, Ollama and Lemonade all have native Windows installers.

### Data flow

1. **Collect:** metrics every 2 s, probes, log lines, organizer events. Each is normalised to `{event_time UTC, source_tz, source, kind, fields}`.
2. **Keep raw locally:** SQLite `raw.db`, 24 h retention, visible only on the shop screen.
3. **Scrub:** detect-secrets + regex mask keys, passwords, tokens and card numbers, and count what was found.
4. **Mine patterns:** Drain3 turns each line into a pattern ID and count.
5. **Aggregate:** 2 s windows with avg, max and counts.
6. **Detect locally:** login-failure bursts, honeypot hits, 3 AM shop-time logins, power on battery.
7. **Pseudonymise:** `host-` / `src-` / `user-` + first 4 bytes of HMAC-SHA256(tenant key, value). Mapping stays local.
8. **Policy gate:** build the payload against the schema (unknown field = blocked) and scan it for canaries before sending.
9. **Ledger + outbox:** store the exact JSON, its SHA-256, the previous hash and seq; queue it in SQLite.
10. **Send:** HTTPS POST with HMAC signature, timestamp and payload ID. Backoff 1, 2, 4, 8, 10 s while the endpoint is unreachable.
11. **Ingest checks:** known guard → valid signature → timestamp within 5 min → schema → pinned policy hash → canary and secret tripwire → insert once by `payload_id` → seq gap and chain check.
12. **Receipt:** `{payload_id, sha256, received_at, status: stored | duplicate}`. The guard marks the ledger row ✅.
13. **AIOps:** baselines, health, anomalies, incidents, recommendations, AI narrative.
14. **Push:** WebSocket to dashboards and phone pages.

### Payload schema v1 (the allow-list)

```json
{
  "schema": "airlock.v1",
  "payload_id": "0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
  "tenant_id": "acme",
  "guard_id": "guard-acme-01",
  "seq": 1042,
  "prev_hash": "sha256:9c1e…",
  "policy_version": "sha256:ab12…",
  "sent_at": "2026-11-21T04:12:08Z",
  "window": {"start": "2026-11-21T04:12:04Z", "end": "2026-11-21T04:12:06Z", "source_tz": "Asia/Kolkata"},
  "metrics": [
    {"name": "cpu_pct", "source": "host-7f3a", "avg": 34.2, "max": 51.0}
  ],
  "events": [
    {"category": "auth_failure_burst", "severity": "high", "source": "host-7f3a", "actor": "src-9c2e", "count": 50, "window_s": 60}
  ],
  "log_patterns": [
    {"pattern_id": "tpl-3fa1", "level": "ERROR", "count": 40, "is_new": true}
  ],
  "health": {"guard_version": "0.3.1", "guard_cpu_pct": 1.2, "guard_mem_mb": 80, "buffer_depth": 0, "config_ok": true, "canaries_planted": 12, "secrets_redacted": 3}
}
```

| Field type | Allowed values |
| --- | --- |
| Metric names | `cpu_pct`, `mem_pct`, `disk_pct`, `net_in_kbps`, `net_out_kbps`, `latency_ms`, `packet_loss_pct`, `service_up`, `battery_pct`, `on_battery`, `battery_min_left` |
| Event categories | `auth_failure_burst`, `login_after_failures`, `honeypot_hit`, `odd_hour_login`, `service_down`, `new_log_pattern`, `log_pattern_spike`, `power_on_battery`, `secret_redacted`, app\_restarted, version\_changed, config\_changed, new\_process |
| Severity | `info`, `low`, `medium`, `high`, `critical` |
| Identifiers | Pseudonyms matching `^(host\|src\|user\|proc)-[0-9a-f]{8}$` only |
| Never sent | Raw log lines, usernames, passwords, keys, IPs, hostnames, request bodies, command lines, file paths, pattern text |

### Security controls

- **Guard authentication:** per-guard secret registered in `airlock_core`. HMAC-SHA256 over the body + timestamp; payload ID as nonce, so replays are rejected.
- **Transport:** HTTPS with an mkcert certificate on the head office. mTLS is a stretch goal.
- **Outbound only:** the guard pulls action intents; head office never connects in.
- **Defence in depth:** schema enforced on both sides, canary scan on both sides, policy-hash pinning per tenant.
- **Local retention:** raw data deleted after 24 h (configurable), with a countdown on the shop screen.
- **Audit:** egress ledger (guard), receipts table (head office), action audit log (both).

* **Reveal with permission:** head office can only *request* the value behind a pseudonym (`POST /reveal-requests`). The guard pulls the request, the shop admin approves or rejects it on the shop screen, and the answer is shown only there. Both sides log requester, reason, decision and UTC time.
* **Receipt-log checkpoints:** every 60 s the guard and head office each compute a running SHA-256 over all payload hashes in seq order and publish `{guard_id, up_to_seq, root}`. Equal roots show ✅ on both screens; a mismatch names the first differing seq.

### Global-ready design

- **Regional ingest:** each tenant has one assigned region in `airlock_core.tenants`, and its guard only knows that endpoint.
- **Residency:** metrics and events live only in that region's database. No cross-region replication; no failover.
- **Time:** UTC everywhere + `source_tz` per window. Dashboards render in the viewer's zone. Clock skew over 30 s raises a warning.
- **Out-of-order:** stored and charted by `window.start`, never arrival time. Late windows trigger a recompute of the affected baseline points.
- **Idempotent:** a unique `payload_id` makes duplicates no-ops counted on the reconciliation panel. A seq gap means "still buffered" until filled.

* **Time-zone switch:** every timestamp on the dashboard can render in UTC, the viewer's zone or the shop's zone. Shop A's laptop runs on Asia/Kolkata and Shop B's on Europe/Berlin, so judges see both line up on one UTC timeline.

## AIOps design and screens

Math decides what is wrong; the AI only explains it. Every number on an incident card traces back to a stored metric or event.

### Health states (thresholds configurable per tenant)

| State | Any of these | Defaults |
| --- | --- | --- |
| Excellent | Heartbeat fresh, every metric inside its normal band | \|z\| < 2, heartbeat < 10 s |
| Good | One minor deviation, no service impact | One metric 2 ≤ \|z\| < 3, or above warning for < 30 s |
| Fair | Elevated resources, latency, loss or recurring warnings, or stale data | \|z\| ≥ 3 for 3 windows; latency > 200 ms; loss > 2 %; CPU > 85 %; memory or disk > 90 %; medium login burst; no data 10–30 s |
| Poor | Collector offline, service down, critical security event, severe degradation | No heartbeat ≥ 30 s; `service_down`; honeypot or kill chain; latency > 1,000 ms or loss > 10 % |

Stale data never shows the last good value: the state drops with the reason "no data for 14 s". Every transition is stored with UTC time, old state, new state and reasons, and shown in the history panel.

### Anomaly detection

- **Baseline:** per tenant, source and metric, an exponentially weighted mean and spread (alpha 0.1, 30-point warm-up = 60 s).
- **Flag:** |z| ≥ 3 for 3 windows in a row (6 s), so one blip is ignored.
- **Second opinion:** River HalfSpaceTrees on `[cpu, mem, latency, loss, net_out]`. Agreement raises confidence.
- **Usage spike vs incident:** CPU high alone, with latency and errors normal, is `info: usage spike`. CPU plus latency plus errors opens an incident.
- **Feedback:** 👎 raises that signal's flag level from 3 to 3.5 for 30 min, logged with who and when.

* **No flapping (hysteresis):** a source enters a worse state only after 6 s of bad data and returns to a better state only after 20 s of good data. Every blocked flip-flop increments a "flaps prevented" counter.
* **Learned scheduled jobs:** for each source and metric, keep the gaps between spikes. Three gaps within ±10 % of each other = a learned interval. Spikes on that schedule become `info: scheduled job (every ~60 s)` and are suppressed with the reason shown; a spike off-schedule, or one larger than usual, still alerts.

### Correlation and noise reduction

- Alerts with the same tenant and related component (from the topology map) within 120 s join one incident. Repeats of the same source and signal become a counter, not a new alert.
- **Kill-chain rule:** `auth_failure_burst` → `login_after_failures` or `odd_hour_login` → CPU anomaly → `net_out_kbps` anomaly within 10 min = one critical incident, "Possible compromise: cryptomining".
- Header counter: "Raw alerts 47 → incidents 3 (94 % noise cut)".

* **What changed just before:** change events (`app_restarted`, `version_changed`, `config_changed`, `new_process`) within 5 min before an incident's first signal are attached to it, shown as "started 40 s after shop-api restarted", and add 0.1 to confidence.

### Incident object (what every explanation is built from)

```json
{
  "incident_id": "inc-0042", "tenant_id": "acme", "title": "Possible compromise: cryptomining",
  "severity": "critical", "confidence": 0.85, "started_at": "2026-11-21T04:10:02Z",
  "affected": ["host-7f3a", "shop-api", "checkout"],
  "signals": [
    {"evidence_id": "ev-1", "name": "auth_failure_burst", "value": 50, "baseline": 2, "contribution_pct": 35},
    {"evidence_id": "ev-2", "name": "cpu_pct", "value": 96, "baseline": 21, "z": 7.4, "contribution_pct": 40},
    {"evidence_id": "ev-3", "name": "net_out_kbps", "value": 900, "baseline": 40, "z": 5.1, "contribution_pct": 25}
  ],
  "reasoning_path": ["login burst at 04:10", "login success at 04:11", "CPU anomaly at 04:12", "outbound spike at 04:12", "kill-chain rule matched"],
  "counterfactual": "Without the outbound spike this would be a High security incident, not Critical",
  "recommendation": {"action": "kill_process", "target": "proc-1a2b3c4d", "why": "Process started after the suspicious login and uses 90 % CPU", "risk": "low", "reversible": true, "rollback": "Restart shop-api if it was affected"},
  "narrative": "(written by the head-office AI from the fields above)"
}
```

**Confidence** = 0.4 + 0.15 × agreeing signals + 0.1 if a named rule matched, capped at 0.95. The formula is shown on hover. **Contribution** = each signal's |z| (or count ratio for events) as a share of the total.

### Safe remediation

| Incident type | Action | Executed by | Rollback |
| --- | --- | --- | --- |
| CPU hog / miner | Kill process | Guard (resolves the pseudonym to the real PID locally) | Restart shop-api if needed |
| Login brute force | Block source for 15 min | Guard (`iptables` on Linux; logged simulation on Windows) | Auto-unblock after 15 min or Undo button |
| Service down | Restart shop-api | Guard | Escalate if still down after 10 s |
| Latency / loss | Recommend investigation only | — | — |

Flow: head office proposes → policy check (action allowed for tenant, risk ≤ medium, max 3 per 10 min) → judge approves on the phone page with their name → signed intent → guard pulls it and re-checks local policy → executes → reports the result → if health hasn't improved in 120 s, auto-rollback and escalate. Every step is written to the audit log on both sides.

**Dry run first:** the phone page shows a Dry run button before Approve is enabled. The guard answers with exactly what would happen ("would kill proc-1a2b3c4d, using 92 % CPU, started 04:11:40 UTC; rollback: restart shop-api") without changing anything, and the dry run is logged too.

### AI assistants

- **Head office (LOQ, Ollama):** `qwen3.5:4b`, fallback `qwen2.5` (already installed). Input: the incident JSON + a 10-minute metric summary for the logged-in tenant only. Rules: answer only from evidence, cite evidence IDs, say "I don't have that, raw data stays in the customer's environment" for anything else. Narratives are pre-written when an incident opens.
- **Shop (Ryzen, Lemonade on the NPU, CPU fallback):** tools `search_raw_logs(query, minutes)` and `recent_auth_failures(minutes)` over local SQLite. Reachable only on that laptop.
- Both use the OpenAI Python client; only the base URL changes.

### Screens

| Screen | Where | Key panels |
| --- | --- | --- |
| Head office | LOQ, projector | Tenant switcher + login; fleet grid with 4 states and reasons; live charts with normal band; security box; incidents with contribution bars, confidence, reasoning, counterfactual, action; history; reconciliation (sent / received / duplicates / gaps); latency meter; leak badge; damage map; AI chat; time-zone switch; flaps-prevented counter; receipt-log ✅; reveal request button |
| Inside the shop | Ryzen and Linux, own browser | Raw logs with secrets visible; egress proof panel (exact JSON, hash, ✅/❌ receipt); buffer depth; retention countdown; reveal-pseudonym lookup; reveal requests to approve or reject; receipt-log ✅; shop AI chat |
| Chaos console | Laptop 4 | Buttons per scenario and target shop; try-to-leak box; tamper menu; scenario log with UTC timestamps |
| Phone pages | Judges' phones | `/join` collector (QR); `/approve` fix approvals; `/raw` noisy alerts; `/smart` incidents only |

The frontend follows the team's design.md once it's shared.

## Open source: install vs reference

We install small libraries for the plumbing and build the product ourselves; no GitHub project is forked. Rule of thumb: if it's plumbing, install it; if judges score it, build it.

### Install and use

| Library / tool | Used for | Owner |
| --- | --- | --- |
| Python 3.11+, FastAPI, uvicorn, httpx, pydantic v2 | All backends (guard, ingest, hq-api, chaos agent, shop-api) | All |
| psutil | Host metrics + battery | G |
| [Drain3](https://github.com/logpai/Drain3) | Log line → pattern ID | G |
| [detect-secrets](https://github.com/Yelp/detect-secrets) | Secret scrubbing + canary format | G |
| SQLite (stdlib) | Guard raw store, ledger, outbox | G |
| PostgreSQL 16 (Windows installer) + psycopg 3 | Head office storage + row-level security | H |
| mkcert | HTTPS certificate for head office | H |
| River | HalfSpaceTrees second-opinion anomaly score | A |
| [Ollama](https://github.com/ollama/ollama) + Qwen | Head-office AI | A |
| [Lemonade](https://lemonade-server.ai/) | Shop AI on the Ryzen NPU, OpenAI-compatible | G |
| openai (Python client) | One client for Ollama and Lemonade | A + G |
| Vue 3 + Vite + Apache ECharts | All screens | F |
| Toxiproxy (Windows binary) + `tc netem` (Linux) | Latency, loss, link cut | H |
| qrcode (Python) | QR for the phone `/join` page | F |
| [Microsoft Presidio](https://microsoft.github.io/presidio) | Optional extra check for the try-to-leak box | G (P2) |
| NATS JetStream | Optional queue; only mentioned as the scale-up path if no time | H (P2) |

### Reference only (clone into `reference/`, read patterns, write our own code)

| Repo | What to take | Read by |
| --- | --- | --- |
| [yuvrajpawar09/AI-Ops](https://github.com/yuvrajpawar09/AI-Ops) | Incident report fields, LLM prompt, "fix only if confidence ≥ 0.85 and known pattern", verify + rollback | A, G |
| [Ayush-Singh986/AIops-Agent](https://github.com/Ayush-Singh986/AIops-Agent) | Statistics rank causes first, then LLM confirms | A |
| [SupOps/SupOps](https://github.com/SupOps/SupOps) | Human approval before risky commands | H, F |
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | Vue dashboard look, live-update pattern, status bars | F |
| [CrowdSec docs](https://doc.crowdsec.net/docs/concepts) | Exactly which security signal fields leave the machine | G |
| [Netdata: role of the cloud](https://learn.netdata.cloud/docs/architecture/the-role-of-netdata-cloud) | Metadata-only cloud precedent for Q&A | F |

Not used: Keep (its AI correlation isn't in the open-source edition, and the UI is React), Coroot (Go; AI root cause analysis is Enterprise-only), Beszel (Go), Glances (psutil directly is simpler). Credit every reference repo in the README under "Inspired by".

## Team split and 24-hour plan

Four owners, one folder each, one shared `contracts/` folder frozen by H2. Everyone builds against the contract plus the simulator, so nobody waits on anybody.

### Roles (map names here)

| Role | Name | Owns (folder) | Machines | Done means |
| --- | --- | --- | --- | --- |
| **G · Guard engineer** | \_\_\_\_\_ | `guard/`, `shop-api/` | Ryzen (Shop A), Linux (Shop B), laptop 4 guard | Both shops + organizer guard send signed, allow-listed payloads; survive outages with zero loss; local UI API; shop AI; executes approved actions |
| **H · Head-office backend** | \_\_\_\_\_ | `hq/ingest`, `hq/api`, `chaos/` | LOQ (PostgreSQL, ingest, API), chaos agents | Two regions, all ingest checks, receipts, row-level security, WebSocket, reconciliation, action intents + audit, chaos and tamper scenarios |
| **A · AIOps and AI** | \_\_\_\_\_ | `hq/aiops`, `hq/ai`, `tools/simulate.py` | LOQ (worker, Ollama) | Simulator by H3; health states; anomalies; incidents with contributions, confidence, counterfactual, recommendation; head-office AI with evidence tags |
| **F · Frontend and demo** | \_\_\_\_\_ | `web/`, `docs/`, slides | Laptop 4 (chaos console), projector | Head-office, shop, chaos and phone screens from design.md; latency meter; slides, demo script and Q&A sheet |

Role **A** fits whoever is strongest with LLMs and stats. **G** should be comfortable on Linux.

### Who does what, by phase

| Phase | G · Guard | H · Head office | A · AIOps and AI | F · Frontend and demo |
| --- | --- | --- | --- | --- |
| **H0–H2** Setup + contracts | Python on shops; test Lemonade on the NPU; `sshd` on Linux | PostgreSQL + mkcert on LOQ; hotspot; repo | Pull `qwen3.5:4b`; draft incident JSON | Vue scaffold; data-flow sketch for judging round 1 |
| (all four) | Write and freeze `contracts/`: payload schema, enums, API + WebSocket messages, action intent, ports, tenant IDs |  |  |  |
| **H2–H6** Thin slice | psutil → payload → sign → send | `ingest-in`: verify, store, receipt; WebSocket push | Simulator posting real payloads; baseline + health v1 | One live CPU tile per tenant; architecture slide for round 2 |
| **H6–H12** Core | Scrub, Drain3, pseudonyms, ledger + outbox, local detectors, shop-api, guard UI API | Schema + policy pin + tripwire, row-level security, logins, `ingest-eu`, reconciliation, chaos agent v1 | Anomaly flags, usage-spike rule, incident grouping, contributions, confidence | Head-office screen, shop screen, egress panel, chaos console |
| **H12–H15** Integrate on real laptops | Run guards on all 3 machines over hotspot | Fix ingest issues, measure delivery | Tune thresholds on real data | Latency meter; rehearse round 3 demo |
| **H15–H20** Intelligence + extras (nap 90 min each, staggered) | Action executor, honeypot, power cut, shop AI, organizer adapter | Action intents + approvals + audit, region pause, tamper scenarios, phone `/join` backend | Kill chain, counterfactual, runbook, head-office AI + narratives, feedback, damage map | Phone pages (`/join`, `/approve`, `/raw`, `/smart`), AI chat panel, damage map |
| **H20–H22** Freeze + rehearse | Bug fixes only | Bug fixes only | Bug fixes only | Run all live scenarios twice; slides; Q&A sheet |
| **H22–H24** Final | On Shop A + B during demo | On chaos console with judge | Answers AI and AIOps questions | Presents |

**Innovation extras (added to the phases above):**

- **G:** change events and receipt-log checkpoints in H6–H12; reveal-request pull + local approve API in H15–H20.
- **H:** checkpoint compare + reveal-request API in H6–H12; dry-run endpoint in H15–H20; chaos buttons "Backup job" and "Restart app".
- **A:** hysteresis together with health v1 (H2–H6); scheduled-job learning and change linking in H15–H20.
- **F:** time-zone switch, flaps counter and receipt-log badge in H6–H12; reveal UI on both screens and dry-run panel in H15–H20.

&#91;embedded content: 24-hour roadmap · 7 phases, 4 judging rounds\]

Each round has a ready artefact: the data-flow sketch at round 1, the architecture diagram and schema at round 2, the live split screen and reconciliation at round 3, and the full scenario run at the final.

**Integration rule:** merge to `main` every 2 hours (H4, H6, H8, …) and run the smoke test: simulator → ingest → dashboard. Whoever breaks `main` fixes it first.

## Working in Antigravity

One monorepo, a shared contract, and a rules file every agent reads first. Each person gives their agent a small, well-defined module, never "build the whole thing".

### Repo layout

```text
airlock/
  AGENTS.md            rules every agent follows (below)
  contracts/           payload schema, enums, API + WebSocket messages, action intent (frozen at H2)
  guard/               G: collector pipeline, ledger, outbox, local API, executor, shop AI
  shop-api/            G: tiny demo shop with login, products, checkout
  hq/ingest/           H: regional ingest services
  hq/api/              H: dashboards API, WebSocket, actions, auth
  hq/aiops/            A: baselines, health, anomalies, incidents, recommendations
  hq/ai/               A: head-office assistant
  chaos/               H: chaos agent + tamper scripts
  tools/simulate.py    A: fake guards posting real signed payloads
  web/                 F: hq, shop, chaos and phone screens (Vue 3)
  docs/                README, architecture, demo script, Q&A
  reference/           cloned repos to read (git-ignored)
```

### AGENTS.md (paste as-is)

```markdown
# Airlock rules for coding agents
- Read contracts/ before writing code. Never change contracts/ without telling the team; bump the version if you do.
- Python 3.11, FastAPI, pydantic v2 with extra="forbid" on every payload model. Vue 3 + ECharts for UI.
- All times are UTC ISO-8601 with Z. Every window also carries source_tz.
- Never send raw text, usernames, IPs, hostnames, paths or secrets from guard/ to hq/. Only fields in contracts/payload.schema.json.
- Every function that touches the network must time out, retry with backoff, and log what happened.
- Config comes from a .env per machine (ports, tenant, region URL, keys). No hard-coded IPs.
- Write a small test for every rule that protects privacy or prevents duplicates.
- Keep modules small; one file per concern. Explain non-obvious logic in a one-line comment.
- reference/ is read-only inspiration. Do not copy code from it; write our own.
```

### Starter prompts (each person pastes theirs)

**G · Guard**

```text
Read AGENTS.md and contracts/. Build guard/ as a FastAPI app plus background loops:
1) collectors: psutil metrics every 2 s, TCP latency/loss probes, HTTP health of shop-api, tail shop-api log and /var/log/auth.log on Linux;
2) raw.db (SQLite, 24 h retention); 3) scrubber using detect-secrets + regex, plus canary planting every 30 s;
4) Drain3 pattern mining; 5) 2 s window aggregation; 6) local detectors (login burst, honeypot user, 3 AM local login, on battery);
7) HMAC pseudonyms with a local reveal table; 8) payload builder validated by the contract model + canary scan;
9) hash-chained ledger + SQLite outbox + sender with HMAC signature, backoff and receipt check;
10) local API for the shop screen: raw logs, ledger, buffer depth, reveal. Start with steps 1, 8 and 9 end to end.
```

**H · Head office**

```text
Read AGENTS.md and contracts/. Build hq/ingest (one app, run twice with REGION=in|eu) and hq/api.
Ingest: check guard key, HMAC, timestamp ±5 min, schema, pinned policy hash, canary/secret tripwire; insert by payload_id
with ON CONFLICT DO NOTHING; track seq gaps and prev_hash chain; return a signed receipt. Region pause switch for the demo.
PostgreSQL: airlock_core (tenants, guards, users, audit), airlock_in and airlock_eu (metrics, events, patterns, receipts,
health, incidents), with row-level security on tenant_id. API: login (engineer vs customer), queries, reconciliation,
WebSocket push, action intents with approval + audit, phone /join heartbeats. Start with ingest + receipt + WebSocket.
```

**A · AIOps and AI**

```text
Read AGENTS.md and contracts/. First write tools/simulate.py: N fake guards posting valid signed payloads with
scenario switches (cpu spike, latency, login burst, outage, duplicates, out-of-order, kill chain).
Then hq/aiops as a worker every 2 s: EWMA baselines, z-score flags (3 windows), River HalfSpaceTrees score,
health states with reasons and stale handling, incident grouping (tenant + topology + 120 s), kill-chain rule,
contribution %, confidence formula, counterfactual, runbook recommendation, feedback suppression.
Then hq/ai: Ollama via the OpenAI client, evidence-only answers that cite evidence_id, narrative on incident open.
```

**F · Frontend**

```text
Read AGENTS.md, contracts/ and design.md. Build web/ in Vue 3 + Vite + ECharts with 4 entry points:
hq (projector dashboard), shop (served by the guard), chaos (laptop 4), phone (/join, /approve, /raw, /smart).
Use mock JSON from contracts/examples until the APIs are live, then switch to the WebSocket.
Must-have widgets: fleet grid with 4 states + reasons, live charts with normal band, incident card with contribution
bars + confidence + reasoning + counterfactual + action, reconciliation panel, latency meter, egress proof panel, leak badge.
```

## Demo script, judge Q&A, limitations

The judge drives the chaos console; we narrate what each screen proves. Every scenario below is rehearsed twice in H20–H22.

### Live scenarios (from the guide, plus ours)

| Scenario | Trigger | What the judge sees | Proof |
| --- | --- | --- | --- |
| Raw log contains a secret | Try-to-leak box | Shop screen shows the line with the key; head office shows `secret_redacted` count + pattern ID only | Egress panel JSON for that payload; leak badge still 0 |
| Collector loses head office | "Pause India region" button, or Wi-Fi off on Shop A | Guard goes stale (10 s) then Poor (30 s); buffer depth climbs; on resume it drains | Reconciliation: sent = received, duplicates 0, gaps 0 |
| Repeated failed logins | Brute-force button (real `sshd` on Shop B) | Security box: 50 failures, risk High, attacker `src-9c2e` | Head office has no usernames or IPs; shop AI lists the real lines |
| Network latency rises | Latency button (Toxiproxy / `tc netem`) | Affected source, severity, trend, damage map lights checkout | Alert stamp ≤ 15 s after injection |
| CPU or memory leaves baseline | CPU spike button | Usage spike (alone) vs incident (with latency); contribution bars | Counterfactual line |
| Several alerts, one incident | Kill-chain button | 4 alerts → 1 critical incident with reasoning path | Noise counter |
| Duplicate or out-of-order delivery | Replay + shuffle button | Charts unchanged and in event-time order | Duplicate counter rises, totals don't |
| Remediation proposed | From the kill-chain incident | Phone `/approve` → Approve → process killed → rollback timer → audit row | Audit log both sides |
| Tamper | Edit payload / rogue guard / policy edit / ledger delete / clock skew | Rejected, unauthenticated, quarantined, chain break, skew warning | Each shows its own alert |
| Power cut | Pull Shop A's charger | "On backup power, \~N min left" | Real battery data |
| Phones join | QR on screen | Fleet grows; closed tab goes offline within 60 s | Offline timestamp |
| Normal recurring spike | Backup job button (CPU spike every 60 s) | 3 alerts, then "scheduled job (every \~60 s), suppressed"; an off-schedule spike still alerts | Suppression reason on the card |
| Change caused it | Restart app button, then latency button | Incident says "started 40 s after shop-api restarted" | Change event in the egress panel |
| Who is behind a pseudonym? | Reveal button on an incident at head office | Request appears on the shop screen; after approval the real IP shows only there | Audit rows on both sides; head office still shows the pseudonym |
| Time zones | Time-zone switch on the dashboard | Events from India and Europe line up on one UTC timeline; labels change, order doesn't | source\_tz shown per event |

### 3-minute story for the final round

1. **Problem (20 s):** shipping raw logs to a vendor is a breach waiting to happen.
2. **Proof of privacy (50 s):** split screen, try-to-leak, egress panel, canary badge.
3. **Reliability (40 s):** pause the region, buffer, resume, reconciliation with zero loss and zero duplicates.
4. **Intelligence (50 s):** kill chain → one incident → why → judge approves on the phone → rollback-safe fix.
5. **AI (20 s):** ask head-office AI for the password; it refuses with the reason; shop AI shows the line locally.

### Judge questions, short answers

| Question | Answer |
| --- | --- |
| What leaves the environment? | Only the fields in the schema table: numbers, fixed labels, pseudonyms, health. Open the egress panel to show the last payload. |
| How does the guard decide what's allowed? | A versioned schema (default deny) whose hash is pinned per tenant at head office; anything else is blocked on both sides. |
| How do you stop accidental secret leaks? | Free text can't be sent at all; on top, secret scrubbing, canary tripwires and a pre-send scan. |
| Authentication and encryption? | HTTPS, per-guard secret, HMAC signature + timestamp on every payload, payload ID as nonce, outbound-only guard. mTLS is next. |
| Real anomaly vs normal spike? | Learned baseline per metric, 3 windows in a row, and signals must agree before it becomes an incident. Spikes that repeat on a steady schedule are learned as scheduled jobs and suppressed, with the reason shown. |
| How do you correlate? | Same tenant + related component within 120 s, plus named rules like the kill chain. |
| Why this action? | Runbook mapping from incident type, with risk, rollback and the evidence shown on the card. |
| Safeguards before automation? | Policy check on both sides, human approval, rate limit, audit log, auto-rollback if health doesn't improve. |
| Head office unreachable? | Guard keeps collecting, buffers in SQLite, retries with backoff, drains oldest-first; nothing goes to another region. |
| No loss or duplicates? | Unique payload ID, seq numbers with gap tracking, receipts compared on both sides. |
| Scale to many collectors and tenants? | Stateless ingest per region behind a load balancer, a queue (NATS JetStream) before the workers, and tenant-partitioned PostgreSQL or a time-series store. |
| Regions, residency, time, ordering? | Assigned regional endpoint, per-region database with no replication, UTC + source timezone, event-time ordering. |

### Honest limitations

- Keys are files on disk; production needs a vault and key rotation.
- mTLS, SNMP and flow (NetFlow/sFlow) collection are designed but not built.
- Baselines need about 60 s to warm up and don't learn daily or weekly patterns yet.
- Small local models can phrase things imperfectly; detection never depends on them.
- Windows IP blocking is simulated; Linux uses real `iptables`.

### Sources

- Hackathon guide: Smart Observability Hackathon Evaluation Guide v8 (CICADA 2026, uploaded PDF)
- [CrowdSec concepts](https://doc.crowdsec.net/docs/concepts) · [Netdata Cloud role](https://learn.netdata.cloud/docs/architecture/the-role-of-netdata-cloud) · [OpenTelemetry redaction processor guide](https://www.dash0.com/guides/opentelemetry-redaction-processor) · [NATS headers](https://docs.nats.io/reference/jetstream/api/headers) · [Lemonade OpenAI API](https://lemonade-server.ai/docs/api/openai/)
