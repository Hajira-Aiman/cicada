import { api, apiFetch } from '../../services/apiClient';
import { useLiveSync } from '../../services/liveSync';
import { useUiStore } from '../../stores/uiStore';
import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useLiveStore } from '../../stores/liveStore';
import { StatusBadge } from '../../components/StatusBadge';
import { TimeText } from '../../components/TimeText';

const PhoneLogin: React.FC = () => {
  const setAuth = useUiStore((s) => s.setAuth);
  const [u, setU] = useState('admin'); const [p, setP] = useState('admin123'); const [err, setErr] = useState('');
  return (
    <form className="hud-panel p-4 space-y-2" onSubmit={async (e) => { e.preventDefault(); try { const r = await api.login(u, p); setAuth(r.token, r.user_id, r.role as any, r.tenant_id || undefined); } catch (x: any) { setErr(x.message); } }}>
      <span className="text-[10px] text-slate-400 uppercase block">Approver login</span>
      <input value={u} onChange={(e) => setU(e.target.value)} className="w-full bg-[#080A10] border border-slate-700 p-2 text-white rounded" />
      <input type="password" value={p} onChange={(e) => setP(e.target.value)} className="w-full bg-[#080A10] border border-slate-700 p-2 text-white rounded" />
      {err && <div className="text-rose-400">{err}</div>}
      <button className="w-full py-2 rounded bg-sky-600 text-white font-bold">LOG IN</button>
    </form>
  );
};

export const PhoneApp: React.FC = () => {
  const location = useLocation();
  const path = location.pathname;

  // Views: join, approve, raw, smart
  const view = path.includes('approve') ? 'approve' :
               path.includes('raw') ? 'raw' :
               path.includes('smart') ? 'smart' : 'join';

  const alerts = useLiveStore((s) => s.alerts);
  const incidents = useLiveStore((s) => s.incidents);
  const counters = useLiveStore((s) => s.counters);
  const token = useUiStore((s) => s.authToken);
  useLiveSync();   // alerts, incidents and counters come from head office; needs the login below
  const [intent, setIntent] = useState<any>(null);
  const [note, setNote] = useState('');

  // Join state
  const [deviceId] = useState(() => `phone-${Math.random().toString(16).substring(2, 6)}`);
  const [latency, setLatency] = useState(42);
  const [connected, setConnected] = useState(true);

  const [approverName, setApproverName] = useState('Judge-01');
  const call = async (path: string, body?: object) => {
    try {
      const r = await apiFetch<any>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined });
      setNote(r.simulation?.impact || `OK: ${r.status}`);
    } catch (e: any) { setNote(e.message); }
  };
  useEffect(() => {
    if (view !== 'approve' || !token) return;
    const load = () => apiFetch<{ intents: any[] }>('/api/actions?limit=10').then((r) => setIntent(r.intents.find((i) => ['proposed', 'dry_run_done', 'approved'].includes(i.status)) || null)).catch(() => {});
    load();
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [view, token]);

  // Raw alerts buzz simulation
  const [buzzCount, setBuzzCount] = useState(0);

  // real heartbeat: measure the round trip to head office, report it, show the colour head office assigns (red above 150 ms)
  const [color, setColor] = useState<'green' | 'red' | null>(null);
  useEffect(() => {
    if (view !== 'join') return;
    let live = true;
    const beat = async () => {
      try {
        const t0 = performance.now();
        await apiFetch('/health');
        const rtt = Math.round(performance.now() - t0);
        setLatency(rtt);
        const r = await apiFetch<{ color: 'green' | 'red' }>('/api/phones/heartbeat', { method: 'POST', body: JSON.stringify({ phone_id: deviceId, latency_ms: rtt }) });
        if (live) { setColor(r.color); setConnected(true); }
      } catch { if (live) setConnected(false); }
    };
    beat();
    const interval = setInterval(beat, 2000);
    return () => { live = false; clearInterval(interval); };
  }, [view, deviceId]);

  useEffect(() => {
    if (view === 'raw' && alerts.length > 0) {
      setBuzzCount((b) => b + 1);
      // Attempt mobile navigator vibration if available
      if (typeof window !== 'undefined' && 'vibrate' in navigator) {
        try { navigator.vibrate(200); } catch {}
      }
    }
  }, [alerts, view]);

  return (
    <div className="min-h-screen max-w-md mx-auto bg-[#080A10] text-[#D1D5DB] font-mono text-xs flex flex-col border-x border-white/10 shadow-2xl">
      {/* Top Mobile Bar */}
      <header className="h-12 bg-[#0C1017] border-b border-white/[0.08] px-3 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="font-bold text-white text-sm">AIRLOCK MOBILE</span>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        </div>
        <div className="flex space-x-1 text-[10px]">
          <Link
            to="/m/join"
            className={`px-2 py-0.5 rounded font-bold ${view === 'join' ? 'bg-sky-500 text-black' : 'text-slate-400'}`}
          >
            JOIN
          </Link>
          <Link
            to="/m/approve"
            className={`px-2 py-0.5 rounded font-bold ${view === 'approve' ? 'bg-sky-500 text-black' : 'text-slate-400'}`}
          >
            APPROVE
          </Link>
          <Link
            to="/m/raw"
            className={`px-2 py-0.5 rounded font-bold ${view === 'raw' ? 'bg-rose-500 text-black' : 'text-slate-400'}`}
          >
            RAW
          </Link>
          <Link
            to="/m/smart"
            className={`px-2 py-0.5 rounded font-bold ${view === 'smart' ? 'bg-emerald-500 text-black' : 'text-slate-400'}`}
          >
            SMART
          </Link>
        </div>
      </header>

      {/* Content Body */}
      <main className="p-4 flex-1 space-y-4">
        {/* VIEW: JOIN */}
        {view === 'join' && (
          <div className="space-y-4 text-center">
            <div className="p-6 rounded-xl bg-[#0C1017] border border-white/10 space-y-3">
              <span className="w-12 h-12 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center justify-center mx-auto text-lg font-bold">
                ✓
              </span>
              <h2 className="text-base font-bold text-white">CONNECTED AS COLLECTOR</h2>
              <div className="text-xs text-sky-400 font-bold">{deviceId}</div>
              <p className="text-[11px] text-slate-400">
                This device is participating in the Live Fleet Bridge. Sending telemetry heartbeat every 2s.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 text-left">
              <div className="p-3 rounded bg-[#121620] border border-white/5">
                <span className="text-[10px] text-slate-500 block">DEVICE LATENCY</span>
                <span className={`text-sm font-bold font-tabular ${color === 'red' ? 'text-rose-400' : 'text-emerald-400'}`}>{latency} ms</span>
              </div>
              <div className="p-3 rounded bg-[#121620] border border-white/5">
                <span className="text-[10px] text-slate-500 block">REGION ASSIGNED</span>
                <span className="text-sm font-bold text-white uppercase">INDIA (IN)</span>
              </div>
            </div>
          </div>
        )}

        {/* VIEW: APPROVE (real intents from head office) */}
        {view === 'approve' && (
          <div className="space-y-4">
            {!token && <PhoneLogin />}
            {token && !intent && <div className="hud-panel p-4 text-slate-400">No remediation is waiting. Propose one from an incident card on the projector.</div>}
            {token && intent && (
            <div className="hud-panel p-4 space-y-3 border border-cyan-500/30">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-cyan-400 font-bold uppercase">1-TAP REMEDIATION · {intent.status.toUpperCase()}</span>
                <StatusBadge status="high" />
              </div>
              <h3 className="text-sm font-bold text-white">{intent.tenant_id.toUpperCase()}</h3>
              <p className="text-xs text-slate-300">
                Action: <strong className="text-sky-300">{intent.action} {intent.target}</strong>
              </p>
              <div className="text-[10px] text-slate-400">
                Risk: {String(intent.risk).toUpperCase()} · Rollback window: 120s
              </div>

              <div className="pt-2 border-t border-white/5 space-y-2">
                <label className="text-[10px] text-slate-400 uppercase block">Approver Name</label>
                <input type="text" value={approverName} onChange={(e) => setApproverName(e.target.value)}
                  className="w-full bg-[#080A10] border border-slate-700 p-2 text-xs text-white rounded" />

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <button onClick={() => call(`/api/actions/${intent.intent_id}/dry-run`)}
                    className="py-2 rounded bg-slate-800 text-slate-200 font-bold border border-slate-600">1. DRY RUN</button>
                  <button onClick={() => call(`/api/actions/${intent.intent_id}/approve`, { approved_by: approverName })}
                    disabled={intent.status !== 'dry_run_done'}
                    className={`py-2 rounded font-bold ${intent.status === 'approved' ? 'bg-emerald-600/30 text-emerald-400 border border-emerald-500/40'
                      : intent.status === 'dry_run_done' ? 'bg-emerald-600 hover:bg-emerald-500 text-white' : 'bg-slate-800 text-slate-600 cursor-not-allowed'}`}>
                    {intent.status === 'approved' ? '✓ APPROVED' : '2. APPROVE'}
                  </button>
                </div>
                {note && <div className="p-2 rounded bg-black/60 text-[10px] text-cyan-300">{note}</div>}
              </div>
            </div>
            )}
          </div>
        )}

        {/* VIEW: RAW (Noisy stream comparison) */}
        {view === 'raw' && (
          <div className="space-y-3">
            {!token && <PhoneLogin />}
            <div className="p-3 rounded bg-rose-950/20 border border-rose-500/30 text-center">
              <span className="text-[10px] text-rose-400 font-bold uppercase block">
                RAW ALERT STREAM (NOISE DEMO)
              </span>
              <span className="text-xl font-bold text-rose-300 mt-1 block">
                {counters.raw_alerts} RAW ALERTS
              </span>
              <span className="text-[10px] text-slate-400">Vibrates on every unsuppressed threshold hit</span>
            </div>

            <div className="space-y-2">
              {alerts.slice(0, 10).map((a) => (
                <div key={a.alert_id} className="p-2 rounded bg-[#121620] border border-white/5 space-y-1">
                  <div className="flex justify-between text-[10px]">
                    <span className="text-white font-bold">{a.title}</span>
                    <span className="text-rose-400 font-bold">{a.severity.toUpperCase()}</span>
                  </div>
                  <p className="text-[11px] text-slate-400">{a.body || 'Threshold exceeded on source'}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* VIEW: SMART (Filtered incidents only) */}
        {view === 'smart' && (
          <div className="space-y-3">
            {!token && <PhoneLogin />}
            <div className="p-3 rounded bg-emerald-950/20 border border-emerald-500/30 text-center">
              <span className="text-[10px] text-emerald-400 font-bold uppercase block">
                AIOPS CORRELATED STREAM (CLEAN DEMO)
              </span>
              <span className="text-xl font-bold text-emerald-300 mt-1 block">
                {incidents.length} CORRELATED INCIDENTS
              </span>
              <span className="text-[10px] text-emerald-400 font-bold">{counters.raw_alerts ? Math.round((1 - counters.incidents / counters.raw_alerts) * 100) : 0}% NOISE CUT</span>
            </div>

            <div className="space-y-3">
              {incidents.map((inc) => (
                <div key={inc.incident_id} className="p-3 rounded bg-[#121620] border border-emerald-500/20 space-y-2">
                  <div className="flex justify-between items-start">
                    <span className="text-white font-bold text-xs">{inc.title}</span>
                    <StatusBadge status={inc.severity} />
                  </div>
                  <p className="text-[11px] text-slate-300">{inc.narrative || inc.counterfactual || ''}</p>
                  <div className="text-[10px] text-slate-500">
                    Confidence: <strong className="text-cyan-400">{Math.round(inc.confidence * 100)}%</strong>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
};
