import React, { useState } from 'react';
import { apiFetch } from '../services/apiClient';

interface Explanation {
  parts: { what: string; why: string; serious: string; next: string } | null;
  evidence_ids: string[];
  source: 'model' | 'rules' | 'error';
  message?: string;
}

const ROWS: [keyof NonNullable<Explanation['parts']>, string, string][] = [
  ['what', 'WHAT HAPPENED', 'text-sky-300'], ['why', 'WHY IT WAS FLAGGED', 'text-purple-300'],
  ['serious', 'HOW SERIOUS', 'text-amber-300'], ['next', 'WHAT NEXT', 'text-emerald-300'],
];

// "Explain with AI": sends this one alert (and only its own evidence) to the head-office copilot and shows the answer right here.
export const ExplainAI: React.FC<{ kind: 'alert' | 'incident'; id: string; tenant: string }> = ({ kind, id, tenant }) => {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [res, setRes] = useState<Explanation | null>(null);

  const click = async () => {
    if (res) { setOpen((o) => !o); return; }
    setOpen(true); setBusy(true);
    try {
      setRes(await apiFetch<Explanation>('/api/ai/explain', { method: 'POST', body: JSON.stringify({ kind, id, tenant_id: tenant }), timeoutMs: 120000 }));
    } catch (e: any) {
      setRes({ parts: null, evidence_ids: [], source: 'error', message: e.message });
    }
    setBusy(false);
  };

  return (
    <>
      <button onClick={click} disabled={busy}
        className="px-2.5 py-1 rounded border border-sky-500/40 text-sky-300 hover:bg-sky-500/10 disabled:opacity-60 font-mono text-[11px] font-bold">
        {busy ? 'AI IS READING THE EVIDENCE…' : res && open ? 'HIDE EXPLANATION' : 'EXPLAIN WITH AI'}
      </button>
      {open && (busy || res) && (
        <div className="basis-full w-full mt-2 p-3 rounded bg-[#0d1320] border border-sky-500/20 font-mono text-xs space-y-2">
          {busy && <div className="text-slate-400">Collecting this alert&apos;s evidence and asking the local model. This can take up to half a minute.</div>}
          {res?.parts && ROWS.map(([k, label, color]) => (
            <div key={k}><div className={`text-[10px] font-bold tracking-widest ${color}`}>{label}</div><div className="text-slate-200 leading-relaxed">{res.parts![k]}</div></div>
          ))}
          {res && !res.parts && <div className="text-amber-300">{res.message || 'No explanation available.'}</div>}
          {res?.parts && (
            <div className="pt-2 border-t border-white/5 flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-slate-500">EVIDENCE</span>
              {res.evidence_ids.map((e) => <span key={e} className="px-1.5 py-0.5 rounded bg-sky-900/40 border border-sky-500/30 text-[10px] text-sky-300">{e}</span>)}
              <span className={`ml-auto text-[10px] font-bold ${res.source === 'model' ? 'text-emerald-400' : 'text-amber-300'}`}>
                {res.source === 'model' ? 'LOCAL AI MODEL, CHECKED AGAINST THE EVIDENCE' : 'RULES-BASED: THE MODEL ANSWER DID NOT PASS THE EVIDENCE CHECK'}
              </span>
            </div>
          )}
        </div>
      )}
    </>
  );
};
