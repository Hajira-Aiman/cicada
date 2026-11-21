import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ResponsiveContainer, ComposedChart, Bar, BarChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceArea, ReferenceLine } from 'recharts';
import { apiFetch } from '@/services/apiClient';
import { formatClock } from '@/components/TimeText';
import { useUiStore } from '@/stores/uiStore';

// Every number here is pulled from the backend: /api/metrics, /api/events, /api/health/history, /api/baselines and the shop's chaos agent.

interface Pt { t: number; v: number }
interface Ev { id: number; tenant_id: string; category: string; severity: string; count: number; event_time: string }
interface Hist { id: number; tenant_id: string; source: string; state: string; old_state: string | null; reasons: any; at: string }
interface Mark { id: string; name: string; started_at: number; duration_s: number }

const METRICS: { name: string; label: string; unit: string; color: string; step?: boolean; minDelta: number }[] = [
  { name: 'cpu_pct', label: 'CPU', unit: '%', color: '#38BDF8', minDelta: 10 },
  { name: 'mem_pct', label: 'MEMORY', unit: '%', color: '#06B6D4', minDelta: 5 },
  { name: 'disk_pct', label: 'DISK', unit: '%', color: '#94A3B8', minDelta: 3 },
  { name: 'net_out_kbps', label: 'NET OUT', unit: 'kbps', color: '#A855F7', minDelta: 200 },
  { name: 'net_in_kbps', label: 'NET IN', unit: 'kbps', color: '#8B5CF6', minDelta: 200 },
  { name: 'latency_ms', label: 'LATENCY', unit: 'ms', color: '#10B981', minDelta: 50 },
  { name: 'packet_loss_pct', label: 'PACKET LOSS', unit: '%', color: '#F43F5E', minDelta: 2 },
  { name: 'service_up', label: 'SHOP SERVICE UP', unit: '', color: '#22C55E', step: true, minDelta: 0.5 },
  { name: 'battery_pct', label: 'BATTERY', unit: '%', color: '#FBBF24', minDelta: 5 },
  { name: 'on_battery', label: 'ON BATTERY', unit: '', color: '#F59E0B', step: true, minDelta: 0.5 },
  { name: 'battery_min_left', label: 'BATTERY MIN LEFT', unit: 'min', color: '#EAB308', minDelta: 5 },
];

type Focus = string;   // a metric name, 'logins' (login failures) or 'arrivals' (payloads reaching head office)
const SCENARIOS: { id: string; label: string; names: string[]; metrics: string[]; events: string[]; health?: boolean; hint: string; focus: Focus[] }[] = [
  { id: 'cpu_spike', label: 'CPU SPIKE', names: ['cpu_spike'], metrics: ['cpu_pct'], events: [], hint: 'CPU should climb well above its normal band.', focus: ['cpu_pct'] },
  { id: 'latency', label: 'LATENCY SPIKE', names: ['latency'], metrics: ['latency_ms', 'packet_loss_pct'], events: [], hint: 'The shop answers slower, so latency should jump.', focus: ['latency_ms'] },
  { id: 'brute_force', label: 'BRUTE FORCE', names: ['brute_force', 'login_burst'], metrics: [], events: ['auth_failure_burst', 'login_after_failures'], hint: 'A burst of failed logins should appear as one tall bar.', focus: ['logins'] },
  { id: 'kill_chain', label: 'KILL CHAIN', names: ['kill_chain'], metrics: ['cpu_pct', 'net_out_kbps'], events: ['auth_failure_burst', 'login_after_failures'], hint: 'Failed logins, then CPU, then outbound traffic: one critical incident.', focus: ['cpu_pct', 'net_out_kbps'] },
  { id: 'backup_job', label: 'BACKUP JOB', names: ['backup_job'], metrics: ['cpu_pct'], events: [], hint: 'Repeating CPU pulses: the system learns them as a normal schedule.', focus: ['cpu_pct'] },
  { id: 'port_scan', label: 'PORT SCAN', names: ['port_scan'], metrics: ['net_out_kbps', 'net_in_kbps'], events: [], hint: 'NETWORK: a flood of connection probes, visible as outbound traffic.', focus: ['net_out_kbps'] },
  { id: 'data_exfil', label: 'DATA EXFIL', names: ['data_exfil'], metrics: ['net_out_kbps'], events: [], hint: 'NETWORK: outbound traffic should jump far above its normal band.', focus: ['net_out_kbps'] },
  { id: 'crypto_miner', label: 'CRYPTO-MINER', names: ['crypto_miner'], metrics: ['cpu_pct', 'net_out_kbps'], events: [], hint: 'COMPUTE: sustained high CPU with steady outbound traffic.', focus: ['cpu_pct', 'net_out_kbps'] },
  { id: 'crash_loop', label: 'CRASH LOOP', names: ['crash_loop'], metrics: ['service_up'], events: ['app_restarted'], hint: 'COMPUTE: the shop app restarts every few seconds, each one an app_restarted event.', focus: ['service_up'] },
  { id: 'ransomware', label: 'RANSOMWARE CHURN', names: ['ransomware'], metrics: ['disk_pct', 'cpu_pct'], events: [], hint: 'STORAGE: files rewritten and renamed with encryption work, so CPU climbs.', focus: ['cpu_pct'] },
  { id: 'slow_disk', label: 'SLOW DISK / DB', names: ['slow_disk'], metrics: ['latency_ms', 'disk_pct'], events: [], hint: 'STORAGE: the shop answers slower while the disk is saturated.', focus: ['latency_ms'] },
  { id: 'http_5xx', label: 'HTTP 5XX STORM', names: ['http_5xx'], metrics: ['latency_ms', 'service_up'], events: [], hint: 'WEB APP: catalog, checkout and the health check fail, so the shop shows as down.', focus: ['latency_ms'] },
  { id: 'credential_stuffing', label: 'CREDENTIAL STUFFING', names: ['credential_stuffing'], metrics: [], events: ['auth_failure_burst', 'login_after_failures'], hint: 'WEB APP: a steady stream of failed logins, then one success.', focus: ['logins'] },
];

const RANGES =[{ l: '5 MIN', ms: 5 * 60e3 }, { l: '15 MIN', ms: 15 * 60e3 }, { l: '1 HOUR', ms: 3600e3 }];
const STATE_COLOR: Record<string, string> = { excellent: '#34d399', good: '#a3e635', fair: '#fbbf24', poor: '#f43f5e', offline: '#64748b' };
const SYSTEMS = [{ id: 'acme', label: 'SYSTEM 1' }, { id: 'globex', label: 'SYSTEM 2' }];

const median = (a: number[]) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

function bucket(pts: Pt[], from: number, to: number, n = 150): Pt[] {
  // keep the peak of each bucket so a short spike is never averaged away
  const w = (to - from) / n; const out: Record<number, Pt> = {};
  for (const p of pts) {
    if (p.t < from) continue;
    const i = Math.min(n - 1, Math.floor((p.t - from) / w));
    if (!out[i] || Math.abs(p.v) > Math.abs(out[i].v)) out[i] = { t: from + (i + 0.5) * w, v: p.v };
  }
  return Object.values(out).sort((a, b) => a.t - b.t);
}

export const TelemetryTab: React.FC = () => {
  const tzMode = useUiStore((s) => s.tzMode);
  const fmtT = (t: number) => formatClock(t, tzMode);   // follows the top-bar zone switch (it used to print UTC regardless)
  const [tenant, setTenant] = useState('acme');
  const [rangeMs, setRangeMs] = useState(RANGES[0].ms);
  const [scenario, setScenario] = useState(SCENARIOS[0].id);
  const [series, setSeries] = useState<Record<string, Pt[]>>({});
  const [events, setEvents] = useState<Ev[]>([]);
  const [hist, setHist] = useState<Hist[]>([]);
  const [base, setBase] = useState<Record<string, { mean: number; std: number }>>({});
  const [marks, setMarks] = useState<Mark[]>([]);
  const [chaosUrl, setChaosUrl] = useState(() => { try { return localStorage.getItem('chaosUrl') || (import.meta.env.VITE_CHAOS_API_URL as string) || ''; } catch { return ''; } });
  const [chaosOk, setChaosOk] = useState<boolean | null>(null);
  const [arrivals, setArrivals] = useState<number[]>([]);   // when each payload of this system reached head office
  const [now, setNow] = useState(Date.now());
  const lastSeen = useRef<Record<string, string>>({});

  // metrics: first load fetches the last hour, then only what is newer
  useEffect(() => {
    let stop = false;
    setSeries({}); lastSeen.current[tenant] = '';
    const load = async () => {
      try {
        const since = lastSeen.current[tenant] || new Date(Date.now() - 3600e3).toISOString();
        const r = await apiFetch<{ metrics: any[] }>(`/api/metrics?since=${encodeURIComponent(since)}&limit=20000`, { timeoutMs: 20000 });
        if (stop) return;
        const mine = r.metrics.filter((m) => m.tenant_id === tenant);
        if (!mine.length) return;
        lastSeen.current[tenant] = mine.reduce((mx, m) => (m.event_time > mx ? m.event_time : mx), lastSeen.current[tenant] || '');
        setSeries((prev) => {
          const next = { ...prev };
          for (const m of mine) {
            const arr = next[m.name] ? [...next[m.name]] : [];
            arr.push({ t: new Date(m.event_time).getTime(), v: Number(m.avg) });
            next[m.name] = arr;
          }
          const cut = Date.now() - 3600e3 - 60e3;
          for (const k of Object.keys(next)) next[k] = next[k].filter((p) => p.t >= cut).sort((a, b) => a.t - b.t);
          return next;
        });
      } catch { /* the next poll retries */ }
    };
    load();
    const id = setInterval(load, 3000);
    return () => { stop = true; clearInterval(id); };
  }, [tenant]);

  // events, health transitions, baselines
  useEffect(() => {
    let stop = false;
    const load = async () => {
      try {
        const [e, h, pl] = await Promise.all([apiFetch<{ events: Ev[] }>('/api/events?limit=500'), apiFetch<{ history: Hist[] }>('/api/health/history?limit=300'),
          apiFetch<{ payloads: any[] }>('/api/payloads?limit=2000', { timeoutMs: 15000 })]);
        if (stop) return;
        setArrivals(pl.payloads.filter((x) => x.tenant_id === tenant).map((x) => new Date(x.received_at).getTime()).sort((a, b) => a - b));
        setEvents(e.events.filter((x) => x.tenant_id === tenant));
        setHist(h.history.filter((x) => x.tenant_id === tenant));
      } catch { /* retry */ }
      try {
        const rows: any[] = await apiFetch(`/api/baselines/${tenant}`);
        if (!stop) { const b: Record<string, { mean: number; std: number }> = {}; rows.forEach((r) => { if (r.source.startsWith('host-')) b[r.metric] = { mean: r.mean, std: r.std }; }); setBase(b); }
      } catch { /* band stays empty */ }
    };
    load();
    const id = setInterval(load, 4000);
    return () => { stop = true; clearInterval(id); };
  }, [tenant]);

  // scenario markers from the shop's chaos agent
  useEffect(() => {
    let stop = false;
    const load = async () => {
      if (!chaosUrl) { setChaosOk(null); return; }
      try {
        const r = await fetch(`${chaosUrl.replace(/\/$/, '')}/chaos/history`, { signal: AbortSignal.timeout(3000) });
        const j = await r.json();
        if (!stop) { setMarks(j.history || []); setChaosOk(true); }
      } catch { if (!stop) setChaosOk(false); }
    };
    load();
    const id = setInterval(load, 4000);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => { stop = true; clearInterval(id); clearInterval(clock); };
  }, [chaosUrl]);

  const saveUrl = (v: string) => { setChaosUrl(v); try { localStorage.setItem('chaosUrl', v); } catch { /* ignore */ } };
  const from = now - rangeMs;
  const sc = SCENARIOS.find((s) => s.id === scenario)!;
  const shownMarks = marks.filter((m) => m.started_at * 1000 >= from);

  // did the selected scenario leave a trace? compare its window with the minute before it
  const result = useMemo(() => {
    const m = [...marks].filter((x) => sc.names.includes(x.name)).sort((a, b) => b.started_at - a.started_at)[0];
    if (!m) return null;
    const t0 = m.started_at * 1000, t1 = t0 + m.duration_s * 1000 + 30e3;
    const lines: { ok: boolean; text: string }[] = [];
    for (const name of sc.metrics) {
      const def = METRICS.find((d) => d.name === name)!;
      const pts = series[name] || [];
      const win = pts.filter((p) => p.t >= t0 && p.t <= t1).map((p) => p.v);
      const pre = pts.filter((p) => p.t >= t0 - 60e3 && p.t < t0).map((p) => p.v);
      if (!win.length) { lines.push({ ok: false, text: `${def.label}: no data in the run window yet` }); continue; }
      const peak = Math.max(...win), before = median(pre);
      const b = base[name];
      const z = b && b.std > 0 ? (peak - b.mean) / b.std : NaN;
      const ok = peak - (isNaN(before) ? 0 : before) >= def.minDelta;
      lines.push({ ok, text: `${def.label}: peak ${peak.toFixed(1)}${def.unit}${isNaN(before) ? '' : ` vs ${before.toFixed(1)} before`}${isNaN(z) ? '' : ` (+${z.toFixed(1)} sigma)`}` });
    }
    for (const cat of sc.events) {
      const n = events.filter((e) => e.category === cat && new Date(e.event_time).getTime() >= t0 - 5e3 && new Date(e.event_time).getTime() <= t1).reduce((s, e) => s + e.count, 0);
      lines.push({ ok: n > 0, text: `${cat}: ${n} occurrence${n === 1 ? '' : 's'} reported` });
    }
    if (sc.health) {
      const bad = hist.filter((h) => new Date(h.at).getTime() >= t0 && new Date(h.at).getTime() <= t1 + 60e3 && ['poor', 'offline', 'fair'].includes(h.state));
      lines.push({ ok: bad.length > 0, text: bad.length ? `Health went ${bad[0].state.toUpperCase()}: ${String(Array.isArray(bad[0].reasons) ? bad[0].reasons[0] : bad[0].reasons)}` : 'No health change recorded in the run window' });
    }
    return { m, lines };
  }, [marks, sc, series, events, hist, base]);

  const ticks = Array.from({ length: 6 }, (_, i) => from + ((now - from) * i) / 5);
  const evInRange = events.filter((e) => new Date(e.event_time).getTime() >= from);
  const histHere = hist.filter((h) => h.source.startsWith('host-')).sort((a, b) => +new Date(a.at) - +new Date(b.at));
  const segs = histHere.map((h, i) => ({ s: Math.max(from, new Date(h.at).getTime()), e: i + 1 < histHere.length ? new Date(histHere[i + 1].at).getTime() : now, state: h.state }))
    .filter((x) => x.e > from);

  // a gap is a stretch where no payload arrived (they normally come every 2 s): shaded grey on every chart
  const gaps: [number, number][] = [];
  for (let i = 1; i < arrivals.length; i++) if (arrivals[i] - arrivals[i - 1] > 8000 && arrivals[i] > from) gaps.push([Math.max(from, arrivals[i - 1]), arrivals[i]]);
  if (arrivals.length && now - arrivals[arrivals.length - 1] > 8000) gaps.push([Math.max(from, arrivals[arrivals.length - 1]), now]);
  const bucketMs = Math.max(2000, Math.round(rangeMs / 60 / 2000) * 2000);   // about 60 bars across the range
  const nBars = Math.ceil(rangeMs / bucketMs);
  const arrivalBars = Array.from({ length: nBars }, (_, i) => ({ t: from + i * bucketMs + bucketMs / 2, n: 0 }));
  arrivals.forEach((t) => { const i = Math.floor((t - from) / bucketMs); if (i >= 0 && i < nBars) arrivalBars[i].n++; });
  const failBars = Array.from({ length: nBars }, (_, i) => ({ t: from + i * bucketMs + bucketMs / 2, fails: 0, after: 0 }));
  events.forEach((e) => {
    const i = Math.floor((new Date(e.event_time).getTime() - from) / bucketMs);
    if (i < 0 || i >= nBars) return;
    if (e.category === 'auth_failure_burst') failBars[i].fails += e.count; else if (e.category === 'login_after_failures') failBars[i].after += e.count;
  });
  const sumCat = (cat: string, ms: number) => events.filter((e) => e.category === cat && new Date(e.event_time).getTime() >= now - ms).reduce((a, e) => a + e.count, 0);
  const tiles = [
    { l: 'FAILED LOGINS (60 S)', v: sumCat('auth_failure_burst', 60e3), hot: sc.events.includes('auth_failure_burst') },
    { l: 'LOGIN AFTER FAILURES (5 MIN)', v: sumCat('login_after_failures', 300e3), hot: sc.events.includes('login_after_failures') },
    { l: 'HONEYPOT HITS (5 MIN)', v: sumCat('honeypot_hit', 300e3), hot: false },
    { l: 'SECRETS REDACTED (5 MIN)', v: sumCat('secret_redacted', 300e3), hot: false },
    { l: 'PAYLOAD GAPS IN RANGE', v: gaps.length, hot: !!sc.health },
  ];

  const [showAll, setShowAll] = useState(false);
  const [showLog, setShowLog] = useState(false);
  const [showMarkers, setShowMarkers] = useState(false);

  const metricCard = (m: typeof METRICS[number], height = 150) => {
    const data = bucket(series[m.name] || [], from, now);
    const b = base[m.name];
    const last = data[data.length - 1]?.v;
    return (
      <div key={m.name} className="hud-panel p-3">
        <div className="flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{m.label}</span>
          <span className="text-xl font-black text-slate-100">{last === undefined ? '—' : last.toFixed(m.step ? 0 : 1)}<span className="text-[10px] text-slate-500 ml-1">{m.unit}</span></span>
        </div>
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
              <CartesianGrid stroke="#ffffff10" vertical={false} />
              <XAxis dataKey="t" type="number" domain={[from, now]} ticks={ticks} tickFormatter={fmtT} tick={{ fontSize: 9, fill: '#64748b' }} />
              <YAxis tick={{ fontSize: 9, fill: '#64748b' }} domain={m.step ? [0, 1] : [0, 'auto']} allowDecimals={false} />
              <Tooltip contentStyle={{ background: '#0c1017', border: '1px solid #ffffff22', fontSize: 11 }} labelFormatter={(t) => fmtT(Number(t))} formatter={(v: any) => [Number(v).toFixed(2) + m.unit, m.label]} />
              {b && !m.step && <ReferenceArea y1={Math.max(0, b.mean - 2 * b.std)} y2={b.mean + 2 * b.std} fill={m.color} fillOpacity={0.1} stroke="none" />}
              {gaps.map(([x1, x2], i) => <ReferenceArea key={i} x1={x1} x2={x2} fill="#94a3b8" fillOpacity={0.22} stroke="none" />)}
              {shownMarks.map((k) => (
                <ReferenceLine key={k.id} x={k.started_at * 1000} stroke={sc.names.includes(k.name) ? '#fbbf24' : '#ffffff55'} strokeDasharray="3 3"
                  label={{ value: k.name, position: 'insideTopRight', fontSize: 9, fill: '#cbd5e1' }} />
              ))}
              <Line type={m.step ? 'stepAfter' : 'monotone'} dataKey="v" stroke={m.color} strokeWidth={2} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  };

  const barCard = (title: string, data: any[], keys: { k: string; c: string; name: string }[], withGaps: boolean, height = 150) => (
    <div className="hud-panel p-3">
      <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{title}</span>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
            <CartesianGrid stroke="#ffffff10" vertical={false} />
            <XAxis dataKey="t" type="number" domain={[from, now]} ticks={ticks} tickFormatter={fmtT} tick={{ fontSize: 9, fill: '#64748b' }} />
            <YAxis tick={{ fontSize: 9, fill: '#64748b' }} allowDecimals={false} />
            <Tooltip contentStyle={{ background: '#0c1017', border: '1px solid #ffffff22', fontSize: 11 }} labelFormatter={(t) => fmtT(Number(t))} />
            {withGaps && gaps.map(([x1, x2], i) => <ReferenceArea key={i} x1={x1} x2={x2} fill="#94a3b8" fillOpacity={0.22} stroke="none" />)}
            {shownMarks.map((k) => <ReferenceLine key={k.id} x={k.started_at * 1000} stroke="#fbbf24" strokeDasharray="3 3" label={{ value: k.name, position: 'insideTopRight', fontSize: 9, fill: '#cbd5e1' }} />)}
            {keys.map((x) => <Bar key={x.k} dataKey={x.k} name={x.name} stackId="a" fill={x.c} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );

  const focusChart = (f: Focus) => {
    if (f === 'logins') return <div key={f}>{barCard('FAILED LOGINS', failBars, [{ k: 'fails', c: '#f43f5e', name: 'failed logins' }, { k: 'after', c: '#fbbf24', name: 'login after failures' }], false, 190)}</div>;
    if (f === 'arrivals') return <div key={f}>{barCard('PAYLOADS REACHING HEAD OFFICE', arrivalBars, [{ k: 'n', c: '#38bdf8', name: 'payloads' }], true, 190)}</div>;
    return metricCard(METRICS.find((m) => m.name === f)!, 190);
  };

  const verdict = result ? result.lines.every((l) => l.ok) : null;
  const health = [...histHere].pop();
  const countText = sc.events.map((c) => `${sumCat(c, 300e3)} ${c.replace(/_/g, ' ')}`).join(' · ');

  return (
    <div className="p-5 space-y-4 max-w-[1400px] mx-auto font-mono text-xs">
      {/* one slim bar: system, range, health, markers */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center bg-black/40 p-0.5 rounded border border-white/10">
          {SYSTEMS.map((x) => (
            <button key={x.id} onClick={() => setTenant(x.id)} className={`px-3 py-1 rounded font-bold ${tenant === x.id ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-white'}`}>{x.label}</button>
          ))}
        </div>
        <div className="flex items-center bg-black/40 p-0.5 rounded border border-white/10">
          {RANGES.map((r) => (
            <button key={r.l} onClick={() => setRangeMs(r.ms)} className={`px-3 py-1 rounded font-bold ${rangeMs === r.ms ? 'bg-purple-500 text-white' : 'text-slate-400 hover:text-white'}`}>{r.l}</button>
          ))}
        </div>
        {health && <span className="px-2.5 py-1 rounded font-bold border border-white/10" style={{ color: STATE_COLOR[health.state] }}>● HEALTH {health.state.toUpperCase()}</span>}
        <button onClick={() => setShowMarkers((v) => !v)} className={`ml-auto px-2.5 py-1 rounded border font-bold ${chaosOk ? 'border-emerald-500/40 text-emerald-400' : 'border-amber-400/50 text-amber-300'}`}>
          {chaosOk ? `MARKERS ON (${shownMarks.length})` : 'SET UP MARKERS'}
        </button>
      </div>
      {showMarkers && (
        <div className="hud-panel p-3 flex items-center gap-2">
          <span className="text-slate-400">Shop chaos agent address</span>
          <input value={chaosUrl} onChange={(e) => saveUrl(e.target.value)} placeholder="http://192.168.137.56:9100"
            className="bg-black/50 border border-white/15 rounded px-2 py-1 w-64 text-slate-200 outline-none focus:border-sky-400" />
          <span className={chaosOk ? 'text-emerald-400' : chaosOk === false ? 'text-rose-400' : 'text-slate-500'}>{chaosOk ? 'connected' : chaosOk === false ? 'not reachable' : 'not set'}</span>
        </div>
      )}

      {/* pick a scenario */}
      <div className="flex flex-wrap gap-2">
        {SCENARIOS.map((x) => (
          <button key={x.id} onClick={() => setScenario(x.id)}
            className={`px-4 py-2 rounded-lg border font-bold ${scenario === x.id ? 'bg-sky-500/20 border-sky-400 text-sky-100' : 'border-white/10 text-slate-400 hover:text-white'}`}>{x.label}</button>
        ))}
      </div>

      {/* the answer: one verdict, then only the charts that matter */}
      <div className={`hud-panel p-5 space-y-2 ${verdict === true ? 'border-emerald-500/50' : verdict === false ? 'border-amber-400/50' : 'border-white/10'}`}>
        <div className="text-base font-black text-white">{sc.label}</div>
        <div className="text-slate-400">{sc.hint}</div>
        {result ? (
          <>
            <div className={`text-lg font-black ${verdict ? 'text-emerald-400' : 'text-amber-300'}`}>{verdict ? '✓ SEEN ON THE DASHBOARD' : '… NOT SEEN (YET)'}</div>
            {result.lines.map((l, i) => <div key={i} className={l.ok ? 'text-emerald-300' : 'text-amber-200'}>{l.ok ? '✓' : '•'} {l.text}</div>)}
            <div className="text-slate-500">Run at {fmtT(result.m.started_at * 1000)} for {result.m.duration_s} s</div>
          </>
        ) : (
          <div className="text-slate-500">{chaosOk ? 'No run yet. Start this scenario from the chaos console.' : 'Turn on markers (top right) to see when a scenario ran and whether it showed up.'}</div>
        )}
        {sc.events.length > 0 && <div className="text-slate-300 pt-1">Last 5 minutes: {countText}</div>}
        {sc.health && <div className="text-slate-300 pt-1">Gaps in payload arrival in this range: {gaps.length}</div>}
      </div>
      <div className={`grid gap-3 ${sc.focus.length > 1 ? 'md:grid-cols-2' : 'grid-cols-1'}`}>{sc.focus.map(focusChart)}</div>

      {/* everything else, on request */}
      <div className="flex gap-2">
        <button onClick={() => setShowAll((v) => !v)} className="px-3 py-1.5 rounded border border-white/10 text-slate-300 hover:text-white font-bold">{showAll ? '▲ HIDE' : '▼ SHOW'} ALL 11 METRICS</button>
        <button onClick={() => setShowLog((v) => !v)} className="px-3 py-1.5 rounded border border-white/10 text-slate-300 hover:text-white font-bold">{showLog ? '▲ HIDE' : '▼ SHOW'} HEALTH &amp; EVENT LOG</button>
      </div>
      {showAll && <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">{METRICS.map((m) => metricCard(m, 110))}</div>}
      {showLog && (
        <div className="grid md:grid-cols-2 gap-3">
          <div className="hud-panel p-4 space-y-1">
            <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">HEALTH CHANGES</span>
            {histHere.slice(-8).reverse().map((h) => (
              <div key={h.id} className="text-slate-400"><span style={{ color: STATE_COLOR[h.state] }}>{h.old_state ? `${h.old_state} → ` : ''}{h.state.toUpperCase()}</span> · {fmtT(new Date(h.at).getTime())} · {Array.isArray(h.reasons) ? h.reasons.join(', ') : String(h.reasons)}</div>
            ))}
            {histHere.length === 0 && <div className="text-slate-500">None yet.</div>}
          </div>
          <div className="hud-panel p-4 space-y-1">
            <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">EVENTS IN RANGE ({evInRange.length})</span>
            <div className="max-h-52 overflow-y-auto divide-y divide-white/5">
              {evInRange.slice(0, 40).map((e) => (
                <div key={e.id} className="flex items-center gap-3 py-1">
                  <span className="text-slate-500 w-16">{fmtT(new Date(e.event_time).getTime())}</span>
                  <span className="text-slate-200">{e.category}</span>
                  <span className="text-slate-400">x{e.count}</span>
                </div>
              ))}
              {evInRange.length === 0 && <div className="py-2 text-slate-500">No events in this range.</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TelemetryTab;
