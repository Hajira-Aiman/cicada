import React, { useEffect, useState } from 'react';
import { useLiveStore } from '../stores/liveStore';
import { useUiStore } from '../stores/uiStore';
import { StatusBadge } from '../components/StatusBadge';

export const Fallback2D: React.FC<{ height?: number | string }> = ({ height = '100%' }) => {
  const guards = useLiveStore((s) => s.guards);
  const receipts = useLiveStore((s) => s.receipts);
  const setSelectedGuardId = useUiStore((s) => s.setSelectedGuardId);
  const setInspectorOpen = useUiStore((s) => s.setInspectorOpen);

  const [particles, setParticles] = useState<{ id: string; from: number; progress: number; status: string }[]>([]);

  useEffect(() => {
    if (receipts.length > 0) {
      const latest = receipts[0];
      const fromIdx = latest.guard_id.includes('acme') ? 0 : latest.guard_id.includes('globex') ? 1 : 2;
      const newParticle = {
        id: `p-${Date.now()}`,
        from: fromIdx,
        progress: 0,
        status: latest.status,
      };
      setParticles((prev) => [...prev.slice(-15), newParticle]);
    }
  }, [receipts]);

  useEffect(() => {
    const interval = setInterval(() => {
      setParticles((prev) =>
        prev
          .map((p) => ({ ...p, progress: p.progress + 0.05 }))
          .filter((p) => p.progress <= 1.0)
      );
    }, 50);
    return () => clearInterval(interval);
  }, []);

  const guardList = Object.values(guards);

  const handleNodeClick = (gId: string) => {
    setSelectedGuardId(gId);
    setInspectorOpen(true);
  };

  return (
    <div className="relative w-full overflow-hidden bg-[#080A10] border border-white/5 rounded-xl p-4" style={{ height }}>
      {/* Title */}
      <div className="absolute top-4 left-4 z-10 flex items-center space-x-3">
        <span className="text-xs font-mono font-bold tracking-widest text-slate-300">
          LIVE FLEET BRIDGE · 2D TELEMETRY STREAM
        </span>
        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
          TRUST GATEWAY ACTIVE
        </span>
      </div>

      <svg className="w-full h-full" viewBox="0 0 1000 500" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="gateGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#A855F7" stopOpacity="0.4" />
            <stop offset="50%" stopColor="#A855F7" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#A855F7" stopOpacity="0.4" />
          </linearGradient>
        </defs>

        {/* Trust Boundary Gate */}
        <line x1="500" y1="40" x2="500" y2="460" stroke="url(#gateGrad)" strokeWidth="3" strokeDasharray="6 4" />
        <text x="508" y="60" fill="#A855F7" fontSize="11" fontFamily="JetBrains Mono" fontWeight="bold">
          TRUST BOUNDARY (PLANE X = -1)
        </text>
        <text x="508" y="75" fill="#94A3B8" fontSize="9" fontFamily="JetBrains Mono">
          RAW DATA NEVER CROSSES
        </text>

        {/* Guard Laptops on Left */}
        {guardList.map((g, idx) => {
          const yPos = 120 + idx * 130;
          return (
            <g key={g.guard_id} className="cursor-pointer" onClick={() => handleNodeClick(g.guard_id)}>
              {/* Stream Path to Gate */}
              <path
                d={`M 220 ${yPos} C 360 ${yPos}, 440 250, 500 250`}
                fill="none"
                stroke="#1E293B"
                strokeWidth="2"
              />
              {/* Local Data Orb (lime, stays on left) */}
              <circle cx="90" cy={yPos - 25} r="7" fill="#A3E635" opacity="0.8">
                <animateTransform
                  attributeName="transform"
                  type="rotate"
                  from={`0 130 ${yPos}`}
                  to={`360 130 ${yPos}`}
                  dur="4s"
                  repeatCount="indefinite"
                />
              </circle>
              {/* Node Box */}
              <rect
                x="80"
                y={yPos - 35}
                width="140"
                height="70"
                rx="8"
                fill="#0C1017"
                stroke={g.state === 'Poor' ? '#EF4444' : '#3A3F4C'}
                strokeWidth="1.5"
              />
              <text x="92" y={yPos - 15} fill="#FFFFFF" fontSize="12" fontFamily="JetBrains Mono" fontWeight="bold">
                {g.tenant_id.toUpperCase()}
              </text>
              <text x="92" y={yPos + 2} fill="#94A3B8" fontSize="10" fontFamily="JetBrains Mono">
                {g.guard_id}
              </text>
              <text
                x="92"
                y={yPos + 22}
                fill={g.state === 'Excellent' ? '#10B981' : g.state === 'Good' ? '#06B6D4' : '#F59E0B'}
                fontSize="10"
                fontFamily="JetBrains Mono"
                fontWeight="bold"
              >
                ● {g.state?.toUpperCase()}
              </text>
            </g>
          );
        })}

        {/* Head Office (LOQ) on Right */}
        <g className="cursor-pointer" onClick={() => handleNodeClick('head-office')}>
          {/* Paths from Gate to HQ */}
          <path d="M 500 250 C 620 250, 720 250, 800 250" fill="none" stroke="#1E293B" strokeWidth="3" />
          <rect x="800" y="200" width="160" height="100" rx="10" fill="#0C1017" stroke="#38BDF8" strokeWidth="2" />
          <text x="815" y="235" fill="#FFFFFF" fontSize="14" fontFamily="JetBrains Mono" fontWeight="bold">
            HEAD OFFICE (LOQ)
          </text>
          <text x="815" y="255" fill="#38BDF8" fontSize="11" fontFamily="JetBrains Mono">
            SaaS Aggregator & AI
          </text>
          <text x="815" y="278" fill="#10B981" fontSize="10" fontFamily="JetBrains Mono" fontWeight="bold">
            VERIFIED RECEIPTS: 100%
          </text>
        </g>

        {/* Moving Particles */}
        {particles.map((p) => {
          const startY = 120 + p.from * 130;
          let cx = 0;
          let cy = 0;

          if (p.progress <= 0.5) {
            // Guard to Gate
            const norm = p.progress / 0.5;
            cx = 220 + norm * 280;
            cy = startY + norm * (250 - startY);
          } else {
            // Gate to HQ
            const norm = (p.progress - 0.5) / 0.5;
            cx = 500 + norm * 300;
            cy = 250;
          }

          const color = p.status === 'stored' ? '#A855F7' : p.status === 'duplicate' ? '#64748B' : '#EF4444';

          return (
            <circle
              key={p.id}
              cx={cx}
              cy={cy}
              r={p.progress > 0.48 && p.progress < 0.52 ? '7' : '5'}
              fill={color}
              filter="drop-shadow(0 0 4px #A855F7)"
            />
          );
        })}
      </svg>
    </div>
  );
};
