import React from 'react';
import { TimeText } from '@/components/TimeText';
import { StatusBadge } from '@/components/StatusBadge';
import { apiFetch } from '@/services/apiClient';
const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1);

export const HistoryTab: React.FC = () => {
  const [transitions, setTransitions] = React.useState<any[]>([]);
  React.useEffect(() => {
    const load = () => apiFetch<{ history: any[] }>('/api/health/history?limit=100').then((r) => setTransitions(r.history.map((h) => ({
      id: String(h.id), tenant_id: h.tenant_id, source: h.source, old_state: cap(h.old_state || 'good'), new_state: cap(h.state),
      reasons: h.reasons || [], at: h.at, source_tz: undefined })))).catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-white tracking-widest">
            FLEET HEALTH TRANSITION HISTORY
          </h2>
          <p className="text-slate-400 text-[11px] mt-0.5">
            Single unified UTC chronological timeline. Switching time-zone control modifies display labels but never event ordering.
          </p>
        </div>
      </div>

      <div className="hud-panel overflow-hidden">
        <table className="w-full text-left">
          <thead className="bg-[#141721] text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/5">
            <tr>
              <th className="p-3">Event Timestamp</th>
              <th className="p-3">Tenant</th>
              <th className="p-3">Source Target</th>
              <th className="p-3">Transition</th>
              <th className="p-3">Reason Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {transitions.map((t) => (
              <tr key={t.id} className="hover:bg-white/[0.02]">
                <td className="p-3 font-bold">
                  <TimeText timestamp={t.at} sourceTz={t.source_tz} />
                </td>
                <td className="p-3 uppercase font-bold text-white">{t.tenant_id}</td>
                <td className="p-3 text-slate-300">{t.source}</td>
                <td className="p-3">
                  <div className="flex items-center space-x-2">
                    <StatusBadge status={t.old_state as any} />
                    <span className="text-slate-500">→</span>
                    <StatusBadge status={t.new_state as any} />
                  </div>
                </td>
                <td className="p-3 text-slate-400">{t.reasons.join(' · ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
