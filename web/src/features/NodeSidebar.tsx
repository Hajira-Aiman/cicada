import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { useLiveStore } from '../stores/liveStore';
import { useUiStore } from '../stores/uiStore';
import { apiFetch } from '../services/apiClient';

const STATE_COLOR: Record<string, string> = { Excellent: '#34d399', Good: '#a3e635', Fair: '#fbbf24', Poor: '#f43f5e', Offline: '#64748b' };

// "3 s ago", live; red when the shop has been silent for more than 30 s
export const Ago: React.FC<{ iso: string }> = ({ iso }) => {
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(id); }, []);
  if (new Date(iso).getFullYear() < 2000) return <span className="text-slate-500">never</span>;   // a system that has not reported yet
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  const text = s < 90 ? `${s} s ago` : s < 5400 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
  return <span className={s > 30 ? 'text-rose-400 font-bold' : 'text-emerald-300 font-bold'}>{text}</span>;
};

const Row: React.FC<{ k: string; children: React.ReactNode }> = ({ k, children }) => (
  <div className="flex justify-between gap-4 py-1 border-b border-white/5"><span className="text-slate-500">{k}</span><span className="text-slate-100 text-right">{children}</span></div>
);

export const NodeSidebar: React.FC<{ node: string; onClose: () => void }> = ({ node, onClose }) => {
  const nav = useNavigate();
  const setTenant = useUiStore((s) => s.setActiveTenant);
  const guard = useLiveStore((s) => s.guards[node]);
  const metrics = useLiveStore((s) => s.metrics);
  const receipts = useLiveStore((s) => s.receipts);
  const incidents = useLiveStore((s) => s.incidents);
  const recon = useLiveStore((s) => s.reconciliation);
  const [aiops, setAiops] = useState<{ sources: number; updated: string } | null>(null);
  const [regions, setRegions] = useState<Record<string, boolean>>({});
  const isHq = node === 'hq';

  useEffect(() => {
    if (!isHq) return;
    let stop = false;
    const load = async () => {
      try {
        const h = await apiFetch<{ health: any[] }>('/api/health');
        const newest = h.health.reduce((m, r) => (String(r.updated) > m ? String(r.updated) : m), '');
        if (!stop) setAiops({ sources: h.health.length, updated: newest });
        const st: Record<string, boolean> = {};
        for (const r of ['in', 'eu']) st[r] = (await apiFetch<{ is_paused: boolean }>(`/api/regions/${r}/status`)).is_paused;
        if (!stop) setRegions(st);
      } catch { /* shown as unknown */ }
    };
    load();
    const id = setInterval(load, 4000);
    return () => { stop = true; clearInterval(id); };
  }, [isHq]);

  const panel = 'absolute top-0 right-0 bottom-0 w-[360px] max-w-[92%] bg-[#0b0f18]/95 backdrop-blur border-l border-white/10 shadow-2xl z-30 overflow-y-auto font-mono text-xs';
  const header = (title: string, sub: string, chip?: React.ReactNode) => (
    <div className="p-4 border-b border-white/10 flex items-start justify-between">
      <div><div className="text-sm font-black text-white tracking-wider">{title}</div><div className="text-slate-500 mt-0.5">{sub}</div>{chip && <div className="mt-2">{chip}</div>}</div>
      <button onClick={onClose} className="px-2 py-1 rounded border border-white/10 text-slate-300 hover:bg-white/10" aria-label="Close">✕</button>
    </div>
  );

  if (isHq) {
    const rows = Object.values(recon);
    const received = rows.reduce((n, r) => n + r.received_count, 0);
    const dups = rows.reduce((n, r) => n + r.duplicate_count, 0);
    const gaps = rows.reduce((n, r) => n + r.gaps.length, 0);
    return (
      <div className={panel}>
        {header('HEAD OFFICE', 'Cloud: ingest, ledger, AIOps, AI')}
        <div className="p-4 space-y-4">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">INGEST</div>
            <Row k="India region">{regions.in === undefined ? '—' : regions.in ? <b className="text-rose-400">PAUSED</b> : <b className="text-emerald-300">ACCEPTING</b>}</Row>
            <Row k="Europe region">{regions.eu === undefined ? '—' : regions.eu ? <b className="text-rose-400">PAUSED</b> : <b className="text-emerald-300">ACCEPTING</b>}</Row>
            <Row k="Payloads stored">{received.toLocaleString()}</Row>
            <Row k="Duplicates blocked">{dups}</Row>
            <Row k="Missing sequence numbers">{gaps}</Row>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">AIOPS</div>
            <Row k="Sources tracked">{aiops ? aiops.sources : '—'}</Row>
            <Row k="Last health update">{aiops?.updated ? <Ago iso={aiops.updated} /> : '—'}</Row>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold mb-1">LATEST INCIDENTS</div>
            {incidents.slice(0, 3).map((i) => (
              <div key={i.incident_id} className="py-1.5 border-b border-white/5">
                <div className="text-slate-100">{i.title}</div>
                <div className="text-slate-500">{i.severity} · {i.tenant_id === 'acme' ? 'System 1' : i.tenant_id === 'globex' ? 'System 2' : i.tenant_id} · {i.status}</div>
              </div>
            ))}
            {incidents.length === 0 && <div className="text-slate-500 py-1">No incidents.</div>}
          </div>
          <div className="flex gap-2">
            <button onClick={() => nav('/incidents')} className="flex-1 py-2 rounded bg-sky-500 text-black font-black">OPEN INCIDENTS</button>
            <button onClick={() => nav('/privacy')} className="flex-1 py-2 rounded border border-white/15 text-slate-200 font-bold">PRIVACY &amp; PROOF</button>
          </div>
        </div>
      </div>
    );
  }

  if (!guard) return <div className={panel}>{header('SYSTEM', 'No guard has reported yet')}</div>;
  const label = guard.tenant_id === 'acme' ? 'SYSTEM 1' : guard.tenant_id === 'globex' ? 'SYSTEM 2' : guard.tenant_id.toUpperCase();
  const series = (name: string) => metrics[`${guard.tenant_id}:${name}`] || [];
  const last = (name: string, d = 0, unit = '') => { const v = series(name).slice(-1)[0]?.avg; return v === undefined ? '—' : `${v.toFixed(d)}${unit}`; };
  const perMin = receipts.filter((r) => r.guard_id === guard.guard_id && Date.now() - new Date(r.received_at).getTime() < 60000).length;
  const open = incidents.filter((i) => i.tenant_id === guard.tenant_id && i.status !== 'resolved').length;
  const spark = series('cpu_pct').slice(-60).map((p) => ({ v: p.avg }));
  const goto = (path: string) => { setTenant(guard.tenant_id as any); nav(path); };
  return (
    <div className={panel}>
      {header(label, `Local guard · ${guard.source}`, <span className="px-2 py-0.5 rounded font-bold border border-white/10" style={{ color: STATE_COLOR[guard.state] }}>● {guard.state.toUpperCase()}</span>)}
      <div className="p-4 space-y-4">
        <div className="text-slate-300">{guard.reasons.length ? guard.reasons.join(' · ') : 'All metrics within their normal band.'}</div>
        <div>
          <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">CPU, LAST MINUTES</div>
          <div style={{ height: 70 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={spark}><YAxis hide domain={[0, 'auto']} /><Line type="monotone" dataKey="v" stroke="#38BDF8" strokeWidth={2} dot={false} isAnimationActive={false} /></LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div>
          <Row k="CPU">{last('cpu_pct', 0, '%')}</Row>
          <Row k="Memory">{last('mem_pct', 0, '%')}</Row>
          <Row k="Disk">{last('disk_pct', 0, '%')}</Row>
          <Row k="Latency">{last('latency_ms', 0, ' ms')}</Row>
          <Row k="Packet loss">{last('packet_loss_pct', 1, '%')}</Row>
          <Row k="Net out">{last('net_out_kbps', 0, ' kbps')}</Row>
          <Row k="Payloads / min">{perMin}</Row>
          <Row k="Last seen"><Ago iso={guard.last_seen} /></Row>
          <Row k="Buffer depth">{guard.buffer_depth}</Row>
          <Row k="Guard version">{guard.guard_version}</Row>
          <Row k="Open incidents">{open}</Row>
        </div>
        <div className="flex gap-2">
          <button onClick={() => goto('/telemetry')} className="flex-1 py-2 rounded bg-sky-500 text-black font-black">TELEMETRY VIEW</button>
          <button onClick={() => goto('/incidents')} className="flex-1 py-2 rounded border border-white/15 text-slate-200 font-bold">INCIDENTS</button>
        </div>
      </div>
    </div>
  );
};
