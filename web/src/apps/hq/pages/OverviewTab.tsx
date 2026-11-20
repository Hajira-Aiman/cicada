import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { KpiStrip } from '@/features/KpiStrip';
import { LatencyMeter } from '@/features/LatencyMeter';
import { MetricChart } from '@/components/MetricChart';
import { IncidentCard } from '@/components/IncidentCard';
import { StatusBadge } from '@/components/StatusBadge';
import { TimeText } from '@/components/TimeText';
import { Fallback2D } from '@/three/Fallback2D';
import { DamageMap } from '@/components/DamageMap';
import { GuardInfo, Incident } from '@/types';

const bandOf = (d: { baseline?: number; spread?: number }[]): [number, number] | undefined => {
  const p = d[d.length - 1];
  const r1 = (x: number) => Math.round(x * 10) / 10;
  return p?.baseline !== undefined && p.spread !== undefined ? [Math.max(0, r1(p.baseline - p.spread)), r1(p.baseline + p.spread)] : undefined;
};

export const OverviewTab: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const metrics = useLiveStore((s) => s.metrics);
  const incidents = useLiveStore((s) => s.incidents);
  const activeTenant = useUiStore((s) => s.activeTenant);
  const setSelectedGuardId = useUiStore((s) => s.setSelectedGuardId);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);

  // Tenant isolation filter
  const filteredGuards: GuardInfo[] = Object.values(guards).filter(
    (g: GuardInfo) => activeTenant === 'ALL' || g.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const filteredIncidents: Incident[] = incidents.filter(
    (i: Incident) => activeTenant === 'ALL' || i.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const cpuData = metrics[`${activeTenant === 'ALL' ? 'acme' : activeTenant}:cpu_pct`] || [];
  const latencyData = metrics[`${activeTenant === 'ALL' ? 'acme' : activeTenant}:latency_ms`] || [];
  const netData = metrics[`${activeTenant === 'ALL' ? 'acme' : activeTenant}:net_out_kbps`] || [];
  const memData = metrics[`${activeTenant === 'ALL' ? 'acme' : activeTenant}:mem_pct`] || [];

  const handleTileClick = (guardId: string) => {
    setSelectedGuardId(guardId);
    setInspectorOpen(true);
  };

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto">
      {/* KPI Top Strip */}
      <KpiStrip />

      {/* Fleet Health Grid */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
            FLEET HEALTH STATUS (4-TIER OBSERVABILITY)
          </span>
          <span className="text-[11px] font-mono text-slate-500">
            CLICK TILE TO OPEN HARDWARE INSPECTOR
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {filteredGuards.map((g) => (
            <div
              key={g.guard_id}
              onClick={() => handleTileClick(g.guard_id)}
              className="hud-panel p-3.5 cursor-pointer hover:border-slate-500 transition-colors flex flex-col justify-between"
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-sm font-bold text-white uppercase">{g.tenant_id}</span>
                    <span className="text-xs font-mono text-slate-400">({g.guard_id})</span>
                  </div>
                  <span className="text-xs font-mono text-slate-500 block mt-0.5">{g.source} · {g.region.toUpperCase()}</span>
                </div>
                <StatusBadge status={g.state} />
              </div>

              <div className="mt-3 space-y-1">
                <span className="text-[10px] font-mono uppercase text-slate-500 font-bold block">REASONS</span>
                <p className="text-xs font-mono text-slate-300 truncate">
                  {g.reasons && g.reasons.length > 0 ? g.reasons.join(' · ') : 'Normal baseline'}
                </p>
              </div>

              <div className="mt-3 pt-2 border-t border-white/5 flex items-center justify-between text-[11px] font-mono text-slate-400">
                <span>CPU: <strong className="text-slate-200">{g.guard_cpu_pct}%</strong></span>
                <span>Buffer: <strong className={g.buffer_depth > 0 ? 'text-amber-400' : 'text-emerald-400'}>{g.buffer_depth}</strong></span>
                <span>Flaps: <strong className="text-cyan-400">{g.flaps_prevented}</strong></span>
                <span>Last seen: <TimeText timestamp={g.last_seen} /></span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live Charts Strip */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <MetricChart
          title="CPU USAGE"
          unit="%"
          data={cpuData}
          normalRange={bandOf(cpuData)}
          color="#38BDF8"
        />
        <MetricChart
          title="LATENCY"
          unit="ms"
          data={latencyData}
          normalRange={bandOf(latencyData)}
          color="#10B981"
        />
        <MetricChart
          title="NET OUTBOUND"
          unit="kbps"
          data={netData}
          normalRange={bandOf(netData)}
          color="#A855F7"
        />
        <MetricChart
          title="MEMORY USAGE"
          unit="%"
          data={memData}
          normalRange={bandOf(memData)}
          color="#06B6D4"
        />
      </div>

      {/* Split: Incidents Feed + Mini Live Fleet Bridge */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Incidents Section */}
        <div className="lg:col-span-7 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
              CORRELATED INCIDENTS ({filteredIncidents.length})
            </span>
            <span className="text-[11px] font-mono text-slate-500">
              CLICK BAR TO PIN EVIDENCE TO COPILOT
            </span>
          </div>

          <div className="space-y-3">
            {filteredIncidents.length > 0 ? (
              filteredIncidents.map((inc) => (
                <IncidentCard key={inc.incident_id} incident={inc} />
              ))
            ) : (
              <div className="hud-panel p-8 text-center text-xs font-mono text-slate-500">
                NO ACTIVE INCIDENTS FOR {activeTenant.toUpperCase()}
              </div>
            )}
          </div>
        </div>

        {/* Mini Fleet Bridge */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-widest text-slate-400 font-bold">
              MINI FLEET BRIDGE (PARTICLE STREAM)
            </span>
            <span className="text-[11px] font-mono text-purple-400 font-bold">
              ZERO CLEAR-TEXT EXPORT
            </span>
          </div>
          <DamageMap tenant={activeTenant === 'ALL' ? 'acme' : activeTenant} />
          <div className="h-[420px]">
            <Fallback2D height="100%" />
          </div>
        </div>
      </div>

      {/* Latency Meter Footer */}
      <LatencyMeter />
    </div>
  );
};
