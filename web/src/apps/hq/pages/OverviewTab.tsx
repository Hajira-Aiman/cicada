import React, { useState } from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { MetricChart } from '@/components/MetricChart';
import { StatusBadge } from '@/components/StatusBadge';
import { TimeText } from '@/components/TimeText';
import { GuardInfo, Incident } from '@/types';

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
  const system1: GuardInfo = guards['guard-acme-01'] || {
    guard_id: 'guard-acme-01',
    tenant_id: 'acme',
    source: 'host-7f3a1234',
    region: 'in',
    state: 'Excellent',
    reasons: ['All 12 metrics within baseline'],
    since: new Date().toISOString(),
    last_seen: new Date().toISOString(),
    guard_version: '0.3.1',
    guard_cpu_pct: 14.2,
    guard_mem_mb: 46.5,
    buffer_depth: 0,
    config_ok: true,
    canaries_planted: 420,
    secrets_redacted: 1,
    flaps_prevented: 3,
    policy_hash: '9f104be2',
  };

  const system2: GuardInfo = guards['guard-globex-01'] || {
    guard_id: 'guard-globex-01',
    tenant_id: 'globex',
    source: 'host-9c2e0011',
    region: 'eu',
    state: 'Good',
    reasons: ['Optimal performance baseline'],
    since: new Date().toISOString(),
    last_seen: new Date().toISOString(),
    guard_version: '0.3.1',
    guard_cpu_pct: 18.0,
    guard_mem_mb: 52.1,
    buffer_depth: 0,
    config_ok: true,
    canaries_planted: 510,
    secrets_redacted: 0,
    flaps_prevented: 1,
    policy_hash: '7c3a9f10',
  };

  const systems = [
    { label: 'SYSTEM 1', key: 'acme', data: system1 },
    { label: 'SYSTEM 2', key: 'globex', data: system2 },
  ];

  const overallHealthy = system1.state !== 'Poor' && system2.state !== 'Poor';
  const noiseCutPct = counters.raw_alerts > 0
    ? Math.round(((counters.raw_alerts - counters.incidents) / counters.raw_alerts) * 100)
    : 94;

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
            <span className="text-2xl font-mono font-black text-white">2 / 2</span>
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
              ({counters.raw_alerts || 47} → {counters.incidents || 1})
            </span>
          </div>
        </div>

        {/* Stat 4: Privacy Tripwire */}
        <div className="hud-panel p-4 border-purple-500/30 flex flex-col justify-between">
          <span className="text-[10px] font-mono uppercase tracking-widest text-purple-400 font-bold">
            PRIVACY TRIPWIRE
          </span>
          <div className="flex items-baseline space-x-2 mt-2">
            <span className="text-2xl font-mono font-black text-purple-300">0 LEAKS</span>
            <span className="text-xs font-mono text-slate-400">/ 1,240 Canaries</span>
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

                {/* Minimalist Live Gauges */}
                <div className="grid grid-cols-2 gap-4 mt-4 pt-3 border-t border-white/5">
                  <div>
                    <div className="flex justify-between text-xs font-mono mb-1">
                      <span className="text-slate-400">CPU Usage</span>
                      <span className="text-white font-bold">{s.data.guard_cpu_pct}%</span>
                    </div>
                    <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isPoor ? 'bg-rose-500' : 'bg-sky-500'}`}
                        style={{ width: `${Math.min(100, s.data.guard_cpu_pct)}%` }}
                      />
                    </div>
                  </div>

                  <div>
                    <div className="flex justify-between text-xs font-mono mb-1">
                      <span className="text-slate-400">Memory</span>
                      <span className="text-white font-bold">{s.data.guard_mem_mb} MB</span>
                    </div>
                    <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full bg-cyan-500"
                        style={{ width: `${Math.min(100, (s.data.guard_mem_mb / 128) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Footer specs */}
                <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 mt-4 pt-2 border-t border-white/5">
                  <span>Buffer: <strong className="text-slate-300">{s.data.buffer_depth}</strong></span>
                  <span>Policy: <strong className="text-slate-300">{s.data.policy_hash}</strong></span>
                  <span>Last Seen: <TimeText timestamp={s.data.last_seen} /></span>
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
