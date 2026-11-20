import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { StatusBadge } from '@/components/StatusBadge';
import { TimeText } from '@/components/TimeText';
import { GuardInfo } from '@/types';

export const FleetTab: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const activeTenant = useUiStore((s) => s.activeTenant);
  const setSelectedGuardId = useUiStore((s) => s.setSelectedGuardId);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);

  const guardList: GuardInfo[] = Object.values(guards).filter(
    (g: GuardInfo) => activeTenant === 'ALL' || g.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const handleRowClick = (guardId: string) => {
    setSelectedGuardId(guardId);
    setInspectorOpen(true);
  };

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-white tracking-widest">
            GUARD FLEET DIRECTORY
          </h2>
          <p className="text-slate-400 text-[11px] mt-0.5">
            Registered collectors, health status, and cryptographic policy versions
          </p>
        </div>
        <span className="text-slate-400">Total Guards: {guardList.length}</span>
      </div>

      <div className="hud-panel overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-[#141721] text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/5">
            <tr>
              <th className="p-3">Guard ID</th>
              <th className="p-3">Tenant</th>
              <th className="p-3">Region</th>
              <th className="p-3">State</th>
              <th className="p-3">Last Seen</th>
              <th className="p-3">Version</th>
              <th className="p-3 text-right">CPU %</th>
              <th className="p-3 text-right">Mem MB</th>
              <th className="p-3 text-right">Buffer</th>
              <th className="p-3">Config</th>
              <th className="p-3">Policy Hash</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {guardList.map((g) => (
              <tr
                key={g.guard_id}
                onClick={() => handleRowClick(g.guard_id)}
                className="hover:bg-white/[0.04] cursor-pointer"
              >
                <td className="p-3 font-bold text-white">{g.guard_id}</td>
                <td className="p-3 uppercase text-slate-300">{g.tenant_id}</td>
                <td className="p-3 uppercase text-slate-400">{g.region}</td>
                <td className="p-3">
                  <StatusBadge status={g.state} />
                </td>
                <td className="p-3">
                  <TimeText timestamp={g.last_seen} />
                </td>
                <td className="p-3 text-cyan-400">{g.guard_version}</td>
                <td className="p-3 text-right font-tabular">{g.guard_cpu_pct}%</td>
                <td className="p-3 text-right font-tabular">{g.guard_mem_mb}</td>
                <td className="p-3 text-right font-tabular">
                  <span className={g.buffer_depth > 0 ? 'text-amber-400' : 'text-emerald-400'}>
                    {g.buffer_depth}
                  </span>
                </td>
                <td className="p-3">
                  <span className={g.config_ok ? 'text-emerald-400 font-bold' : 'text-rose-400'}>
                    {g.config_ok ? 'OK' : 'MISCONFIG'}
                  </span>
                </td>
                <td className="p-3 text-slate-400 font-tabular">{g.policy_hash}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
