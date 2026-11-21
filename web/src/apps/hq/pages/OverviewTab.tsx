import React, { useState } from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { MetricChart } from '@/components/MetricChart';
import { StatusBadge } from '@/components/StatusBadge';
import { Ago } from '@/features/NodeSidebar';
import { GuardInfo, Incident } from '@/types';

const offlineGuard = (id: string, tenant: string, region: 'in' | 'eu'): GuardInfo => ({
  guard_id: id, tenant_id: tenant, source: '—', region, state: 'Offline', reasons: ['no guard reporting'],
  since: new Date(0).toISOString(), last_seen: new Date(0).toISOString(), guard_version: '—', guard_cpu_pct: 0, guard_mem_mb: 0,
  buffer_depth: 0, config_ok: false, canaries_planted: 0, secrets_redacted: 0, flaps_prevented: 0, policy_hash: '—',
});

export const OverviewTab: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const metrics = useLiveStore((s) => s.metrics);
  const incidents = useLiveStore((s) => s.incidents);
  const counters = useLiveStore((s) => s.counters);
  const activeTenant = useUiStore((s) => s.activeTenant);
  const setActiveTenant = useUiStore((s) => s.setActiveTenant);
  const setSelectedGuardId = useUiStore((s) => s.setSelectedGuardId);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);

  const [signalsOpen, setSignalsOpen] = useState(false);

  // Strictly 2 Systems: System 1 (acme) and System 2 (globex)
  const system1: GuardInfo = Object.values(guards).find((g) => g.tenant_id === 'acme') || offlineGuard('guard-acme-01', 'acme', 'in');
  const system2: GuardInfo = Object.values(guards).find((g) => g.tenant_id === 'globex') || offlineGuard('guard-globex-01', 'globex', 'eu');

  const systems = [
    { label: 'SYSTEM 1', key: 'acme', data: system1 },
    { label: 'SYSTEM 2', key: 'globex', data: system2 },
  ];

  const overallHealthy = ![system1, system2].filter((g) => new Date(g.last_seen).getFullYear() > 2000).some((g) => g.state === 'Poor' || g.state === 'Offline');
  const noiseCutPct = counters.raw_alerts > 0
    ? Math.round(((counters.raw_alerts - counters.incidents) / counters.raw_alerts) * 100)
    : 0;

  // Selected system chart data
  const chartTenant = activeTenant === 'globex' ? 'globex' : 'acme';
  const cpuData = metrics[`${chartTenant}:cpu_pct`] || [];
  const latencyData = metrics[`${chartTenant}:latency_ms`] || [];

  const activeIncidents = incidents.filter(
    (i) => activeTenant === 'ALL' || i.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const handleSystemClick = (guardId: string) => {
    setSelectedGuardId(guardId);
    setInspectorOpen(true);
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto font-sans">
      {/* SECTION 1: Minimalist 4-Stat KPI Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Stat 1: Systems Monitored */}
        <div className="hud-panel p-4 flex flex-col justify-between">
          <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">
            SYSTEMS MONITORED
          </span>
          <div className="flex items-center space-x-2 mt-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-2xl font-mono font-black text-white">{[system1, system2].filter((g) => g.state !== 'Offline').length} / 2</span>
            <span className="text-xs font-mono text-emerald-400 font-bold">ACTIVE</span>
          </div>
        </div>

        {/* Stat 2: Fleet Health */}
        <div className="hud-panel p-4 flex flex-col justify-between">
          <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">
            OVERALL STATUS
          </span>
          <div className="flex items-center space-x-2 mt-2">
            <span className={`text-2xl font-mono font-black ${overallHealthy ? 'text-emerald-400' : 'text-rose-400'}`}>
              {overallHealthy ? 'HEALTHY' : 'NEEDS ATTENTION'}
            </span>
          </div>
        </div>

        {/* Stat 3: AIOps Noise Cut */}
        <div className="hud-panel p-4 flex flex-col justify-between">
          <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">
            AIOPS NOISE CUT
          </span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className="text-2xl font-mono font-black text-sky-400">{noiseCutPct}%</span>
            <span className="text-xs font-mono text-slate-400">
              ({counters.raw_alerts} → {counters.incidents})
            </span>
          </div>
        </div>

        {/* Stat 4: Privacy Tripwire */}
        <div className="hud-panel p-4 border-purple-500/30 flex flex-col justify-between">
          <span className="text-[10px] font-mono uppercase tracking-widest text-purple-400 font-bold">
            PRIVACY TRIPWIRE
          </span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className="text-2xl font-mono font-black text-purple-300">{counters.leaks_detected} LEAKS</span>
            <span className="text-xs font-mono text-slate-400">/ {counters.canaries_planted.toLocaleString()} Canaries</span>
          </div>
        </div>
      </div>

      {/* SECTION 2: Clean Cards for System 1 & System 2 (Only 2 Systems) */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
            PROTECTED SYSTEMS (LOCAL GUARDS)
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            CLICK CARD TO VIEW DETAILED HARDWARE METRICS
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {systems.map((s) => {
            const isPoor = s.data.state === 'Poor';
            return (
              <div
                key={s.key}
                onClick={() => handleSystemClick(s.data.guard_id)}
                className={`hud-panel p-5 cursor-pointer transition-all hover:border-slate-500 ${
                  isPoor ? 'border-rose-500/40 bg-rose-950/10' : ''
                }`}
              >
                {/* Header */}
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-base font-mono font-bold text-white tracking-wide">
                      {s.label}
                    </h3>
                    <span className="text-xs font-mono text-slate-500 mt-0.5 block">
                      Local Guard · {s.data.source}
                    </span>
                  </div>
                  <StatusBadge status={s.data.state} />
                </div>

                {/* 1-Line Clean Reason */}
                <div className="mt-3 py-2 px-3 rounded bg-black/40 border border-white/5">
                  <span className="text-[10px] font-mono uppercase text-slate-500 block font-bold">
                    HEALTH DIAGNOSTIC
                  </span>
                  <p className="text-xs font-mono text-slate-200 mt-0.5 truncate">
                    {s.data.reasons && s.data.reasons.length > 0 ? s.data.reasons.join(' · ') : 'Optimal baseline'}
                  </p>
                </div>

                {/* Live gauges: the shop machine's own numbers from telemetry */}
                {(() => {
                  const last = (n: string) => (metrics[`${s.key}:${n}`] || []).slice(-1)[0]?.avg;
                  const cpu = last('cpu_pct'), mem = last('mem_pct'), lat = last('latency_ms');
                  const bar = (v: number | undefined, color: string) => (
                    <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden"><div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(100, v ?? 0)}%` }} /></div>
                  );
                  return (
                    <div className="grid grid-cols-3 gap-4 mt-4 pt-3 border-t border-white/5">
                      <div><div className="flex justify-between text-xs font-mono mb-1"><span className="text-slate-400">CPU</span><span className="text-white font-bold">{cpu === undefined ? '—' : `${cpu.toFixed(0)}%`}</span></div>{bar(cpu, isPoor ? 'bg-rose-500' : 'bg-sky-500')}</div>
                      <div><div className="flex justify-between text-xs font-mono mb-1"><span className="text-slate-400">Memory</span><span className="text-white font-bold">{mem === undefined ? '—' : `${mem.toFixed(0)}%`}</span></div>{bar(mem, 'bg-cyan-500')}</div>
                      <div><div className="flex justify-between text-xs font-mono mb-1"><span className="text-slate-400">Latency</span><span className="text-white font-bold">{lat === undefined ? '—' : `${lat.toFixed(0)} ms`}</span></div>{bar(lat === undefined ? 0 : lat / 5, 'bg-emerald-500')}</div>
                    </div>
                  );
                })()}

                {/* Footer specs */}
                <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 mt-4 pt-2 border-t border-white/5">
                  <span>Buffer: <strong className="text-slate-300">{s.data.buffer_depth}</strong></span>
                  <span>Guard: <strong className="text-slate-300">{s.data.guard_version}</strong></span>
                  <span>Last seen: <Ago iso={s.data.last_seen} /></span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 3: Live CPU & Latency Charts with Collapsible Signal Details */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
              LIVE TELEMETRY (BASELINE ±2σ BANDS)
            </span>
            {/* System toggle for charts */}
            <div className="flex items-center space-x-1 bg-[#141721] p-0.5 rounded border border-white/10 text-xs font-mono">
              <button
                onClick={() => setActiveTenant('acme')}
                className={`px-2.5 py-0.5 rounded font-bold ${
                  chartTenant === 'acme' ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-white'
                }`}
              >
                SYSTEM 1
              </button>
              <button
                onClick={() => setActiveTenant('globex')}
                className={`px-2.5 py-0.5 rounded font-bold ${
                  chartTenant === 'globex' ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-white'
                }`}
              >
                SYSTEM 2
              </button>
            </div>
          </div>

          <button
            onClick={() => setSignalsOpen(!signalsOpen)}
            className="text-xs font-mono text-sky-400 hover:text-sky-300 font-bold"
          >
            {signalsOpen ? '▼ HIDE SIGNAL EVIDENCE' : '▶ VIEW SIGNAL EVIDENCE & CORRELATION'}
          </button>
        </div>

        {/* 2 Clean Live Charts Side by Side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MetricChart
            title={`${chartTenant === 'acme' ? 'SYSTEM 1' : 'SYSTEM 2'} · CPU UTILIZATION`}
            unit="%"
            data={cpuData}
            normalRange={[15, 35]}
            color="#38BDF8"
            height={180}
          />
          <MetricChart
            title={`${chartTenant === 'acme' ? 'SYSTEM 1' : 'SYSTEM 2'} · DELIVERY LATENCY`}
            unit="ms"
            data={latencyData}
            normalRange={[30, 60]}
            color="#10B981"
            height={180}
          />
        </div>

        {/* Collapsible Signal Evidence Details */}
        {signalsOpen && (
          <div className="hud-panel p-4 border border-sky-500/30 bg-[#0C1017] space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-sky-400 uppercase font-bold tracking-wider">
                AIOPS ACTIVE SIGNAL CORRELATION ({activeIncidents.length} INCIDENT OPEN)
              </span>
              <span className="text-slate-400">Algorithm: Z-Score Thresholding + Kill-Chain Match</span>
            </div>

            {activeIncidents.length > 0 ? (
              activeIncidents.map((inc) => (
                <div key={inc.incident_id} className="p-3 rounded bg-[#121620] border border-white/5 space-y-2">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-white">{inc.title}</span>
                    <span className="text-cyan-400 font-bold">Confidence: {Math.round(inc.confidence * 100)}%</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {inc.signals.map((sig) => (
                      <div key={sig.evidence_id} className="p-2 rounded bg-black/40 text-[11px]">
                        <span className="text-slate-400 block">{sig.name}</span>
                        <span className="text-white font-bold">{sig.value} vs base {sig.baseline}</span>
                        <span className="text-sky-400 ml-1">({sig.contribution_pct}%)</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))
            ) : (
              <div className="p-3 text-slate-500 text-center">No anomalous signals active. Baseline normal.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
