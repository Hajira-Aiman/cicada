import React, { useState, useEffect } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { useLiveStore } from '../../stores/liveStore';
import { StatusBadge } from '../../components/StatusBadge';
import { TimeText } from '../../components/TimeText';

export const PhoneApp: React.FC = () => {
  const location = useLocation();
  const path = location.pathname;

  // Views: join, approve, raw, smart
  const view = path.includes('approve') ? 'approve' :
               path.includes('raw') ? 'raw' :
               path.includes('smart') ? 'smart' : 'join';

  const alerts = useLiveStore((s) => s.alerts);
  const incidents = useLiveStore((s) => s.incidents);
  const actions = useLiveStore((s) => s.actions);
  const updateActionState = useLiveStore((s) => s.updateActionState);

  // Join state
  const [deviceId] = useState(() => `phone-${Math.random().toString(16).substring(2, 6)}`);
  const [latency, setLatency] = useState(42);
  const [connected, setConnected] = useState(true);

  // Approve state
  const [approverName, setApproverName] = useState('Judge-01');
  const [dryRunDone, setDryRunDone] = useState(false);
  const [approved, setApproved] = useState(false);

  // Raw alerts buzz simulation
  const [buzzCount, setBuzzCount] = useState(0);

  useEffect(() => {
    if (view === 'join') {
      const interval = setInterval(() => {
        setLatency(35 + Math.floor(Math.random() * 20));
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [view]);

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
                <span className="text-sm font-bold text-emerald-400 font-tabular">{latency} ms</span>
              </div>
              <div className="p-3 rounded bg-[#121620] border border-white/5">
                <span className="text-[10px] text-slate-500 block">REGION ASSIGNED</span>
                <span className="text-sm font-bold text-white uppercase">INDIA (IN)</span>
              </div>
            </div>
          </div>
        )}

        {/* VIEW: APPROVE */}
        {view === 'approve' && (
          <div className="space-y-4">
            <div className="hud-panel p-4 space-y-3 border border-cyan-500/30">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-cyan-400 font-bold uppercase">1-TAP REMEDIATION</span>
                <StatusBadge status="high" />
              </div>
              <h3 className="text-sm font-bold text-white">Cryptomining Containment</h3>
              <p className="text-xs text-slate-300">
                Action: <strong className="text-sky-300">kill_process proc-1a2b3c4d</strong>
              </p>
              <div className="text-[10px] text-slate-400">
                Risk: LOW · Reversible: YES · Rollback window: 120s
              </div>

              <div className="pt-2 border-t border-white/5 space-y-2">
                <label className="text-[10px] text-slate-400 uppercase block">Approver Name</label>
                <input
                  type="text"
                  value={approverName}
                  onChange={(e) => setApproverName(e.target.value)}
                  className="w-full bg-[#080A10] border border-slate-700 p-2 text-xs text-white rounded"
                />

                <div className="grid grid-cols-2 gap-2 pt-1">
                  <button
                    onClick={() => setDryRunDone(true)}
                    className="py-2 rounded bg-slate-800 text-slate-200 font-bold border border-slate-600"
                  >
                    1. DRY RUN
                  </button>
                  <button
                    onClick={() => {
                      setApproved(true);
                      updateActionState('act-001', 'approved', approverName);
                    }}
                    disabled={!dryRunDone || approved}
                    className={`py-2 rounded font-bold ${
                      approved
                        ? 'bg-emerald-600/30 text-emerald-400 border border-emerald-500/40'
                        : dryRunDone
                        ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                        : 'bg-slate-800 text-slate-600 cursor-not-allowed'
                    }`}
                  >
                    {approved ? '✓ APPROVED' : '2. APPROVE'}
                  </button>
                </div>

                {dryRunDone && (
                  <div className="p-2 rounded bg-black/60 text-[10px] text-cyan-300">
                    ✓ Dry run simulated: 0 casualties, CPU drops to 22%.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* VIEW: RAW (Noisy stream comparison) */}
        {view === 'raw' && (
          <div className="space-y-3">
            <div className="p-3 rounded bg-rose-950/20 border border-rose-500/30 text-center">
              <span className="text-[10px] text-rose-400 font-bold uppercase block">
                RAW ALERT STREAM (NOISE DEMO)
              </span>
              <span className="text-xl font-bold text-rose-300 mt-1 block">
                {alerts.length + 40} RAW ALERTS
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
            <div className="p-3 rounded bg-emerald-950/20 border border-emerald-500/30 text-center">
              <span className="text-[10px] text-emerald-400 font-bold uppercase block">
                AIOPS CORRELATED STREAM (CLEAN DEMO)
              </span>
              <span className="text-xl font-bold text-emerald-300 mt-1 block">
                {incidents.length} CORRELATED INCIDENTS
              </span>
              <span className="text-[10px] text-emerald-400 font-bold">94% NOISE CUT ACTIVE</span>
            </div>

            <div className="space-y-3">
              {incidents.map((inc) => (
                <div key={inc.incident_id} className="p-3 rounded bg-[#121620] border border-emerald-500/20 space-y-2">
                  <div className="flex justify-between items-start">
                    <span className="text-white font-bold text-xs">{inc.title}</span>
                    <StatusBadge status={inc.severity} />
                  </div>
                  <p className="text-[11px] text-slate-300">{inc.narrative || inc.counterfactual}</p>
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
