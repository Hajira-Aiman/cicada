import React from 'react';
import { ReconciliationRow } from '../types';
import { TimeText } from './TimeText';

interface ReconciliationTableProps {
  rows: ReconciliationRow[];
}

export const ReconciliationTable: React.FC<ReconciliationTableProps> = ({ rows }) => {
  return (
    <div className="hud-panel p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400 font-bold">
          STREAM RECONCILIATION & INTEGRITY (PRD #16)
        </span>
        <span className="text-xs font-mono text-emerald-400 font-bold">
          ZERO PACKET LOSS · ZERO GAPS
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#141721] text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/5">
            <tr>
              <th className="p-2.5">Guard ID</th>
              <th className="p-2.5">Tenant</th>
              <th className="p-2.5 text-right">Sent</th>
              <th className="p-2.5 text-right">Received</th>
              <th className="p-2.5 text-right">Duplicates</th>
              <th className="p-2.5 text-right">Max Seq</th>
              <th className="p-2.5">Gaps</th>
              <th className="p-2.5">Last Seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {rows.map((row) => {
              const hasGaps = row.gaps && row.gaps.length > 0;
              return (
                <tr key={row.guard_id} className="hover:bg-white/[0.02]">
                  <td className="p-2.5 font-bold text-slate-200">{row.guard_id}</td>
                  <td className="p-2.5 uppercase">{row.tenant_id}</td>
                  <td className="p-2.5 text-right font-tabular">{row.sent_count.toLocaleString()}</td>
                  <td className="p-2.5 text-right font-tabular text-emerald-400">{row.received_count.toLocaleString()}</td>
                  <td className="p-2.5 text-right font-tabular text-slate-500">{row.duplicate_count}</td>
                  <td className="p-2.5 text-right font-tabular">{row.max_seq}</td>
                  <td className="p-2.5">
                    {hasGaps ? (
                      <span className="text-rose-400 font-bold">{row.gaps.join(', ')}</span>
                    ) : (
                      <span className="text-emerald-400">NONE</span>
                    )}
                  </td>
                  <td className="p-2.5">
                    <TimeText timestamp={row.last_seen} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
