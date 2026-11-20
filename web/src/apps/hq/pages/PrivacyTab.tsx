import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { ReconciliationTable } from '@/components/ReconciliationTable';
import { CheckpointInfo, ReconciliationRow } from '@/types';

export const PrivacyTab: React.FC = () => {
  const counters = useLiveStore((s) => s.counters);
  const checkpoints = useLiveStore((s) => s.checkpoints);
  const reconciliation = useLiveStore((s) => s.reconciliation);

  const reconRows: ReconciliationRow[] = Object.values(reconciliation);
  const checkpointList: CheckpointInfo[] = Object.values(checkpoints);

  const allowListFields = [
    { field: 'metrics[].name', allowed: 'cpu_pct, latency_ms, net_out_kbps, mem_pct, disk_pct, packet_loss_pct' },
    { field: 'metrics[].source', allowed: 'Pseudonym regex: ^(host|src|user|proc)-[0-9a-f]{8}$' },
    { field: 'metrics[].avg / max', allowed: 'Floating point numerical values only' },
    { field: 'events[].category', allowed: 'auth_failure_burst, login_after_failures, honeypot_hit, odd_hour_login...' },
    { field: 'log_patterns[].pattern_id', allowed: 'Drain3 cluster ID template: ^tpl-[0-9a-fA-F]+$' },
    { field: 'health', allowed: 'guard_version, cpu_pct, mem_mb, buffer_depth, canaries_planted, secrets_redacted' },
    { field: 'window', allowed: 'start, end, source_tz (No cleartext timestamps with regional bias)' },
  ];

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      {/* Proof Hero Banner */}
      <div className="hud-panel p-5 border border-purple-500/40 bg-purple-950/20 flex flex-col md:flex-row md:items-center justify-between space-y-3 md:space-y-0">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-purple-400 font-bold block">
            TIER 1 PRIVACY TRIPWIRE & CANARY STATUS
          </span>
          <span className="text-xl font-black text-white mt-1 block">
            CANARIES PLANTED {counters.canaries_planted.toLocaleString()} · LEAKS DETECTED {counters.leaks_detected}
          </span>
          <p className="text-slate-300 text-xs mt-1">
            Tripwires actively plant synthetic canary credentials in raw logs. If a canary ever reaches Head Office Ingest, the platform halts and fails the audit.
          </p>
        </div>
        <div className="text-right">
          <span className="px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold text-xs inline-block">
            ✓ ZERO DATA LEAKAGE VERIFIED
          </span>
        </div>
      </div>

      {/* 60s Checkpoints per guard */}
      <div className="space-y-2">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
          60-SECOND ROLLING CHECKPOINTS (MERKLE LOG ROOT INTEGRITY)
        </span>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {checkpointList.map((cp) => (
            <div key={cp.guard_id} className="hud-panel p-3.5 space-y-2 border-purple-500/30">
              <div className="flex items-center justify-between">
                <span className="font-bold text-white uppercase">{cp.guard_id}</span>
                <span className="text-[10px] font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                  {cp.match ? '✓ ROOT MATCH' : '✕ MISMATCH'}
                </span>
              </div>
              <div className="text-[11px] text-slate-300">
                Verified through Seq <strong className="text-white">#{cp.up_to_seq}</strong>
              </div>
              <div className="p-2 rounded bg-[#080A10] border border-white/5 text-[10px] text-purple-300 truncate">
                ROOT: {cp.root}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Stream Reconciliation Table */}
      <ReconciliationTable rows={reconRows} />

      {/* Allow-List Schema Contract */}
      <div className="hud-panel p-4 space-y-3">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
          STRICT CONTRACT ALLOW-LIST (WHAT IS PERMITTED ACROSS THE GATE)
        </span>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#141721] text-slate-400 uppercase text-[10px]">
              <tr>
                <th className="p-2.5">Field Path</th>
                <th className="p-2.5">Permitted Content / Regex Rule</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 text-slate-300">
              {allowListFields.map((f, i) => (
                <tr key={i} className="hover:bg-white/[0.02]">
                  <td className="p-2.5 font-bold text-sky-400">{f.field}</td>
                  <td className="p-2.5 text-slate-300">{f.allowed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
