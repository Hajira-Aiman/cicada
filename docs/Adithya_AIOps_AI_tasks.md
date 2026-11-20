# Airlock: Adithya's tasks (A · AIOps and AI)

**Source:** *CICADA 2026 – Smart Observability Hackathon Plan* (the PRD). Every task points back to it:
- `PRD #n` = row *n* of the table "PRD: requirements to features"
- `§Section › Part` = a section of the plan

**Your role in one line:** you build the **brain**. It learns what "normal" looks like, decides health states, spots anomalies, groups alerts into explained incidents, suggests safe fixes, and runs the head-office AI. You also build the **simulator** everyone tests with. (§Team split › Roles)

**You own:** `hq/aiops/`, `hq/ai/`, `tools/simulate.py` (§Working in Antigravity › Repo layout)

**Your laptop on demo day:** LOQ = **head office, on the projector**. It runs:
- your AIOps worker + Ollama (:11434)
- Sahiti's `hq-api`, `ingest-in`, `ingest-eu` and PostgreSQL (§Architecture › Machines and ports)

**Golden rule (§AIOps design):** math decides what is wrong; the AI only explains it. Every number on an incident card must trace back to a stored metric or event.

---

## Handoffs: who you depend on, who depends on you

| You need… | From | By |
|---|---|---|
| Payload schema v1 in `contracts/` | Hajira | H2 |
| Ingest + tables for metrics, events, patterns, health, incidents | Sahiti | H6 |
| PostgreSQL on your LOQ (you give access, she installs) | Sahiti | H2 |
| Change events in payloads | Hajira | H12 |

| Others need from you… | Who | By |
|---|---|---|
| Incident object shape in `contracts/` | Everyone | H2 |
| **Simulator posting real signed payloads** | Everyone | **H3** |
| Health states with reasons | Anisa, Sahiti | H6 |
| Incidents with contributions, confidence, recommendation | Anisa, Sahiti | H12 |
| AI chat endpoint + incident narratives | Anisa | H20 |

---

## Shared team tasks (§Team split, §Demo script)

- [ ] **H0–H2, contract:** with the team, write and freeze `contracts/`. **Your part:** the incident object (§AIOps design › Incident object) + health-state messages.
- [ ] **Every 2 hours:** merge to `main` and run the smoke test (simulator → ingest → dashboard).
- [ ] **H12–H15, integration** on real laptops; tune thresholds on real data.
- [ ] **H15–H20:** take one 90-minute nap, staggered (you're first, after round 3).
- [ ] **H20–H22:** bug fixes only, and rehearse all live scenarios twice.
- [ ] **H22–H24:** answer the AI and AIOps questions during the final.

---

## Tasks by phase

### H0–H2 · Setup + contract

#### T0. LOQ setup · PRD #21, §AI assistants
- [x] `ollama pull qwen3.5:4b`. Keep `qwen2.5` as the fallback (already installed). (using qwen2.5:7b instead, decided)
- [ ] Give Sahiti access to install PostgreSQL on the LOQ.
- **Done when:** Ollama answers through the OpenAI Python client at `http://localhost:11434`.

#### T1. Incident object in `contracts/` · §AIOps design › Incident object
- [x] Fields: `incident_id`, `tenant_id`, `title`, `severity`, `confidence`, `started_at`, `affected[]`, `signals[]` (each with `evidence_id`, `name`, `value`, `baseline`, `z`, `contribution_pct`), `reasoning_path[]`, `counterfactual`, `recommendation{action, target, why, risk, reversible, rollback}`, `narrative`.
- [x] Health-state message: `source`, `state`, `reasons[]`, UTC time, old → new.
- **Done when:** frozen at H2 with an example in `contracts/examples/`.

### H2–H6 · Thin slice

#### T2. Simulator (needed by H3) · §Team split › Roles, §Working in Antigravity › starter prompt A
- [x] `tools/simulate.py`: N fake guards posting **valid, signed** airlock.v1 payloads to ingest.
- [x] Scenario switches: CPU spike, latency, login burst, outage, duplicates, out-of-order, kill chain.
- **Done when:** Sahiti and Anisa can run it and see data flow without a real guard.

```text
Prompt: Read AGENTS.md and contracts/. Write tools/simulate.py: N fake guards (tenants acme/globex/contoso) that
post valid, HMAC-signed airlock.v1 payloads every 2 s to the region endpoint from .env. Add CLI switches for
scenarios: cpu_spike, latency, login_burst, outage (stop sending), duplicates, out_of_order, kill_chain.
```

#### T3. Baselines + health v1 + no flapping · PRD #12, #13, #25, §Health states, §Anomaly detection
- [x] Baseline per tenant, source and metric: exponentially weighted mean and spread, alpha 0.1, 30-point warm-up (60 s).
- [x] Health states (thresholds configurable per tenant):

| State | Any of these |
|---|---|
| Excellent | Heartbeat < 10 s, every metric \|z\| < 2 |
| Good | One metric 2 ≤ \|z\| < 3, or above warning for < 30 s |
| Fair | \|z\| ≥ 3 for 3 windows; latency > 200 ms; loss > 2 %; CPU > 85 %; memory or disk > 90 %; medium login burst; no data 10–30 s |
| Poor | No heartbeat ≥ 30 s; `service_down`; honeypot or kill chain; latency > 1,000 ms or loss > 10 % |

- [x] Stale data never shows the last good value. The state drops with a reason, e.g. "no data for 14 s".
- [x] Every transition is stored with UTC time, old state, new state and reasons.
- [x] **No flapping (PRD #25):** a source enters a worse state only after 6 s of bad data and returns only after 20 s of good data. Count blocked flips ("flaps prevented").
- **Done when:** stopping the simulator turns a source Fair at 10 s and Poor at 30 s, and the history shows each change with reasons.

### H6–H12 · Core

#### T4. Anomaly flags + usage-spike rule · PRD #13, §Anomaly detection
- [x] Flag when \|z\| ≥ 3 for 3 windows in a row (6 s), so one blip is ignored.
- [x] Second opinion: River HalfSpaceTrees on `[cpu, mem, latency, loss, net_out]`. Agreement raises confidence.
- [x] CPU high alone, with latency and errors normal → `info: usage spike`. CPU + latency + errors → opens an incident.
- **Done when:** the CPU-spike button alone gives "usage spike", and CPU + latency gives an incident.

#### T5. Incident grouping + noise counter · PRD #14, §Correlation and noise reduction
- [ ] Same tenant + related component (topology map) within 120 s → one incident.
- [ ] Repeats of the same source and signal become a counter, not a new alert.
- [ ] Header counter: "Raw alerts N → incidents M (x % noise cut)".
- **Done when:** a burst of related alerts becomes one incident and the counter shows the cut.

#### T6. Contributions + confidence · PRD #14, §Incident object
- [ ] **Contribution** = each signal's \|z\| (or count ratio for events) as a share of the total.
- [ ] **Confidence** = 0.4 + 0.15 × agreeing signals + 0.1 if a named rule matched, capped at 0.95. Show the formula on hover.
- **Done when:** every incident card has contribution bars and a confidence value you can recompute by hand.

```text
Prompt (worker): Read AGENTS.md and contracts/. Build hq/aiops as a worker that runs every 2 s on airlock_in and
airlock_eu: EWMA baselines (alpha 0.1, 30-point warm-up), health states per the plan's table with reasons, stale
handling and hysteresis (6 s to enter worse, 20 s to exit), z-score flags (|z| >= 3 for 3 windows), River
HalfSpaceTrees second opinion, usage-spike rule, incident grouping (tenant + topology + 120 s), repeat counters,
contribution % and the confidence formula. Write incidents in the contract shape.
```

### H12–H15 · Integrate on real laptops

- [ ] Tune thresholds on real data from Shop A, Shop B and the organizer stream.
- [ ] With Anisa, show the latency meter (PRD #19): event time → render p50/p95, plus alert-delay and offline-delay stamps.
- **Done when:** an injected spike creates an alert within 15 s, and real (not simulated) data shows no false alarms.

### H15–H20 · Intelligence + extras

#### T7. Kill-chain rule · PRD #14, §Differentiators › Kill-chain story
- [ ] `auth_failure_burst` → `login_after_failures` or `odd_hour_login` → CPU anomaly → `net_out_kbps` anomaly, all within 10 min = one critical incident, "Possible compromise: cryptomining".
- **Done when:** the kill-chain button turns 4 alerts into 1 incident with the reasoning path.

#### T8. Counterfactual + runbook + learned extras · PRD #14, #26, #27, §Safe remediation
- [ ] **Counterfactual:** re-run the health rule without each signal, e.g. "If latency had stayed normal, this would be Fair, not Poor".
- [ ] **Runbook:**

| Incident type | Recommended action |
|---|---|
| CPU hog / miner | Kill process |
| Login brute force | Block source for 15 min |
| Service down | Restart shop-api |
| Latency / loss | Recommend investigation only |

  Each recommendation carries why, risk, reversible and rollback.
- [ ] **Learned scheduled jobs (PRD #26):** keep the gaps between spikes per source and metric. Three gaps within ±10 % = a learned interval. Spikes on that schedule → `info: scheduled job (every ~60 s)`, suppressed with the reason shown. Off-schedule or larger spikes still alert.
- [ ] **What changed just before (PRD #27):** change events within 5 min before an incident's first signal are attached ("started 40 s after shop-api restarted") and add 0.1 to confidence.
- **Done when:** the Backup job button alerts 3 times and then is labelled a scheduled job; Restart app followed by latency shows the change line.

#### T9. Feedback + damage map · PRD #24, §Differentiators
- [ ] 👎 on an alert raises that signal's flag level from 3 to 3.5 for 30 min, logged with who and when.
- [ ] Small topology map per tenant, so the damage map lights up affected parts (website, login, checkout).
- **Done when:** a 👎 stops repeats of that alert, and a database slowdown lights its dependents.

#### T10. Head-office AI + narratives · PRD #21, §AI assistants
- [ ] Ollama via the OpenAI Python client.
- [ ] Input: the incident JSON + a 10-minute metric summary for the **logged-in tenant only**.
- [ ] Rules: answer only from evidence and cite evidence IDs. For anything else, say "I don't have that, raw data stays in the customer's environment."
- [ ] Pre-write the narrative when an incident opens.
- **Done when:** asked "What password did the attacker use?", it refuses with that reason. Asked "Why is Shop A red?", it answers with evidence tags.

```text
Prompt (intelligence + AI): Read AGENTS.md and contracts/. In hq/aiops add the kill-chain rule (10 min), counterfactuals
(re-run health without each signal), runbook recommendations with why/risk/reversible/rollback, scheduled-job learning
(3 gaps within ±10 %), change linking (5 min before first signal, +0.1 confidence), thumbs-down suppression (3 → 3.5 for
30 min) and a per-tenant topology for the damage map. In hq/ai use the OpenAI client against Ollama (qwen3.5:4b,
fallback qwen2.5): answer only from the incident JSON + 10-min tenant summary, cite evidence_id, refuse anything else
with the "raw data stays in the customer's environment" reason, and pre-write a narrative when an incident opens.
```

### H20–H24
- [ ] Bug fixes only. Rehearse twice. During the final, answer the AI and AIOps questions.

---

## If time runs short (§Summary › cut order)
In this order: damage map → thumbs feedback. Never cut: health states, incidents with explanations, head-office AI (§Summary › MVP).

## Your demo scenarios (§Demo script › Live scenarios)
- Network latency rises
- CPU or memory leaves baseline
- Several alerts, one incident (kill chain)
- Normal recurring spike (backup job)
- Change caused it
- AI part of the 3-minute story

## Judge questions you answer (§Judge questions)
Real anomaly vs normal spike? · How do you correlate? · Why this action? · Safeguards before automation?
