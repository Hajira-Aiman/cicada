import React, { useState } from 'react';

export const SettingsTab: React.FC = () => {
  const [cpuThreshold, setCpuThreshold] = useState(85);
  const [latencyThreshold, setLatencyThreshold] = useState(200);
  const [memThreshold, setMemThreshold] = useState(90);
  const [flapsDamping, setFlapsDamping] = useState(3);
  const [saved, setSaved] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReset = () => {
    setCpuThreshold(85);
    setLatencyThreshold(200);
    setMemThreshold(90);
    setFlapsDamping(3);
  };

  return (
    <div className="p-4 space-y-4 max-w-[900px] mx-auto font-mono text-xs">
      <div>
        <h2 className="text-base font-bold text-white tracking-widest">
          AIOPS THRESHOLDS & DAMPING CONFIGURATION
        </h2>
        <p className="text-slate-400 text-[11px] mt-0.5">
          Tune automated anomaly detection thresholds per tenant. Changes sync with AIOps worker engine.
        </p>
      </div>

      <form onSubmit={handleSave} className="hud-panel p-6 space-y-5">
        <div className="space-y-4">
          <div>
            <div className="flex justify-between text-xs mb-1">
              <label className="text-slate-300 font-bold">CPU Elevated Anomaly Threshold (%)</label>
              <span className="text-sky-400 font-bold">{cpuThreshold}%</span>
            </div>
            <input
              type="range"
              min="50"
              max="98"
              value={cpuThreshold}
              onChange={(e) => setCpuThreshold(Number(e.target.value))}
              className="w-full accent-sky-400 cursor-pointer"
            />
            <span className="text-[10px] text-slate-500">Consecutive windows above this trigger Fair/Poor transition.</span>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-1">
              <label className="text-slate-300 font-bold">Latency SLA Spike Threshold (ms)</label>
              <span className="text-sky-400 font-bold">{latencyThreshold} ms</span>
            </div>
            <input
              type="range"
              min="50"
              max="1000"
              step="10"
              value={latencyThreshold}
              onChange={(e) => setLatencyThreshold(Number(e.target.value))}
              className="w-full accent-sky-400 cursor-pointer"
            />
            <span className="text-[10px] text-slate-500">Triggers degraded latency alert if p95 exceeds window.</span>
          </div>

          <div>
            <div className="flex justify-between text-xs mb-1">
              <label className="text-slate-300 font-bold">Memory Critical Limit (%)</label>
              <span className="text-sky-400 font-bold">{memThreshold}%</span>
            </div>
            <input
              type="range"
              min="60"
              max="99"
              value={memThreshold}
              onChange={(e) => setMemThreshold(Number(e.target.value))}
              className="w-full accent-sky-400 cursor-pointer"
            />
          </div>

          <div>
            <div className="flex justify-between text-xs mb-1">
              <label className="text-slate-300 font-bold">Flap Prevention Damping Windows</label>
              <span className="text-cyan-400 font-bold">{flapsDamping} windows</span>
            </div>
            <input
              type="range"
              min="1"
              max="10"
              value={flapsDamping}
              onChange={(e) => setFlapsDamping(Number(e.target.value))}
              className="w-full accent-cyan-400 cursor-pointer"
            />
            <span className="text-[10px] text-slate-500">Requires state to remain healthy for N windows before clearing alerts.</span>
          </div>
        </div>

        <div className="pt-4 border-t border-white/5 flex items-center justify-between">
          <button
            type="button"
            onClick={handleReset}
            className="px-3 py-1.5 rounded bg-slate-800 text-slate-400 hover:text-white"
          >
            RESET TO DEFAULTS
          </button>
          <div className="flex items-center space-x-3">
            {saved && <span className="text-emerald-400 font-bold">✓ THRESHOLDS APPLIED</span>}
            <button
              type="submit"
              className="px-5 py-1.5 rounded bg-sky-500 hover:bg-sky-400 text-black font-bold"
            >
              SAVE CONFIGURATION
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};
