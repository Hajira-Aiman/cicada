import React, { useState } from 'react';
import { askShopAI } from '../services/shopApi';

// Shop AI (PRD #22): asks the guard on this machine, which answers from the local raw logs. Nothing leaves the shop.
export const ShopAssistant: React.FC = () => {
  const [q, setQ] = useState('');
  const [a, setA] = useState('');
  const [busy, setBusy] = useState(false);

  const ask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!q.trim() || busy) return;
    setBusy(true);
    setA('');
    try { setA(await askShopAI(q.trim())); } catch (x: any) { setA(x.message); }
    setBusy(false);
  };

  return (
    <div className="hud-panel p-3 m-4 font-mono text-xs space-y-2">
      <span className="text-[10px] uppercase tracking-widest text-cyan-400 font-bold block">SHOP AI · LOCAL, READS RAW LOGS ON THIS MACHINE</span>
      <form onSubmit={ask} className="flex space-x-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. who failed to log in in the last 10 minutes?"
          className="flex-1 bg-[#121620] border border-white/10 rounded px-2 py-1.5 text-slate-200" />
        <button disabled={busy} className="px-3 py-1.5 rounded bg-sky-500 text-black font-bold disabled:opacity-50">{busy ? '…' : 'ASK'}</button>
      </form>
      {a && <div className="p-2.5 rounded bg-[#121620] border border-white/5 text-slate-300 whitespace-pre-wrap">{a}</div>}
    </div>
  );
};
