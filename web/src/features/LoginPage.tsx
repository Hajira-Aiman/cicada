import React, { useState } from 'react';
import { GradientASCII } from '../components/GradientASCII';
import { api } from '../services/apiClient';
import { useUiStore } from '../stores/uiStore';

const DEMO = [
  { label: 'Engineer (all)', user: 'admin', pass: 'admin123' },
  { label: 'System 1', user: 'user-acme', pass: 'acme123' },
  { label: 'System 2', user: 'user-globex', pass: 'globex123' },
];

// Full-screen sign-in: the animated backdrop owns the whole page, the form is a slim bar at the bottom so nothing covers it.
export const LoginPage: React.FC = () => {
  const setAuth = useUiStore((s) => s.setAuth);
  const [user, setUser] = useState('admin');
  const [pass, setPass] = useState('admin123');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const res = await api.login(user, pass);
      setAuth(res.token, res.user_id, res.role as any, res.tenant_id || undefined);
    } catch (err: any) {
      setError(err.message || 'Login failed');
      setBusy(false);
    }
  };

  const field = 'bg-black/55 border border-white/15 focus:border-sky-400 rounded px-3 py-2 text-xs font-mono text-white outline-none w-full sm:w-44 backdrop-blur-sm';

  return (
    <div className="fixed inset-0 bg-[#05070d] overflow-hidden select-none">
      <div className="absolute inset-0">
        <GradientASCII colors={['#1e3fd8', '#2563eb', '#38bdf8', '#22d3ee']} shape="pinch" characters=" .:-=+*#%@" cellSize={14}
          density={0.9} glow={0.5} mouseInteraction clickEffect="wave" />
      </div>

      <div className="absolute top-8 left-10 pointer-events-none">
        <div className="font-mono text-3xl font-black tracking-[0.35em] text-white drop-shadow-[0_0_18px_rgba(56,189,248,0.7)]">AIRLOCK</div>
        <div className="font-mono text-[11px] tracking-widest text-sky-200/80 mt-1">METADATA-ONLY TELEMETRY · CLOUD DASHBOARD</div>
      </div>

      <form onSubmit={submit} className="absolute bottom-8 left-1/2 -translate-x-1/2 w-[min(94vw,860px)] flex flex-col gap-2 p-3 rounded-xl
        bg-[#070b14]/60 border border-white/10 backdrop-blur-md">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <input className={field} value={user} onChange={(e) => setUser(e.target.value)} placeholder="username" autoComplete="username" />
          <input className={field} type="password" value={pass} onChange={(e) => setPass(e.target.value)} placeholder="password" autoComplete="current-password" />
          <button disabled={busy} className="px-5 py-2 rounded bg-sky-500 hover:bg-sky-400 disabled:opacity-60 text-black text-xs font-mono font-black tracking-wider">
            {busy ? 'SIGNING IN…' : 'SIGN IN →'}
          </button>
          <div className="flex items-center gap-1.5 sm:ml-auto">
            {DEMO.map((d) => (
              <button key={d.user} type="button" onClick={() => { setUser(d.user); setPass(d.pass); }}
                className="text-[10px] font-mono px-2 py-1 rounded bg-white/10 hover:bg-white/20 text-slate-200">{d.label}</button>
            ))}
          </div>
        </div>
        {error && <div className="text-[11px] font-mono text-rose-300">✕ {error}</div>}
      </form>
    </div>
  );
};
