# Airlock: Anisa's tasks (F · Frontend and demo)

**Source:** *CICADA 2026 – Smart Observability Hackathon Plan* (the PRD). Every task points back to it:
- `PRD #n` = row *n* of the table "PRD: requirements to features"
- `§Section › Part` = a section of the plan

**Your role in one line:** you build **every screen people see**: the head-office dashboard, the shop screen, the chaos console and the phone pages. You also own the **slides, demo script and judge Q&A sheet**, and you present. (§Team split › Roles)

**You own:** `web/`, `docs/`, slides (§Working in Antigravity › Repo layout)
**Stack:** Vue 3 + Vite + Apache ECharts, following the team's **design.md** (§Open source, §Screens)

**Your laptop on demo day:** laptop 4 = **chaos console** (:5173). It also runs Hajira's guard for the organizer stream. The head-office dashboard is shown on the projector from the LOQ.

**One codebase, 4 entry points** (starter prompt F):

| Entry | Served from | Who sees it |
|---|---|---|
| `hq` | LOQ (Sahiti's `hq-api`) | Projector, engineer + customer logins |
| `shop` | Each shop's guard (:9000, Hajira) | Only on that shop's laptop |
| `chaos` | Laptop 4 | Judges press the buttons |
| `phone` | LOQ | Judges' phones: `/join`, `/approve`, `/raw`, `/smart` |

---

## Handoffs: who you depend on, who depends on you

| You need… | From | By |
|---|---|---|
| design.md | Team (you share it) | H2 |
| Example JSON in `contracts/examples/` (payload, receipt, WebSocket messages, incident) | Hajira, Sahiti, Adithya | H2 |
| Live WebSocket + APIs | Sahiti | H6 |
| Guard local API (raw logs, ledger, buffer, reveal) | Hajira | H12 |
| Chaos agent API | Sahiti | H12 |
| Incidents + AI chat endpoint | Adithya | H12 / H20 |

| Others need from you… | Who | By |
|---|---|---|
| Data-flow sketch for judging round 1 | Team | H2 |
| Architecture slide for judging round 2 | Team | H6 |
| Shop screen bundle (the guard serves it) | Hajira | H12 |
| Chaos console working | Sahiti, judges | H15 |

---

## Shared team tasks (§Team split, §Demo script)

- [ ] **H0–H2, contract:** with the team, write and freeze `contracts/`. **Your part:** check the examples have every field your screens need. Then you never wait on live APIs.
- [ ] **Every 2 hours:** merge to `main` and run the smoke test (simulator → ingest → dashboard).
- [ ] **H12–H15, integration** on real laptops; switch the screens from mock JSON to the WebSocket.
- [ ] **H15–H20:** take one 90-minute nap, staggered with the team.
- [ ] **H20–H22:** run all live scenarios twice with the team; finish the slides and Q&A sheet.
- [ ] **H22–H24:** present.

---

## Tasks by phase

### H0–H2 · Setup + round 1

#### T0. Vue scaffold · §Team split › phase table
- [ ] Vue 3 + Vite + ECharts project in `web/` with the 4 entry points above and mock JSON loading.
- **Done when:** all 4 entry pages open locally with sample data.

#### T1. Round 1 data-flow sketch · §Roadmap, §Architecture
- [ ] A one-page sketch: the trust boundary, what stays local, what is sent (allow-listed fields), and who sees what.
- **Done when:** the team can explain it at round 1 (10 marks).

### H2–H6 · Thin slice + round 2

#### T2. One live CPU tile per tenant · §Team split › phase table
- [ ] Connect to Sahiti's WebSocket and show CPU for each tenant.
- **Done when:** the Ryzen's CPU moves on the tile in under 10 s.

#### T3. Architecture slide for round 2 · §Architecture (diagram, payload schema, security, global-ready)
- [ ] Use the plan's diagram + the payload schema + allow-list table + how outages and duplicates are handled.
- **Done when:** ready for round 2 (25 marks).

### H6–H12 · Core screens

#### T4. Head-office dashboard · PRD #8, #10, #12, #14, §Screens › Head office
- [ ] Tenant switcher + login.
- [ ] Fleet grid with the 4 states (Excellent / Good / Fair / Poor) and reasons. Guard last seen, version, CPU and memory, buffer depth, config OK.
- [ ] Live charts with the normal-range band.
- [ ] Security box: counts + risk level, never usernames or IPs.
- [ ] Incident cards (from Adithya's incident object):
  - contribution bars
  - confidence (formula on hover)
  - reasoning path
  - counterfactual
  - recommended action
- [ ] History of state changes in UTC.
- [ ] Reconciliation panel: sent / received / duplicates / gaps.
- [ ] Leak badge: "Canaries planted N · leaks detected 0".
- [ ] Noise counter: "Raw alerts N → incidents M".
- **Done when:** every panel shows simulator data live, and switching to the Acme login hides Globex.

#### T5. Shop screen + egress proof panel · PRD #2, #7, §Screens › Inside the shop
- [ ] Raw logs with secrets visible (local only).
- [ ] **Egress proof panel:** the exact JSON of each payload, its hash, and ✅/❌ receipt match.
- [ ] Buffer depth, retention countdown, reveal-pseudonym lookup.
- **Done when:** a judge can open the last payload and compare it with what head office shows. This is **mandatory** (§Summary › MVP).

#### T6. Chaos console · PRD #23, §Screens › Chaos console
- [ ] A button per scenario and target shop:
  - CPU spike, latency, brute force
  - pause region, replay + shuffle, tamper menu
  - kill chain, Backup job, Restart app
- [ ] **Try-to-leak box** (§Differentiators): any text the judge types is sent to the shop app.
- [ ] Scenario log with UTC timestamps.
- **Done when:** each button triggers Sahiti's chaos agent and its effect appears on the dashboard.

#### T7. Time-zone switch, flaps counter, receipt-log badge · PRD #25, #29, #30
- [ ] Time-zone switch: every timestamp in UTC / viewer zone / shop zone. India and Europe events line up on one UTC timeline.
- [ ] "Flaps prevented" counter.
- [ ] Receipt-log ✅ badge on both the head-office and shop screens.
- **Done when:** switching zones changes labels but never the order of events.

```text
Prompt (core screens): Read AGENTS.md, contracts/ and design.md. In web/ (Vue 3 + Vite + ECharts) build the hq entry:
tenant switcher + login, fleet grid with 4 states + reasons and guard health, live charts with a normal band,
security box, incident card (contribution bars, confidence with formula on hover, reasoning path, counterfactual,
recommended action), UTC history, reconciliation panel, leak badge, noise counter, flaps counter, receipt-log badge,
time-zone switch (UTC / viewer / shop). Build the shop entry: raw logs, egress proof panel (exact JSON, hash, ✅/❌),
buffer depth, retention countdown, reveal lookup. Build the chaos entry with one button per scenario + the try-to-leak
box + a UTC scenario log. Use contracts/examples until the WebSocket is live.
```

### H12–H15 · Integrate + round 3

#### T8. Latency meter · PRD #19
- [ ] Live event time → render time, p50/p95, plus alert-delay and offline-delay stamps (with Adithya).
- **Done when:** the meter shows p95 under 10 s on real data.
- [ ] Rehearse the round 3 demo (§Roadmap): the live split screen + forced outage + reconciliation (35 marks).

### H15–H20 · Intelligence + extras

#### T9. Phone pages · PRD #20, #24, §Differentiators
- [ ] **`/join`:** QR on the projector (python `qrcode`). The phone sends a heartbeat + latency every 2 s and appears in the fleet; a closed tab goes offline within 60 s.
- [ ] **`/approve`:** pending fixes with the explanation, **Dry run** first, then Approve / Reject with the judge's name, rollback timer, audit row.
- [ ] **`/raw`** (buzzes for every raw alert) vs **`/smart`** (one incident only), both from the same WebSocket.
- **Done when:** two phones held side by side clearly show noisy vs clean.

#### T10. AI chat panel + damage map · PRD #21, #24
- [ ] Head-office AI chat with clickable evidence tags that open the matching chart.
- [ ] Damage map: a database slowdown lights up website, login and checkout.
- [ ] 👎 button on alerts (feedback, PRD #24).
- **Done when:** asking "Why is Shop A red?" shows an answer with evidence tags.

#### T11. Reveal UI + dry-run panel · PRD #28, #31
- [ ] Head office: Reveal button on an incident. The shop screen gets an approve/reject prompt and shows the real value only there.
- [ ] A dry-run panel showing exactly what the fix would change before Approve is enabled.
- **Done when:** head office still shows `src-9c2e` while the shop screen shows the real IP after approval.

```text
Prompt (phones + AI): Read AGENTS.md, contracts/ and design.md. In web/ build the phone entry: /join (heartbeat +
latency every 2 s as tenant guests, QR shown on hq), /approve (incident explanation, Dry run first, then Approve /
Reject with name, rollback timer, audit row), /raw (vibrate on every raw alert) and /smart (incidents only) from the same
WebSocket. On hq add the AI chat panel with clickable evidence tags, the damage map, the thumbs-down button and the
Reveal button; on shop add reveal approve/reject.
```

### H20–H24 · Freeze, rehearse, present

#### T12. Demo script, slides, Q&A sheet · §Demo script, judge Q&A, limitations
- [ ] Slides following the **3-minute story**:
  1. Problem (20 s)
  2. Proof of privacy (50 s)
  3. Reliability (40 s)
  4. Intelligence (50 s)
  5. AI (20 s)
- [ ] A "real-world precedent" slide: CrowdSec and Netdata ship metadata-only designs (§Differentiators).
- [ ] A Q&A sheet from the plan's judge-questions table (answers without slides) + the honest limitations.
- [ ] A screen-to-scenario map for every live scenario.
- **Done when:** the full scenario run works twice in a row and you can answer every Q&A row without notes.

---

## If time runs short (§Summary › cut order)
In this order: talking alerts → damage map → phone fleet join → thumbs feedback. Never cut: egress proof panel, health states, incident explanations, reconciliation (§Summary › MVP).

## Your demo moments (§Demo script › Live scenarios)
- Try-to-leak challenge
- Noisy vs clean phones
- Phones join
- Time zones
- Remediation on the phone
- The 3-minute story (you present)

## Judge questions you open (§Judge questions)
"What leaves the environment?" (open the egress panel and show the last payload) · the real-world precedent slide.
