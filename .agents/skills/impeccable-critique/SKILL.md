---
name: impeccable-critique
description: Rigorous design heuristic review to detect and eliminate AI slop, visual clutter, weak hierarchy, and contrast failures before shipping UI code.
---

# Impeccable Critique

Use this skill to audit an existing screen or component design against professional standards.

## The Heuristic Critique Rubric

### 1. The 5-Second Scan Test
- Where do the user's eyes land first? If they land on a generic background or a giant meaningless box instead of the critical status or metric, the hierarchy is broken.
- Is the primary metric distinct in size, weight, and contrast?

### 2. Clutter & Containeritis Audit
- Count nested containers: Is there a card inside a card inside a card?
- **Rule:** If a container doesn't separate conceptually different data or provide necessary grouping, **delete the box**. Use whitespace or subtle horizontal divider rules (`divide-y divide-slate-800/60`) instead of wrapping everything in heavy borders.

### 3. Palette Semantics
- Are semantic colors overused? If half the screen is bright red or neon green, nothing stands out.
- Red/Crimson is reserved exclusively for actionable critical errors or active security threats.
- Amber is reserved for warnings and deviations.
- Emerald is reserved for verified healthy states.
- Normal data, graphs, and UI chrome must remain neutral (slate, zinc, navy).

### 4. Typography Hierarchy
- Are there more than 3 font sizes within a single card? (Simplify to: Eyebrow label, Main Value, Subtitle context).
- Is tracking applied intentionally? (Negative tracking `-0.02em` on big headers, positive tracking `+0.05em` on small all-caps labels).
