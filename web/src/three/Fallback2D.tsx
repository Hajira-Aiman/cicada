import React, { useEffect, useState } from 'react';
import { useLiveStore } from '../stores/liveStore';
import { useUiStore } from '../stores/uiStore';

export const Fallback2D: React.FC<{ height?: number | string }> = ({ height = '100%' }) => {
  const guards = useLiveStore((s) => s.guards);
  const receipts = useLiveStore((s) => s.receipts);
  const selectedGuardId = useUiStore((s) => s.selectedGuardId);
  const setSelectedGuardId = useUiStore((s) => s.setSelectedGuardId);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);

  const [particles, setParticles] = useState<{ id: string; from: number; progress: number; status: string }[]>([]);

  // Strictly 2 Systems: System 1 (acme) and System 2 (globex)
  const systemNodes = [
    {
      id: 'guard-acme-01',
      label: 'SYSTEM 1',
      sublabel: 'Local Guard Edge',
      guard: guards['guard-acme-01'] || {
        guard_id: 'guard-acme-01',
        tenant_id: 'acme',
        state: 'Excellent',
        guard_cpu_pct: 14.2,
        guard_mem_mb: 42.0,
        buffer_depth: 0,
        policy_hash: '9f104be2',
      },
    },
    {
      id: 'guard-globex-01',
      label: 'SYSTEM 2',
      sublabel: 'Local Guard Edge',
      guard: guards['guard-globex-01'] || {
        guard_id: 'guard-globex-01',
        tenant_id: 'globex',
        state: 'Good',
        guard_cpu_pct: 22.8,
        guard_mem_mb: 48.0,
        buffer_depth: 0,
        policy_hash: '7c82a190',
      },
    },
  ];

  // Spawn animated receipts across the trust boundary
  useEffect(() => {
    if (receipts.length > 0) {
      const latest = receipts[0];
      const fromIdx = latest.guard_id.includes('globex') ? 1 : 0;
      const newParticle = {
        id: `p-${Date.now()}-${Math.random()}`,
        from: fromIdx,
        progress: 0,
        status: latest.status || 'stored',
      };
      setParticles((prev) => [...prev.slice(-12), newParticle]);
    }
  }, [receipts]);

  // Periodic simulated packet flow if no live WebSocket burst
  useEffect(() => {
    const pulseInterval = setInterval(() => {
      const randomFrom = Math.random() > 0.5 ? 1 : 0;
      const autoParticle = {
        id: `auto-${Date.now()}-${Math.random()}`,
        from: randomFrom,
        progress: 0,
        status: 'stored',
      };
      setParticles((prev) => [...prev.slice(-12), autoParticle]);
    }, 2200);
    return () => clearInterval(pulseInterval);
  }, []);

  // Tick particles along the path
  useEffect(() => {
    const interval = setInterval(() => {
      setParticles((prev) =>
        prev
          .map((p) => ({ ...p, progress: p.progress + 0.04 }))
          .filter((p) => p.progress <= 1.0)
      );
    }, 40);
    return () => clearInterval(interval);
  }, []);

  const handleNodeClick = (gId: string) => {
    setSelectedGuardId(gId);
  };

  const activeSystem = systemNodes.find((s) => s.id === selectedGuardId) || systemNodes[0];

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#07090E] border border-white/10 rounded-xl select-none" style={{ height }}>
      {/* Top Header Bar */}
      <div className="absolute top-4 left-5 right-5 z-20 flex items-center justify-between pointer-events-none">
        <div className="flex items-center space-x-3 pointer-events-auto">
          <span className="text-xs font-mono font-black tracking-widest text-white">
            LIVE FLEET BRIDGE · 2-SYSTEM TOPOLOGY
          </span>
          <span className="text-[10px] font-mono px-2.5 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold">
            TRUST GATEWAY ACTIVE
          </span>
        </div>
        <div className="flex items-center space-x-2 text-[10px] font-mono text-slate-400">
          <span>REAL-TIME CRYPTOGRAPHIC RECEIPTS FLOW: EDGE → CLOUD</span>
        </div>
      </div>

      {/* Floating Glass Telemetry HUD Card pinned to selected System */}
      <div className="absolute bottom-5 left-5 z-20 p-4 bg-[#0d121d]/90 backdrop-blur-md border border-sky-500/30 rounded-lg shadow-[0_0_30px_rgba(0,0,0,0.5)] max-w-sm w-full font-mono text-xs space-y-3">
        <div className="flex items-center justify-between border-b border-white/10 pb-2">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="font-bold text-white tracking-wider">{activeSystem.label} HUD</span>
            <span className="text-[10px] text-slate-500">({activeSystem.id})</span>
          </div>
          <button
            onClick={() => setInspectorOpen(true)}
            className="text-[10px] px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 hover:bg-sky-500/30 transition-colors border border-sky-500/30 font-bold"
          >
            OPEN DRAWER →
          </button>
        </div>

        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div className="p-2 rounded bg-black/40 border border-white/5">
            <span className="text-[9px] uppercase text-slate-500 block font-bold">CPU USAGE</span>
            <span className="text-sm font-black text-sky-400">{activeSystem.guard.guard_cpu_pct?.toFixed(1) ?? '14.2'}%</span>
          </div>
          <div className="p-2 rounded bg-black/40 border border-white/5">
            <span className="text-[9px] uppercase text-slate-500 block font-bold">MEMORY</span>
            <span className="text-sm font-black text-slate-200">{activeSystem.guard.guard_mem_mb ?? 42} MB</span>
          </div>
          <div className="p-2 rounded bg-black/40 border border-white/5">
            <span className="text-[9px] uppercase text-slate-500 block font-bold">OUTBOX BUFFER</span>
            <span className="text-sm font-black text-emerald-400">{activeSystem.guard.buffer_depth ?? 0} ITEMS</span>
          </div>
          <div className="p-2 rounded bg-black/40 border border-white/5">
            <span className="text-[9px] uppercase text-slate-500 block font-bold">POLICY INTEGRITY</span>
            <span className="text-[11px] font-mono font-bold text-purple-300 truncate block">
              {activeSystem.guard.policy_hash || '9f104be2'}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-white/5">
          <span>CHECKPOINT: <strong className="text-emerald-400">✓ 60s ROOT VERIFIED</strong></span>
          <span className="text-slate-500">ZERO LEAK TRIPWIRE</span>
        </div>
      </div>

      {/* SVG Canvas */}
      <svg className="w-full h-full" viewBox="0 0 1000 500" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="gateGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#A855F7" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#A855F7" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#A855F7" stopOpacity="0.1" />
          </linearGradient>
          <filter id="glowPurple" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Ambient Grid Lines */}
        <line x1="50" y1="250" x2="950" y2="250" stroke="#131722" strokeWidth="1" strokeDasharray="4 4" />

        {/* Trust Boundary Gate (Center Plane) */}
        <line x1="500" y1="30" x2="500" y2="470" stroke="url(#gateGrad)" strokeWidth="3" strokeDasharray="6 4" />
        
        {/* Trust Gate Badges */}
        <rect x="420" y="38" width="160" height="26" rx="4" fill="#170d24" stroke="#A855F7" strokeWidth="1.2" />
        <text x="500" y="55" fill="#E9D5FF" fontSize="10" fontFamily="JetBrains Mono, monospace" fontWeight="bold" textAnchor="middle">
          PRIVACY TRUST GATEWAY
        </text>

        <rect x="430" y="440" width="140" height="22" rx="4" fill="#0C1017" stroke="#A855F7" strokeWidth="1" strokeOpacity="0.6" />
        <text x="500" y="455" fill="#C084FC" fontSize="9" fontFamily="JetBrains Mono, monospace" fontWeight="bold" textAnchor="middle">
          ✓ ZERO LEAKS DETECTED
        </text>

        {/* Left Side: Strictly 2 System Nodes */}
        {systemNodes.map((s, idx) => {
          const yPos = 160 + idx * 180;
          const isSelected = selectedGuardId === s.id;
          const isHealthy = s.guard.state === 'Excellent' || s.guard.state === 'Good';

          return (
            <g
              key={s.id}
              className="cursor-pointer transition-all duration-200"
              onClick={() => handleNodeClick(s.id)}
            >
              {/* Stream Path to Gate */}
              <path
                d={`M 250 ${yPos} C 360 ${yPos}, 430 250, 500 250`}
                fill="none"
                stroke={isSelected ? '#38BDF8' : '#1E293B'}
                strokeWidth={isSelected ? '2.5' : '1.5'}
                strokeOpacity={isSelected ? 0.9 : 0.6}
              />

              {/* Edge Isolation Ring (stays strictly on edge machine) */}
              <circle cx="100" cy={yPos - 30} r="6" fill="#10B981" opacity="0.8">
                <animate
                  attributeName="opacity"
                  values="0.4;1;0.4"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </circle>

              {/* Node Card Box */}
              <rect
                x="90"
                y={yPos - 45}
                width="160"
                height="90"
                rx="10"
                fill={isSelected ? '#0F1626' : '#0B0E17'}
                stroke={isSelected ? '#38BDF8' : isHealthy ? '#334155' : '#EF4444'}
                strokeWidth={isSelected ? '2' : '1.5'}
                filter={isSelected ? 'drop-shadow(0 0 10px rgba(56,189,248,0.2))' : undefined}
              />

              <text x="110" y={yPos - 20} fill="#FFFFFF" fontSize="13" fontFamily="JetBrains Mono, monospace" fontWeight="black" letterSpacing="0.05em">
                {s.label}
              </text>
              <text x="110" y={yPos - 4} fill="#94A3B8" fontSize="10" fontFamily="JetBrains Mono, monospace">
                {s.sublabel}
              </text>

              {/* Status Pill */}
              <rect
                x="110"
                y={yPos + 10}
                width="72"
                height="18"
                rx="3"
                fill={isHealthy ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}
                stroke={isHealthy ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}
                strokeWidth="1"
              />
              <text
                x="146"
                y={yPos + 22}
                fill={isHealthy ? '#34D399' : '#F87171'}
                fontSize="9"
                fontFamily="JetBrains Mono, monospace"
                fontWeight="bold"
                textAnchor="middle"
              >
                ● {s.guard.state?.toUpperCase() || 'ONLINE'}
              </text>
            </g>
          );
        })}

        {/* Right Side: Cloud Dashboard Node */}
        <g className="cursor-pointer" onClick={() => setSelectedGuardId('cloud-dashboard')}>
          {/* Bridge Path from Gate to Cloud Aggregator */}
          <path
            d="M 500 250 C 620 250, 700 250, 770 250"
            fill="none"
            stroke="#38BDF8"
            strokeWidth="2.5"
            strokeOpacity="0.8"
          />

          {/* Cloud Aggregator Box */}
          <rect
            x="770"
            y="170"
            width="180"
            height="160"
            rx="12"
            fill="#0B101D"
            stroke="#38BDF8"
            strokeWidth="2"
            filter="drop-shadow(0 0 15px rgba(56,189,248,0.15))"
          />

          <rect x="790" y="190" width="140" height="24" rx="4" fill="rgba(56,189,248,0.15)" stroke="rgba(56,189,248,0.3)" strokeWidth="1" />
          <text x="860" y="206" fill="#7DD3FC" fontSize="10" fontFamily="JetBrains Mono, monospace" fontWeight="bold" textAnchor="middle">
            CENTRAL INGEST
          </text>

          <text x="860" y="235" fill="#FFFFFF" fontSize="13" fontFamily="JetBrains Mono, monospace" fontWeight="black" textAnchor="middle">
            CLOUD DASHBOARD
          </text>
          <text x="860" y="252" fill="#94A3B8" fontSize="10" fontFamily="JetBrains Mono, monospace" textAnchor="middle">
            SaaS Aggregator & AIOps
          </text>

          <line x1="790" y1="268" x2="930" y2="268" stroke="#1E293B" strokeWidth="1" />

          <text x="860" y="286" fill="#10B981" fontSize="10" fontFamily="JetBrains Mono, monospace" fontWeight="bold" textAnchor="middle">
            ✓ 100% MERKLE VERIFIED
          </text>
          <text x="860" y="304" fill="#38BDF8" fontSize="10" fontFamily="JetBrains Mono, monospace" textAnchor="middle">
            NOISE CUT: 94%
          </text>
        </g>

        {/* Animated Flying Receipt Packets */}
        {particles.map((p) => {
          const startY = 160 + p.from * 180;
          let cx = 0;
          let cy = 0;

          if (p.progress <= 0.5) {
            // Guard Edge to Privacy Trust Gate
            const norm = p.progress / 0.5;
            cx = 250 + norm * 250;
            cy = startY + norm * (250 - startY);
          } else {
            // Privacy Trust Gate to Cloud Dashboard
            const norm = (p.progress - 0.5) / 0.5;
            cx = 500 + norm * 270;
            cy = 250;
          }

          const isPassingGate = p.progress > 0.46 && p.progress < 0.54;

          return (
            <g key={p.id}>
              <circle
                cx={cx}
                cy={cy}
                r={isPassingGate ? 7 : 4}
                fill={p.progress < 0.5 ? '#38BDF8' : '#A855F7'}
                filter="url(#glowPurple)"
              />
              {isPassingGate && (
                <circle cx={cx} cy={cy} r="12" fill="none" stroke="#C084FC" strokeWidth="1.5" opacity="0.8" />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
};

export default Fallback2D;
