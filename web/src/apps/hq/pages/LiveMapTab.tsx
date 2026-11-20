import React from 'react';
import { Fallback2D } from '@/three/Fallback2D';

export const LiveMapTab: React.FC = () => {
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
        <Fallback2D height="100%" />
      </div>
    </div>
  );
};
