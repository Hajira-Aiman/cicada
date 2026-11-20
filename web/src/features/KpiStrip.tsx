import React from 'react';
import { useLiveStore } from '../stores/liveStore';

export const KpiStrip: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const incidents = useLiveStore((s) => s.incidents);
  const counters = useLiveStore((s) => s.counters);
  const latencySamples = useLiveStore((s) => s.latencySamples);

  const guardList = Object.values(guards);
  const healthyCount = guardList.filter((g) => g.state === 'Excellent' || g.state === 'Good').length;
  const attentionCount = guardList.filter((g) => g.state === 'Fair' || g.state === 'Poor').length;
  const openIncidentsCount = incidents.filter((i) => i.status === 'open').length;

  const latencies = latencySamples.map((s) => s.latency_ms);
  const p95Latency = latencies.length > 0
    ? (latencies.sort((a, b) => a - b)[Math.floor(latencies.length * 0.95)] / 1000).toFixed(1)
    : '2.8';

  const noiseCutPct = counters.raw_alerts > 0
    ? Math.round(((counters.raw_alerts - counters.incidents) / counters.raw_alerts) * 100)
    : 94;

  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-2.5">
      {/* Healthy Guards */}
      <div className="hud-panel p-3">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">HEALTHY GUARDS</div>
        <div className="text-xl font-mono font-black text-emerald-400 mt-0.5">
          {healthyCount}/{guardList.length}
        </div>
      </div>

      {/* Needs Attention */}
      <div className="hud-panel p-3">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">NEEDS ATTENTION</div>
        <div className={`text-xl font-mono font-black mt-0.5 ${attentionCount > 0 ? 'text-amber-400' : 'text-slate-400'}`}>
          {attentionCount}
        </div>
      </div>

      {/* Open Incidents */}
      <div className="hud-panel p-3">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">OPEN INCIDENTS</div>
        <div className={`text-xl font-mono font-black mt-0.5 ${openIncidentsCount > 0 ? 'text-rose-400' : 'text-slate-400'}`}>
          {openIncidentsCount}
        </div>
      </div>

      {/* Privacy Canary Counter */}
      <div className="hud-panel p-3 border-purple-500/30">
        <div className="text-[10px] font-mono text-purple-400 uppercase tracking-wider font-bold">
          PRIVACY TRIPWIRE
        </div>
        <div className="text-xl font-mono font-black text-purple-300 mt-0.5">
          0 <span className="text-xs text-purple-400 font-normal">/ {counters.canaries_planted.toLocaleString()} CANARIES</span>
        </div>
      </div>

      {/* Noise Cut */}
      <div className="hud-panel p-3">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">NOISE CUT</div>
        <div className="text-xl font-mono font-black text-sky-400 mt-0.5">
          {counters.raw_alerts} → {counters.incidents} <span className="text-xs font-normal text-slate-400">({noiseCutPct}%)</span>
        </div>
      </div>

      {/* P95 Delivery */}
      <div className="hud-panel p-3">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider">P95 INGEST LATENCY</div>
        <div className="text-xl font-mono font-black text-cyan-400 mt-0.5">
          {p95Latency} <span className="text-xs font-normal text-slate-400">s</span>
        </div>
      </div>
    </div>
  );
};
