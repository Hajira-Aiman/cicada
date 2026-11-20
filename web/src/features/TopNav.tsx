import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useUiStore } from '../stores/uiStore';
import { useLiveStore } from '../stores/liveStore';
import { api } from '../services/apiClient';
import { GradientASCII } from '../components/GradientASCII';

const TABS = [
  { path: '/overview', label: 'OVERVIEW' },
  { path: '/live-map', label: 'LIVE MAP' },
  { path: '/incidents', label: 'INCIDENTS & ALERTS' },
  { path: '/privacy', label: 'PRIVACY & PROOF' },
];

export const TopNav: React.FC = () => {
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('admin123');
  const [loginError, setLoginError] = useState('');

  const setAuth = useUiStore((s) => s.setAuth);
  const connected = useLiveStore((s) => s.connected);

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError('');
    try {
      const res = await api.login(loginUsername, loginPassword);
      setAuth(res.token, res.user_id, res.role as any, res.tenant_id || undefined);
      setLoginModalOpen(false);
    } catch (err: any) {
      setLoginError(err.message || 'Login failed');
    }
  };

  return (
    <>
      <header className="h-14 bg-[#080A10] border-b border-white/[0.08] px-5 flex items-center z-30 select-none">
        {/* Brand wordmark + live pulse */}
        <div className="flex items-center space-x-6">
          <div
            onClick={() => setLoginModalOpen(true)}
            title="Airlock Cloud Dashboard (Click for Auth Gateway)"
            className="flex items-center space-x-3 cursor-pointer group"
          >
            <span className="font-mono text-lg font-black tracking-widest text-white group-hover:text-sky-400 transition-colors">
              AIRLOCK
            </span>
            <span className="text-[11px] font-mono text-slate-500 uppercase tracking-widest font-semibold hidden sm:inline">
              CLOUD DASHBOARD
            </span>
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                connected ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_#10B981]' : 'bg-rose-500'
              }`}
              title={connected ? 'Connected to live ingest stream' : 'Disconnected'}
            />
          </div>

          {/* 4 Core Nav Tabs */}
          <nav className="flex items-center space-x-1.5">
            {TABS.map((tab) => (
              <NavLink
                key={tab.path}
                to={tab.path}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-xs font-mono font-bold tracking-wider transition-colors ${
                    isActive
                      ? 'bg-sky-500/15 text-sky-300 border border-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {/* Login Modal */}
      {loginModalOpen && (
        <div className="fixed inset-0 z-50 bg-[#080A10]/85 flex items-center justify-center p-4 backdrop-blur-md overflow-hidden select-none">
          {/* Reactive GradientASCII Interactive Backdrop */}
          <div className="absolute inset-0 opacity-40 pointer-events-auto">
            <GradientASCII
              colors={['#1e3fd8', '#1309e7', '#38bdf8', '#0ea5e9']}
              shape="pinch"
              characters=" .:-=+*#%@"
              cellSize={16}
              density={0.75}
              glow={0.3}
              mouseInteraction={true}
              clickEffect="wave"
            />
          </div>

          <form
            onSubmit={handleLoginSubmit}
            className="hud-panel relative z-10 p-7 max-w-md w-full bg-[#0c101a]/95 backdrop-blur-xl border border-sky-500/30 shadow-[0_0_50px_rgba(14,165,233,0.15)] rounded-lg space-y-4"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div>
                <h3 className="text-sm font-mono font-black text-white tracking-wider flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
                  AUTHENTICATION GATEWAY
                </h3>
                <p className="text-[11px] font-mono text-slate-400 mt-0.5">
                  Sign in to access Cloud Dashboard telemetry
                </p>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20 font-bold">
                AIRLOCK
              </span>
            </div>

            {loginError && (
              <div className="text-xs font-mono p-2.5 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300">
                ✕ {loginError}
              </div>
            )}

            {/* Quick Demo Fill Buttons */}
            <div className="flex items-center gap-1.5 pt-1">
              <span className="text-[10px] font-mono text-slate-500 uppercase font-bold">DEMO:</span>
              <button
                type="button"
                onClick={() => {
                  setLoginUsername('admin');
                  setLoginPassword('admin123');
                }}
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.06] hover:bg-white/[0.12] text-slate-300 transition-colors"
              >
                Engineer (All)
              </button>
              <button
                type="button"
                onClick={() => {
                  setLoginUsername('user-acme');
                  setLoginPassword('acme123');
                }}
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.06] hover:bg-white/[0.12] text-slate-300 transition-colors"
              >
                System 1
              </button>
              <button
                type="button"
                onClick={() => {
                  setLoginUsername('user-globex');
                  setLoginPassword('globex123');
                }}
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/[0.06] hover:bg-white/[0.12] text-slate-300 transition-colors"
              >
                System 2
              </button>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
                Username
              </label>
              <input
                type="text"
                value={loginUsername}
                onChange={(e) => setLoginUsername(e.target.value)}
                placeholder="admin / user-acme / user-globex"
                className="w-full bg-[#080A10] border border-white/10 focus:border-sky-500/50 p-2.5 text-xs font-mono text-white rounded outline-none transition-colors"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-slate-400 font-semibold tracking-wider">
                Password
              </label>
              <input
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="admin123 / acme123 / globex123"
                className="w-full bg-[#080A10] border border-white/10 focus:border-sky-500/50 p-2.5 text-xs font-mono text-white rounded outline-none transition-colors"
              />
            </div>

            <div className="flex justify-end items-center space-x-2.5 pt-2 border-t border-white/10">
              <button
                type="button"
                onClick={() => setLoginModalOpen(false)}
                className="px-3 py-1.5 text-xs font-mono rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300 transition-colors"
              >
                CANCEL
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 text-xs font-mono font-bold rounded bg-sky-500 hover:bg-sky-400 text-black shadow-[0_0_15px_rgba(14,165,233,0.3)] transition-all"
              >
                SIGN IN →
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
};
