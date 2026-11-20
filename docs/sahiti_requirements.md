# Airlock — Role A: AIOps and AI Requirements Specification

## 1. Executive Summary & Role Ownership

- **Role:** **A · AIOps and AI Engineer**
- **Core Philosophy:** *"Math decides what is wrong; the AI only explains it."* Every number on an incident card traces directly back to stored allow-listed metrics or events. The AI never guesses or hallucinates root causes.
- **Owned Codebases:**
  - `tools/simulate.py`: Multi-guard payload simulator supporting all live hackathon chaos scenarios.
  - `hq/aiops/`: Mathematical analytics engine (EWMA baselines, River anomaly detection, 4 health states with hysteresis, multi-signal agreement, incident correlation, kill-chain detection, contribution bars, confidence scoring, counterfactuals, runbook recommendations, scheduled job learning).
  - `hq/ai/`: Head-office AI assistant (Ollama / Qwen integration via OpenAI client, evidence-only citation enforcement, automated incident narratives).
  - Shared contracts for incidents (`contracts/models.py`).

---

## 2. Mathematical & Algorithmic Specifications

### 2.1 Baseline Engine (`hq/aiops/baseline.py`)
- **Metric Scope:** Per `(tenant_id, source, metric_name)`.
- **Model:** Exponentially Weighted Moving Average (EWMA) and Exponentially Weighted Moving Variance (EWMVar).
- **Parameters:**
  - $\alpha = 0.1$ (smoothing factor).
  - Warm-up threshold: 30 data points (60 seconds at 2s intervals).
- **Deviation Metric ($z$-score):**
  $$z = \frac{x_t - \mu_t}{\sigma_t + \epsilon}$$
  where $\epsilon = 10^{-6}$ prevents division by zero.
- **Flag Condition:** $|z| \ge 3.0$ for **3 consecutive windows** (6 seconds), preventing single-sample transient blips from triggering false alarms.
- **Feedback Suppression:** A thumbs-down (👎) feedback on a signal raises the threshold from $|z| \ge 3.0$ to $|z| \ge 3.5$ for that metric for 30 minutes.

### 2.2 River Online ML Anomaly Scoring (`hq/aiops/anomaly.py`)
- **Algorithm:** `river.anomaly.HalfSpaceTrees` (streaming isolation trees).
- **Features:** 5-dimensional normalized vector: `[cpu_pct, mem_pct, latency_ms, packet_loss_pct, net_out_kbps]`.
- **Role:** Second opinion score $[0.0, 1.0]$.
- **Consensus Rule ("Signals Must Agree"):**
  - High CPU alone with normal latency and normal errors is classified as `info: usage spike`.
  - An anomaly is escalated to an incident only when multiple signals agree (e.g. CPU + latency + errors) or River anomaly score $> 0.75$.

### 2.3 Four Health States & Hysteresis Engine (`hq/aiops/health.py`)
- **Health States & Evaluation Order:**
  1. **Poor (Critical):**
     - Collector offline: no heartbeat received for $\ge 30\text{ s}$.
     - `service_down` event received.
     - Honeypot hit (`honeypot_hit`) or kill-chain match.
     - `latency_ms > 1000\text{ ms}` or `packet_loss_pct > 10\%`.
  2. **Fair (Degraded / Warning):**
     - Stale data: no heartbeat received for $10\text{ s} \le t < 30\text{ s}$.
     - Sustained anomaly: $|z| \ge 3.0$ for 3 consecutive windows.
     - Resource pressure: `cpu_pct > 85\%`, `mem_pct > 90\%`, `disk_pct > 90\%`.
     - Network degradation: `latency_ms > 200\text{ ms}` or `packet_loss_pct > 2\%`.
     - Medium `auth_failure_burst`.
  3. **Good (Minor Warning):**
     - Single metric $2.0 \le |z| < 3.0$, or single warning threshold breached for $< 30\text{ s}$.
     - Service fully available.
  4. **Excellent (Normal):**
     - Heartbeat fresh ($< 10\text{ s}$).
     - All metrics within normal baseline ($|z| < 2.0$).
- **Anti-Flapping (Hysteresis):**
  - **Degrade:** Transitions to a worse state require bad data sustained for $\ge 6\text{ s}$ (3 windows).
  - **Recover:** Transitions to a better state require good data sustained for $\ge 20\text{ s}$ (10 windows).
  - Blocked flapping transitions increment a persistent `flaps_prevented` counter.
- **Explainability:** Every state transition records: `tenant_id`, `source`, `old_state`, `new_state`, `reasons` (list of human-readable evidence strings), and `transition_at` (UTC ISO-8601).

### 2.4 Scheduled Job Learning (`hq/aiops/scheduled_jobs.py`)
- **Problem:** Periodic cron jobs (e.g. backup, report generation) trigger recurring CPU spikes that cause alert fatigue.
- **Algorithm:**
  - Track timestamps of metric spikes ($|z| \ge 3$) per `(tenant_id, source, metric)`.
  - Calculate inter-spike intervals: $\Delta t_1, \Delta t_2, \Delta t_3$.
  - If 3 consecutive intervals match within $\pm 10\%$ tolerance (e.g. $60\text{ s} \pm 6\text{ s}$), establish a **Learned Scheduled Job**.
- **Action:** Future spikes occurring within the expected window are classified as `info: scheduled job (every ~N s)` and suppressed from opening incidents, with the suppression reason displayed. Off-schedule spikes still alert immediately.

### 2.5 Incident Correlation & Kill-Chain Engine (`hq/aiops/correlator.py`)
- **Incident Grouping Window:** 120 seconds for same tenant + related topology component. Repeated signals increment a counter rather than creating duplicate alerts.
- **Kill-Chain Rule ("Possible compromise: cryptomining"):**
  1. `auth_failure_burst` (burst of failed logins)
  2. Followed by `login_after_failures` or `odd_hour_login` within 10 min
  3. Followed by `cpu_pct` anomaly ($|z| \ge 3$) within 10 min
  4. Followed by `net_out_kbps` anomaly ($|z| \ge 3$) within 10 min
  $\rightarrow$ Merges all 4 into **1 Critical Incident**.
- **Change Event Correlation ("What changed just before"):**
  - Guard sends change events: `app_restarted`, `version_changed`, `config_changed`, `new_process`.
  - Any change occurring within 5 minutes prior to the first incident signal is linked as likely trigger (e.g., *"started 40 s after shop-api restarted"*) and adds $+0.10$ to confidence.
- **Mathematical Formulations:**
  - **Confidence:**
    $$\text{Confidence} = \min\left(0.95, 0.40 + 0.15 \times N_{\text{agreeing}} + (0.10 \text{ if rule matched}) + (0.10 \text{ if change linked})\right)$$
  - **Signal Contribution Percentage:**
    $$\text{Contribution}_i = \frac{|z_i|}{\sum_j |z_j|} \times 100\%$$
    (or event count ratio for discrete event categories).
  - **Counterfactual Reasoning:**
    Deterministic re-evaluation: re-run the health evaluation rule omitting signal $i$. If the resulting state would be lower, generate the counterfactual explanation (e.g. *"Without the outbound spike this would be a High security incident, not Critical"*).

### 2.6 Incident Object Specification
```json
{
  "incident_id": "inc-0042",
  "tenant_id": "globex",
  "title": "Possible compromise: cryptomining",
  "severity": "critical",
  "confidence": 0.85,
  "started_at": "2026-11-21T04:10:02Z",
  "affected": ["host-7f3a1234", "shop-api", "checkout"],
  "signals": [
    {"evidence_id": "ev-1", "name": "auth_failure_burst", "value": 50, "baseline": 2, "contribution_pct": 35},
    {"evidence_id": "ev-2", "name": "cpu_pct", "value": 96.0, "baseline": 21.0, "z": 7.4, "contribution_pct": 40},
    {"evidence_id": "ev-3", "name": "net_out_kbps", "value": 900.0, "baseline": 40.0, "z": 5.1, "contribution_pct": 25}
  ],
  "reasoning_path": [
    "login burst at 04:10",
    "login success at 04:11",
    "CPU anomaly at 04:12",
    "outbound spike at 04:12",
    "kill-chain rule matched"
  ],
  "counterfactual": "Without the outbound spike this would be a High security incident, not Critical",
  "recommendation": {
    "action": "kill_process",
    "target": "proc-1a2b3c4d",
    "why": "Process started after suspicious login and consumes 90% CPU",
    "risk": "low",
    "reversible": true,
    "rollback": "Restart shop-api if affected"
  },
  "narrative": "At 04:10 UTC, host-7f3a1234 suffered an auth failure burst (50 attempts [ev-1]). A login succeeded at 04:11 UTC followed by a CPU spike to 96% [ev-2] and outbound network spike of 900 kbps [ev-3]. This pattern matches the cryptomining kill-chain rule."
}
```

---

## 3. Simulator Tool Specification (`tools/simulate.py`)

Must run as an asynchronous multi-guard simulator generating cryptographically valid, schema-compliant `airlock.v1` payloads:
- **CLI Options:**
  - `--guards N`: Number of concurrent guards to simulate.
  - `--tenants`: Tenant list (e.g. `acme,globex,contoso`).
  - `--interval`: Post interval in seconds (default: 2.0).
  - `--endpoint`: Ingest URL (default: `http://localhost:8002/ingest`).
  - `--secret`: HMAC signing key.
- **Scenario Switches:**
  - `--scenario normal`: Normal baseline telemetry ($|z| < 1.5$).
  - `--scenario cpu_spike`: Injects CPU spike ($>95\%$) on target guard.
  - `--scenario latency`: Injects latency ($>500\text{ ms}$) and packet loss ($>5\%$).
  - `--scenario login_burst`: Emits `auth_failure_burst` (count=50) with honeypot user `admin_backup`.
  - `--scenario outage`: Halts transmissions for 35s to trigger stale (10s) and offline (30s) state transitions.
  - `--scenario duplicates`: Sends replayed payloads with identical `payload_id` to verify deduplication.
  - `--scenario out_of_order`: Shuffles window timestamps to verify event-time ordering.
  - `--scenario kill_chain`: Executes 4-stage sequential progression (login burst $\rightarrow$ login success $\rightarrow$ CPU spike $\rightarrow$ network out spike).
  - `--scenario scheduled_job`: Generates predictable CPU spikes every 60 seconds to demonstrate learned job suppression.

---

## 4. Head-Office AI Assistant Specification (`hq/ai/`)

- **Model:** Ollama `qwen3.5:4b` (fallback `qwen2.5`) via standard OpenAI Python client.
- **Evidence-Only System Prompt:**
  1. The assistant has access ONLY to the incident JSON and 10-minute metric summary for the logged-in tenant.
  2. Every technical assertion MUST cite an `evidence_id` in brackets (e.g. `[ev-1]`).
  3. If asked for information not present in the payload (passwords, raw logs, real IPs, customer data), it MUST respond: *"I do not have access to that information. Raw customer data never leaves the customer environment."*
- **Incident Narrative Generation:**
  - Triggered automatically when an incident is opened.
  - Translates the structured `reasoning_path`, `signals`, and `counterfactual` into a 3-sentence executive summary.
