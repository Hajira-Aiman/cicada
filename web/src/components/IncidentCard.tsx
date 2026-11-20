import React, { useState } from 'react';
import { Incident } from '../types';
import { StatusBadge } from './StatusBadge';
import { TimeText } from './TimeText';
import { useLiveStore } from '../stores/liveStore';
import { api, apiFetch } from '../services/apiClient';
import { useUiStore } from '../stores/uiStore';

interface IncidentCardProps {
  incident: Incident;
  onSelectEvidence?: (evidenceId: string) => void;
}

export const IncidentCard: React.FC<IncidentCardProps> = ({ incident, onSelectEvidence }) => {
  const [dryRunOutput, setDryRunOutput] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);
  const [actionDispatched, setActionDispatched] = useState(false);
  const [revealModal, setRevealModal] = useState<string | null>(null);
  const [revealReason, setRevealReason] = useState('');
  const [revealStatus, setRevealStatus] = useState<string | null>(null);
  const updateActionState = useLiveStore((s) => s.updateActionState);

  const [intentId, setIntentId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const userId = useUiStore((s) => s.currentUserId) || 'operator';

  // real flow: propose -> dry run -> human approval (guard then pulls the signed intent)
  const handleDryRun = async () => {
    const rec = incident.recommendation;
    if (!rec) return;
    setActionError(null);
    try {
      let id = intentId;
      if (!id) {
        const p = await apiFetch<any>('/api/actions/propose', { method: 'POST', body: JSON.stringify({
          action: rec.action, target: rec.target || incident.affected[0], why: rec.why, risk: rec.risk, reversible: rec.reversible,
          rollback: rec.rollback, incident_id: incident.incident_id, tenant_id: incident.tenant_id }) });
        id = p.intent_id; setIntentId(id);
      }
      const d = await apiFetch<any>(`/api/actions/${id}/dry-run`, { method: 'POST' });
      setDryRunOutput(`DRY RUN [${id}]:
Target: ${d.simulation.target}
Action: ${d.simulation.action}
` +
        `Would succeed: ${d.simulation.would_succeed ? 'YES' : 'NO'}
${d.simulation.impact}
Rollback: ${rec.rollback || 'n/a'}`);
      useLiveStore.setState((st) => ({ actions: [{ action_id: id!, tenant_id: incident.tenant_id, action: rec.action, target: rec.target,
        state: 'dry_run' as const, result: d.simulation.impact, requested_by: 'aiops', at: new Date().toISOString(), rollback_window_s: 120 },
        ...st.actions.filter((x) => x.action_id !== id)] }));
    } catch (e: any) { setActionError(e.message); }
  };

  const handleApprove = async () => {
    if (!intentId) { setActionError('Run the dry run first.'); return; }
    setIsApproving(true); setActionError(null);
    try {
      await apiFetch(`/api/actions/${intentId}/approve`, { method: 'POST', body: JSON.stringify({ approved_by: userId }) });
      setActionDispatched(true);
      updateActionState(intentId, 'approved', userId);
    } catch (e: any) { setActionError(e.message); }
    setIsApproving(false);
  };

  const thumbsDown = async () => {
    const mine = useLiveStore.getState().alerts.filter((a) => a.tenant_id === incident.tenant_id && a.status === 'open');
    try {
      await Promise.all(mine.map((a) => api.postFeedback(a.alert_id, a.tenant_id, userId)));
      setActionError(mine.length ? `Thanks. ${mine.length} alert(s) will need a stronger signal for 30 min.` : 'No open alert to give feedback on.');
    } catch (e: any) { setActionError(e.message); }
  };

  const submitRevealRequest = async (pseudonym: string) => {
    try {
      await api.createRevealRequest(pseudonym, revealReason || 'Investigating cryptomining incident', incident.tenant_id);
      setRevealStatus(`REQUEST SENT for ${pseudonym}. Awaiting shop manager sign-off.`);
      setTimeout(() => {
        setRevealModal(null);
        setRevealStatus(null);
        setRevealReason('');
      }, 2000);
    } catch (err: any) {
      setRevealStatus(`Error: ${err.message}`);
    }
  };

  return (
    <div className="hud-panel p-4 border border-rose-500/20 bg-[#0C1017]/95 space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <StatusBadge status={incident.severity} />
            <h3 className="text-base font-mono font-bold text-slate-100">{incident.title}</h3>
            {incident.repeat_count > 1 && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-700 text-slate-200">
                x{incident.repeat_count}
              </span>
            )}
          </div>
          <div className="flex items-center space-x-3 text-xs font-mono text-slate-400">
            <span>ID: {incident.incident_id}</span>
            <span>·</span>
            <span>Started: <TimeText timestamp={incident.started_at} /></span>
            <span>·</span>
            <span className="text-slate-300">Tenant: <strong className="text-white">{incident.tenant_id.toUpperCase()}</strong></span>
          </div>
        </div>

        {/* Confidence with hover formula */}
        <div className="text-right group relative cursor-help">
          <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">CONFIDENCE</div>
          <div className="text-lg font-mono font-black text-cyan-400">
            {Math.round(incident.confidence * 100)}%
          </div>
          {/* Tooltip with exact formula */}
          <div className="hidden group-hover:block absolute right-0 top-12 z-50 w-72 p-2.5 bg-[#1A1C23] border border-white/10 rounded shadow-2xl text-[11px] font-mono text-slate-300 text-left">
            <div className="text-cyan-400 font-bold mb-1">Confidence Calculation:</div>
            <div>0.4 (base) + 0.15 × 3 signals + 0.1 (rule match) = 0.85</div>
            <div className="text-[10px] text-slate-500 mt-1">Capped at 0.95 maximum confidence.</div>
          </div>
        </div>
      </div>

      {/* Affected Topology Nodes */}
      <div className="flex items-center space-x-2 text-xs font-mono">
        <span className="text-slate-500 uppercase text-[10px] font-bold">AFFECTED:</span>
        {incident.affected.map((item, idx) => (
          <span key={idx} className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
            {item}
          </span>
        ))}
      </div>

      {/* Contribution bars */}
      <div className="space-y-1.5 bg-[#141721] p-3 rounded border border-white/5">
        <div className="text-[10px] font-mono uppercase text-slate-400 font-bold tracking-widest">
          SIGNAL CONTRIBUTIONS
        </div>
        <div className="space-y-2 mt-2">
          {incident.signals.map((sig) => (
            <div
              key={sig.evidence_id}
              onClick={() => onSelectEvidence && onSelectEvidence(sig.evidence_id)}
              className="cursor-pointer hover:bg-white/5 p-1 rounded transition-colors"
            >
              <div className="flex justify-between text-xs font-mono mb-1">
                <span className="text-slate-300">
                  <strong className="text-sky-400">{sig.name}</strong>: {sig.value} vs baseline {sig.baseline}
                  {sig.z && <span className="text-slate-500 ml-1.5">(z={sig.z}σ)</span>}
                </span>
                <span className="text-slate-400 font-bold">{sig.contribution_pct}%</span>
              </div>
              <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                <div
                  className="bg-sky-500 h-full rounded-full transition-all duration-500"
                  style={{ width: `${sig.contribution_pct}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Reasoning path timeline */}
      <div className="space-y-1.5">
        <div className="text-[10px] font-mono uppercase text-slate-400 font-bold tracking-widest">
          REASONING PATH (AIOPS TIMELINE)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-1.5">
          {incident.reasoning_path.map((step, idx) => (
            <div
              key={idx}
              className="bg-[#161A23] p-2 rounded border border-white/5 text-[11px] font-mono text-slate-300 flex items-center space-x-1.5"
            >
              <span className="w-4 h-4 rounded-full bg-slate-700 flex items-center justify-center text-[10px] text-white shrink-0">
                {idx + 1}
              </span>
              <span className="truncate">{step}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Changes before & Counterfactual */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
        {incident.changes_before && incident.changes_before.length > 0 && (
          <div className="bg-[#161A23] p-2.5 rounded border border-amber-500/20 text-amber-300/90">
            <span className="text-[10px] text-amber-400 font-bold block mb-1">CHANGES DETECTED BEFORE INCIDENT:</span>
            {incident.changes_before.join(' · ')}
          </div>
        )}
        {incident.counterfactual && (
          <div className="bg-[#161A23] p-2.5 rounded border border-purple-500/20 text-purple-300/90 italic">
            <span className="text-[10px] text-purple-400 font-bold not-italic block mb-1">COUNTERFACTUAL ANALYSIS:</span>
            "{incident.counterfactual}"
          </div>
        )}
      </div>

      {/* Recommendation and Action Gate */}
      {incident.recommendation && (
        <div className="bg-[#121620] p-3.5 rounded border border-cyan-500/30 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[10px] font-mono uppercase text-cyan-400 font-bold tracking-widest block">
                RECOMMENDED ACTION
              </span>
              <span className="text-sm font-mono font-bold text-white">
                {incident.recommendation.action.toUpperCase()}: <span className="text-cyan-300">{incident.recommendation.target}</span>
              </span>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => setRevealModal(incident.recommendation!.target)}
                className="px-2.5 py-1 text-xs font-mono font-bold rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 hover:bg-purple-500/30"
              >
                REQUEST REVEAL
              </button>
              <button
                onClick={thumbsDown}
                title="Not useful: raise this signal's alert level for 30 min"
                className="px-2.5 py-1 text-xs font-mono font-bold rounded bg-slate-800 text-slate-200 border border-slate-600 hover:bg-slate-700"
              >
                👎
              </button>
              <button
                onClick={handleDryRun}
                className="px-3 py-1 text-xs font-mono font-bold rounded bg-slate-800 text-slate-200 border border-slate-600 hover:bg-slate-700"
              >
                DRY RUN
              </button>
              <button
                onClick={handleApprove}
                disabled={isApproving || actionDispatched}
                className={`px-3 py-1 text-xs font-mono font-bold rounded border ${
                  actionDispatched
                    ? 'bg-emerald-600/30 text-emerald-400 border-emerald-500/40'
                    : 'bg-emerald-600 text-white border-emerald-500 hover:bg-emerald-500'
                }`}
              >
                {actionDispatched ? '✓ DISPATCHED' : isApproving ? 'DISPATCHING...' : 'SEND FOR APPROVAL'}
              </button>
            </div>
          </div>

          <p className="text-xs text-slate-300 font-sans">{incident.recommendation.why}</p>

          <div className="flex items-center space-x-4 text-[11px] font-mono text-slate-400">
            <span>Risk: <strong className="text-emerald-400">{incident.recommendation.risk.toUpperCase()}</strong></span>
            <span>·</span>
            <span>Reversible: <strong className="text-slate-200">{incident.recommendation.reversible ? 'YES' : 'NO'}</strong></span>
            <span>·</span>
            <span>Rollback: <span className="text-slate-400">{incident.recommendation.rollback}</span></span>
          </div>

          {actionError && <div className="text-[11px] font-mono text-amber-300">{actionError}</div>}
          {dryRunOutput && (
            <pre className="p-2.5 rounded bg-black/60 border border-slate-700 text-[11px] font-mono text-cyan-300 whitespace-pre-wrap">
              {dryRunOutput}
            </pre>
          )}
        </div>
      )}

      {/* Reveal Modal */}
      {revealModal && (
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <div className="hud-panel p-5 max-w-md w-full bg-[#121620] border border-purple-500/40 space-y-4">
            <h4 className="text-sm font-mono font-bold text-purple-300">
              CREATE REVEAL REQUEST FOR {revealModal}
            </h4>
            <p className="text-xs text-slate-300">
              Per privacy boundary rules, raw identifiers stay strictly inside the customer's machine. To reveal this pseudonym, you must submit a formal justification to the shop manager.
            </p>
            <div>
              <label className="text-[10px] font-mono uppercase text-slate-400 block mb-1">
                Investigation Justification
              </label>
              <textarea
                value={revealReason}
                onChange={(e) => setRevealReason(e.target.value)}
                placeholder="Reason for pseudonym resolution..."
                rows={3}
                className="w-full bg-[#080A10] border border-slate-700 p-2 text-xs font-mono text-slate-100 rounded focus:border-purple-500 outline-none"
              />
            </div>
            {revealStatus && (
              <div className="text-xs font-mono text-purple-400">{revealStatus}</div>
            )}
            <div className="flex justify-end space-x-2">
              <button
                onClick={() => setRevealModal(null)}
                className="px-3 py-1 text-xs font-mono rounded bg-slate-800 text-slate-300"
              >
                CANCEL
              </button>
              <button
                onClick={() => submitRevealRequest(revealModal)}
                className="px-3 py-1 text-xs font-mono font-bold rounded bg-purple-600 text-white hover:bg-purple-500"
              >
                SUBMIT REQUEST
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
