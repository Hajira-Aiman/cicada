---
name: impeccable-layout
description: High-density layout composition, Bento grid ergonomics, responsive breakpoints, and information hierarchy for complex data screens.
---

# Impeccable Layout

## 1. Bento Grid Architecture
Organize complex dashboards using the **Bento Grid** paradigm:
- Unequal, self-contained rectangles that visually communicate weight and priority.
- Primary telemetry / chart occupies a 2-column or 3-column span (`col-span-2` or `col-span-3`).
- Secondary summary cards (Security, Fleet, Reconciliation) occupy single complementary columns.
- Ensure strict vertical alignment across rows using `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4`.

## 2. Information Density vs. Breathing Room
- Enterprise operators want information at a glance without endless scrolling.
- Use **compact vertical padding**: `py-3 px-4` inside cards instead of bloated `p-8`.
- Keep primary controls (tenant switcher, timezone toggle, proof badges) anchored in a sticky header or top toolbar.
- Avoid nested vertical scrollbars within small cards; reserve scrolling strictly for event feeds and log streams (`max-h-[400px] overflow-y-auto`).

## 3. Responsive Breakpoints
- **Mobile (< 768px)**: 1 column vertical stack; collapse dense tables into swipeable cards or simplified rows; ensure touch targets are at least 44x44px.
- **Tablet (768px - 1024px)**: 2-column grid; chart spans both columns.
- **Projector / Desktop (> 1280px)**: 3-column to 4-column Bento grid; optimal for LOQ projector viewing.
