---
name: observability-dashboard-design
description: Specialized domain design guidelines for high-density observability dashboards, AIOps incident storytelling, and cryptographic proof verification screens.
---

# Observability Dashboard Design Skill

Tailored specifically for **Airlock** and modern observability platforms.

## 1. High-Density Mission-Control Ergonomics
- **The Top-Level Status Bar**:
  - Anchors the operator immediately: Tenant Switcher, Timezone Switcher, Flaps Prevented counter, and Proof Badge.
  - Live pulse indicators: Subtle 2s pulse animation on healthy node indicators (`animate-pulse`).
- **The 4 Health States Visualization**:
  - `Excellent`: Emerald badge + glowing green dot (`#10b981`).
  - `Good`: Azure blue badge (`#3b82f6`).
  - `Fair`: Amber warning badge (`#f59e0b`).
  - `Poor`: Crimson alert badge (`#ef4444`).
  - Always pair the state with its **explicit reason** (e.g. "Stale data for 14s", "CPU > 90% for 3 windows"). Never leave an operator guessing why a tile changed color.

---

## 2. AIOps Incident Storytelling UX
- **The Anatomy of an Incident Card**:
  1. **Header**: Severity badge (`CRITICAL`), Incident ID, UTC Start Time.
  2. **Title**: Plain-English diagnosis ("Possible compromise: cryptomining activity").
  3. **Confidence Meter**: Visual progress bar + hover tooltip exposing the exact formula (`0.40 base + 0.30 agreeing signals + ...`).
  4. **Signal Contribution Bars**: Proportional bars showing which metrics drove the anomaly (e.g. Auth Burst 35%, CPU 40%, Egress 25%).
  5. **Reasoning Path**: Sequential bullet points tracing the kill-chain chronologically.
  6. **Counterfactual Callout**: Highlighted box explaining *"Without signal X, this would be classified as Y"*.
  7. **One-Tap Safe Remediation**: Dry-run preview button with risk rating and reversible rollback explanation.

---

## 3. Cryptographic Egress Proof Panel (The Differentiator)
- Side-by-side verification:
  - Left: Local Raw Logs (with secrets, passwords, and raw client IPs visible for local troubleshooting).
  - Right: Cryptographic Egress Proof (showing exact JSON sent, SHA-256 hash, and signed receipt from Head Office).
- Status Indicator: Large, bold `100% MATCHED ✅` badge showing that sent hash equals received hash bit-for-bit.
