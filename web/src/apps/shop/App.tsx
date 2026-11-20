import React, { useState, useEffect } from 'react';
import { shopApi, LocalGuardStatus, LocalLogEntry, EgressPayloadEntry, RevealRequestItem } from '../../services/shopApi';
import { EgressProofPanel } from '../../components/EgressProofPanel';
import { TimeText } from '../../components/TimeText';
import { LocalAiChat, AiReference } from './LocalAiChat';

const MOCK_STATUS: LocalGuardStatus = {
  status: 'active',
  buffer_depth: 0,
  retention_countdown_s: 84200,
  canaries_planted: 420,
  secrets_redacted: 3,
  checkpoint_seq: 1420,
  checkpoint_root: 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  guard_id: 'guard-acme-01',
  tenant_id: 'acme',
  guard_cpu_pct: 14.2,
  guard_mem_mb: 46.5,
  policy_version: '0.3.1',
};

const MOCK_LOGS: LocalLogEntry[] = [
  {
    id: '1041',
    timestamp: new Date(Date.now() - 180000).toISOString(),
    level: 'INFO',
    message: 'Worker thread spawned on pid 1402 · socket initialized on 127.0.0.1:9000',
    has_secret: false,
    parts: [{ text: 'Worker thread spawned on pid 1402 · socket initialized on 127.0.0.1:9000', secret: false }],
  },
  {
    id: '1042',
    timestamp: new Date(Date.now() - 140000).toISOString(),
    level: 'WARN',
    message: 'Inbound request with header Authorization: Bearer sk_live_51M0SecretApiKey992381',
    has_secret: true,
    secret_type: 'Stripe API Key',
    redacted_preview: 'Inbound request with header Authorization: Bearer [REDACTED]',
    parts: [
      { text: 'Inbound request with header Authorization: Bearer ', secret: false },
      { text: 'sk_live_51M0SecretApiKey992381', secret: true },
    ],
  },
  {
    id: '1043',
    timestamp: new Date(Date.now() - 90000).toISOString(),
    level: 'WARN',
    message: 'SSH login burst: 50 failed auth attempts from src-9c2e0011 targeting user admin',
    has_secret: false,
    parts: [{ text: 'SSH login burst: 50 failed auth attempts from src-9c2e0011 targeting user admin', secret: false }],
  },
  {
    id: '1044',
    timestamp: new Date(Date.now() - 40000).toISOString(),
    level: 'INFO',
    message: 'Database connection string logged: postgres://app_user:db_password_super_secret_99@db.internal:5432/orders',
    has_secret: true,
    secret_type: 'Database Credential',
    redacted_preview: 'Database connection string logged: [REDACTED]@db.internal:5432/orders',
    parts: [
      { text: 'Database connection string logged: ', secret: false },
      { text: 'postgres://app_user:db_password_super_secret_99', secret: true },
      { text: '@db.internal:5432/orders', secret: false },
    ],
  },
  {
    id: '1045',
    timestamp: new Date(Date.now() - 10000).toISOString(),
    level: 'INFO',
    message: 'Synthetic tripwire canary credential planted: can_tripwire_7f3a99281a_sec',
    has_secret: true,
    secret_type: 'Tripwire Canary',
    redacted_preview: 'Synthetic tripwire canary credential planted: [REDACTED]',
    parts: [
      { text: 'Synthetic tripwire canary credential planted: ', secret: false },
      { text: 'can_tripwire_7f3a99281a_sec', secret: true },
    ],
  },
];

const MOCK_EGRESS: EgressPayloadEntry[] = [
  {
    payload_id: 'pay-7f3a1234-9c2e0011-0001420',
    seq: 1420,
    sent_at: new Date(Date.now() - 15000).toISOString(),
    sha256: 'a6c8e3100f91bc32e5b721894d0c1e6792a40bf59123847e09ab1847192847a1',
    receipt_sha256: 'a6c8e3100f91bc32e5b721894d0c1e6792a40bf59123847e09ab1847192847a1',
    match: true,
    raw_payload: {
      metrics: [
        { name: 'cpu_pct', avg: 14.2, max: 18.0, source: 'host-7f3a1234' },
        { name: 'mem_pct', avg: 42.1, max: 45.0, source: 'host-7f3a1234' },
        { name: 'latency_ms', avg: 38.0, max: 54.0, source: 'host-7f3a1234' },
      ],
      events: [
        { category: 'auth_failure_burst', count: 0, pseudonym: 'src-9c2e0011' },
      ],
      log_patterns: [
        { pattern_id: 'tpl-4a8f10b2', count: 14 },
      ],
      tripwire_canaries_planted: 420,
      cleartext_secrets_found: 0,
    },
  },
  {
    payload_id: 'pay-7f3a1234-9c2e0011-0001419',
    seq: 1419,
    sent_at: new Date(Date.now() - 35000).toISOString(),
    sha256: 'b4d9f1200e82ab21d4a610783c0b0e5681a30ae48012736d08ca0736081736b2',
    receipt_sha256: 'b4d9f1200e82ab21d4a610783c0b0e5681a30ae48012736d08ca0736081736b2',
    match: true,
    raw_payload: {
      metrics: [
        { name: 'cpu_pct', avg: 13.8, max: 16.5, source: 'host-7f3a1234' },
        { name: 'mem_pct', avg: 41.9, max: 44.0, source: 'host-7f3a1234' },
      ],
      events: [],
      tripwire_canaries_planted: 419,
      cleartext_secrets_found: 0,
    },
  },
];

const MOCK_REVEAL: RevealRequestItem[] = [
  {
    request_id: 'rev-01',
    pseudonym: 'user-7f3a91bc',
    reason: 'Investigate root cause of cryptomining sudo process execution',
    requested_by: 'Cloud Platform Engineer',
    status: 'pending',
    requested_at: new Date(Date.now() - 120000).toISOString(),
  },
];

export const ShopApp: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'logs' | 'ai'>('logs');
  const [status, setStatus] = useState<LocalGuardStatus | null>(MOCK_STATUS);
  const [guardDown, setGuardDown] = useState(false);
  const [logs, setLogs] = useState<LocalLogEntry[]>(MOCK_LOGS);
  const [egressList, setEgressList] = useState<EgressPayloadEntry[]>(MOCK_EGRESS);
  const [revealRequests, setRevealRequests] = useState<RevealRequestItem[]>(MOCK_REVEAL);
  const [countdown, setCountdown] = useState(84200);
  const [selectedEgress, setSelectedEgress] = useState<EgressPayloadEntry | null>(MOCK_EGRESS[0]);
  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [spotlightId, setSpotlightId] = useState<string | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      const [st, lg, eg, rev] = await Promise.all([
        shopApi.getStatus(),
        shopApi.getRawLogs(),
        shopApi.getEgressLedger(),
        shopApi.getRevealRequests(),
      ]);

      if (st) {
        setStatus(st);
        setGuardDown(false);
      } else {
        setGuardDown(true);
      }

      if (lg && lg.length > 0) setLogs(lg);
      if (eg && eg.length > 0) {
        setEgressList(eg);
        setSelectedEgress((cur) => (cur ? eg.find((e) => e.seq === cur.seq) || cur : eg[0]));
      }
      if (rev && rev.length > 0) setRevealRequests(rev);
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
      {/* Sleek Top Navigation Bar */}
      <header className="h-14 bg-[#0A0D15] border-b border-white/[0.08] px-5 flex items-center justify-between z-30">
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-3">
            <span className="text-sm font-black tracking-widest text-white">
              AIRLOCK
            </span>
            <span className="text-[11px] text-lime-400 uppercase tracking-widest font-bold hidden sm:inline px-2 py-0.5 rounded bg-lime-500/10 border border-lime-500/20">
              LOCAL GUARD
            </span>
            <span className="w-2 h-2 rounded-full bg-lime-400 animate-pulse shadow-[0_0_8px_#A3E635]" />
          </div>

          {/* Navigation Tabs */}
          <nav className="flex space-x-1">
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
              className={`px-3 py-1.5 rounded text-xs font-bold tracking-wider transition-colors flex items-center space-x-1.5 ${
                activeTab === 'ai'
                  ? 'bg-lime-500/15 text-lime-300 border border-lime-500/30 shadow-[0_0_15px_rgba(163,230,53,0.15)]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
              }`}
            >
              <span>🤖</span>
              <span>LOCAL AI COPILOT</span>
              <span className="w-1.5 h-1.5 rounded-full bg-lime-400"></span>
            </button>
          </nav>
        </div>

        {/* Security & Boundary Badges */}
        <div className="flex items-center space-x-3 text-xs">
          <span className="hidden md:inline px-2.5 py-1 rounded bg-black/40 text-slate-300 border border-white/5 text-[10px]">
            NODE: <strong className="text-white">SYSTEM 1 (EDGE)</strong>
          </span>
          <span className="px-2.5 py-1 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-bold text-[10px]">
            ✓ ZERO CLOUD EXPORT OF SECRETS
          </span>
          {guardDown && (
            <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px]">
              DEMO STANDBY
            </span>
          )}
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
                  {status?.status?.toUpperCase() || 'ACTIVE'}
                </span>
                <span className="text-[10px] text-slate-500 block">CPU: {status?.guard_cpu_pct?.toFixed(1) || '14.2'}% · {status?.guard_mem_mb || 46} MB</span>
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
                  {status?.secrets_redacted ?? 3} <span className="text-xs text-slate-400">TRIPPED & MASKED</span>
                </span>
                <span className="text-[10px] text-slate-500 block">Canaries planted: {status?.canaries_planted ?? 420}</span>
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
                            {log.has_secret ? `⚠️ ${log.secret_type || 'TRIPWIRE SECRET'}` : log.level}
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
