import { ShopAssistant } from '../../features/ShopAssistant';
import React, { useState, useEffect } from 'react';
import { shopApi, LocalGuardStatus, LocalLogEntry, EgressPayloadEntry, RevealRequestItem } from '../../services/shopApi';
import { EgressProofPanel } from '../../components/EgressProofPanel';
import { TimeText } from '../../components/TimeText';

export const ShopApp: React.FC = () => {
  const [status, setStatus] = useState<LocalGuardStatus | null>(null);
  const [guardDown, setGuardDown] = useState(false);
  const [logs, setLogs] = useState<LocalLogEntry[]>([]);
  const [egressList, setEgressList] = useState<EgressPayloadEntry[]>([]);
  const [revealRequests, setRevealRequests] = useState<RevealRequestItem[]>([]);
  const [countdown, setCountdown] = useState(0);
  const [selectedEgress, setSelectedEgress] = useState<EgressPayloadEntry | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      const [st, lg, eg, rev] = await Promise.all([
        shopApi.getStatus(),
        shopApi.getRawLogs(),
        shopApi.getEgressLedger(),
        shopApi.getRevealRequests(),
      ]);
      setStatus(st);
      setGuardDown(!st);
      setLogs(lg);
      setEgressList(eg);
      setSelectedEgress((cur) => (cur ? eg.find((e) => e.seq === cur.seq) || cur : eg[0] || null));
      setRevealRequests(rev);
    };

    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (status) setCountdown(status.retention_countdown_s);   // resync from the guard on every poll
  }, [status]);
  useEffect(() => {
    const timer = setInterval(() => setCountdown((prev) => (prev > 0 ? prev - 1 : 0)), 1000);
    return () => clearInterval(timer);
  }, []);

  const formatCountdown = (s: number) => {
    const hrs = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const secs = s % 60;
    return `${hrs}h ${mins.toString().padStart(2, '0')}m ${secs.toString().padStart(2, '0')}s`;
  };

  const handleRevealDecision = async (requestId: string, decision: 'approved' | 'rejected') => {
    setDecidingId(requestId);
    await shopApi.decideReveal(requestId, decision, 'Actioned by Acme Shop Manager');
    setRevealRequests((prev) =>
      prev.map((r) => (r.request_id === requestId ? { ...r, status: decision } : r))
    );
    setDecidingId(null);
  };

  return (
    <div className="min-h-screen bg-[#080A10] text-[#D1D5DB] font-sans flex flex-col">
      {guardDown && <div className="bg-rose-900/60 text-rose-200 text-xs font-mono px-4 py-2">Cannot reach the guard API on port 9000. Start the guard on this machine; nothing is shown until it answers.</div>}
      {/* Full-width Lime Local Accent Banner */}
      <div className="w-full bg-[#A3E635] text-black px-4 py-2 flex items-center justify-between font-mono font-bold text-xs shadow-lg">
        <div className="flex items-center space-x-2">
          <span className="w-2.5 h-2.5 rounded-full bg-black animate-pulse" />
          <span>LOCAL · RAW DATA STAYS ON THIS MACHINE · ACME (INDIA)</span>
        </div>
        <div className="flex items-center space-x-3 text-[11px]">
          <span>TIER 1 COLLECTOR GUARD :9000</span>
          <span>·</span>
          <span>ZERO CLOUD EXPORT OF SECRETS</span>
        </div>
      </div>

      <div className="p-4 space-y-4 max-w-[1920px] mx-auto flex-1 w-full font-mono text-xs">
        {/* Status Strip */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="hud-panel hud-panel--local p-3">
            <span className="text-[10px] text-lime-400 font-bold uppercase block">GUARD STATUS</span>
            <span className="text-lg font-black text-white uppercase mt-0.5 block">{guardDown ? 'GUARD OFFLINE' : status?.status || '…'}</span>
          </div>
          <div className="hud-panel hud-panel--local p-3">
            <span className="text-[10px] text-lime-400 font-bold uppercase block">BUFFER DEPTH</span>
            <span className="text-lg font-black text-white mt-0.5 block">{status?.buffer_depth ?? 0} <span className="text-xs text-slate-400">payloads</span></span>
          </div>
          <div className="hud-panel hud-panel--local p-3">
            <span className="text-[10px] text-lime-400 font-bold uppercase block">RETENTION PURGE COUNTDOWN</span>
            <span className="text-lg font-black text-amber-400 font-tabular mt-0.5 block">{formatCountdown(countdown)}</span>
          </div>
          <div className="hud-panel hud-panel--local p-3">
            <span className="text-[10px] text-lime-400 font-bold uppercase block">CANARIES ACTIVE</span>
            <span className="text-lg font-black text-purple-300 mt-0.5 block">{status?.canaries_planted ?? '—'}</span>
          </div>
          <div className="hud-panel hud-panel--local p-3">
            <span className="text-[10px] text-lime-400 font-bold uppercase block">SECRETS REDACTED (LOCAL)</span>
            <span className="text-lg font-black text-emerald-400 mt-0.5 block">{status?.secrets_redacted ?? '—'}</span>
          </div>
        </div>

        {/* Egress Proof Panel (Hero) */}
        {selectedEgress && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-purple-400 uppercase tracking-wider">
                MANDATORY EGRESS PROOF: COMPARE LOCAL OUTBOX VS HEAD OFFICE INGEST
              </span>
              <div className="flex space-x-1">
                {egressList.map((eg) => (
                  <button
                    key={eg.seq}
                    onClick={() => setSelectedEgress(eg)}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      selectedEgress.seq === eg.seq
                        ? 'bg-purple-600 text-white'
                        : 'bg-slate-800 text-slate-400 hover:text-white'
                    }`}
                  >
                    Seq #{eg.seq}
                  </button>
                ))}
              </div>
            </div>
            <EgressProofPanel localEgress={selectedEgress} />
          </div>
        )}

        {/* Split: Raw Logs with Crimson Secrets + Reveal Requests */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Raw Local Logs Stream */}
          <div className="lg:col-span-8 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-lime-400 uppercase tracking-wider">
                TIER 1 RAW LOG STORE (SECRETS HIGHLIGHTED IN CRIMSON - VISIBLE ONLY HERE)
              </span>
              <span className="text-[10px] text-slate-500">24H ROLLING IN-MEMORY DB</span>
            </div>

            <div className="hud-panel p-3 bg-[#080A10] max-h-80 overflow-auto space-y-2 border-lime-500/20">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className={`p-2 rounded border text-[11px] font-mono leading-relaxed ${
                    log.has_secret
                      ? 'bg-rose-950/20 border-rose-500/30'
                      : 'bg-[#121620] border-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between text-[10px] mb-1">
                    <span className="text-slate-400"><TimeText timestamp={log.timestamp} /></span>
                    <span className={log.has_secret ? 'text-rose-400 font-bold' : 'text-slate-500'}>
                      {log.has_secret ? `TRIPWIRE: ${log.secret_type || 'SECRET'}` : log.level}
                    </span>
                  </div>
                  {/* Highlight secrets in crimson */}
                  <div className="text-slate-200">
                    {(log.parts || [{ text: log.message, secret: false }]).map((p, i) =>
                      p.secret
                        ? <mark key={i} className="bg-rose-600/30 text-rose-300 font-bold px-1 rounded mx-1">{p.text}</mark>
                        : <span key={i}>{p.text}</span>)}
                  </div>
                  {log.redacted_preview && (
                    <div className="mt-1 text-[10px] text-slate-500 italic">
                      Scrubber preview before egress: {log.redacted_preview}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Reveal Requests */}
          <div className="lg:col-span-4 space-y-2">
            <span className="text-xs font-bold text-purple-400 uppercase tracking-wider block">
              HEAD OFFICE REVEAL REQUESTS
            </span>

            <div className="space-y-2">
              {revealRequests.map((rev) => (
                <div key={rev.request_id} className="hud-panel p-3 space-y-2 border-purple-500/30">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">{rev.pseudonym}</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        rev.status === 'approved'
                          ? 'bg-emerald-500/20 text-emerald-400'
                          : rev.status === 'rejected'
                          ? 'bg-rose-500/20 text-rose-400'
                          : 'bg-amber-500/20 text-amber-400'
                      }`}
                    >
                      {rev.status.toUpperCase()}
                    </span>
                  </div>
                  <p className="text-slate-300 text-[11px]">{rev.reason}</p>
                  <div className="text-[10px] text-slate-500">
                    Requested by: {rev.requested_by}
                  </div>

                  {rev.status === 'pending' && (
                    <div className="flex space-x-2 pt-1">
                      <button
                        onClick={() => handleRevealDecision(rev.request_id, 'approved')}
                        disabled={decidingId === rev.request_id}
                        className="flex-1 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs"
                      >
                        APPROVE REVEAL
                      </button>
                      <button
                        onClick={() => handleRevealDecision(rev.request_id, 'rejected')}
                        disabled={decidingId === rev.request_id}
                        className="flex-1 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs"
                      >
                        REJECT
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
      <ShopAssistant />
    </div>
  );
};
