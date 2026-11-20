import React from 'react';
import { Fallback2D } from '@/three/Fallback2D';
import { useLiveStore } from '@/stores/liveStore';
import type { Machine } from '@/three/LaptopModel';
const LaptopViewer = React.lazy(() => import('@/three/LaptopModel').then(m => ({ default: m.LaptopViewer })));

const COLOR: Record<string, string> = { acme: '#3b82f6', globex: '#10b981', contoso: '#a855f7' };
const RISK = { Excellent: 0.1, Good: 0.2, Fair: 0.55, Poor: 0.95, Offline: 0.2 } as const;

export const LiveMapTab: React.FC = () => {
  const guards = useLiveStore((s) => s.guards);
  const machines: Machine[] = Object.values(guards).map((g) => ({
    id: g.guard_id, risk: RISK[g.state] ?? 0.2, baseColor: COLOR[g.tenant_id] || '#06b6d4',
    connected: Date.now() - new Date(g.last_seen).getTime() < 30000 && g.state !== 'Offline',
  }));
  return (
    <div className="h-[calc(100vh-3.5rem)] w-full p-4 flex flex-col space-y-3">
      <div className="flex items-center justify-between font-mono text-xs">
        <div>
          <h2 className="text-base font-bold text-white tracking-widest">
            3D LIVE FLEET BRIDGE (HERO VIEW)
          </h2>
          <p className="text-slate-400 text-[11px] mt-0.5">
            4 Real Machines · Translucent Trust Gate at x = -1 · Real-time cryptographic receipts flow right → left
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 font-bold text-[11px]">
            CAMERA: OVERVIEW
          </span>
          <span className="px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 font-bold text-[11px]">
            60 FPS SYNCHRONIZED
          </span>
        </div>
      </div>

      <div className="flex-1 w-full rounded-xl overflow-hidden border border-white/10">
        <React.Suspense fallback={<Fallback2D height="100%" />}>
          <LaptopViewer machines={machines.length ? machines : undefined} />
        </React.Suspense>
      </div>
    </div>
  );
};
