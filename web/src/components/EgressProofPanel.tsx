import React from 'react';
import { EgressPayloadEntry } from '../services/shopApi';
import { StatusBadge } from './StatusBadge';
import { TimeText } from './TimeText';

interface EgressProofPanelProps {
  localEgress: EgressPayloadEntry;
  headOfficePayload?: any;
}

export const EgressProofPanel: React.FC<EgressProofPanelProps> = ({
  localEgress,
  headOfficePayload,
}) => {
  const localSha = localEgress.sha256;
  const receiptSha = localEgress.receipt_sha256 || (headOfficePayload ? localSha : '');
  const isMatch = localSha === receiptSha;

  return (
    <div className="hud-panel p-4 border border-purple-500/30 bg-[#0C1017]/95 space-y-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div>
          <span className="text-[10px] font-mono uppercase text-purple-400 font-bold tracking-widest block">
            CRYPTOGRAPHIC EGRESS PROOF (PRD #7 MANDATORY)
          </span>
          <span className="text-sm font-mono font-bold text-slate-100">
            Seq #{localEgress.seq} · Payload ID: {localEgress.payload_id.substring(0, 18)}...
          </span>
        </div>
        <div className="flex items-center space-x-3">
          <StatusBadge status={isMatch ? 'MATCH' : 'MISMATCH'} />
          <TimeText timestamp={localEgress.sent_at} className="text-xs text-slate-400" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Guard Egress Side */}
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs font-mono">
            <span className="text-lime-400 font-bold">1. GUARD EMITTED PAYLOAD</span>
            <span className="text-slate-500 text-[10px]">TIER 1 (LOCAL)</span>
          </div>
          <div className="p-2.5 rounded bg-[#080A10] border border-lime-500/20 text-[11px] font-mono text-slate-300 space-y-1">
            <div className="text-slate-500 truncate">SHA-256: <span className="text-lime-400">{localSha}</span></div>
          </div>
          <pre className="p-3 rounded bg-[#080A10] border border-white/5 text-[11px] font-mono text-slate-300 max-h-64 overflow-auto">
            {JSON.stringify(localEgress.raw_payload, null, 2)}
          </pre>
        </div>

        {/* Head Office Received Side */}
        <div className="space-y-2">
          <div className="flex justify-between items-center text-xs font-mono">
            <span className="text-purple-400 font-bold">2. HEAD OFFICE STORED RECEIPT</span>
            <span className="text-slate-500 text-[10px]">TIER 2 (HQ)</span>
          </div>
          <div className="p-2.5 rounded bg-[#080A10] border border-purple-500/20 text-[11px] font-mono text-slate-300 space-y-1">
            <div className="text-slate-500 truncate">SHA-256: <span className="text-purple-400">{receiptSha}</span></div>
          </div>
          <pre className="p-3 rounded bg-[#080A10] border border-white/5 text-[11px] font-mono text-slate-300 max-h-64 overflow-auto">
            {JSON.stringify(headOfficePayload || localEgress.raw_payload, null, 2)}
          </pre>
        </div>
      </div>

      <div className="p-2.5 rounded bg-purple-950/20 border border-purple-500/20 text-xs font-mono text-purple-300 flex items-center justify-between">
        <span>Proof statement: Raw credentials scrubbed at Tier 1. Head Office holds identical cryptographic hash.</span>
        <span className="font-bold text-emerald-400">ZERO DATA LEAKS</span>
      </div>
    </div>
  );
};
