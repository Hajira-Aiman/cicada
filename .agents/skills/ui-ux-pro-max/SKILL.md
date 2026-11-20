---
name: ui-ux-pro-max
description: NextLevelBuilder's UI/UX Pro Max design intelligence framework. Comprehensive design system blueprints, style archetypes, token systems, and component ergonomics.
---

# UI/UX Pro Max Design Intelligence

The **UI/UX Pro Max** skill provides a structured, multi-dimensional design intelligence framework for AI coding assistants.

## 1. Design System Blueprint (`MASTER.md` Model)
When creating or refining a web application, establish a persistent design source of truth:
- **Design Archetype**: Mission-Control Dark / Cyber-Sleek
- **Base Canvas**: Deep space obsidian `#080c14`
- **Surface Layer 1**: Panel slate `#0f172a`
- **Surface Layer 2**: Card slate `#1e293b`
- **Border Tokens**: `rgba(255, 255, 255, 0.08)` (subtle) / `rgba(56, 189, 248, 0.3)` (active)
- **Primary Accent**: Electric Sky `#38bdf8`
- **Typography**: Inter / System Sans for interface copy; JetBrains Mono / SF Mono for telemetry

---

## 2. Component Design Tokens & Anatomy

### Cards & Panels
- Border Radius: `rounded-xl` (12px) for cards, `rounded-2xl` (16px) for hero containers, `rounded-lg` (8px) for buttons.
- Border Width: 1px subtle stroke (`border border-slate-800` or `border border-white/5`).
- Elevation: Ambient shadow `shadow-lg shadow-black/30`.

### Data Visualization & Charts (Apache ECharts)
- **Theme**: Seamless transparent background (`backgroundColor: 'transparent'`).
- **Axis Styling**: Dimmed grid lines (`#1e293b`), muted axis labels (`#94a3b8`).
- **Tooltips**: Sleek dark tooltip container (`#1e293b` with `#334155` border, text `#f1f5f9`).
- **Confidence Bands**: Area fill using semi-transparent primary color (`rgba(56, 189, 248, 0.08)`).
- **Line Width**: 2px for normal metrics, 3px bold for primary focus metric.

### Accessibility (A11y) Standards
- Minimum contrast ratio of 4.5:1 for all readable text.
- Touch target minimum: 44×44px on mobile phone views (`min-h-[44px] min-w-[44px]`).
- Screen-reader friendly semantic HTML (`<header>`, `<main>`, `<nav>`, `<button>`).
