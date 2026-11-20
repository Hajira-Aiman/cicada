# Airlock — Role A: AIOps and AI Implementation Milestones

## Project Tracking & Progress (Role A · AIOps & AI Engineer)

| Milestone | Phase | Focus Area | Status | Target Delivery |
| --- | --- | --- | --- | --- |
| **M0** | H0–H2 | Prerequisites, ML/AI Dependencies & Contracts | ✅ Completed | Immediate |
| **M1** | H2–H6 | Simulator (`tools/simulate.py`) & Baseline + Health Engine v1 | ✅ Completed | H2–H6 |
| **M2** | H6–H12 | River ML Anomaly Scoring, Multi-Signal Agreement & Incident Grouping | 🔄 Ready / Next | H6–H12 |
| **M3** | H12–H15 | Real Telemetry Ingest Integration & Threshold Tuning | ⏳ Pending | H12–H15 |
| **M4** | H15–H20 | Kill-Chain Engine, Counterfactuals, AI Assistant (Ollama) & Scheduled Jobs | ⏳ Pending | H15–H20 |
| **M5** | H20–H22 | Full Scenario Verification Suite & Chaos Rehearsal | ⏳ Pending | H20–H22 |
| **M6** | H22–H24 | Final Live Demonstration & Judging Support | ⏳ Pending | H22–H24 |

---

## Milestone 0: Prerequisites, Dependencies & Incident Contracts (H0–H2)
*Goal: Ensure Python environment contains math/ML libraries and shared contracts define full incident schemas.*

- [x] **0.1 Environment & Tool Verification**
  - [x] Python 3.13/3.14 virtual environment `.venv` active.
  - [x] Install streaming ML & LLM libraries: `river`, `openai`, `numpy`, `scipy`.
- [x] **0.2 Shared Contracts Frozen (`contracts/models.py`)**
  - [x] `AirlockPayload` with strict `extra="forbid"` and allow-listed metrics/events.
  - [x] Add `Incident`, `SignalEvidence`, and `Recommendation` models to `contracts/models.py`.
  - [x] Unit tests in `tests/test_contracts.py` verifying serialization and schema constraints.

---

## Milestone 1: Simulator & Baseline + Health Engine v1 (H2–H6)
*Goal: Deliver the multi-guard chaos simulator for team unblocking and build the core EWMA baseline and 4-state health engine with hysteresis.*

- [x] **1.1 Multi-Guard Chaos Simulator (`tools/simulate.py`)**
  - [x] Asynchronous multi-guard runner sending valid signed `airlock.v1` payloads.
  - [x] Implement scenario switches:
    - [x] `normal`: Healthy baseline metrics.
    - [x] `cpu_spike`: Rapid CPU excursion ($>95\%$).
    - [x] `latency`: Elevated round-trip latency ($>500\text{ ms}$) and packet loss.
    - [x] `login_burst`: Authentication burst (count=50) with honeypot user `admin_backup`.
    - [x] `outage`: Interrupted heartbeat for $\ge 35\text{ s}$ to test stale/offline detection.
    - [x] `duplicates`: Replay payload ID transmission for deduplication testing.
    - [x] `out_of_order`: Out-of-order window delivery.
    - [x] `kill_chain`: Automated progression across the 4 stages.
- [x] **1.2 EWMA Baseline Engine (`hq/aiops/baseline.py`)**
  - [x] Rolling mean ($\mu$) and standard deviation ($\sigma$) with $\alpha=0.1$.
  - [x] Warm-up tracking (30 data points / 60 seconds).
  - [x] Calculate $|z|$-scores per `(tenant_id, source, metric)`.
  - [x] 3-window consecutive persistence filter (6 seconds) before flagging.
- [x] **1.3 Four Health States & Anti-Flapping Engine (`hq/aiops/health.py`)**
  - [x] Implement 4 health states: `Excellent`, `Good`, `Fair`, `Poor`.
  - [x] Stale data detector (10s without data $\rightarrow$ Fair; 30s $\rightarrow$ Poor/Offline).
  - [x] Explicit reason generation for every transition.
  - [x] Anti-flapping hysteresis (6s bad to enter worse state, 20s good to recover).
  - [x] Maintain persistent `flaps_prevented` counter.
- [x] **1.4 Milestone 1 Automated Tests**
  - [x] `tests/test_simulate.py`: Verify simulator payload compliance and signature validity (6 tests passing).
  - [x] `tests/test_aiops_health.py`: Verify baseline convergence, 4-state transitions, stale handling, and hysteresis (4 tests passing).

---

## Milestone 2: River ML Anomaly Scoring & Incident Grouping (H6–H12)
*Goal: Implement streaming ML second-opinion scoring, signal consensus, and 120s incident correlation.*

- [ ] **2.1 Streaming ML Anomaly Scoring (`hq/aiops/anomaly.py`)**
  - [ ] Implement `river.anomaly.HalfSpaceTrees` streaming isolation forest.
  - [ ] Multi-dimensional vector: `[cpu, mem, latency, packet_loss, net_out]`.
  - [ ] "Signals must agree" rule: Single CPU spike classified as `info: usage spike`; multi-signal deviation opens an incident.
- [ ] **2.2 Incident Grouping Engine (`hq/aiops/correlator.py`)**
  - [ ] 120-second correlation window for same tenant and related topology component.
  - [ ] Deduplication of repeating alerts into counters.
  - [ ] Signal contribution percentage calculation: $\frac{|z_i|}{\sum |z|} \times 100\%$.
  - [ ] Confidence formula calculation: $0.40 + 0.15 \times N_{\text{agreeing}} + 0.10 \times \text{rule\_matched}$.

---

## Milestone 3: Real Integration & Threshold Tuning (H12–H15)
*Goal: Integrate AIOps engine with live regional ingest services and tune baselines on real guard telemetry.*

- [ ] **3.1 Ingest Service Integration**
  - [ ] Consume ingested payloads from PostgreSQL / in-memory ingest worker.
  - [ ] Process out-of-order payloads by event-time (`window.start`).
- [ ] **3.2 Threshold Calibration**
  - [ ] Tune EWMA $\alpha$ and warm-up parameters against real multi-laptop telemetry.
  - [ ] Verify transition latency (under 15s from injection to alert).

---

## Milestone 4: Advanced Intelligence, AI Assistant & Extras (H15–H20)
*Goal: Deliver Ollama-powered explainable AI assistant, kill-chain detection, counterfactuals, and learned scheduled jobs.*

- [ ] **4.1 Kill-Chain Rule Engine**
  - [ ] Detect sequence: `auth_failure_burst` $\rightarrow$ login success $\rightarrow$ CPU anomaly $\rightarrow$ outbound spike within 10 min.
  - [ ] Merge into single Critical Incident: *"Possible compromise: cryptomining"*.
- [ ] **4.2 Change Event Linking ("What changed just before")**
  - [ ] Correlate guard change events (`app_restarted`, `config_changed`) occurring within 5 min before an incident.
  - [ ] Annotate incident and raise confidence by $+0.10$.
- [ ] **4.3 Counterfactual Engine**
  - [ ] Deterministically re-run health engine without each signal to prove necessity.
- [ ] **4.4 Learned Scheduled Jobs (`hq/aiops/scheduled_jobs.py`)**
  - [ ] Track recurring spike intervals; learn 3 regular intervals ($\pm 10\%$).
  - [ ] Suppress predictable spikes as `info: scheduled job (every ~N s)` with reason displayed.
- [ ] **4.5 Head-Office AI Assistant (`hq/ai/`)**
  - [ ] Ollama integration using OpenAI Python client (`qwen3.5:4b`).
  - [ ] Evidence-only system prompt with mandatory `[ev-N]` citations.
  - [ ] Hard refusal rule: *"I do not have access to that information. Raw customer data never leaves the customer environment."*
  - [ ] Automated incident narrative synthesis.
- [ ] **4.6 Thumbs Feedback Suppression**
  - [ ] 👎 on an alert temporarily raises $|z|$ threshold from 3.0 to 3.5 for 30 min.

---

## Milestone 5: Verification Suite & Rehearsal (H20–H22)
*Goal: Rehearse and pass all 15 hackathon judge scenarios end-to-end.*

- [ ] Automated execution of all scenarios using `tools/simulate.py`.
- [ ] Verification of noise reduction metrics (e.g. 47 alerts $\rightarrow$ 3 incidents, 94% noise cut).
- [ ] Freeze code and eliminate regressions.

---

## Milestone 6: Live Demonstration & Judging (H22–H24)
*Goal: Stand by during live judging to explain mathematical models and AI evidence citations.*
