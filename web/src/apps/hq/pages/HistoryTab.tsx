import React from 'react';
import { TimeText } from '@/components/TimeText';
import { StatusBadge } from '@/components/StatusBadge';

export const HistoryTab: React.FC = () => {
  const transitions = [
    {
      id: 'h-1',
      tenant_id: 'acme',
      source: 'host-7f3a1234',
      old_state: 'Good',
      new_state: 'Poor',
      reasons: ['Elevated CPU > 85% for 3 windows', 'Cryptominer signature matched'],
      at: '2026-11-21T04:12:06Z',
      source_tz: 'Asia/Kolkata',
    },
    {
      id: 'h-2',
      tenant_id: 'globex',
      source: 'host-9c2e0011',
      old_state: 'Excellent',
      new_state: 'Good',
      reasons: ['Slight net_out variance in window 980'],
      at: '2026-11-21T04:11:40Z',
      source_tz: 'Europe/Berlin',
    },
    {
      id: 'h-3',
      tenant_id: 'contoso',
      source: 'host-1a2b3c4d',
      old_state: 'Poor',
      new_state: 'Fair',
      reasons: ['CPU dropping following restart'],
      at: '2026-11-21T04:09:12Z',
      source_tz: 'Asia/Kolkata',
    },
    {
      id: 'h-4',
      tenant_id: 'acme',
      source: 'host-7f3a1234',
      old_state: 'Excellent',
      new_state: 'Good',
      reasons: ['SSH failed login burst detected'],
      at: '2026-11-21T04:05:00Z',
      source_tz: 'Asia/Kolkata',
    },
  ];

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
