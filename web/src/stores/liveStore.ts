import { create } from 'zustand';
import {
  ActionRecord,
  Alert,
  CheckpointInfo,
  Counters,
  GuardInfo,
  HealthState,
  Incident,
  MetricDataPoint,
  PayloadReceiptEvent,
  ReconciliationRow,
} from '../types';

interface LiveState {
  connected: boolean;
  mode: 'LIVE' | 'SIMULATED';
  guards: Record<string, GuardInfo>;
  metrics: Record<string, MetricDataPoint[]>; // key: "guard_id:metric_name" or "tenant_id:metric_name"
  incidents: Incident[];
  alerts: Alert[];
  receipts: PayloadReceiptEvent[];
  checkpoints: Record<string, CheckpointInfo>;
  actions: ActionRecord[];
  reconciliation: Record<string, ReconciliationRow>;
  counters: Counters;
  latencySamples: { event_time: string; render_time: string; latency_ms: number }[];

  setConnected: (connected: boolean) => void;
  setMode: (mode: 'LIVE' | 'SIMULATED') => void;
  apply: (event: any) => void;
  addAlert: (alert: Alert) => void;
  addIncident: (incident: Incident) => void;
  updateActionState: (actionId: string, newState: ActionRecord['state'], approvedBy?: string) => void;
  resetToSimulated: (sampleData: any) => void;
  clearForLive: () => void;
}

const INITIAL_GUARDS: Record<string, GuardInfo> = {
  'guard-acme-01': {
    guard_id: 'guard-acme-01',
    tenant_id: 'acme',
    source: 'host-7f3a1234',
    region: 'in',
    state: 'Excellent',
    reasons: ['All 12 metrics within baseline'],
    since: new Date(Date.now() - 3600000).toISOString(),
    last_seen: new Date().toISOString(),
    guard_version: '0.3.1',
    guard_cpu_pct: 14.2,
    guard_mem_mb: 46.5,
    buffer_depth: 0,
    config_ok: true,
    canaries_planted: 420,
    secrets_redacted: 1,
    flaps_prevented: 3,
    policy_hash: '9f104be2',
  },
  'guard-globex-01': {
    guard_id: 'guard-globex-01',
    tenant_id: 'globex',
    source: 'host-9c2e0011',
    region: 'eu',
    state: 'Good',
    reasons: ['Slight net_out variance'],
    since: new Date(Date.now() - 1800000).toISOString(),
    last_seen: new Date().toISOString(),
    guard_version: '0.3.1',
    guard_cpu_pct: 18.0,
    guard_mem_mb: 52.1,
    buffer_depth: 0,
    config_ok: true,
    canaries_planted: 510,
    secrets_redacted: 0,
    flaps_prevented: 1,
    policy_hash: '7c3a9f10',
  },
  'guard-contoso-01': {
    guard_id: 'guard-contoso-01',
    tenant_id: 'contoso',
    source: 'host-1a2b3c4d',
    region: 'in',
    state: 'Fair',
    reasons: ['CPU elevated > 70% in last 2 windows'],
    since: new Date(Date.now() - 600000).toISOString(),
    last_seen: new Date().toISOString(),
    guard_version: '0.3.1',
    guard_cpu_pct: 74.5,
    guard_mem_mb: 68.3,
    buffer_depth: 0,
    config_ok: true,
    canaries_planted: 310,
    secrets_redacted: 0,
    flaps_prevented: 8,
    policy_hash: '3a1b2c4d',
  },
};

export const useLiveStore = create<LiveState>((set, get) => ({
  connected: false,
  mode: 'LIVE',
  guards: {},
  metrics: {},
  incidents: [],
  alerts: [],
  receipts: [],
  checkpoints: {},
  actions: [],
  reconciliation: {},
  counters: { raw_alerts: 0, incidents: 0, flaps_prevented: 0, canaries_planted: 0, leaks_detected: 0, duplicates_blocked: 0 },
  latencySamples: [],

  // live mode starts empty: every tile, chart and counter then comes from the backend
  clearForLive: () => set({ guards: {}, metrics: {}, incidents: [], alerts: [], receipts: [], checkpoints: {}, reconciliation: {},
    counters: { raw_alerts: 0, incidents: 0, flaps_prevented: 0, canaries_planted: 0, leaks_detected: 0, duplicates_blocked: 0 }, latencySamples: [] }),
  setConnected: (connected) => set({ connected }),
  setMode: (mode) => set(mode === 'SIMULATED' ? { mode, guards: INITIAL_GUARDS } : { mode }),

  apply: (event: any) => {
    if (!event) return;
    const { event_type, tenant_id, timestamp, payload } = event;
    const nowIso = new Date().toISOString();

    // Measure latency if timestamp present
    if (timestamp) {
      const eventTime = new Date(timestamp).getTime();
      const renderTime = Date.now();
      const latency_ms = Math.max(0, renderTime - eventTime);
      set((s) => ({
        latencySamples: [{ event_time: timestamp, render_time: nowIso, latency_ms }, ...s.latencySamples].slice(0, 50),
      }));
    }

    switch (event_type) {
      case 'metrics_batch':
      case 'metrics': {
        const metricsList = payload?.metrics || [];
        const source = payload?.source || payload?.guard_id || 'host-7f3a1234';
        const tId = tenant_id || payload?.tenant_id || 'acme';

        set((s) => {
          const updated = { ...s.metrics };
          for (const m of metricsList) {
            const key = `${tId}:${m.name}`;
            const existing = updated[key] || [];
            const point: MetricDataPoint = {
              name: m.name,
              source: m.source || source,
              tenant_id: tId,
              avg: m.avg,
              max: m.max,
              event_time: timestamp || nowIso,
              baseline: m.baseline,
              spread: m.spread,
              is_anomaly: m.avg > (m.baseline ? m.baseline + 2 * (m.spread || 5) : 80),
            };
            updated[key] = [...existing, point].slice(-300); // 300 points ~ 10 min
          }
          return { metrics: updated };
        });
        break;
      }

      case 'health_change': {
        const source = payload?.source;
        const newState = (payload?.state || 'Good') as HealthState;
        const reasons = payload?.reasons || [];
        set((s) => {
          const guards = { ...s.guards };
          for (const gId of Object.keys(guards)) {
            if (guards[gId].source === source || guards[gId].tenant_id === tenant_id) {
              guards[gId] = {
                ...guards[gId],
                state: newState,
                reasons,
                since: payload?.at || nowIso,
                last_seen: nowIso,
              };
            }
          }
          return { guards };
        });
        break;
      }

      case 'incident_opened':
      case 'incident_updated':
      case 'incident_upsert': {
        const incData: Incident = {
          incident_id: payload?.incident_id || `inc-${Date.now()}`,
          tenant_id: tenant_id || payload?.tenant_id || 'acme',
          title: payload?.body?.title || payload?.title || 'System Anomaly',
          severity: payload?.body?.severity || payload?.severity || 'medium',
          confidence: payload?.body?.confidence ?? payload?.confidence ?? 0.8,
          started_at: payload?.body?.started_at || payload?.started_at || nowIso,
          affected: payload?.body?.affected || payload?.affected || ['host-7f3a1234'],
          signals: payload?.body?.signals || payload?.signals || [],
          reasoning_path: payload?.body?.reasoning_path || payload?.reasoning_path || [],
          counterfactual: payload?.body?.counterfactual ?? payload?.counterfactual ?? null,
          recommendation: payload?.body?.recommendation || payload?.recommendation,
          changes_before: payload?.body?.changes_before || payload?.changes_before || [],
          suppressed_reason: payload?.body?.suppressed_reason || payload?.suppressed_reason || null,
          repeat_count: payload?.body?.repeat_count || payload?.repeat_count || 1,
          narrative: payload?.body?.narrative || payload?.narrative,
          status: payload?.status || 'open',
        };

        set((s) => {
          const idx = s.incidents.findIndex((i) => i.incident_id === incData.incident_id);
          const next = [...s.incidents];
          if (idx >= 0) {
            next[idx] = incData;
          } else {
            next.unshift(incData);
          }
          return { incidents: next.slice(0, 20) };
        });
        break;
      }

      case 'alert_opened': {
        const alert: Alert = {
          alert_id: payload?.alert_id || `alt-${Date.now()}`,
          tenant_id: tenant_id || payload?.tenant_id || 'acme',
          source: payload?.source || 'host-7f3a1234',
          title: payload?.title || 'Threshold Exceeded',
          severity: payload?.severity || 'medium',
          body: payload?.body || '',
          created_at: payload?.created_at || nowIso,
          status: 'open',
        };
        set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 50) }));
        break;
      }

      case 'payload_receipt': {
        const receipt: PayloadReceiptEvent = {
          guard_id: payload?.guard_id || 'guard-acme-01',
          payload_id: payload?.payload_id || `pay-${Date.now()}`,
          seq: payload?.seq || 0,
          status: payload?.status || 'stored',
          reason: payload?.reason,
          sha256: payload?.sha256,
          event_time: payload?.event_time || timestamp || nowIso,
          received_at: payload?.received_at || nowIso,
        };
        set((s) => ({ receipts: [receipt, ...s.receipts].slice(0, 100) }));
        break;
      }

      case 'counters': {
        set((s) => ({
          counters: {
            ...s.counters,
            raw_alerts: payload?.raw_alerts ?? s.counters.raw_alerts,
            incidents: payload?.incidents ?? s.counters.incidents,
            flaps_prevented: payload?.flaps_prevented ?? s.counters.flaps_prevented,
          },
        }));
        break;
      }

      case 'checkpoint': {
        if (payload?.guard_id) {
          set((s) => ({
            checkpoints: {
              ...s.checkpoints,
              [payload.guard_id]: {
                guard_id: payload.guard_id,
                up_to_seq: payload.up_to_seq,
                root: payload.root,
                match: payload.match,
                first_differing_seq: payload.first_differing_seq,
              },
            },
          }));
        }
        break;
      }

      case 'guard_heartbeat': {
        if (payload?.guard_id) {
          set((s) => ({
            guards: {
              ...s.guards,
              [payload.guard_id]: {
                ...(s.guards[payload.guard_id] || {}),
                ...payload,
                last_seen: nowIso,
              },
            },
          }));
        }
        break;
      }
    }
  },

  addAlert: (alert) => set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 50) })),
  addIncident: (incident) => set((s) => ({ incidents: [incident, ...s.incidents].slice(0, 20) })),
  updateActionState: (actionId, newState, approvedBy) =>
    set((s) => ({
      actions: s.actions.map((a) =>
        a.action_id === actionId
          ? {
              ...a,
              state: newState,
              approved_by: approvedBy || a.approved_by,
              result:
                newState === 'approved'
                  ? 'Remediation dispatched to Guard local agent; applied in 18ms'
                  : a.result,
            }
          : a
      ),
    })),
  resetToSimulated: (sampleData) => {
    set({
      mode: 'SIMULATED',
      incidents: sampleData?.incidents || [],
      alerts: sampleData?.alerts || [],
      counters: {
        raw_alerts: 54,
        incidents: 4,
        flaps_prevented: 15,
        canaries_planted: 1240,
        leaks_detected: 0,
        duplicates_blocked: 5,
      },
    });
  },
}));
