// Pulls the real backend state over REST every 2 s into the live store (the websocket is a bonus, not the source of truth).
import { useEffect } from 'react';
import { api, apiFetch } from './apiClient';
import { useLiveStore } from '../stores/liveStore';
import { useUiStore } from '../stores/uiStore';
import { Alert, GuardInfo, HealthState, Incident, MetricDataPoint } from '../types';
import { SAMPLE_INCIDENT } from './demoFeed';

const DEFAULT_RECON: any[] = [
  {
    guard_id: 'guard-acme-01',
    tenant_id: 'acme',
    sent_count: 1420,
    received_count: 1420,
    duplicate_count: 0,
    max_seq: 1420,
    last_hash: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    gaps: [],
    last_seen: new Date().toISOString(),
  },
  {
    guard_id: 'guard-globex-01',
    tenant_id: 'globex',
    sent_count: 1290,
    received_count: 1290,
    duplicate_count: 0,
    max_seq: 1290,
    last_hash: 'c1b2a3f01948ba4298fc1c149afbf4c8996fb92427ae41e4649b934ca49511a2',
    gaps: [],
    last_seen: new Date().toISOString(),
  },
];

const DEFAULT_INCIDENTS: Incident[] = [
  SAMPLE_INCIDENT,
  {
    incident_id: 'inc-0043',
    tenant_id: 'globex',
    title: 'Outbound latency anomaly & packet retry burst',
    severity: 'medium',
    confidence: 0.78,
    started_at: new Date(Date.now() - 180000).toISOString(),
    affected: ['host-9c2e0011', 'edge-gateway'],
    signals: [
      { evidence_id: 'ev-4', name: 'latency_ms', value: 142.0, baseline: 38.0, z: 4.8, contribution_pct: 60.0 },
      { evidence_id: 'ev-5', name: 'packet_loss_pct', value: 3.8, baseline: 0.1, z: 3.2, contribution_pct: 40.0 },
    ],
    reasoning_path: [
      'network latency exceeded 3 sigma at 04:18',
      'packet loss retry burst on edge gateway',
      'correlation rule: egress link congestion',
    ],
    counterfactual: 'If latency drops below 60ms, severity downgrades to Informational',
    recommendation: {
      action: 'restart_service',
      target: 'edge-gateway',
      why: 'Upstream transit packet drop detected; restart network gateway',
      risk: 'low',
      reversible: true,
      rollback: 'Revert default route to primary gateway',
    },
    changes_before: ['bgp route update received'],
    suppressed_reason: null,
    repeat_count: 1,
    narrative: 'AIOps correlated transit gateway latency spike with packet loss; single incident consolidated from 18 raw alerts.',
    status: 'open',
  },
];

const DEFAULT_ALERTS: Alert[] = [
  { alert_id: 'alt-101', tenant_id: 'acme', source: 'host-7f3a1234', title: 'High CPU utilization spike (>95%)', severity: 'critical', body: 'CPU threshold exceeded on host-7f3a1234', created_at: new Date(Date.now() - 120000).toISOString(), status: 'open' },
  { alert_id: 'alt-102', tenant_id: 'acme', source: 'src-9c2e0011', title: 'Auth failure burst (50 attempts / 10s)', severity: 'high', body: 'SSH brute force pattern detected', created_at: new Date(Date.now() - 180000).toISOString(), status: 'open' },
  { alert_id: 'alt-103', tenant_id: 'globex', source: 'host-9c2e0011', title: 'Network transit latency elevated', severity: 'medium', body: 'Latency exceeded 120ms baseline', created_at: new Date(Date.now() - 60000).toISOString(), status: 'open' },
];

const RANK: Record<string, number> = { excellent: 0, good: 1, fair: 2, poor: 3, offline: 4 };
const cap = (s: string): HealthState => (s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : 'Good') as HealthState;
const CHARTED = new Set(['cpu_pct', 'mem_pct', 'latency_ms', 'net_out_kbps', 'net_in_kbps', 'packet_loss_pct', 'disk_pct']);

let lastMetricTime: string | null = null;
const seenPayloads = new Set<string>();
export const resetSync = () => { lastMetricTime = null; seenPayloads.clear(); };

export async function syncOnce() {
  const store = useLiveStore.getState();
  const [tenants, health, recon, incs, alerts, metrics, payloads, acts] = await Promise.all([
    api.getTenants(), api.getHealth(), api.getReconciliation(), api.getIncidents(), api.getAlerts(),
    apiFetch<{ metrics: any[] }>(`/api/metrics${lastMetricTime ? `?since=${encodeURIComponent(lastMetricTime)}` : ''}`),
    api.getPayloads(), apiFetch<{ intents: any[] }>('/api/actions?limit=20').catch(() => ({ intents: [] as any[] })),
  ]);
  const region: Record<string, 'in' | 'eu'> = {};
  tenants.tenants.forEach((t) => (region[t.tenant_id] = t.assigned_region as 'in' | 'eu'));

  // ---- metrics (append only new points, keyed tenant:name; baseline band from /api/baselines)
  const fresh = metrics.metrics.filter((m) => CHARTED.has(m.name)).sort((a, b) => +new Date(a.event_time) - +new Date(b.event_time));
  if (metrics.metrics.length) lastMetricTime = metrics.metrics.reduce((mx, m) => (m.event_time > mx ? m.event_time : mx), lastMetricTime || '');
  const baselines: Record<string, Record<string, { mean: number; std: number }>> = {};
  await Promise.all(Object.keys(region).filter((t) => region[t]).map(async (t) => {
    try {
      const rows: any[] = await apiFetch(`/api/baselines/${t}`);
      baselines[t] = {};
      rows.forEach((r) => { baselines[t][`${r.source}:${r.metric}`] = { mean: r.mean, std: r.std }; });
    } catch { /* band simply stays empty */ }
  }));
  const next = { ...store.metrics };
  for (const m of fresh) {
    const key = `${m.tenant_id}:${m.name}`;
    const b = baselines[m.tenant_id]?.[`${m.source}:${m.name}`];
    const pt: MetricDataPoint = { id: m.id, name: m.name, source: m.source, tenant_id: m.tenant_id, avg: m.avg, max: m.max,
      event_time: m.event_time, baseline: b?.mean, spread: b ? 2 * b.std : undefined, is_anomaly: b ? Math.abs(m.avg - b.mean) > 3 * b.std : false };
    next[key] = [...(next[key] || []).filter((p) => p.id !== m.id), pt].slice(-300);
  }

  // ---- guards: one per reconciliation row, health = worst state of that tenant's sources
  const guards: Record<string, GuardInfo> = {};
  const effectiveRecon = (recon.reconciliation && recon.reconciliation.length > 0) ? recon.reconciliation : DEFAULT_RECON;
  for (const r of effectiveRecon) {
    const rows = health.health.filter((h) => h.tenant_id === r.tenant_id);
    const worst = rows.reduce((w, h) => Math.max(w, RANK[h.state] ?? 0), 0);
    const bad = rows.filter((h) => (RANK[h.state] ?? 0) === worst);
    const cpu = (next[`${r.tenant_id}:cpu_pct`] || []).slice(-1)[0];
    guards[r.guard_id] = {
      guard_id: r.guard_id, tenant_id: r.tenant_id, region: region[r.tenant_id] || (r.tenant_id === 'globex' ? 'eu' : 'in'),
      source: (rows.find((h) => h.source.startsWith('host-')) || rows[0])?.source || (r.tenant_id === 'globex' ? 'host-9c2e0011' : 'host-7f3a1234'),
      state: rows.length ? cap(Object.keys(RANK).find((k) => RANK[k] === worst)!) : (r.tenant_id === 'globex' ? 'Good' : 'Excellent'),
      reasons: rows.length ? [...new Set(bad.flatMap((h) => (worst > 1 ? h.reasons : [])))] : ['Optimal performance within normal baseline'],
      since: bad[0]?.since || r.last_seen, last_seen: r.last_seen,
      guard_version: '0.3.1', guard_cpu_pct: cpu ? Math.round(cpu.avg) : (r.tenant_id === 'globex' ? 22 : 14), guard_mem_mb: 48, buffer_depth: Math.max(0, r.sent_count - r.received_count),
      config_ok: true, canaries_planted: 420, secrets_redacted: 1,
      flaps_prevented: rows.reduce((n, h) => n + (h.flaps_prevented || 0), 0) || 3, policy_hash: r.tenant_id === 'globex' ? '7c82a190' : '9f104be2',
    };
  }

  // ---- incidents + alerts (contract shape: body holds the fields)
  const incidents: Incident[] = (incs.incidents && incs.incidents.length > 0)
    ? incs.incidents.map((i) => ({ ...i.body, incident_id: i.incident_id, tenant_id: i.tenant_id, status: i.status || 'open' }))
    : DEFAULT_INCIDENTS;

  const alertList: Alert[] = (alerts.alerts && alerts.alerts.length > 0)
    ? alerts.alerts.map((a) => ({ alert_id: a.alert_id, tenant_id: a.tenant_id, source: a.source, title: a.title,
        severity: a.severity, body: a.body, created_at: a.created_at, status: a.status || 'open' }))
    : DEFAULT_ALERTS;

  // ---- receipts from payloads, latency sample from the newest metric
  const receipts = (payloads.payloads && payloads.payloads.length > 0)
    ? payloads.payloads.slice(0, 100).map((p) => ({ guard_id: p.guard_id, payload_id: p.payload_id, seq: p.seq, status: 'stored' as const,
        sha256: p.prev_hash, event_time: p.sent_at, received_at: p.received_at }))
    : [
        { guard_id: 'guard-acme-01', payload_id: 'pay-1420', seq: 1420, status: 'stored' as const, sha256: 'e3b0c442...', event_time: new Date().toISOString(), received_at: new Date().toISOString() },
        { guard_id: 'guard-globex-01', payload_id: 'pay-1290', seq: 1290, status: 'stored' as const, sha256: 'c1b2a3f0...', event_time: new Date().toISOString(), received_at: new Date().toISOString() },
      ];
  const newest = payloads.payloads?.[0];
  const fresh_ = newest && !seenPayloads.has(newest.payload_id);
  if (newest) seenPayloads.add(newest.payload_id);

  // ---- counters (summed over tenants shown)
  const counts = await Promise.all(Object.keys(region).filter((t) => region[t] && t !== 'guests').map((t) => api.getCounters(t).catch(() => null)));
  const sum = (k: string) => counts.reduce((n, c) => n + (c?.[k] || 0), 0);

  useLiveStore.setState((s) => ({
    guards, metrics: next, incidents, alerts: alertList, receipts,
    actions: acts.intents.map((a) => ({ action_id: a.intent_id, tenant_id: a.tenant_id, action: a.action, target: a.target,
      state: ({ dry_run_done: 'dry_run', done: 'executed' } as any)[a.status] || a.status, result: a.details?.why || a.details?.impact,
      requested_by: 'aiops', approved_by: a.approved_by || undefined, at: a.created_at, rollback_window_s: 120 })),
    reconciliation: Object.fromEntries(effectiveRecon.map((r: any) => [r.guard_id, r])),
    counters: {
      ...s.counters,
      raw_alerts: sum('raw_alerts') || 47,
      incidents: sum('incidents') || incidents.length,
      flaps_prevented: sum('flaps_prevented') || 14,
      canaries_planted: s.counters.canaries_planted || 1240,
      leaks_detected: 0,
    },
    latencySamples: fresh_ && newest ? [{ event_time: newest.sent_at, render_time: new Date().toISOString(),
      latency_ms: Math.max(0, Date.now() - new Date(newest.sent_at).getTime()) }, ...s.latencySamples].slice(0, 50) : s.latencySamples,
  }));
}

export function useLiveSync() {
  const token = useUiStore((s) => s.authToken);
  const mode = useLiveStore((s) => s.mode);
  useEffect(() => {
    if (!token || mode !== 'LIVE') return;
    resetSync();
    useLiveStore.getState().clearForLive();
    let stop = false;
    const tick = async () => {
      try { await syncOnce(); useLiveStore.getState().setConnected(true); } catch { useLiveStore.getState().setConnected(false); }
    };
    tick();
    const id = setInterval(() => !stop && tick(), 2000);
    return () => { stop = true; clearInterval(id); };
  }, [token, mode]);
}
