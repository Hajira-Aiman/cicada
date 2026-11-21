# Airlock Live Demo Script (docs/DEMO_SCRIPT.md)

**Presenters:** Anisa (Frontend & Presentation Lead), Adithya (AIOps & AI), Sahiti (HQ API & Ingest), Hajira (Guard & Tier 1)  
**Laptops:**
- Laptop 1 (Ryzen / India): Acme Shop Guard (:9000)
- Laptop 2 (Linux / Europe): Globex Shop Guard (:9000)
- Laptop 3 (LOQ / Head Office): Head Office API (:8000), India Ingest (:8001), Europe Ingest (:8002), AIOps Worker, Projector Display
- Laptop 4 (Anisa / Chaos): Chaos Console (:5173), Contoso Organizer Guard

---

## 14 Live Scenarios Walkthrough

### Scenario 1: Clean Baseline & Real-Time Sync
- **Action:** Open Head Office Dashboard on Projector (`/overview`). Show TopNav pulse dot (green), live clock, and KPI strip.
- **Script:** *"Judges, welcome to Airlock. We are observing 3 global customer environments—Acme in India, Globex in Europe, and Contoso. Telemetry is streaming over WebSocket every 2 seconds. Every number you see uses JetBrains Mono with tabular figures so values never jitter."*

### Scenario 2: The Trust Boundary (2D/3D Fleet Bridge)
- **Action:** Switch to `/live-map`.
- **Script:** *"This is our Live Fleet Bridge. On the left are our customers' local environments. In the center is the purple Trust Boundary plane at x = -1. On the right is Head Office. Notice the green lime orb orbiting Acme: that represents private cleartext data that NEVER crosses the gate. Only cryptographic hashes and allow-listed metadata cross the boundary."*

### Scenario 3: CPU Spike Simulation
- **Action:** On Laptop 4 (`/chaos`), click **`CPU Spike`** on Acme.
- **Script:** *"Now, let's inject a sudden 95% CPU spike on Acme. Within 2 observation windows, watch the Head Office dashboard..."*
- **Effect:** Acme tile on `/overview` transitions to **FAIR**, reason reads `"Elevated CPU > 85% for 2 windows"`. Recharts shows red anomaly dot exceeding the baseline $\pm 2\sigma$ band.

### Scenario 4: Latency Degradation
- **Action:** On Laptop 4, click **`Latency Spike`** on Globex.
- **Script:** *"Injecting network degradation on Globex Europe. Notice the Latency chart immediately renders the spike, while our Latency Meter records P95 delivery remaining under 3 seconds."*

### Scenario 5: SSH Brute Force Attack
- **Action:** Click **`Brute Force Attack`** on Acme.
- **Script:** *"50 failed logins hit Acme in 2 seconds. In standard observability tools, this generates 50 distinct alert notifications. In Airlock, the Guard detects the pattern, redacts credentials, and emits a single pseudonymized event category."*

### Scenario 6: Full Kill-Chain Attack (The Hero Scenario)
- **Action:** Click **`Full Kill Chain`** on Acme.
- **Script:** *"Watch closely: an attacker brute-forces SSH, gains access, starts a cryptomining binary `proc-1a2b3c4d`, and begins exfiltrating data."*
- **Effect:** Head Office Incident Feed instantly opens **`CRITICAL · Possible compromise: cryptomining`** with 85% confidence.

### Scenario 7: Noise Cut Proof (47 Alerts → 1 Incident)
- **Action:** Highlight the Noise Reduction Header on `/incidents`: `RAW ALERTS 47 → INCIDENTS 1 (98% NOISE CUT)`.
- **Script:** *"Instead of flooding the on-call engineer's phone with 47 separate alerts, AIOps correlated all signals into one incident. Notice the contribution bars: CPU 40%, Auth Failure 35%, Network 25%."*

### Scenario 8: Explainable AI & Hover Formula
- **Action:** Hover over the **85% CONFIDENCE** badge on the Incident Card.
- **Script:** *"Judges, no black-box hallucinations. Hovering reveals the exact deterministic formula: base 0.4 + 0.15 × 3 agreeing signals + 0.1 for rule match = 0.85. The reasoning path details every chronological step."*

### Scenario 9: 1-Tap Remediation with Dry Run & 120s Rollback
- **Action:** Click **`DRY RUN`** on the incident card. Show the simulation result. Then click **`SEND FOR APPROVAL`**. On Laptop 4 or phone (`/m/approve`), show Judge 1-tap **`APPROVE`**.
- **Script:** *"Airlock never modifies production blindly. Step 1 is a pre-flight dry run simulation. Once approved by human-in-the-loop, an armed 120-second rollback timer appears. If anything misbehaves, one click reverts the fix."*

### Scenario 10: Mandatory Egress Proof (PRD #7)
- **Action:** Open `/shop` on Laptop 1. Open the **Egress Proof Panel**.
- **Script:** *"This is our mandatory MVP proof. On the left is the exact JSON payload leaving Acme's guard. On the right is the exact receipt stored at Head Office. Compare the SHA-256 hashes: they are bit-for-bit identical, yielding a verified ✓ MATCH."*

### Scenario 11: The "Try-to-Leak" Challenge (Judges Type a Secret)
- **Action:** Invite a judge to type `DB_PASSWORD=SuperSecretPass123!` into the Try-to-Leak box on `/chaos`.
- **Script:** *"Judge, type any password into this box. It is sent into the shop's local log. Watch Laptop 1: the password appears in crimson in local logs. But look at Head Office Ingest: our Scrubber and Tripwire zeroed it out. The leak counter remains strictly at ZERO."*

### Scenario 12: Regional Outage & Buffer Accumulation (PRD #15)
- **Action:** Click **`India Region Pause`** on `/chaos`.
- **Script:** *"We just simulated a complete outage of our India ingest region (:8001). India ingest now returns HTTP 503. Notice what happens: Acme guard does not crash and does not forward to Europe (which would violate GDPR/data residency). Instead, its local ring buffer depth increments: 1, 2, 3..."*

### Scenario 13: Zero-Loss Resumption & Stream Reconciliation
- **Action:** Click **`RESET ALL`** to unpause India region.
- **Script:** *"The outage resolves. Watch the Fleet Bridge: buffered payloads stream across the gate in strict FIFO sequence. Look at `/privacy` -> Reconciliation Table: Sent = 1,420, Received = 1,420, Gaps = NONE. Zero data loss."*

### Scenario 14: Privacy Refusal in AI Copilot
- **Action:** Open Copilot Drawer. Type: *"What is the password of user-7f3a1234?"*
- **Script:** *"Notice the Copilot response in purple: 'PRIVACY POLICY REFUSAL: Head Office AI cannot access cleartext passwords or user secrets.' The system provably enforces privacy at every layer."*
