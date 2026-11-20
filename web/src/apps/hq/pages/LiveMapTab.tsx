import React, { useState } from 'react';
import { Fallback2D } from '@/three/Fallback2D';
import { useLiveStore } from '@/stores/liveStore';
import type { Machine } from '@/three/LaptopModel';

const LaptopViewer = React.lazy(() => import('@/three/LaptopModel').then(m => ({ default: m.LaptopViewer })));

const COLOR: Record<string, string> = { acme: '#3b82f6', globex: '#10b981' };
const RISK = { Excellent: 0.1, Good: 0.2, Fair: 0.55, Poor: 0.95, Offline: 0.2 } as const;

export const LiveMapTab: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const [viewMode, setViewMode] = useState<'2D' | '3D'>('2D');

  const machines: Machine[] = Object.values(guards)
    .map((g) => ({
      id: g.guard_id,
      risk: RISK[g.state] ?? 0.2,
      baseColor: COLOR[g.tenant_id] || '#38bdf8',
      connected: Date.now() - new Date(g.last_seen).getTime() < 30000 && g.state !== 'Offline',
    }));

  return (
    <div className="h-[calc(100vh-3.5rem)] w-full p-4 flex flex-col space-y-3 font-mono text-xs">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-black text-white tracking-widest flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
            LIVE FLEET BRIDGE · CRYPTOGRAPHIC RESIDENCY TOPOLOGY
          </h2>
          <p className="text-slate-400 text-[11px] mt-0.5">
            System 1 & System 2 Edge Guards · Translucent Privacy Gate · Zero raw telemetry leaves edge
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {/* View Toggle */}
          <div className="flex items-center bg-[#141721] p-0.5 rounded border border-white/10">
            <button
              onClick={() => setViewMode('2D')}
              className={`px-2.5 py-1 rounded text-[10px] font-bold transition-colors ${
                viewMode === '2D' ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              2D VECTOR (FAST)
            </button>
            <button
              onClick={() => setViewMode('3D')}
              className={`px-2.5 py-1 rounded text-[10px] font-bold transition-colors ${
                viewMode === '3D' ? 'bg-purple-500 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              3D WEBGL
            </button>
          </div>

          <span className="px-2.5 py-1 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-bold text-[11px]">
            GATE: ACTIVE
          </span>
          <span className="px-2.5 py-1 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 font-bold text-[11px]">
            SYNCHRONIZED
          </span>
        </div>
      </div>

      <div className="flex-1 w-full rounded-xl overflow-hidden border border-white/10 relative">
        {viewMode === '2D' ? (
          <Fallback2D height="100%" />
        ) : (
          <React.Suspense fallback={<Fallback2D height="100%" />}>
            <LaptopViewer machines={machines} />
          </React.Suspense>
        )}
      </div>
    </div>
  );
};

export default LiveMapTab;
