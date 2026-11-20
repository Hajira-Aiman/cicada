import React, { useState, useEffect } from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { AuditLogTable } from '@/components/AuditLogTable';
import { ActionRecord } from '@/types';

export const ActionsTab: React.FC = () => {
  const actions: ActionRecord[] = useLiveStore((s) => s.actions);
  const updateActionState = useLiveStore((s) => s.updateActionState);

  const [rollbackTimers, setRollbackTimers] = useState<Record<string, number>>({});

  useEffect(() => {
    const interval = setInterval(() => {
      setRollbackTimers((prev) => {
        const next: Record<string, number> = {};
        for (const [k, v] of Object.entries(prev)) {
          if (v > 0) next[k] = v - 1;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleRollback = (actionId: string) => {
    updateActionState(actionId, 'rolled_back', 'operator-rollback');
  };

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-white tracking-widest">
            AUTOMATED REMEDIATION & HUMAN-IN-THE-LOOP ACTIONS
          </h2>
          <p className="text-slate-400 text-[11px] mt-0.5">
            Every remediation requires pre-flight simulation (dry run) and 120s rollback safety timer.
          </p>
        </div>
      </div>

      {/* Pending Actions / Active Rollback Timers */}
      <div className="space-y-3">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
          ACTIVE REMEDIATION DISPATCHES
        </span>

        {actions.map((act) => {
          const remaining = rollbackTimers[act.action_id] ?? 0;
          return (
            <div
              key={act.action_id}
              className="hud-panel p-4 border border-cyan-500/30 flex flex-col md:flex-row md:items-center justify-between space-y-3 md:space-y-0"
            >
              <div className="space-y-1">
                <div className="flex items-center space-x-2">
                  <span className="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-400 font-bold text-xs uppercase">
                    {act.action}
                  </span>
                  <span className="text-sm font-bold text-white">{act.target}</span>
                  <span className="text-slate-500">({act.tenant_id.toUpperCase()})</span>
                </div>
                <p className="text-slate-300 text-xs">{act.result}</p>
                <div className="text-[11px] text-slate-400">
                  Requested by: <strong className="text-slate-300">{act.requested_by}</strong> · Approved by: <strong className="text-slate-300">{act.approved_by || 'PENDING'}</strong>
                </div>
              </div>

              <div className="flex items-center space-x-4">
                {act.state === 'approved' && remaining > 0 && (
                  <div className="text-right">
                    <span className="text-[10px] text-slate-400 block uppercase">ROLLBACK WINDOW</span>
                    <span className="text-sm font-bold text-amber-400 font-tabular">{remaining}s remaining</span>
                  </div>
                )}
                {act.state === 'approved' && remaining > 0 && (
                  <button
                    onClick={() => handleRollback(act.action_id)}
                    className="px-3 py-1.5 rounded bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs"
                  >
                    TRIGGER ROLLBACK
                  </button>
                )}
                {act.state === 'rolled_back' && (
                  <span className="px-3 py-1 rounded bg-rose-950 text-rose-400 border border-rose-500/30 font-bold">
                    ROLLED BACK
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Immutable Audit Log Table */}
      <AuditLogTable records={actions} />
    </div>
  );
};
