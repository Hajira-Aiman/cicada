import React, { useEffect, useState } from 'react';
import { useLiveStore } from '../stores/liveStore';

// Proof that the numbers on screen are fresh: "LIVE · updated 2 s ago", red when nothing has arrived for a while.
export const SyncChip: React.FC = () => {
  const lastSync = useLiveStore((s) => s.lastSync);
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(id); }, []);
  const age = lastSync ? Math.round((Date.now() - lastSync) / 1000) : null;
  const stale = age === null || age > 10;
  return (
    <span className={`px-2.5 py-1 rounded border text-[10px] font-mono font-bold ${stale ? 'border-rose-500/40 text-rose-300 bg-rose-500/10' : 'border-emerald-500/40 text-emerald-300 bg-emerald-500/10'}`}>
      {age === null ? 'CONNECTING…' : stale ? `NO UPDATE FOR ${age} S` : `LIVE · UPDATED ${age} S AGO`}
    </span>
  );
};
