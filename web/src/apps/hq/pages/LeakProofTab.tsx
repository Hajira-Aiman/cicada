import React, { useEffect, useState } from 'react';
import { apiFetch } from '@/services/apiClient';
import { chaosApi } from '@/services/chaosApi';
import { shopApi, EgressPayloadEntry, LocalGuardStatus, LocalLogEntry } from '@/services/shopApi';
import { useLiveStore } from '@/stores/liveStore';
import { TimeText } from '@/components/TimeText';

// One page for the try-to-leak demo: type a secret, see it in full inside the shop, and see that head office never gets it.
// The left side reads the shop's own guard API (localhost:9000, raw logs are served to the shop machine only), so open this tab in a browser on the shop laptop.

const SAMPLE = 'DB_PASSWORD=SuperSecret123!';
interface Ev { id: number; category: string; severity: string; count: number; event_time: string; source: string }

export const LeakProofTab: React.FC = () => {
  const counters = useLiveStore((s) => s.counters);
  const [text, setText] = useState(SAMPLE);
  const [sent, setSent] = useState<{ text: string; at: number } | null>(null);
  const [msg, setMsg] = useState('');
  const [status, setStatus] = useState<LocalGuardStatus | null>(null);
  const [logs, setLogs] = useState<LocalLogEntry[]>([]);
  const [egress, setEgress] = useState<EgressPayloadEntry[]>([]);
  const [shopUp, setShopUp] = useState(true);
  const [events, setEvents] = useState<Ev[]>([]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      const [st, lg, eg, ev] = await Promise.all([
        shopApi.getStatus(), shopApi.getRawLogs(), shopApi.getEgressLedger(),
        apiFetch<{ events: Ev[] }>('/api/events?limit=200').catch(() => ({ events: [] as Ev[] })),
      ]);
      if (stop) return;
      setShopUp(!!st);
      if (st) setStatus(st);
      setLogs(lg);
      setEgress(eg);
      setEvents(ev.events.filter((e) => e.category === 'secret_redacted').slice(0, 6));
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  const attempt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    const r = await chaosApi.injectLog(text, 'guard-acme-01');
    setMsg(r.message);
    if (r.success) setSent({ text, at: Date.now() });
  };

  // does anything the typed secret contains appear in the exact JSON the guard sent out?
  const needles = sent ? [sent.text, sent.text.split(/[:=]/).slice(1).join('=').trim()].filter((n) => n.length >= 4) : [];
  const sentSince = egress.filter((p) => !sent || new Date(p.sent_at).getTime() >= sent.at - 5000);
  const leaked = sent ? sentSince.filter((p) => needles.some((n) => JSON.stringify(p.raw_payload).includes(n))).length : 0;
  const secretLogs = logs.filter((l) => l.has_secret).slice(0, 4);
  const latest = egress[0];

  const box = 'hud-panel p-4 space-y-3';
  const label = 'text-[10px] font-mono uppercase font-bold tracking-widest';

  return (
    <div className="p-5 space-y-4 max-w-[1700px] mx-auto font-mono text-xs">
      {/* script */}
      <div className={`${box} border border-purple-500/30 bg-purple-950/10`}>
        <div className={`${label} text-purple-400`}>TRY-TO-LEAK · LIVE DEMO</div>
        <ol className="text-slate-300 space-y-1 list-decimal list-inside">
          <li>A judge types any password or key below and presses <b>ATTEMPT LEAK</b>.</li>
          <li><b className="text-lime-400">Left (inside the shop):</b> the line appears with the secret in red, then the masked copy that is allowed to leave.</li>
          <li><b className="text-purple-300">Right (head office):</b> only a count of redacted secrets arrives. The leak counter stays at 0 and the typed text is not found in anything sent.</li>
        </ol>
        <form onSubmit={attempt} className="flex gap-2">
          <input value={text} onChange={(e) => setText(e.target.value)} className="flex-1 bg-[#080A10] border border-purple-500/30 rounded px-3 py-2 text-white outline-none focus:border-purple-400" />
          <button type="submit" className="px-5 rounded bg-purple-600 hover:bg-purple-500 text-white font-bold">ATTEMPT LEAK</button>
        </form>
        {msg && <div className="text-purple-300">{msg}</div>}
        <div className="text-[10px] text-slate-500">Best formats: <code>password=…</code>, <code>api_key=…</code>, <code>AKIA…</code> keys, JWTs, bearer tokens, card numbers. Anything else is still blocked by the payload schema, which cannot carry free text.</div>
      </div>

      {!shopUp && (
        <div className="p-3 rounded border border-amber-500/40 bg-amber-500/10 text-amber-300">
          Shop guard not reachable on this browser (localhost:9000). Open this page on the shop laptop; raw logs are only served there.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* LEFT: inside the shop */}
        <div className={`${box} border border-lime-500/30`}>
          <div className="flex justify-between"><span className={`${label} text-lime-400`}>INSIDE THE SHOP · local only</span><span className="text-slate-500">TIER 1</span></div>
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">SECRETS TRIPPED &amp; MASKED</div><div className="text-2xl font-black text-lime-300">{status?.secrets_redacted ?? 0}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">CANARIES PLANTED</div><div className="text-2xl font-black text-lime-300">{status?.canaries_planted ?? 0}</div></div>
          </div>
          <div className="text-slate-400 font-bold">RAW LOG (what the shop really holds)</div>
          {secretLogs.length === 0 && <div className="text-slate-500">No log line with a secret yet. Press ATTEMPT LEAK.</div>}
          {secretLogs.map((l) => (
            <div key={l.id} className="p-2 rounded bg-black/40 border border-rose-500/20 space-y-1">
              <div className="text-slate-500"><TimeText timestamp={l.timestamp} /></div>
              <div className="break-all">{(l.parts || [{ text: l.message, secret: false }]).map((p, i) => (
                <span key={i} className={p.secret ? 'text-rose-400 font-bold bg-rose-500/10' : 'text-slate-200'}>{p.text}</span>))}</div>
              {l.redacted_preview && <div className="break-all text-slate-400">↳ leaves the shop as: <span className="text-emerald-300">{l.redacted_preview}</span></div>}
            </div>
          ))}
        </div>

        {/* RIGHT: head office */}
        <div className={`${box} border border-purple-500/30`}>
          <div className="flex justify-between"><span className={`${label} text-purple-300`}>HEAD OFFICE · cloud</span><span className="text-slate-500">TIER 2</span></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">LEAKS DETECTED</div><div className={`text-2xl font-black ${counters.leaks_detected ? 'text-rose-400' : 'text-emerald-300'}`}>{counters.leaks_detected}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">CANARIES PLANTED</div><div className="text-2xl font-black text-purple-300">{counters.canaries_planted.toLocaleString()}</div></div>
            <div className="p-2 rounded bg-black/30"><div className="text-slate-500">REDACTED (reported)</div><div className="text-2xl font-black text-purple-300">{events.reduce((n, e) => n + (e.count || 0), 0)}</div></div>
          </div>
          <div className="text-slate-400 font-bold">WHAT HEAD OFFICE RECEIVED ABOUT IT</div>
          {events.length === 0 && <div className="text-slate-500">No redaction event yet.</div>}
          {events.map((e) => (
            <div key={e.id} className="p-2 rounded bg-black/40 flex justify-between">
              <span className="text-slate-200">secret_redacted · count {e.count} · {e.severity}</span>
              <TimeText timestamp={e.event_time} />
            </div>
          ))}
          <div className={`p-3 rounded border ${!sent ? 'border-white/10 text-slate-400' : leaked ? 'border-rose-500/50 bg-rose-500/10 text-rose-300' : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'}`}>
            {!sent
              ? 'Leak check waiting for an attempt.'
              : leaked
                ? `✕ Typed text FOUND in ${leaked} payload(s) sent after the attempt.`
                : `✓ Typed text NOT FOUND in the ${sentSince.length} payload(s) sent since the attempt (exact JSON below).`}
          </div>
        </div>
      </div>

      {/* exact bytes that crossed */}
      <div className={`${box} border border-white/10`}>
        <div className="flex justify-between">
          <span className={`${label} text-slate-300`}>LATEST PAYLOAD THAT LEFT THE SHOP (exact JSON)</span>
          {latest && <span className="text-slate-500">seq #{latest.seq} · SHA-256 <span className="text-lime-400">{latest.sha256.slice(0, 16)}…</span> · {latest.match ? <span className="text-emerald-400">✓ receipt matches</span> : <span className="text-amber-300">awaiting receipt</span>}</span>}
        </div>
        <pre className="p-3 rounded bg-[#080A10] border border-white/5 text-[11px] text-slate-300 max-h-72 overflow-auto">{latest ? JSON.stringify(latest.raw_payload, null, 2) : 'No payload yet.'}</pre>
        <div className="text-slate-500">Only numbers, fixed labels and pseudonyms. The schema rejects unknown fields, so free text cannot be added.</div>
      </div>
    </div>
  );
};
