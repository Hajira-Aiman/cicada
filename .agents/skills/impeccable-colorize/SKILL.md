---
name: impeccable-colorize
description: Color theory, semantic status tokens, and dark theme palette generation for enterprise observability applications.
---

# Impeccable Colorize

## 1. The 60-30-10 Rule in Dark Dashboards
- **60% Dominant Neutral**: Canvas & panels (`#080c14` / `#0b0f19` / `#111827`).
- **30% Structural Neutral**: Card borders, dividers, muted text (`#1e293b`, `#334155`, `#94a3b8`).
- **10% High-Signal Accent**: Semantic state colors that communicate health, alerts, and active controls.

## 2. Semantic Status Tokens (Airlock Palette)

```css
/* Excellent / Stored / Match / Success */
--status-success-bg: rgba(16, 185, 129, 0.10);
--status-success-border: rgba(16, 185, 129, 0.30);
--status-success-text: #34d399; /* emerald-400 */
--status-success-glow: rgba(16, 185, 129, 0.20);

/* Minor / Good / Informational */
--status-info-bg: rgba(56, 189, 248, 0.10);
--status-info-border: rgba(56, 189, 248, 0.30);
--status-info-text: #38bdf8; /* sky-400 */

/* Warning / Fair / Stale / Jitter */
--status-warning-bg: rgba(245, 158, 11, 0.10);
--status-warning-border: rgba(245, 158, 11, 0.30);
--status-warning-text: #fbbf24; /* amber-400 */

/* Critical / Poor / Mismatch / Breach */
--status-danger-bg: rgba(239, 68, 68, 0.12);
--status-danger-border: rgba(239, 68, 68, 0.35);
--status-danger-text: #f87171; /* rose-400 */
--status-danger-glow: rgba(239, 68, 68, 0.25);
```

## 3. Strict Rules
- Never use bright un-muted saturated backgrounds for status alerts; use 10% opacity tints with matching 30% opacity borders.
- Gradient text is reserved strictly for the primary brand logo; never apply gradients to metric numbers or status labels.
