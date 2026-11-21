import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ResponsiveContainer, ComposedChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceArea, ReferenceLine } from 'recharts';
import { apiFetch } from '@/services/apiClient';

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

const SCENARIOS: { id: string; label: string; names: string[]; metrics: string[]; events: string[]; health?: boolean; hint: string }[] = [
  { id: 'cpu_spike', label: 'CPU SPIKE', names: ['cpu_spike'], metrics: ['cpu_pct'], events: [], hint: 'CPU rises well above its baseline band.' },
  { id: 'latency', label: 'LATENCY SPIKE', names: ['latency'], metrics: ['latency_ms', 'packet_loss_pct'], events: [], hint: 'Shop request latency jumps (the guard probes the shop).' },
  { id: 'brute_force', label: 'BRUTE FORCE', names: ['brute_force', 'login_burst'], metrics: [], events: ['auth_failure_burst', 'login_after_failures'], hint: 'An auth_failure_burst event with a large count.' },
  { id: 'kill_chain', label: 'KILL CHAIN', names: ['kill_chain'], metrics: ['cpu_pct', 'net_out_kbps'], events: ['auth_failure_burst', 'login_after_failures'], hint: 'Login burst, then CPU and outbound network together; see Incidents for the correlated incident.' },
  { id: 'region_outage', label: 'REGION OUTAGE', names: ['region_outage', 'outage'], metrics: [], events: [], health: true, hint: 'Payloads stop arriving: health drops, then the backlog catches up.' },
  { id: 'backup_job', label: 'BACKUP JOB', names: ['backup_job'], metrics: ['cpu_pct'], events: [], hint: 'A repeating CPU burst the system learns as a scheduled job.' },
];

const RANGES = [{ l: '5 MIN', ms: 5 * 60e3 }, { l: '15 MIN', ms: 15 * 60e3 }, { l: '1 HOUR', ms: 3600e3 }];
const STATE_COLOR: Record<string, string> = { excellent: '#34d399', good: '#a3e635', fair: '#fbbf24', poor: '#f43f5e', offline: '#64748b' };
const SYSTEMS = [{ id: 'acme', label: 'SYSTEM 1' }, { id: 'globex', label: 'SYSTEM 2' }];

const median = (a: number[]) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const fmtT = (t: number) => new Date(t).toISOString().substring(11, 19);

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
        const [e, h] = await Promise.all([apiFetch<{ events: Ev[] }>('/api/events?limit=500'), apiFetch<{ history: Hist[] }>('/api/health/history?limit=300')]);
        if (stop) return;
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

  return (
    <div className="p-5 space-y-4 max-w-[1700px] mx-auto font-mono text-xs">
      {/* controls */}
      <div className="hud-panel p-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center bg-black/40 p-0.5 rounded border border-white/10">
          {SYSTEMS.map((s) => (
            <button key={s.id} onClick={() => setTenant(s.id)} className={`px-3 py-1 rounded font-bold ${tenant === s.id ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-white'}`}>{s.label}</button>
          ))}
        </div>
        <div className="flex items-center bg-black/40 p-0.5 rounded border border-white/10">
          {RANGES.map((r) => (
            <button key={r.l} onClick={() => setRangeMs(r.ms)} className={`px-3 py-1 rounded font-bold ${rangeMs === r.ms ? 'bg-purple-500 text-white' : 'text-slate-400 hover:text-white'}`}>{r.l}</button>
          ))}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-[10px] text-slate-400 uppercase font-bold">SHOP CHAOS AGENT</span>
          <input value={chaosUrl} onChange={(e) => saveUrl(e.target.value)} placeholder="http://192.168.137.56:9100"
            className="bg-black/50 border border-white/15 rounded px-2 py-1 w-60 text-slate-200 outline-none focus:border-sky-400" />
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${chaosOk ? 'bg-emerald-500/20 text-emerald-400' : chaosOk === false ? 'bg-rose-500/20 text-rose-400' : 'bg-slate-700 text-slate-300'}`}>
            {chaosOk ? `${shownMarks.length} RUNS IN RANGE` : chaosOk === false ? 'NOT REACHABLE' : 'ENTER ADDRESS FOR MARKERS'}
          </span>
        </div>
      </div>

      {/* scenario panel */}
      <div className="hud-panel p-4 space-y-3 border-sky-500/30">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-widest text-sky-400 font-bold mr-2">SCENARIO</span>
          {SCENARIOS.map((s) => (
            <button key={s.id} onClick={() => setScenario(s.id)}
              className={`px-3 py-1 rounded border font-bold ${scenario === s.id ? 'bg-sky-500/20 border-sky-400 text-sky-200' : 'border-white/10 text-slate-400 hover:text-white'}`}>{s.label}</button>
          ))}
        </div>
        <p className="text-slate-400">{sc.hint} Highlighted charts below are the ones this scenario should move.</p>
        {result ? (
          <div className="space-y-1">
            <div className="text-slate-500">Last run: {fmtT(result.m.started_at * 1000)} UTC for {result.m.duration_s} s</div>
            {result.lines.map((l, i) => (
              <div key={i} className={l.ok ? 'text-emerald-400' : 'text-amber-300'}>{l.ok ? '✓ SEEN' : '… NOT SEEN'} · {l.text}</div>
            ))}
          </div>
        ) : (
          <div className="text-slate-500">{chaosOk ? 'This scenario has not been run since the chaos agent started.' : 'Enter the shop chaos agent address above to see runs and their effect.'}</div>
        )}
      </div>

      {/* health timeline */}
      <div className="hud-panel p-4 space-y-2">
        <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">HEALTH STATE OVER TIME</span>
        <div className="relative h-6 rounded bg-black/40 overflow-hidden border border-white/5">
          {segs.map((g, i) => (
            <div key={i} title={`${g.state} from ${fmtT(g.s)}`} className="absolute top-0 bottom-0"
              style={{ left: `${((g.s - from) / (now - from)) * 100}%`, width: `${((g.e - g.s) / (now - from)) * 100}%`, background: STATE_COLOR[g.state] || '#475569', opacity: 0.85 }} />
          ))}
          {shownMarks.map((m) => <div key={m.id} className="absolute top-0 bottom-0 w-px bg-white" style={{ left: `${((m.started_at * 1000 - from) / (now - from)) * 100}%` }} />)}
        </div>
        <div className="flex justify-between text-[10px] text-slate-500">{ticks.map((t) => <span key={t}>{fmtT(t)}</span>)}</div>
        <div className="space-y-0.5 text-[11px]">
          {histHere.slice(-5).reverse().map((h) => (
            <div key={h.id} className="text-slate-400"><span style={{ color: STATE_COLOR[h.state] }}>{h.old_state ? `${h.old_state} → ` : ''}{h.state.toUpperCase()}</span> · {fmtT(new Date(h.at).getTime())} · {Array.isArray(h.reasons) ? h.reasons.join(', ') : String(h.reasons)}</div>
          ))}
          {histHere.length === 0 && <div className="text-slate-500">No health transitions recorded yet.</div>}
        </div>
      </div>

      {/* metric charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {METRICS.map((m) => {
          const data = bucket(series[m.name] || [], from, now);
          const b = base[m.name];
          const hot = sc.metrics.includes(m.name);
          const last = data[data.length - 1]?.v;
          return (
            <div key={m.name} className={`hud-panel p-3 ${hot ? 'border border-amber-400/70 shadow-[0_0_18px_rgba(251,191,36,0.15)]' : ''}`}>
              <div className="flex items-baseline justify-between">
                <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">{m.label}{hot && <span className="ml-2 text-amber-300">◄ {sc.label}</span>}</span>
                <span className="text-lg font-black text-slate-100">{last === undefined ? '—' : last.toFixed(m.step ? 0 : 1)}<span className="text-[10px] text-slate-500 ml-1">{m.unit}</span></span>
              </div>
              <div style={{ height: 120 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="#ffffff10" vertical={false} />
                    <XAxis dataKey="t" type="number" domain={[from, now]} ticks={ticks} tickFormatter={fmtT} tick={{ fontSize: 9, fill: '#64748b' }} />
                    <YAxis tick={{ fontSize: 9, fill: '#64748b' }} domain={m.step ? [0, 1] : [0, 'auto']} allowDecimals={false} />
                    <Tooltip contentStyle={{ background: '#0c1017', border: '1px solid #ffffff22', fontSize: 11 }} labelFormatter={(t) => fmtT(Number(t))} formatter={(v: any) => [Number(v).toFixed(2) + m.unit, m.label]} />
                    {b && !m.step && <ReferenceArea y1={Math.max(0, b.mean - 2 * b.std)} y2={b.mean + 2 * b.std} fill={m.color} fillOpacity={0.1} stroke="none" />}
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
        })}
      </div>

      {/* security events */}
      <div className="hud-panel p-4 space-y-2">
        <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">SECURITY &amp; SYSTEM EVENTS ({evInRange.length} IN RANGE)</span>
        <div className="relative h-14 rounded bg-black/40 border border-white/5 overflow-hidden">
          {evInRange.map((e) => {
            const x = ((new Date(e.event_time).getTime() - from) / (now - from)) * 100;
            const hotEv = sc.events.includes(e.category);
            return <div key={e.id} title={`${e.category} x${e.count} at ${fmtT(new Date(e.event_time).getTime())}`} className="absolute bottom-0 w-1.5 rounded-t"
              style={{ left: `${x}%`, height: `${Math.min(100, 18 + Math.log2(1 + e.count) * 14)}%`, background: hotEv ? '#fbbf24' : e.severity === 'high' || e.severity === 'critical' ? '#f43f5e' : '#38bdf8' }} />;
          })}
          {shownMarks.map((m) => <div key={m.id} className="absolute top-0 bottom-0 w-px bg-white/60" style={{ left: `${((m.started_at * 1000 - from) / (now - from)) * 100}%` }} />)}
        </div>
        <div className="max-h-40 overflow-y-auto divide-y divide-white/5">
          {evInRange.slice(0, 40).map((e) => (
            <div key={e.id} className="flex items-center gap-3 py-1 text-[11px]">
              <span className="text-slate-500 w-16">{fmtT(new Date(e.event_time).getTime())}</span>
              <span className={`px-1.5 rounded text-[10px] font-bold ${e.severity === 'high' || e.severity === 'critical' ? 'bg-rose-500/20 text-rose-300' : 'bg-sky-500/15 text-sky-300'}`}>{e.severity}</span>
              <span className="text-slate-200">{e.category}</span>
              <span className="text-slate-400">x{e.count}</span>
            </div>
          ))}
          {evInRange.length === 0 && <div className="py-3 text-center text-slate-500">No events in this time range.</div>}
        </div>
      </div>
    </div>
  );
};

export default TelemetryTab;
