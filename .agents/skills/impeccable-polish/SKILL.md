---
name: impeccable-polish
description: Pixel-level refinement pass to elevate interfaces from good to stunning. Fine-tunes micro-spacing, subtle border glows, shadow depth, and micro-interactions.
---

# Impeccable Polish

Use this skill when refining or finalizing any UI component, screen, or dashboard.

## The Polish Checklist

### 1. Border & Rim Lighting
- [ ] Replace harsh borders (`border-gray-700`) with subtle rim lighting: `border border-slate-800 hover:border-slate-700` or `border border-white/[0.08]`.
- [ ] Add subtle top-edge highlight on key cards: `border-t border-t-white/10` to simulate ambient key lighting.
- [ ] Apply glowing focus rings: `focus-visible:ring-2 focus-visible:ring-sky-500/50 focus-visible:outline-none`.

### 2. Micro-Typography & Alignment
- [ ] Check every label/value pair: label should be `text-[11px] font-mono text-slate-500 uppercase tracking-wider`, value should be crisp `font-bold text-white`.
- [ ] Ensure all numbers in live-updating widgets use `font-mono tracking-tight font-semibold`.
- [ ] Truncate long hashes and UUIDs cleanly: `truncate max-w-[140px]` with copy-on-click or full tooltip.

### 3. Surface & Shadow Layering
- [ ] Add layered elevation: `shadow-lg shadow-black/40` on cards, `shadow-2xl shadow-sky-500/5` on active/featured elements.
- [ ] Floating headers and modal dialogs must use `backdrop-blur-md bg-slate-900/90 border border-slate-800/80`.

### 4. Interactive Feel
- [ ] Hover states: subtle background lightening (`hover:bg-slate-800/80`) + smooth transition (`transition-all duration-150 ease-out`).
- [ ] Buttons: tactile press feedback with `active:scale-[0.98]`.
- [ ] Badges: soft background with matching border (e.g. `bg-emerald-500/10 text-emerald-400 border border-emerald-500/30`).
