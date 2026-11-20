import React from 'react';
import { ActionRecord } from '../types';
import { TimeText } from './TimeText';

interface AuditLogTableProps {
  records: ActionRecord[];
}

export const AuditLogTable: React.FC<AuditLogTableProps> = ({ records }) => {
  return (
    <div className="hud-panel p-4 overflow-hidden">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400 font-bold">
          IMMUTABLE REMEDIATION AUDIT LOG
        </span>
        <span className="text-xs font-mono text-slate-400">
          ALL ACTIONS REQUIRE 2-MAN RULE OR SHOP SIGN-OFF
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#141721] text-slate-400 uppercase text-[10px] tracking-wider border-b border-white/5">
            <tr>
              <th className="p-2.5">Timestamp</th>
              <th className="p-2.5">Tenant</th>
              <th className="p-2.5">Action</th>
              <th className="p-2.5">Target</th>
              <th className="p-2.5">State</th>
              <th className="p-2.5">Requested By</th>
              <th className="p-2.5">Approved By</th>
              <th className="p-2.5">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-slate-300">
            {records.map((r) => (
              <tr key={r.action_id} className="hover:bg-white/[0.02]">
                <td className="p-2.5">
                  <TimeText timestamp={r.at} />
                </td>
                <td className="p-2.5 uppercase">{r.tenant_id}</td>
                <td className="p-2.5 font-bold text-sky-400 uppercase">{r.action}</td>
                <td className="p-2.5 text-slate-200">{r.target}</td>
                <td className="p-2.5">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                      r.state === 'approved' || r.state === 'executed'
                        ? 'bg-emerald-500/20 text-emerald-400'
                        : r.state === 'dry_run'
                        ? 'bg-amber-500/20 text-amber-400'
                        : 'bg-slate-700 text-slate-300'
                    }`}
                  >
                    {r.state.toUpperCase()}
                  </span>
                </td>
                <td className="p-2.5 text-slate-400">{r.requested_by}</td>
                <td className="p-2.5 text-slate-300">{r.approved_by || 'PENDING'}</td>
                <td className="p-2.5 text-slate-400 truncate max-w-xs">{r.result || 'Awaiting execution'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
