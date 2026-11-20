import React from 'react';
import { useLiveStore } from '../stores/liveStore';

export const LatencyMeter: React.FC = () => {
  const latencySamples = useLiveStore((s) => s.latencySamples);

  const values = latencySamples.map((s) => s.latency_ms);
  const sorted = [...values].sort((a, b) => a - b);
  const p50 = sorted.length ? Math.round(sorted[Math.floor(sorted.length * 0.5)]) : '—';
  const p95 = sorted.length ? Math.round(sorted[Math.floor(sorted.length * 0.95)]) : '—';

  return (
    <div className="hud-panel p-3 flex items-center justify-between font-mono text-xs">
      <div className="flex items-center space-x-3">
        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-bold">
          LATENCY METER (EVENT → RENDER)
        </span>
        <span className="text-slate-300">
          p50: <strong className="text-emerald-400">{p50} ms</strong>
        </span>
        <span className="text-slate-300">
          p95: <strong className="text-cyan-400">{p95} ms</strong>
        </span>
      </div>
      <div className="flex items-center space-x-3 text-[11px] text-slate-500">
        <span>ALERT DELAY &lt;15s</span>
        <span>·</span>
        <span>OFFLINE DELAY &lt;60s</span>
      </div>
    </div>
  );
};
