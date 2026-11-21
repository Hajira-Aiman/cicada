import React, { useState } from 'react';
import { CHAOS_API_URL } from '@/services/chaosApi';
import { useLiveStore } from '@/stores/liveStore';
import { TimeText } from '@/components/TimeText';

// One page for the tamper demo: forge two payloads, see head office refuse both, and see that its records stayed clean.
// The attack runs from the shop's chaos agent (localhost:9100), because it copies a real payload from that guard's ledger.

interface Result { byte_flipped?: number; extra_field?: number; error?: string }

const ATTACKS = [
  { key: 'byte_flipped' as const, title: 'ATTACK 1 · Altered after signing',
    what: 'One byte of a real, signed payload is flipped in transit.', expect: 401,
    why: 'The HMAC no longer matches the body, so head office rejects it as unauthenticated.' },
  { key: 'extra_field' as const, title: 'ATTACK 2 · Smuggled field',
    what: 'A correctly signed payload that carries an extra field: raw_log = "password=hunter2".', expect: 422,
    why: 'The signature is valid, but the allow-list schema forbids unknown fields, so it is rejected and nothing is stored.' },
];

export const TamperTab: React.FC = () => {
  const alerts = useLiveStore((s) => s.alerts);
  const recon = useLiveStore((s) => s.reconciliation);
  const checkpoints = useLiveStore((s) => s.checkpoints);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [ranAt, setRanAt] = useState<number | null>(null);

  const run = async () => {
    setBusy(true); setResult(null);
    try {
      const res = await fetch(`${CHAOS_API_URL}/scenarios/tamper`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ duration_s: 20 }), signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`Chaos agent refused: HTTP ${res.status}`);
      const started = await res.json();
      setRanAt(Date.now());
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 600));
        const act = await (await fetch(`${CHAOS_API_URL}/chaos/active`, { signal: AbortSignal.timeout(3000) })).json();
        const mine = (act.active || []).find((a: any) => a.id === started.id);
        if (mine?.result) { setResult(mine.result); setBusy(false); return; }
      }
      setResult({ error: 'No answer from head office ingest in time.' });
    } catch (e: any) {
      setResult({ error: e?.message?.includes('refused') ? e.message : `Chaos agent not reachable on ${CHAOS_API_URL}.` });
    }
    setBusy(false);
  };

  const tamperAlerts = alerts.filter((a) => a.source === 'ingest_security').slice(0, 6);
  const guard = recon['guard-acme-01'] || Object.values(recon)[0];
  const cp = checkpoints[guard?.guard_id || 'guard-acme-01'];
  const box = 'hud-panel p-4 space-y-3';
  const label = 'text-[10px] font-mono uppercase font-bold tracking-widest';

  return (
    <div className="p-5 space-y-4 max-w-[1700px] mx-auto font-mono text-xs">
      <div className={`${box} border border-rose-500/30 bg-rose-950/10`}>
        <div className={`${label} text-rose-400`}>TAMPER TEST · LIVE DEMO</div>
        <ol className="text-slate-300 space-y-1 list-decimal list-inside">
          <li>Press <b>RUN TAMPER ATTACK</b>. Two forged payloads are sent to head office as if from the shop guard.</li>
          <li><b className="text-rose-300">Left:</b> head office answers each with an error code, and nothing is stored.</li>
          <li><b className="text-purple-300">Right:</b> each rejection raises a tamper alert, while the delivery record stays intact: no duplicates, no gaps, checkpoint still matching.</li>
        </ol>
        <button onClick={run} disabled={busy} className="px-5 py-2 rounded bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white font-bold cursor-pointer">
          {busy ? 'ATTACKING…' : 'RUN TAMPER ATTACK'}
        </button>
        {result?.error && <div className="text-amber-300">{result.error}</div>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* what was sent and how head office answered */}
        <div className="space-y-4">
          {ATTACKS.map((a) => {
            const code = result?.[a.key];
            const ok = code === a.expect;
            return (
              <div key={a.key} className={`${box} border ${code === undefined ? 'border-white/10' : ok ? 'border-emerald-500/40' : 'border-rose-500/50'}`}>
                <div className="flex justify-between">
                  <span className={`${label} text-rose-300`}>{a.title}</span>
                  <span className="text-slate-500">expected HTTP {a.expect}</span>
                </div>
                <div className="text-slate-300">{a.what}</div>
                <div className={`p-2 rounded bg-black/40 text-lg font-black ${code === undefined ? 'text-slate-500' : ok ? 'text-emerald-300' : 'text-rose-400'}`}>
                  {code === undefined ? (busy ? 'waiting for head office…' : 'not run yet') : ok ? `HTTP ${code} · REJECTED ✓` : `HTTP ${code} · NOT REJECTED AS EXPECTED ✕`}
                </div>
                <div className="text-slate-500">{a.why}</div>
              </div>
            );
          })}
        </div>

        {/* head office evidence */}
        <div className={`${box} border border-purple-500/30`}>
          <div className="flex justify-between"><span className={`${label} text-purple-300`}>HEAD OFFICE · what it recorded</span><span className="text-slate-500">TIER 2</span></div>
          <div className="text-slate-400 font-bold">TAMPER ALERTS</div>
          {tamperAlerts.length === 0 && <div className="text-slate-500">No tamper alert yet.</div>}
          {tamperAlerts.map((a) => (
            <div key={a.alert_id} className={`p-2 rounded bg-black/40 border ${ranAt && new Date(a.created_at).getTime() >= ranAt - 5000 ? 'border-rose-500/40' : 'border-white/5'} flex justify-between gap-3`}>
              <span className="text-slate-200">{a.title} <span className="text-slate-500">· {a.severity}</span></span>
              <TimeText timestamp={a.created_at} />
            </div>
          ))}
          <div className="text-slate-400 font-bold pt-1">DELIVERY RECORD STAYS CLEAN ({guard?.guard_id || 'guard-acme-01'})</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">SENT / RECEIVED</div><div className="text-lg font-black text-purple-300">{guard ? `${guard.sent_count} / ${guard.received_count}` : '—'}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">DUPLICATES</div><div className="text-lg font-black text-purple-300">{guard?.duplicate_count ?? '—'}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">GAPS</div><div className={`text-lg font-black ${guard && guard.gaps.length ? 'text-rose-400' : 'text-emerald-300'}`}>{guard ? (guard.gaps.length || 'NONE') : '—'}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">CHECKPOINT</div><div className={`text-lg font-black ${cp?.match === false ? 'text-rose-400' : 'text-emerald-300'}`}>{cp ? (cp.match ? '✓ MATCH' : '✕ DIFFERS') : '—'}</div></div>
          </div>
          <div className="text-slate-500">The forged payloads were never stored, so the guard's own sequence and head office's copy still agree.</div>
        </div>
      </div>
    </div>
  );
};
