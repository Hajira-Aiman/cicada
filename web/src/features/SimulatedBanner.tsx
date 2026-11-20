import React from 'react';
import { useLiveStore } from '../stores/liveStore';
import { stopDemoFeed } from '../services/demoFeed';

export const SimulatedBanner: React.FC = () => {
  const mode = useLiveStore((s) => s.mode);

  if (mode !== 'SIMULATED') return null;

  return (
    <div className="w-full bg-amber-500/20 border-b border-amber-500/40 px-4 py-1.5 flex items-center justify-between text-xs font-mono text-amber-300 z-40">
      <div className="flex items-center space-x-2">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        <span className="font-bold">SIMULATED DATA · NOT FROM LIVE GUARDS</span>
        <span className="text-amber-400/80">Replaying schema-compliant payloads from contracts/examples/</span>
      </div>
      <button
        onClick={() => stopDemoFeed()}
        className="px-2.5 py-0.5 rounded bg-amber-600 hover:bg-amber-500 text-black font-bold text-[11px]"
      >
        SWITCH TO LIVE WEBSOCKET
      </button>
    </div>
  );
};
