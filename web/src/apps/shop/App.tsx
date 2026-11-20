import React, { useState, useEffect } from 'react';
import { shopApi, LocalGuardStatus, LocalLogEntry, EgressPayloadEntry, RevealRequestItem, ActionRequestItem } from '../../services/shopApi';
import { EgressProofPanel } from '../../components/EgressProofPanel';
import { TimeText } from '../../components/TimeText';
import { LocalAiChat, AiReference } from './LocalAiChat';

export const ShopApp: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'logs' | 'ai'>('logs');
  const [status, setStatus] = useState<LocalGuardStatus | null>(null);
  const [guardDown, setGuardDown] = useState(false);
  const [logs, setLogs] = useState<LocalLogEntry[]>([]);
  const [egressList, setEgressList] = useState<EgressPayloadEntry[]>([]);
  const [revealRequests, setRevealRequests] = useState<RevealRequestItem[]>([]);
  const [actionRequests, setActionRequests] = useState<ActionRequestItem[]>([]);
  const [countdown, setCountdown] = useState(84200);
  const [selectedEgress, setSelectedEgress] = useState<EgressPayloadEntry | null>(null);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [spotlightId, setSpotlightId] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      const [st, lg, eg, rev, act] = await Promise.all([
        shopApi.getStatus(),
        shopApi.getRawLogs(),
        shopApi.getEgressLedger(),
        shopApi.getRevealRequests(),
        shopApi.getActionRequests(),
      ]);
      setActionRequests(act);

      if (st) {
        setStatus(st);
        setGuardDown(false);
      } else {
        setGuardDown(true);
      }

      if (lg) setLogs(lg);
      if (eg && eg.length > 0) {
        setEgressList(eg);
        setSelectedEgress((cur) => (cur ? eg.find((e) => e.seq === cur.seq) || cur : eg[0]));
      }
      if (rev) setRevealRequests(rev);
    };

    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (status) setCountdown(status.retention_countdown_s);
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
    await shopApi.decideReveal(requestId, decision, 'Actioned by Local Guard Operator');
    setRevealRequests((prev) =>
      prev.map((r) => (r.request_id === requestId ? { ...r, status: decision } : r))
    );
    setDecidingId(null);
  };

  // Clickable reference handler: auto-scroll & spotlight
  const handleNavigateToReference = (ref: AiReference) => {
    setActiveTab('logs');
    setSpotlightId(ref.targetId);

    setTimeout(() => {
      let targetEl: HTMLElement | null = null;
      if (ref.type === 'log' || ref.type === 'secret') {
        targetEl = document.getElementById(`log-row-${ref.targetId}`);
      } else if (ref.type === 'egress') {
        targetEl = document.getElementById(`egress-proof-section`);
        const found = egressList.find((e) => String(e.seq) === ref.targetId);
        if (found) setSelectedEgress(found);
      } else if (ref.type === 'buffer') {
        targetEl = document.getElementById(`kpi-buffer-depth`);
      }

      if (targetEl) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }

      // Clear spotlight pulse after 3.5 seconds
      setTimeout(() => {
        setSpotlightId(null);
      }, 3500);
    }, 120);
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-[#D1D5DB] font-mono flex flex-col select-none">
      {/* De-cluttered Top Header: Local Guard + Two Tabs */}
      <header className="h-14 bg-[#0A0D15] border-b border-white/[0.08] px-5 flex items-center z-30">
        <div className="flex items-center space-x-6">
          <span className="text-sm font-black tracking-widest text-white uppercase">
            LOCAL GUARD
          </span>

          {/* Navigation Tabs */}
          <nav className="flex space-x-2">
            <button
              onClick={() => setActiveTab('logs')}
              className={`px-3 py-1.5 rounded text-xs font-bold tracking-wider transition-colors ${
                activeTab === 'logs'
                  ? 'bg-lime-500/15 text-lime-300 border border-lime-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`}
            >
              LOGS & EGRESS PROOF
            </button>
            <button
              onClick={() => setActiveTab('ai')}
              className={`px-3 py-1.5 rounded text-xs font-bold tracking-wider transition-colors ${
                activeTab === 'ai'
                  ? 'bg-lime-500/15 text-lime-300 border border-lime-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`}
            >
              LOCAL AI COPILOT
            </button>
          </nav>
        </div>
      </header>

      {/* Main Body */}
      <main className="p-5 flex-1 max-w-[1700px] w-full mx-auto space-y-5">
        {/* TAB 1: LOGS & EGRESS PROOF */}
        {activeTab === 'logs' && (
          <div className="space-y-5">
            {/* Minimalist 4-Stat KPI Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="hud-panel p-3.5 bg-[#0C1017] border border-white/10 space-y-1">
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">GUARD STATUS</span>
                <span className="text-base font-black text-white uppercase flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  {status?.status?.toUpperCase() || 'NO GUARD'}
                </span>
                <span className="text-[10px] text-slate-500 block">CPU: {status?.guard_cpu_pct?.toFixed(1) || '0.0'}% · {status?.guard_mem_mb ?? 0} MB</span>
              </div>

              <div
                id="kpi-buffer-depth"
                className={`hud-panel p-3.5 bg-[#0C1017] border border-white/10 space-y-1 transition-all duration-300 ${
                  spotlightId === 'buffer-status' ? 'ring-2 ring-lime-400 bg-lime-500/20 shadow-[0_0_25px_rgba(163,230,53,0.4)]' : ''
                }`}
              >
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">OUTBOX BUFFER DEPTH</span>
                <span className="text-base font-black text-emerald-400 block">
                  {status?.buffer_depth ?? 0} <span className="text-xs text-slate-400">PAYLOADS PENDING</span>
                </span>
                <span className="text-[10px] text-slate-500 block">Immediate dispatch to Cloud</span>
              </div>

              <div className="hud-panel p-3.5 bg-[#0C1017] border border-white/10 space-y-1">
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">RETENTION PURGE COUNTDOWN</span>
                <span className="text-base font-black text-amber-400 font-tabular block">
                  {formatCountdown(countdown)}
                </span>
                <span className="text-[10px] text-slate-500 block">24h rolling local RAM purge</span>
              </div>

              <div className="hud-panel p-3.5 bg-[#0C1017] border border-white/10 space-y-1">
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider block">SECRETS REDACTED (LOCAL)</span>
                <span className="text-base font-black text-purple-300 block">
                  {status?.secrets_redacted ?? 0} <span className="text-xs text-slate-400">TRIPPED & MASKED</span>
                </span>
                <span className="text-[10px] text-slate-500 block">Canaries planted: {status?.canaries_planted ?? 0}</span>
              </div>
            </div>

            {/* Egress Proof Inspector Section */}
            <div id="egress-proof-section" className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                  CRYPTOGRAPHIC EGRESS PROOF (EDGE OUTBOX VS CLOUD INGEST)
                </span>
                <div className="flex items-center space-x-1.5">
                  <span className="text-[10px] text-slate-500 mr-1">PAYLOAD:</span>
                  {egressList.map((eg) => (
                    <button
                      key={eg.seq}
                      onClick={() => setSelectedEgress(eg)}
                      className={`px-2.5 py-1 rounded text-[10px] font-bold transition-all ${
                        selectedEgress?.seq === eg.seq
                          ? 'bg-lime-500 text-black shadow-[0_0_10px_rgba(163,230,53,0.3)]'
                          : 'bg-slate-800 text-slate-400 hover:text-white'
                      }`}
                    >
                      Seq #{eg.seq}
                    </button>
                  ))}
                </div>
              </div>
              {selectedEgress && <EgressProofPanel localEgress={selectedEgress} />}
            </div>

            {/* Split: Raw Logs with Crimson Secrets + Head Office Reveal Requests */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
              {/* Raw Local Logs Stream */}
              <div className="lg:col-span-8 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                    LOCAL RAW LOG STORE (SECRETS HIGHLIGHTED IN CRIMSON - VISIBLE ONLY HERE)
                  </span>
                  <span className="text-[10px] text-slate-500">IN-MEMORY ROLLING DB</span>
                </div>

                <div className="hud-panel p-3 bg-[#080A10] border border-white/10 max-h-96 overflow-y-auto space-y-2.5 divide-y divide-white/5">
                  {logs.map((log) => {
                    const isSpotlighted = spotlightId === log.id;
                    return (
                      <div
                        id={`log-row-${log.id}`}
                        key={log.id}
                        className={`p-3 rounded-lg border text-xs font-mono leading-relaxed transition-all duration-300 ${
                          isSpotlighted
                            ? 'ring-2 ring-lime-400 bg-lime-500/20 border-lime-400 shadow-[0_0_25px_rgba(163,230,53,0.5)] scale-[1.01]'
                            : log.has_secret
                            ? 'bg-rose-950/20 border-rose-500/30'
                            : 'bg-[#10141f] border-white/5'
                        }`}
                      >
                        <div className="flex items-center justify-between text-[10px] mb-1.5">
                          <div className="flex items-center space-x-2">
                            <span className="text-slate-400 font-bold">LOG #{log.id}</span>
                            <span className="text-slate-500">·</span>
                            <span className="text-slate-400"><TimeText timestamp={log.timestamp} /></span>
                          </div>
                          <span className={log.has_secret ? 'text-rose-400 font-bold px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/20' : 'text-slate-500'}>
                            {log.has_secret ? `[${log.secret_type || 'TRIPWIRE SECRET'}]` : log.level}
                          </span>
                        </div>

                        {/* Raw text with secrets highlighted in crimson */}
                        <div className="text-slate-200">
                          {(log.parts || [{ text: log.message, secret: false }]).map((p, i) =>
                            p.secret ? (
                              <mark key={i} className="bg-rose-600/40 text-rose-200 font-bold px-1.5 py-0.5 rounded mx-1 border border-rose-500/40">
                                {p.text}
                              </mark>
                            ) : (
                              <span key={i}>{p.text}</span>
                            )
                          )}
                        </div>

                        {log.redacted_preview && (
                          <div className="mt-1.5 pt-1.5 border-t border-white/5 text-[10px] text-slate-500 italic">
                            Egress scrubber preview: <span className="text-slate-400">{log.redacted_preview}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Reveal Requests */}
              <div className="lg:col-span-4 space-y-2">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  CLOUD ACTION REQUESTS (APPROVE BEFORE ANYTHING RUNS)
                </span>
                <div className="space-y-3">
                  {actionRequests.map((a) => (
                    <div key={a.intent_id} className="hud-panel p-4 space-y-2 border border-cyan-500/30 bg-[#0c101b]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-xs">{a.action.toUpperCase()}: <span className="text-cyan-300">{a.target}</span></span>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          a.status === 'pending' ? 'bg-amber-500/20 text-amber-400'
                          : a.status === 'done' ? 'bg-emerald-500/20 text-emerald-400'
                          : a.status === 'running' ? 'bg-sky-500/20 text-sky-300'
                          : 'bg-rose-500/20 text-rose-400'}`}>{a.status.replace('_', ' ').toUpperCase()}</span>
                      </div>
                      {(a.details?.why || a.details?.impact) && <p className="text-slate-300 text-xs leading-relaxed">{a.details?.why || a.details?.impact}</p>}
                      <div className="text-[10px] text-slate-500">Approved at head office by {a.approved_by || '—'} · <TimeText timestamp={a.created_at} /></div>
                      {a.status === 'pending' && (
                        <div className="flex space-x-2 pt-1 border-t border-white/5">
                          <button onClick={() => shopApi.decideAction(a.intent_id, true)}
                            className="flex-1 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs cursor-pointer">APPROVE &amp; RUN</button>
                          <button onClick={() => shopApi.decideAction(a.intent_id, false)}
                            className="flex-1 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs cursor-pointer">REJECT</button>
                        </div>
                      )}
                    </div>
                  ))}
                  {actionRequests.length === 0 && (
                    <div className="hud-panel p-6 text-center text-slate-500 text-xs">No action requests from Cloud Dashboard.</div>
                  )}
                </div>
              </div>

              <div className="lg:col-span-4 lg:col-start-9 space-y-2">
                <span className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
                  CLOUD REVEAL REQUESTS
                </span>

                <div className="space-y-3">
                  {revealRequests.map((rev) => (
                    <div key={rev.request_id} className="hud-panel p-4 space-y-3 border border-purple-500/30 bg-[#0c101b]">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-white text-xs">{rev.pseudonym}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
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
                      <p className="text-slate-300 text-xs leading-relaxed">{rev.reason}</p>
                      <div className="text-[10px] text-slate-500">
                        Requested by: {rev.requested_by}
                      </div>

                      {rev.status === 'pending' && (
                        <div className="flex space-x-2 pt-1 border-t border-white/5">
                          <button
                            onClick={() => handleRevealDecision(rev.request_id, 'approved')}
                            disabled={decidingId === rev.request_id}
                            className="flex-1 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-sm transition-colors cursor-pointer"
                          >
                            APPROVE REVEAL
                          </button>
                          <button
                            onClick={() => handleRevealDecision(rev.request_id, 'rejected')}
                            disabled={decidingId === rev.request_id}
                            className="flex-1 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-bold text-xs transition-colors cursor-pointer"
                          >
                            REJECT
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                  {revealRequests.length === 0 && (
                    <div className="hud-panel p-6 text-center text-slate-500 text-xs">
                      No pending reveal requests from Cloud Dashboard.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: LOCAL AI COPILOT */}
        {activeTab === 'ai' && (
          <LocalAiChat
            logs={logs}
            status={status}
            egressList={egressList}
            onNavigateToReference={handleNavigateToReference}
          />
        )}
      </main>
    </div>
  );
};

export default ShopApp;
