---
name: impeccable-typeset
description: Typography rules for high-density, high-craft web interfaces and dashboards. Font pairings, scale, optical tracking, and tabular figures.
---

# Impeccable Typeset

## 1. Type Scale & Optical Tracking

```
Size       Class                    Tracking          Weight       Usage
-------------------------------------------------------------------------------------------------
Hero       text-4xl to text-5xl     tracking-tight    font-extrabold Page Title / Key Hero Stat
Title      text-xl to text-2xl      tracking-tight    font-bold      Section Header / Card Title
Body       text-sm                  tracking-normal   font-medium    Paragraphs / Explanations
Sub        text-xs                  tracking-normal   font-normal    Secondary context
Micro      text-[10px] to text-[11px] tracking-wider font-mono      Eyebrows / Labels (UPPERCASE)
Telemetry  text-sm to text-base     tracking-tight    font-mono      Metrics / Latencies / Hashes
```

## 2. Monospace & Tabular Figures Rule
For real-time observability dashboards:
- Every changing metric, percentage, latency, time, or sequence must use `font-mono`.
- Ensures zero horizontal layout jitter when numbers change from `9.9%` to `10.1%`.

## 3. Contrast Requirements (WCAG 2.1 AA)
On dark backgrounds (`#080c14` / `#0b0f19`):
- High-contrast text: `text-white` or `text-slate-100` (14:1+ ratio).
- Mid-contrast text: `text-slate-300` or `text-slate-400` (6.5:1 ratio).
- Low-contrast metadata: `text-slate-500` (4.6:1 ratio, strictly at or above the 4.5:1 threshold).
- Never use `text-slate-600` for readable text on `#0b0f19`.
