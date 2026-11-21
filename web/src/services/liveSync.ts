// Pulls the real backend state over REST every 2 s into the live store (the websocket is a bonus, not the source of truth).
import { useEffect } from 'react';
import { api, apiFetch } from './apiClient';
import { useLiveStore } from '../stores/liveStore';
import { useUiStore } from '../stores/uiStore';
import { Alert, GuardInfo, HealthState, Incident, MetricDataPoint } from '../types';

const RANK: Record<string, number> = { excellent: 0, good: 1, fair: 2, poor: 3, offline: 4 };
const cap = (s: string): HealthState => (s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : 'Good') as HealthState;
const CHARTED = new Set(['cpu_pct', 'mem_pct', 'latency_ms', 'net_out_kbps', 'net_in_kbps', 'packet_loss_pct', 'disk_pct']);

let lastMetricTime: string | null = null;
const seenPayloads = new Set<string>();
export const resetSync = () => { lastMetricTime = null; seenPayloads.clear(); };

export async function syncOnce() {
  const store = useLiveStore.getState();
  const [tenants, health, recon, incs, alerts, metrics, payloads, acts, gd] = await Promise.all([
    api.getTenants(), api.getHealth(), api.getReconciliation(), api.getIncidents(), api.getAlerts(),
    apiFetch<{ metrics: any[] }>(`/api/metrics${lastMetricTime ? `?since=${encodeURIComponent(lastMetricTime)}` : ''}`),
    api.getPayloads(), apiFetch<{ intents: any[] }>('/api/actions?limit=20').catch(() => ({ intents: [] as any[] })),
    apiFetch<{ guards: any[]; leaks: Record<string, number> }>('/api/guards').catch(() => ({ guards: [] as any[], leaks: {} as Record<string, number> })),
  ]);
  const reported: Record<string, any> = Object.fromEntries(gd.guards.map((g) => [g.guard_id, g]));
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
  for (const r of recon.reconciliation) {
    const silentS = (Date.now() - new Date(r.last_seen).getTime()) / 1000;   // payloads stopped arriving
    // while the guard is sending, a source that stopped reporting is a leftover (a restarted process), not a failure
    const rows = health.health.filter((h) => h.tenant_id === r.tenant_id
      && !(silentS < 60 && (Array.isArray(h.reasons) ? h.reasons : [String(h.reasons)]).some((x: string) => String(x).startsWith('no heartbeat'))));
    const worst = rows.reduce((w, h) => Math.max(w, RANK[h.state] ?? 0), 0);
    const bad = rows.filter((h) => (RANK[h.state] ?? 0) === worst);
    const rep = reported[r.guard_id] || {};   // the guard's own health, as sent in its newest payload
    guards[r.guard_id] = {
      guard_id: r.guard_id, tenant_id: r.tenant_id, region: region[r.tenant_id] || 'in',
      source: (rows.find((h) => h.source.startsWith('host-')) || rows[0])?.source || '—',
      state: silentS > 60 ? 'Offline' : rows.length ? cap(Object.keys(RANK).find((k) => RANK[k] === worst)!) : 'Good',
      reasons: silentS > 60 ? [`no payload for ${Math.round(silentS)} s`] : [...new Set(bad.flatMap((h) => (worst > 1 ? h.reasons : [])))],
      since: bad[0]?.since || r.last_seen, last_seen: r.last_seen,
      guard_version: rep.guard_version ?? '—', guard_cpu_pct: rep.guard_cpu_pct ?? 0, guard_mem_mb: rep.guard_mem_mb ?? 0,
      buffer_depth: rep.buffer_depth ?? Math.max(0, r.sent_count - r.received_count),
      config_ok: rep.config_ok ?? true, canaries_planted: rep.canaries_planted ?? 0, secrets_redacted: rep.secrets_redacted ?? 0,
      flaps_prevented: rows.reduce((n, h) => n + (h.flaps_prevented || 0), 0), policy_hash: rep.policy_version ? String(rep.policy_version).replace('sha256:', '').slice(0, 12) : '—',
    };
  }

  // ---- incidents + alerts (contract shape: body holds the fields)
  const incidents: Incident[] = incs.incidents.map((i) => ({ ...i.body, incident_id: i.incident_id, tenant_id: i.tenant_id, status: i.status || 'open' }));
  const alertList: Alert[] = alerts.alerts.map((a) => ({ alert_id: a.alert_id, tenant_id: a.tenant_id, source: a.source, title: a.title,
    severity: a.severity, body: a.body, created_at: a.created_at, status: a.status || 'open' }));

  // ---- receipts from payloads, latency sample from the newest metric
  const byNewest = [...payloads.payloads].sort((a, b) => +new Date(b.received_at) - +new Date(a.received_at));
  const receipts = byNewest.slice(0, 100).map((p) => ({ guard_id: p.guard_id, payload_id: p.payload_id, seq: p.seq,
    status: (p.receipt_status || 'stored') as 'stored' | 'duplicate', sha256: p.sha256, event_time: p.sent_at, received_at: p.received_at }));
  const newest = byNewest[0];
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
    reconciliation: Object.fromEntries(recon.reconciliation.map((r) => [r.guard_id, r])),
    counters: { ...s.counters, raw_alerts: sum('raw_alerts'), incidents: sum('incidents'), flaps_prevented: sum('flaps_prevented'),
      canaries_planted: Object.values(guards).reduce((n, g) => n + g.canaries_planted, 0),
      leaks_detected: Object.values(gd.leaks).reduce((n, v) => n + v, 0),
      duplicates_blocked: recon.reconciliation.reduce((n, r) => n + (r.duplicate_count || 0), 0) },
    latencySamples: fresh_ && newest ? [{ event_time: newest.sent_at, render_time: new Date().toISOString(),
      latency_ms: Math.max(0, Date.now() - new Date(newest.sent_at).getTime()) }, ...s.latencySamples].slice(0, 50) : s.latencySamples,
  }));
}

export function useLiveSync() {
  const token = useUiStore((s) => s.authToken);
  useEffect(() => {
    if (!token) return;
    resetSync();
    useLiveStore.getState().clearForLive();
    let stop = false;
    const tick = async () => {
      try { await syncOnce(); useLiveStore.getState().setConnected(true); } catch { useLiveStore.getState().setConnected(false); }
    };
    tick();
    const id = setInterval(() => !stop && tick(), 2000);
    return () => { stop = true; clearInterval(id); };
  }, [token]);
}
