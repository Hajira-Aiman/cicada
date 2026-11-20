import React from 'react';
import { useUiStore } from '../stores/uiStore';
import { useLiveStore } from '../stores/liveStore';
import { StatusBadge } from '../components/StatusBadge';
import { TimeText } from '../components/TimeText';

export const GuardInspector: React.FC = () => {
  const inspectorOpen = useUiStore((s) => s.inspectorOpen);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);
  const selectedGuardId = useUiStore((s) => s.selectedGuardId);
  const guards = useLiveStore((s) => s.guards);
  const receipts = useLiveStore((s) => s.receipts);

  if (!inspectorOpen || !selectedGuardId) return null;

  const guard = guards[selectedGuardId];
  if (!guard) return null;

  const guardReceipts = receipts.filter((r) => r.guard_id === selectedGuardId).slice(0, 5);

  return (
    <div className="fixed right-0 top-14 bottom-0 w-[440px] bg-[#0C1017] border-l border-white/[0.08] shadow-2xl z-40 flex flex-col font-mono text-xs">
      <div className="p-3.5 border-b border-white/[0.08] flex items-center justify-between bg-[#141721]">
        <div>
          <span className="text-[10px] uppercase text-cyan-400 font-bold tracking-widest block">
            GUARD HARDWARE INSPECTOR
          </span>
          <span className="text-slate-200 font-bold text-sm">{guard.guard_id}</span>
        </div>
        <button
          onClick={() => setInspectorOpen(false)}
          className="text-slate-400 hover:text-white p-1 rounded"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 p-4 overflow-auto space-y-4">
        {/* State Banner */}
        <div className="p-3 rounded bg-[#141721] border border-white/5 flex items-center justify-between">
          <div>
            <span className="text-[10px] text-slate-500 uppercase block">HEALTH STATE</span>
            <StatusBadge status={guard.state} className="mt-1" />
          </div>
          <div className="text-right">
            <span className="text-[10px] text-slate-500 uppercase block">LAST SEEN</span>
            <TimeText timestamp={guard.last_seen} className="text-xs text-slate-300 mt-1 inline-block" />
          </div>
        </div>

        {/* Reasons */}
        <div className="space-y-1">
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">REASONS</span>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5 text-slate-300">
            {guard.reasons.join(', ')}
          </div>
        </div>

        {/* Specs Grid */}
        <div className="grid grid-cols-2 gap-2.5">
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">TENANT & REGION</span>
            <span className="text-sm font-bold text-white uppercase">{guard.tenant_id} ({guard.region})</span>
          </div>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">GUARD VERSION</span>
            <span className="text-sm font-bold text-cyan-400">{guard.guard_version}</span>
          </div>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">CPU & MEMORY</span>
            <span className="text-sm font-bold text-slate-200">{guard.guard_cpu_pct}% / {guard.guard_mem_mb} MB</span>
          </div>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">BUFFER DEPTH</span>
            <span className={`text-sm font-bold ${guard.buffer_depth > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {guard.buffer_depth} payloads
            </span>
          </div>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">CANARIES PLANTED</span>
            <span className="text-sm font-bold text-purple-300">{guard.canaries_planted}</span>
          </div>
          <div className="p-2.5 rounded bg-[#121620] border border-white/5">
            <span className="text-[10px] text-slate-500 uppercase block">SECRETS REDACTED</span>
            <span className="text-sm font-bold text-emerald-400">{guard.secrets_redacted}</span>
          </div>
        </div>

        {/* Policy Hash */}
        <div className="p-2.5 rounded bg-[#121620] border border-white/5">
          <span className="text-[10px] text-slate-500 uppercase block">PINNED POLICY HASH</span>
          <span className="text-xs font-bold text-slate-300">{guard.policy_hash} (Strict Allow-List V1)</span>
        </div>

        {/* Recent Payloads */}
        <div className="space-y-2">
          <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
            RECENT PAYLOAD RECEIPTS
          </span>
          <div className="space-y-1.5">
            {guardReceipts.length > 0 ? (
              guardReceipts.map((r, idx) => (
                <div
                  key={idx}
                  className="p-2 rounded bg-[#121620] border border-white/5 flex items-center justify-between"
                >
                  <div>
                    <span className="text-slate-300 font-bold">Seq #{r.seq}</span>
                    <span className="text-slate-500 text-[10px] block">{r.payload_id.substring(0, 16)}...</span>
                  </div>
                  <div className="text-right">
                    <StatusBadge status={r.status === 'stored' ? 'MATCH' : 'REJECTED'} />
                    <TimeText timestamp={r.received_at} className="text-[10px] text-slate-500 block mt-0.5" />
                  </div>
                </div>
              ))
            ) : (
              <div className="text-slate-500 text-xs">Awaiting live receipts...</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
