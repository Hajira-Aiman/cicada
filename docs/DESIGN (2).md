# AIRLOCK UI: Frontend Design and Architecture Specification

> **Version:** 1.0 (adapted from the THERVO UI spec v2.4.0)
> **Status:** Hackathon implementation blueprint (CICADA 2026, 24 h)
> **Owner:** Anisa (F · Frontend and demo)
> **Target stack:** React 19 + TypeScript + Vite + Tailwind CSS + Three.js / React Three Fiber (`@react-three/fiber` + `@react-three/drei`) + Zustand + TanStack Query + Recharts
> **Source of truth for features and data:** the plan doc *CICADA 2026 – Smart Observability Hackathon Plan* (the PRD) and the repo's `contracts/` folder. `PRD #n` = row *n* of "PRD: requirements to features".

**Decisions already made (from the team):**
- React
- THERVO's dark mission-control look
- 3D adapted to our 4 laptops
- No landing page
- No icons anywhere (text and mono labels only)
- Shop screen gets its own accent
- Top tabs
- The PRD page list
- The copilot as a drawer
- No bottom simulation dock
- WebSocket for live data
- A demo fallback with a SIMULATED banner
- Recharts

**Defaults applied (change if needed):**
- Health colours as in §2.1
- Inter + JetBrains Mono
- 1920×1080 projector; phone pages mobile-first
- Never colour alone: always a text label
- Glass blur toned down for projector performance
- THERVO's live pulse dot, uppercase mono eyebrows and inspector drawer kept

---

## 1. Executive summary and product vision

**AIRLOCK** is a privacy-first observability platform with two tiers:

1. **Tier 1, the guard (inside each customer):** collects telemetry, keeps raw data local, and sends only signed, allow-listed metadata.
2. **Tier 2, head office (multi-customer SaaS):** turns that metadata into health states, explained incidents and human-approved fixes.

The UI has to prove one sentence to judges, live: ***"Show us exactly what your collector sends, prove private data stays local, and show how your system turns that into a useful recommendation."***

### Core tenets
* **Mission-control aesthetic:**
  - dense telemetry on dark aerospace surfaces (`#080A10`, `#0B0E14`)
  - hairline borders (`white/[0.08]`)
  - restrained glass panels
  - status colours that carry meaning
* **Proof over polish:** every privacy claim has a visible proof on screen: the egress JSON, receipts, the leak counter, reconciliation numbers.
* **Hybrid 2D/3D:** HTML/SVG panels + one WebGL hero scene, the **Live Fleet Bridge**. It shows our 4 real laptops, and every payload crosses the trust boundary as a particle in real time.
* **Live first, never fake silently:** data comes from the head office WebSocket. If the backend is unreachable, the UI may switch to the built-in simulator, but **always** shows a full-width `SIMULATED DATA` banner.
* **Instant perception of risk:** a judge should understand fleet health from across the room, without reading a chart.

---

## 2. Visual design system and tokens

### 2.1 Colour palette

```
┌────────────────────────────────────────────────────────────────────────┐
│  SURFACES                                                              │
│  ├── Canvas background:            #080A10 / #0B0E14                   │
│  ├── Panel (elevated):             #0C1017 (95 % opacity)              │
│  ├── Component base:               #1A1C23                             │
│  ├── Card / modal:                 #252830                             │
│  └── Hairline borders:             #3A3F4C / rgba(255,255,255,0.08)    │
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│  HEALTH STATES (PRD #12), always paired with a text label              │
│  ├── EXCELLENT:   #10B981 (emerald)                                    │
│  ├── GOOD:        #06B6D4 (cyan)                                       │
│  ├── FAIR:        #F59E0B (amber)                                      │
│  ├── POOR:        #EF4444 (crimson)                                    │
│  └── OFFLINE / STALE: #64748B (slate), dimmed                          │
└────────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────────┐
│  MEANING COLOURS                                                       │
│  ├── Privacy / proof (egress, canaries, receipts, signed payloads):    │
│  │                     #A855F7 (purple)                                │
│  ├── Local-only accent (shop screen, raw data that never leaves):      │
│  │                     #A3E635 (lime)                                  │
│  ├── Severity critical #EF4444 · high #F97316 · medium #F59E0B         │
│  │   · low #06B6D4 · info #94A3B8                                      │
│  └── Interactive accent (focus, selected tab, links): #38BDF8 (sky)   │
└────────────────────────────────────────────────────────────────────────┘
```

**Rules:**
- **Emerald, cyan, amber and crimson mean health and severity only.** Never use them for decoration.
- **Purple always means "privacy proof".** **Lime always means "local, inside the customer".** Judges learn these two colours in the first minute.
- **One accent per panel.** Everything else stays slate and white.

#### Tailwind configuration extension (`tailwind.config.js`)
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        airlock: {
          canvas: '#0B0E14',
          deep: '#080A10',
          panel: '#0C1017',
          base: '#1A1C23',
          card: '#252830',
          border: '#3A3F4C',
          text: '#D1D5DB',
          muted: '#94A3B8',
          faint: '#64748B',
          excellent: '#10B981',
          good: '#06B6D4',
          fair: '#F59E0B',
          poor: '#EF4444',
          offline: '#64748B',
          privacy: '#A855F7',
          local: '#A3E635',
          accent: '#38BDF8',
          high: '#F97316',
        }
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'Menlo', 'monospace'],
      }
    },
  },
  plugins: [],
}
```

### 2.2 Typography scale

Two families: **Inter** for interface chrome, and **JetBrains Mono** for every number, ID, hash and payload, so live values never jitter. Sizes are raised from THERVO for projector legibility; **nothing below 11px**.

| Element | Font | Size | Weight | Tracking | Colour |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Brand wordmark** "AIRLOCK" | JetBrains Mono | 24px | 900 | `tracking-widest` | `#FFFFFF` |
| **Section header** | JetBrains Mono | 16px | 700 | `tracking-wide` | `#FFFFFF` |
| **Metric large value** | JetBrains Mono | 28–32px | 800 | `tracking-tight` | Health or meaning colour |
| **Card header** | Inter | 13px | 600 | normal | `#E2E8F0` |
| **Body** | Inter | 14px | 400 | normal | `#94A3B8` |
| **Eyebrow / data label** | JetBrains Mono | 11px | 700 | `tracking-widest`, UPPERCASE | `#64748B` |
| **Status badge** | JetBrains Mono | 11px | 700 | `tracking-wider`, UPPERCASE | State colour on a 10 % tint |
| **Payload / JSON / hashes** | JetBrains Mono | 12–13px | 400 | normal | `#D1D5DB`, keys `#94A3B8` |

**No icons anywhere.** No logo mark, no icon library. Status is shown with mono text badges such as `EXCELLENT`, `FAIR`, `POOR`, `OFFLINE`, `✓ MATCH`, `✕ MISMATCH`. Plain text characters (✓ ✕ → ·) are allowed inside labels.

### 2.3 Panel treatment (toned down for projectors)
```css
.hud-panel {
  background-color: rgba(12, 16, 23, 0.95);
  backdrop-filter: blur(8px);            /* THERVO used 12px; 8px is lighter on older laptops */
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 10px 20px -8px rgba(0, 0, 0, 0.55);
  border-radius: 0.75rem;                /* 12px */
}
.hud-panel--local {                      /* shop screen panels */
  border-color: rgba(163, 230, 53, 0.35);
}
.hud-panel--proof {                      /* egress / receipts / leak badge */
  border-color: rgba(168, 85, 247, 0.35);
}
```
If the frame rate drops below 50 fps on the LOQ, set `backdrop-filter: none`. The look survives without blur.

### 2.4 Status presentation rules
- **Health is never shown by colour alone:** always colour + mono label (+ a reason line where space allows), e.g. `FAIR · latency 240 ms`.
- **Stale data never shows the last good value.** It shows `OFFLINE · no data for 14 s` in slate (PRD #12).
- **Confidence** shows as a percentage with the formula on hover: 0.4 + 0.15 × agreeing signals + 0.1 if a rule matched, capped at 0.95 (§AIOps design).
- **Timestamps** default to UTC with a `Z` suffix and switch with the time-zone control (PRD #30).

---

## 3. Application shell and routing

### 3.1 Viewport layout (head office, 1920×1080)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ TOPNAV (h-14): [AIRLOCK wordmark + live pulse dot] [Tabs] [Tenant switch] [TZ: UTC|MINE|SHOP] │
│                [UTC clock] [Mode badge: LIVE | SIMULATED] [Copilot]                         │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ SIMULATED DATA banner (only when the fallback is active, full width, amber)                  │
├──────────────────────────────────────────────────────────────────────────────────────────────┤
│ MAIN CONTENT (flex-1, overflow-auto)                                                         │
│                                                                                              │
│  • /overview   → KPI strip, fleet health grid, live charts, incident feed, mini Fleet Bridge │
│  • /live-map   → Fullscreen 3D Live Fleet Bridge (4 laptops + phones, trust boundary)        │
│  • /fleet      → Guard table + Guard Inspector drawer                                        │
│  • /incidents  → Incident list + incident detail (explanations, actions, reveal)             │
│  • /security   → Login attacks, honeypot hits, odd-hour logins, risk levels                  │
│  • /privacy    → Leak badge, canary counter, receipt-log checkpoints, reconciliation         │
│  • /actions    → Pending approvals, dry-run results, audit log, rollback timers              │
│  • /history    → Health transitions over time, UTC timeline                                  │
│  • /settings   → Health thresholds per tenant                                                │
│                                                                                              │
│                                                    ┌─────────────────────────────┐           │
│                                                    │ AI COPILOT DRAWER (right)   │           │
│                                                    │ opens from any page         │           │
│                                                    └─────────────────────────────┘           │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```
There is **no bottom dock.** Chaos controls live only on the chaos console (laptop 4).

### 3.2 Separate surfaces (same codebase, separate Vite entry points)

| Entry | Served from | Path prefix | Look |
| :--- | :--- | :--- | :--- |
| `hq` | LOQ (`hq-api` :8000) | `/` | Default theme, projector |
| `shop` | Each guard (:9000), built bundle served by the guard | `/shop` | **Lime local accent**, full-width banner `LOCAL · RAW DATA STAYS ON THIS MACHINE` |
| `chaos` | Laptop 4 (:5173) | `/chaos` | Default theme, big buttons |
| `phone` | LOQ | `/m/join`, `/m/approve`, `/m/raw`, `/m/smart` | Mobile-first (375px), same tokens |

### 3.3 Route definitions (`src/apps/hq/App.tsx`)

```tsx
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopNav } from '../../features/TopNav';
import { SimulatedBanner } from '../../features/SimulatedBanner';
import { CopilotDrawer } from '../../features/CopilotDrawer';
import { OverviewTab } from './pages/OverviewTab';
import { LiveMapTab } from './pages/LiveMapTab';
import { FleetTab } from './pages/FleetTab';
import { IncidentsTab } from './pages/IncidentsTab';
import { SecurityTab } from './pages/SecurityTab';
import { PrivacyTab } from './pages/PrivacyTab';
import { ActionsTab } from './pages/ActionsTab';
import { HistoryTab } from './pages/HistoryTab';
import { SettingsTab } from './pages/SettingsTab';
import { useLiveSocket } from '../../services/liveSocket';

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 1000 } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AppContent />
      </Router>
    </QueryClientProvider>
  );
}

function AppContent() {
  useLiveSocket(); // one WebSocket for the whole app, feeds the live store
  return (
    <div className="flex h-screen flex-col bg-[#0B0E14] text-white overflow-hidden font-sans">
      <TopNav />
      <SimulatedBanner />
      <main className="flex-1 overflow-auto relative">
        <Routes>
          <Route path="/overview" element={<OverviewTab />} />
          <Route path="/live-map" element={<LiveMapTab />} />
          <Route path="/fleet" element={<FleetTab />} />
          <Route path="/incidents" element={<IncidentsTab />} />
          <Route path="/security" element={<SecurityTab />} />
          <Route path="/privacy" element={<PrivacyTab />} />
          <Route path="/actions" element={<ActionsTab />} />
          <Route path="/history" element={<HistoryTab />} />
          <Route path="/settings" element={<SettingsTab />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </main>
      <CopilotDrawer />
    </div>
  );
}
```

---

## 4. 3D WebGL: the Live Fleet Bridge

Adapted from THERVO's Dual-Node Edge Hardware Bridge. The same laptop model (`/models/laptop.glb`) now represents **our real machines**, and the GNN heat stream becomes **real payloads crossing the trust boundary**. Every particle is driven by a real WebSocket event, never by a timer.

### 4.1 Scene layout (`three/FleetBridgeScene`)

```
        TIER 1 · CUSTOMER ENVIRONMENTS                 │ TRUST │        TIER 2 · HEAD OFFICE
                                                       │ GATE  │
   ┌──────────────┐                                    │       │
   │ SHOP A · ACME│  Ryzen · India ───────particles────┼──►────┼───┐
   │ raw-data orb │  (stays local)                     │       │   │
   └──────────────┘                                    │       │   │     ┌──────────────────┐
   ┌──────────────┐                                    │       │   ├───► │ HEAD OFFICE · LOQ│
   │SHOP B·GLOBEX │  Linux · Europe ──────particles────┼──►────┼───┤     │ (larger, raised) │
   │ raw-data orb │                                    │       │   │     └──────────────────┘
   └──────────────┘                                    │       │   │
   ┌──────────────┐                                    │       │   │
   │ORGANIZER·CNTSO│ Laptop 4 · India ─────particles───┼──►────┼───┘
   └──────────────┘                                    │       │
   [ phones · GUESTS: small slabs appear as judges join via QR ]

   ◄──────── thin receipt pulses travel back right → left ────────
```

#### Coordinates (world units)
| Object | Position | Notes |
| :--- | :--- | :--- |
| Shop A (Acme) laptop | `[-9, 0, -5]` | on a pedestal ring, lime base glow (local) |
| Shop B (Globex) laptop | `[-9, 0, 0]` | same |
| Organizer (Contoso) laptop | `[-9, 0, 5]` | same |
| Phones (Guests) | arc around `[-13, 0, 0]` | up to 30 small slabs, spawn on `/m/join` heartbeat |
| **Trust gate** | plane at `x = -1`, size 14 × 6 | translucent purple glass, hairline frame, label `TRUST BOUNDARY` |
| Head office (LOQ) laptop | `[6, 1.2, 0]` | scale 1.4, raised pedestal |

All 3 shop laptops render with the same cloned GLTF (THERVO's cloning pattern), each with its own material.

### 4.2 Layers (toggleable from a small layer bar)

1. **`HealthLayer`:** laptop emissive colour = health state (§2.1).
   - Emissive intensity 0.2 normally, 0.8 for `POOR`.
   - `OFFLINE`: the material desaturates to slate and the screen goes dark.
   - A pulsing point light only on `POOR`.
2. **`PayloadLayer`** (the hero):
   - One particle per `payload_receipt` WebSocket event, travelling along a CatmullRom curve from the guard through the gate to head office in **1.2 s**.
   - Colour by outcome:
     - `stored` → purple (privacy) that flashes emerald on arrival
     - `duplicate` → slate, fades out at the gate ("blocked duplicate")
     - `rejected` (bad signature, schema, policy, canary) → crimson burst **at the gate**, with a floating label of the reason (`REJECTED · SIGNATURE`)
   - Instanced mesh, max 300 live particles.
3. **`ReceiptLayer`:** a thin purple pulse travels back from head office to the guard for each receipt. A guard whose last receipt hash didn't match shows a `✕ MISMATCH` badge.
4. **`BufferLayer`** (outage story, PRD #15):
   - When a guard can't reach head office, unsent payloads stack as a growing amber ring of particles orbiting its laptop (count = `buffer_depth`).
   - On reconnect the ring unwinds and streams through the gate oldest-first.
   - This is the visual for "zero loss, zero duplicates".
5. **`LocalDataLayer`:** each shop laptop has a small lime "raw data" orb that orbits **only its own laptop** and never crosses the gate. Label `RAW · LOCAL ONLY`. This is the visual for "private data stays local".
6. **`StatsLayer`:** Drei `<Html>` badges pinned above each laptop:
   - tenant + region
   - health label
   - buffer depth
   - last seen
   - payloads/min
   - receipt `✓ MATCH` / `✕ MISMATCH`

### 4.3 Camera presets (`three/Camera/index.tsx`)
```typescript
export type CameraPreset = 'OVERVIEW' | 'GATE' | 'SHOP_A' | 'HEAD_OFFICE';

export const CAMERA_PRESETS: Record<CameraPreset, { position: [number, number, number]; target: [number, number, number] }> = {
  OVERVIEW:    { position: [0, 14, 20],  target: [-1, 0, 0] },
  GATE:        { position: [-1, 3, 9],   target: [-1, 1.5, 0] },
  SHOP_A:      { position: [-12, 4, -1], target: [-9, 0.8, -5] },
  HEAD_OFFICE: { position: [10, 5, 6],   target: [6, 1.2, 0] },
};
```
Presets animate with a 0.8 s ease. The camera auto-switches to `GATE` for 4 s when a payload is rejected, then returns.

### 4.4 Interactions
- **Click a laptop** → opens the **Guard Inspector** drawer (THERVO's rack inspector, renamed). It shows:
  - guard ID, tenant, region, version
  - guard CPU and memory
  - buffer depth, config OK, policy hash
  - last seen
  - last 5 payload IDs with ✓/✕
- **Hover a particle** → tooltip with `payload_id`, `seq`, status, latency (event time → arrival).
- **Mini version** on `/overview`: the same scene at 360px height, `OVERVIEW` preset, no StatsLayer.

### 4.5 Performance and fallback
- Instanced meshes for particles. Dispose geometries and materials on unmount (THERVO checklist).
- Target 60 fps on the LOQ (RTX 4060).
- If WebGL fails, render a **2D SVG fallback** with the same layout and the same events (dots on paths). The demo must never show a blank canvas.

---

## 5. Pages and components

### 5.1 `/overview`

**KPI strip** (mono values):
- `HEALTHY GUARDS 2/3`
- `NEEDS ATTENTION 1`
- `OPEN INCIDENTS 1`
- `LEAKS DETECTED 0 / 1,240 CANARIES` (purple)
- `NOISE CUT 47 → 3`
- `P95 DELIVERY 3.1 s`

**Panels:**
- **Fleet health grid:** one tile per guard with its state label + reason.
- **Live charts** (Recharts):
  - `Area` for the normal band (baseline ± spread)
  - `Line` for the value
  - red dot on anomaly points
  - metrics: CPU, memory, latency, packet loss, net out
- **Incident feed:** the 5 most recent.
- **Mini Fleet Bridge.**
- **Latency meter** (PRD #19): event time → render time, p50/p95, plus alert-delay and offline-delay stamps.

### 5.2 `/fleet`
- **Guard table:**

| Column | Notes |
| :--- | :--- |
| Guard | |
| Tenant | |
| Region | |
| State | |
| Last seen | |
| Version | |
| CPU % | |
| Mem MB | |
| Buffer | |
| Config | |
| Policy hash | first 8 characters |

  Phones (tenant Guests) are listed in a collapsible group.
- Clicking a row → Guard Inspector drawer (§4.4).

### 5.3 `/incidents`

**Incident card** (built from the incident object, PRD §AIOps design › Incident object):
- **Header:** title, severity badge, confidence %, started (time-zone aware), affected parts.
- **Contribution bars:** one bar per signal, labelled `cpu_pct 96 vs 21 · z 7.4 · 40 %`. Each bar is clickable and opens the matching chart.
- **Reasoning path:** a horizontal UTC timeline of steps.
- **"What changed just before"** line (PRD #27).
- **Counterfactual** line in muted italics.
- **Recommendation box:** action, why, risk, reversible, rollback, with buttons `DRY RUN` → `SEND FOR APPROVAL`.
- **`REVEAL`** button on pseudonyms (PRD #28). It creates a reveal request; the real value is **never** shown here.
- **Noise header:** `RAW ALERTS 47 → INCIDENTS 3 · 94 % NOISE CUT` and `FLAPS PREVENTED 12`.
- Scheduled-job suppressions show as a muted row: `SUPPRESSED · scheduled job (every ~60 s)`.

### 5.4 `/security`
- Login-burst cards (count, window, attacker pseudonym, risk).
- Honeypot hits (always critical).
- Odd-hour logins with shop-local time.
- **Never usernames or IPs.** Only pseudonyms like `src-9c2e`.

### 5.5 `/privacy` (proof page, purple accent)
- **Leak badge:** `CANARIES PLANTED 1,240 · LEAKS DETECTED 0`.
- **Receipt-log checkpoints** per guard: `UP TO SEQ 1042 · ROOT 9c1e… · ✓ MATCH`.
- **Reconciliation table:** sent / received / duplicates / gaps per guard (PRD #16).
- **Allow-list viewer:** the fields that may leave, straight from the contract.
- **Last received payload** as pretty JSON. The judge can compare it with the shop screen's egress panel.

### 5.6 `/actions`
- **Pending approvals:**
  - dry-run result block
  - approver name
  - rollback timer countdown (120 s)
- **Audit log table (UTC):**

| Column |
| :--- |
| Time |
| Tenant |
| Action |
| Target |
| Requested by |
| Approved by |
| Result |
| Rolled back? |

### 5.7 `/history`
- A state-transition timeline per guard: old → new, reasons, UTC time.
- The time-zone switch shows India and Europe events on one timeline. **Order never changes, only labels.**

### 5.8 `/settings`
- Per-tenant health thresholds (the PRD's health table defaults), editable, with "reset to defaults".

### 5.9 Copilot drawer (THERVO's AI Operations Copilot, reused)
- Right-side drawer, 420px wide, opens from the TopNav button or from any incident.
- Head-office AI answers include **evidence tags** (`ev-2 · cpu_pct 96`) that open the matching chart.
- Answers that refuse show in a purple proof style: `RAW DATA STAYS IN THE CUSTOMER'S ENVIRONMENT`.

### 5.10 Shop screen (`shop` entry, lime local accent)
- **Banner:** `LOCAL · RAW DATA STAYS ON THIS MACHINE · ACME (INDIA)`.
- **Raw log stream** with secrets **highlighted in crimson** (visible here only).
- **Egress proof panel** (mandatory, PRD #7): each payload's exact JSON, SHA-256, seq, and receipt `✓ MATCH` / `✕ MISMATCH`, newest first.
- **Status:** buffer depth, retention countdown (24 h), canaries planted, receipt-log checkpoint.
- **Reveal requests:** an approve/reject card for each head-office request.
- **Shop AI drawer** (same component as the copilot, local endpoint).

### 5.11 Chaos console (`chaos` entry)
- **Target selector:** Shop A / Shop B / Organizer.
- **Big button grid** (2 rows):
  - CPU spike, latency, brute force, pause India region
  - replay + shuffle, kill chain, backup job, restart app
- **Tamper menu:** edited payload, rogue guard, policy edit, ledger delete, clock skew.
- **Try-to-leak box:** a large text area with the placeholder `Type any password or key. If it reaches head office, you win.`
- **Scenario log** with UTC timestamps.

### 5.12 Phone pages (`phone` entry, mobile-first)
- **`/m/join`:** joins as a collector; sends heartbeat + latency every 2 s; shows `CONNECTED · host-xxxx`.
- **`/m/approve`:** incident summary → `DRY RUN` → `APPROVE` / `REJECT` with a name field → rollback countdown.
- **`/m/raw`:** vibrates on every raw alert (noisy).
- **`/m/smart`:** incidents only (clean).

---

## 6. State management and data architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ UI state (Zustand: useUiStore)                                         │
│ • selectedGuardId · activeTenant · tzMode: 'UTC' | 'VIEWER' | 'SHOP'   │
│ • cameraPreset · activeLayers · copilotOpen · inspectorOpen            │
└───────────────────────────────────┬────────────────────────────────────┘
┌───────────────────────────────────▼────────────────────────────────────┐
│ Live state (Zustand: useLiveStore), fed by ONE WebSocket               │
│ • ring buffers per guard and metric (last 10 min)                      │
│ • guards, health, incidents, receipts, checkpoints, actions            │
│ • mode: 'LIVE' | 'SIMULATED'                                           │
└───────────────────────────────────┬────────────────────────────────────┘
┌───────────────────────────────────▼────────────────────────────────────┐
│ Request/response (TanStack Query): history, settings, audit log,       │
│ reconciliation, copilot chat, dry run, approve, reveal requests        │
└────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Zustand UI store (`stores/uiStore.ts`)
```typescript
import { create } from 'zustand';

type TzMode = 'UTC' | 'VIEWER' | 'SHOP';
type CameraPreset = 'OVERVIEW' | 'GATE' | 'SHOP_A' | 'HEAD_OFFICE';
type Layer = 'HEALTH' | 'PAYLOAD' | 'RECEIPT' | 'BUFFER' | 'LOCAL' | 'STATS';

interface UiState {
  selectedGuardId: string | null;
  activeTenant: string | 'ALL';
  tzMode: TzMode;
  cameraPreset: CameraPreset;
  activeLayers: Layer[];
  copilotOpen: boolean;
  setSelectedGuardId: (id: string | null) => void;
  setActiveTenant: (t: string | 'ALL') => void;
  setTzMode: (m: TzMode) => void;
  setCameraPreset: (p: CameraPreset) => void;
  toggleLayer: (l: Layer) => void;
  setCopilotOpen: (open: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  selectedGuardId: null,
  activeTenant: 'ALL',
  tzMode: 'UTC',
  cameraPreset: 'OVERVIEW',
  activeLayers: ['HEALTH', 'PAYLOAD', 'RECEIPT', 'BUFFER', 'LOCAL', 'STATS'],
  copilotOpen: false,
  setSelectedGuardId: (id) => set({ selectedGuardId: id }),
  setActiveTenant: (t) => set({ activeTenant: t }),
  setTzMode: (m) => set({ tzMode: m }),
  setCameraPreset: (p) => set({ cameraPreset: p }),
  toggleLayer: (l) => set((s) => ({
    activeLayers: s.activeLayers.includes(l) ? s.activeLayers.filter((x) => x !== l) : [...s.activeLayers, l],
  })),
  setCopilotOpen: (open) => set({ copilotOpen: open }),
}));
```

### 6.2 Demo fallback (replaces THERVO's embedded physics simulator)
- `services/demoFeed.ts` replays the JSON files in `contracts/examples/` as WebSocket-shaped messages every 2 s.
- It switches on **only** when the WebSocket has been down for 10 s **and** the operator presses `USE DEMO FEED` in the TopNav. It's never automatic.
- While active:
  - the mode badge reads `SIMULATED`
  - the amber full-width banner reads `SIMULATED DATA · NOT FROM LIVE GUARDS`
  - the Fleet Bridge particles turn slate

---

## 7. Data contracts the UI consumes

The exact names and shapes live in **`contracts/`**, written by the team at H0–H2 (payload schema by Hajira, API + WebSocket messages by Sahiti, incident object by Adithya). This section lists **what the UI needs**. If `contracts/` differs, `contracts/` wins.

### 7.1 WebSocket messages (from `hq-api` :8000)
| Message | Used by | Fields the UI needs |
| :--- | :--- | :--- |
| `metrics` | charts, KPI strip | `tenant_id`, `source`, `name`, `avg`, `max`, `baseline`, `spread`, `window.start` (UTC), `source_tz` |
| `health_change` | fleet grid, history, 3D HealthLayer | `source`/`guard_id`, `old`, `new`, `reasons[]`, `at` (UTC) |
| `payload_receipt` | 3D PayloadLayer, latency meter | `guard_id`, `payload_id`, `seq`, `status` (`stored`/`duplicate`/`rejected`), `reason`, `event_time`, `received_at` |
| `guard_heartbeat` | fleet, inspector, 3D StatsLayer | `guard_id`, `tenant_id`, `region`, `guard_version`, `guard_cpu_pct`, `guard_mem_mb`, `buffer_depth`, `config_ok`, `canaries_planted`, `secrets_redacted`, `last_seen` |
| `incident_upsert` | incidents, copilot, phones | the incident object (PRD §AIOps design) |
| `checkpoint` | privacy page, shop screen | `guard_id`, `up_to_seq`, `root`, `match` |
| `action_update` | actions page, phones | `action_id`, `state` (proposed / dry_run / approved / executed / rolled_back), `result`, `approved_by`, `at` |
| `reveal_request` | incidents, shop screen | `request_id`, `pseudonym`, `requested_by`, `reason`, `decision` |
| `counters` | KPI strip, noise header | `raw_alerts`, `incidents`, `flaps_prevented`, `leaks_detected`, `duplicates_blocked` |

### 7.2 Shop screen (from the guard, :9000, local only)
Raw logs, the egress ledger (exact JSON, hash, seq, receipt status), buffer depth, retention countdown, reveal requests, and the shop AI chat. These endpoints are **never** called from the head-office bundle.

### 7.3 Example payload (from PRD §Architecture › Payload schema v1)
```json
{
  "schema": "airlock.v1",
  "payload_id": "0193f2c1-7b5e-7c3a-9f10-4be2a1d0c9e1",
  "tenant_id": "acme",
  "guard_id": "guard-acme-01",
  "seq": 1042,
  "window": {"start": "2026-11-21T04:12:04Z", "end": "2026-11-21T04:12:06Z", "source_tz": "Asia/Kolkata"},
  "metrics": [{"name": "cpu_pct", "source": "host-7f3a", "avg": 34.2, "max": 51.0}],
  "events": [{"category": "auth_failure_burst", "severity": "high", "source": "host-7f3a", "actor": "src-9c2e", "count": 50, "window_s": 60}],
  "health": {"guard_version": "0.3.1", "buffer_depth": 0, "canaries_planted": 12, "secrets_redacted": 3}
}
```

---

## 8. Implementation guide

### 8.1 Dependencies
```bash
# Core framework and routing
npm install react@^19.0.0 react-dom@^19.0.0 react-router-dom@^7.0.0

# 3D
npm install three @types/three @react-three/fiber @react-three/drei

# State, data fetching, charts, utilities (no icon library)
npm install zustand @tanstack/react-query recharts clsx tailwind-merge

# Styling and build
npm install -D vite tailwindcss postcss autoprefixer typescript @types/node
```

### 8.2 File tree
```
web/
├── index.html · shop.html · chaos.html · phone.html   # one Vite entry each
├── public/models/laptop.glb                           # reused from THERVO
└── src/
    ├── apps/
    │   ├── hq/      App.tsx + pages/ (Overview, LiveMap, Fleet, Incidents, Security,
    │   │                              Privacy, Actions, History, Settings)
    │   ├── shop/    App.tsx (banner, raw logs, egress proof, reveal, shop AI)
    │   ├── chaos/   App.tsx (target selector, button grid, tamper menu, leak box, log)
    │   └── phone/   App.tsx (join, approve, raw, smart)
    ├── components/
    │   ├── StatusBadge.tsx          # colour + mono label, never colour alone
    │   ├── MetricChart.tsx          # Recharts band + line + anomaly dots
    │   ├── IncidentCard.tsx         # contributions, reasoning, counterfactual, action
    │   ├── EgressProofPanel.tsx     # exact JSON, hash, receipt match
    │   ├── ReconciliationTable.tsx
    │   ├── AuditLogTable.tsx
    │   └── TimeText.tsx             # renders any UTC time per tzMode
    ├── features/
    │   ├── TopNav.tsx               # wordmark + pulse, tabs, tenant, TZ, clock, mode
    │   ├── SimulatedBanner.tsx
    │   ├── CopilotDrawer.tsx        # reused for head-office and shop AI
    │   ├── GuardInspector.tsx       # THERVO RackInspector, renamed
    │   ├── KpiStrip.tsx
    │   └── LatencyMeter.tsx
    ├── services/
    │   ├── apiClient.ts             # fetch wrapper, base URL from env
    │   ├── liveSocket.ts            # single WebSocket → useLiveStore
    │   ├── demoFeed.ts              # replays contracts/examples (SIMULATED only)
    │   └── queries.ts               # TanStack queries and mutations
    ├── stores/
    │   ├── uiStore.ts
    │   └── liveStore.ts
    └── three/
        ├── FleetBridgeScene/index.tsx   # canvas, lights, pedestals, trust gate
        ├── Camera/index.tsx             # presets (§4.3)
        ├── Layers/                      # Health, Payload, Receipt, Buffer, LocalData, Stats
        └── Fallback2D.tsx               # SVG version when WebGL fails
```

### 8.3 Blueprint: the live socket (`services/liveSocket.ts`)
```typescript
import { useEffect } from 'react';
import { useLiveStore } from '../stores/liveStore';

const WS_URL = import.meta.env.VITE_HQ_WS_URL; // e.g. wss://<LOQ>:8000/ws

export function useLiveSocket() {
  const apply = useLiveStore((s) => s.apply);
  const setConnected = useLiveStore((s) => s.setConnected);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 1000;
    let stopped = false;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => { retry = 1000; setConnected(true); };
      ws.onmessage = (e) => apply(JSON.parse(e.data)); // routes by message type (§7.1)
      ws.onclose = () => {
        setConnected(false);
        if (!stopped) setTimeout(connect, retry);
        retry = Math.min(retry * 2, 10000); // same 10 s ceiling as the guard's backoff
      };
    };
    connect();
    return () => { stopped = true; ws?.close(); };
  }, [apply, setConnected]);
}
```

---

## 9. Verification checklist

Before the round 3 demo (H15) and again before the final:
* [ ] **No jitter:** every live number, ID and hash uses `font-mono`.
* [ ] **Never colour alone:** every state and severity has a text label.
* [ ] **No icons** anywhere (no icon library installed).
* [ ] **Privacy:** the head-office bundle never renders a field that isn't in `contracts/` (no raw text, usernames, IPs or hostnames). The shop bundle is the only place raw data appears.
* [ ] **Live, not fake:** particles in the Fleet Bridge come only from `payload_receipt` events. With the guards stopped, the bridge goes quiet and the buffer ring grows.
* [ ] **SIMULATED is obvious:** the banner + mode badge + slate particles whenever `demoFeed` is on.
* [ ] **WebGL safe:** geometries and materials are disposed on unmount; the 2D fallback renders if WebGL fails.
* [ ] **Projector legibility:** 1920×1080, nothing below 11px, readable from 5 m.
* [ ] **Phones:** all 4 phone pages usable at 375px width.
* [ ] **Timing visible:** the latency meter shows p95 event → render under 10 s; alerts appear within 15 s of injection; offline within 60 s.
* [ ] **Time zones:** switching the time-zone mode changes labels but never the order of events.
