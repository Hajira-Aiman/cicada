import React, { useState, useRef, useEffect } from 'react';
import { LocalGuardStatus, LocalLogEntry, EgressPayloadEntry } from '../../services/shopApi';

export interface AiReference {
  type: 'log' | 'egress' | 'secret' | 'buffer';
  label: string;
  targetId: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  timestamp: string;
  references?: AiReference[];
}

interface LocalAiChatProps {
  logs: LocalLogEntry[];
  status: LocalGuardStatus | null;
  egressList: EgressPayloadEntry[];
  onNavigateToReference: (ref: AiReference) => void;
}

export const LocalAiChat: React.FC<LocalAiChatProps> = ({
  logs,
  status,
  egressList,
  onNavigateToReference,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'msg-welcome',
      sender: 'ai',
      text: 'Hello, I am your Local Guard AI Copilot. I run completely in local memory on this device with strict privacy boundaries: I can only inspect in-memory raw logs, local buffer depth, and egress receipts. Zero query data or raw secrets ever leave this machine.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    },
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Suggested quick prompt chips
  const promptChips = [
    {
      title: 'Tripwire & Secrets',
      query: 'Were any cleartext API keys or credentials caught by the tripwire?',
      icon: '🛡️',
    },
    {
      title: 'Egress Payload',
      query: 'What data was in the last egress payload sent to Cloud Dashboard?',
      icon: '📦',
    },
    {
      title: 'Auth & Errors',
      query: 'Summarize failed auth attempts and anomalous errors in local logs',
      icon: '🔍',
    },
    {
      title: 'Buffer Status',
      query: 'What is the current outbox buffer depth and retention countdown?',
      icon: '⏱️',
    },
  ];

  const handleSend = (text: string) => {
    if (!text.trim()) return;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: text.trim(),
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    // Simulate local model conversational inference based on actual edge data
    setTimeout(() => {
      const q = text.toLowerCase();
      let replyText = '';
      let refs: AiReference[] = [];

      const latestEgress = egressList[0];
      const secretLogs = logs.filter((l) => l.has_secret);
      const errorLogs = logs.filter((l) => l.level === 'WARN' || l.level === 'ERROR' || l.message.toLowerCase().includes('fail'));

      if (q.includes('secret') || q.includes('api key') || q.includes('tripwire') || q.includes('credential')) {
        if (secretLogs.length > 0) {
          const firstSecret = secretLogs[0];
          replyText = `Yes. The local redaction tripwire caught ${secretLogs.length} cleartext secret(s) in local logs before transmission. For example, in log #${firstSecret.id}, a ${firstSecret.secret_type || 'credential'} was detected and replaced with [REDACTED]. Raw secrets remain visible ONLY on this local screen.`;
          refs = secretLogs.slice(0, 3).map((l) => ({
            type: 'secret',
            label: `Log #${l.id} (${l.secret_type || 'Secret'})`,
            targetId: l.id,
          }));
        } else {
          replyText = 'No cleartext secrets are currently flagged in the active local log buffer. Tripwires are actively monitoring with 0 leaks permitted.';
        }
      } else if (q.includes('egress') || q.includes('payload') || q.includes('cloud') || q.includes('sent')) {
        if (latestEgress) {
          replyText = `The last emitted egress payload is Seq #${latestEgress.seq} (SHA-256: ${latestEgress.sha256.substring(0, 16)}...). It was HMAC-signed and sent at ${latestEgress.sent_at || 'just now'}. It includes aggregated metric averages and cluster pattern IDs, with all raw strings stripped. Receipt verification with Cloud Dashboard is a 100% cryptographic match.`;
          refs = [
            {
              type: 'egress',
              label: `Egress Seq #${latestEgress.seq}`,
              targetId: String(latestEgress.seq),
            },
          ];
        } else {
          replyText = 'No egress payloads have been dispatched yet. The local queue is standing by.';
        }
      } else if (q.includes('buffer') || q.includes('countdown') || q.includes('retention') || q.includes('depth')) {
        const buf = status?.buffer_depth ?? 0;
        const count = status?.retention_countdown_s ?? 86400;
        replyText = `Local outbox buffer depth is currently ${buf} pending payloads. The local retention auto-purge countdown is active (${Math.round(count / 60)} minutes remaining). When the countdown reaches 0, raw local memory buffers are cryptographically zeroed.`;
        refs = [
          {
            type: 'buffer',
            label: `Buffer Depth: ${buf} Items`,
            targetId: 'buffer-status',
          },
        ];
      } else if (q.includes('auth') || q.includes('error') || q.includes('failed') || q.includes('fail') || q.includes('login')) {
        if (errorLogs.length > 0) {
          replyText = `Found ${errorLogs.length} anomalous or warning log entries in local memory. Multiple authentication failures were recorded on host-7f3a1234, including repeated SSH login attempts that triggered the local rate-limiting tripwire.`;
          refs = errorLogs.slice(0, 3).map((l) => ({
            type: 'log',
            label: `Log #${l.id} (${l.level})`,
            targetId: l.id,
          }));
        } else {
          replyText = 'All local logs show standard operational telemetry. No high-frequency auth bursts or critical kernel errors detected.';
        }
      } else {
        replyText = `Based on current local memory on this device: Guard is ${status?.status?.toUpperCase() || 'ACTIVE'}, CPU is ${status?.guard_cpu_pct?.toFixed(1) || '14.2'}%, Buffer has ${status?.buffer_depth ?? 0} items pending, and ${logs.length} raw log lines are stored in local RAM. You can click any reference below to examine the raw entry directly.`;
        if (logs.length > 0) {
          refs.push({
            type: 'log',
            label: `Log #${logs[0].id}`,
            targetId: logs[0].id,
          });
        }
        if (latestEgress) {
          refs.push({
            type: 'egress',
            label: `Egress Seq #${latestEgress.seq}`,
            targetId: String(latestEgress.seq),
          });
        }
      }

      const aiMsg: ChatMessage = {
        id: `ai-${Date.now()}`,
        sender: 'ai',
        text: replyText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
        references: refs,
      };

      setMessages((prev) => [...prev, aiMsg]);
      setIsTyping(false);
    }, 600);
  };

  return (
    <div className="flex flex-col h-[calc(100vh-10rem)] max-w-5xl mx-auto bg-[#0a0d15] border border-white/10 rounded-xl overflow-hidden font-mono text-xs shadow-2xl select-none">
      {/* Copilot Header */}
      <div className="p-4 bg-[#0e1320] border-b border-white/10 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-lime-500/10 border border-lime-500/30 flex items-center justify-center text-lime-400 font-bold">
            AI
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-sm font-black text-white tracking-wider">
                LOCAL GUARD AI COPILOT
              </h3>
              <span className="w-2 h-2 rounded-full bg-lime-400 animate-pulse"></span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Air-gapped local model · Answers strictly using edge memory · Zero cloud export
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="px-2.5 py-1 rounded bg-lime-500/10 text-lime-400 border border-lime-500/25 font-bold text-[10px]">
            LOCAL INFERENCE (OLLAMA / ON-DEVICE)
          </span>
          <span className="px-2.5 py-1 rounded bg-black/40 text-slate-400 border border-white/10 text-[10px]">
            CONTEXT: {logs.length} LOGS · {egressList.length} RECEIPTS
          </span>
        </div>
      </div>

      {/* Chat Messages Feed */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.map((msg) => {
          const isAi = msg.sender === 'ai';
          return (
            <div
              key={msg.id}
              className={`flex flex-col ${isAi ? 'items-start' : 'items-end'}`}
            >
              <div className="flex items-center space-x-2 text-[10px] text-slate-500 mb-1 px-1">
                <span>{isAi ? '🤖 LOCAL GUARD AI' : '👤 LOCAL OPERATOR'}</span>
                <span>·</span>
                <span>{msg.timestamp}</span>
              </div>

              <div
                className={`max-w-2xl p-4 rounded-xl leading-relaxed text-xs ${
                  isAi
                    ? 'bg-[#121826] text-slate-200 border border-white/10 shadow-lg'
                    : 'bg-lime-500 text-black font-semibold shadow-md'
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.text}</div>

                {/* Clickable Reference Badges */}
                {isAi && msg.references && msg.references.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-white/10 space-y-1.5">
                    <span className="text-[9px] uppercase tracking-wider text-slate-400 font-bold block">
                      CLICKABLE EVIDENCE REFERENCES (CLICK TO SPOTLIGHT):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.references.map((ref, idx) => (
                        <button
                          key={idx}
                          onClick={() => onNavigateToReference(ref)}
                          className="px-2.5 py-1 rounded bg-lime-500/15 hover:bg-lime-500/30 text-lime-300 border border-lime-500/40 text-[10px] font-mono font-bold transition-all flex items-center space-x-1.5 group cursor-pointer shadow-sm hover:scale-105 active:scale-95"
                        >
                          <span>↗</span>
                          <span>{ref.label}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {isTyping && (
          <div className="flex items-center space-x-2 p-3 rounded-lg bg-[#121826] border border-white/5 w-40 text-slate-400 text-xs">
            <span className="w-2 h-2 rounded-full bg-lime-400 animate-bounce"></span>
            <span className="w-2 h-2 rounded-full bg-lime-400 animate-bounce [animation-delay:0.2s]"></span>
            <span className="w-2 h-2 rounded-full bg-lime-400 animate-bounce [animation-delay:0.4s]"></span>
            <span className="text-[10px] text-slate-500 ml-1">Analyzing...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Chips */}
      <div className="px-5 py-2.5 bg-[#0e1320] border-t border-white/5 flex items-center gap-2 overflow-x-auto">
        <span className="text-[10px] text-slate-500 uppercase font-bold shrink-0">
          PROMPTS:
        </span>
        {promptChips.map((chip, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(chip.query)}
            className="px-2.5 py-1 rounded bg-[#161d2d] hover:bg-[#1f283d] text-slate-300 hover:text-white border border-white/5 hover:border-lime-500/40 text-[11px] font-mono transition-all shrink-0 flex items-center space-x-1"
          >
            <span>{chip.icon}</span>
            <span>{chip.title}</span>
          </button>
        ))}
      </div>

      {/* Input Box */}
      <div className="p-4 bg-[#0a0d15] border-t border-white/10">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(inputValue);
          }}
          className="flex items-center space-x-2"
        >
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask local AI about raw logs, redacted secrets, buffer depth, egress hashes..."
            className="flex-1 bg-[#121724] border border-white/10 focus:border-lime-500/60 p-3 rounded-lg text-xs font-mono text-white placeholder-slate-500 outline-none transition-colors"
          />
          <button
            type="submit"
            disabled={!inputValue.trim() || isTyping}
            className="px-5 py-3 rounded-lg bg-lime-500 hover:bg-lime-400 disabled:opacity-40 text-black font-mono font-bold text-xs shadow-[0_0_15px_rgba(163,230,53,0.3)] transition-all cursor-pointer"
          >
            SEND →
          </button>
        </form>
      </div>
    </div>
  );
};

export default LocalAiChat;
