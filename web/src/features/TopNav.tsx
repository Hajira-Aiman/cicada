import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useUiStore } from '../stores/uiStore';
import { useLiveStore } from '../stores/liveStore';
import { startDemoFeed, stopDemoFeed } from '../services/demoFeed';
import { api } from '../services/apiClient';
import { GradientASCII } from '../components/GradientASCII';

const TABS = [
  { path: '/overview', label: 'OVERVIEW' },
  { path: '/live-map', label: 'LIVE MAP' },
  { path: '/incidents', label: 'INCIDENTS & ALERTS' },
  { path: '/privacy', label: 'PRIVACY & PROOF' },
];

export const TopNav: React.FC = () => {
  const [utcClock, setUtcClock] = useState('');
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('admin123');
  const [loginError, setLoginError] = useState('');

  const activeTenant = useUiStore((s) => s.activeTenant);
  const setActiveTenant = useUiStore((s) => s.setActiveTenant);
  const tzMode = useUiStore((s) => s.tzMode);
  const setTzMode = useUiStore((s) => s.setTzMode);
  const copilotOpen = useUiStore((s) => s.copilotOpen);
  const setCopilotOpen = useUiStore((s) => s.setCopilotOpen);
  const authRole = useUiStore((s) => s.authRole);
  const currentUserId = useUiStore((s) => s.currentUserId);
  const setAuth = useUiStore((s) => s.setAuth);
  const logout = useUiStore((s) => s.logout);

  const connected = useLiveStore((s) => s.connected);
  const mode = useLiveStore((s) => s.mode);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcClock(now.toISOString().substring(11, 19) + ' UTC');
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

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
      <header className="h-14 bg-[#080A10] border-b border-white/[0.08] px-5 flex items-center justify-between z-30 select-none">
        {/* Brand wordmark + live pulse */}
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-3">
            <span className="font-mono text-lg font-black tracking-widest text-white">
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

        {/* Controls: System Switcher, TZ, Clock, Mode, Copilot */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          {/* System Switcher (Replacing Tenant & Eliminating Regions) */}
          <div className="flex items-center space-x-1.5 bg-[#141721] px-2.5 py-1 rounded border border-white/10">
            <span className="text-[10px] uppercase text-slate-500 font-bold">SYSTEM:</span>
            <select
              value={activeTenant}
              disabled={authRole === 'customer'}
              onChange={(e) => setActiveTenant(e.target.value as any)}
              className="bg-transparent text-slate-200 font-bold focus:outline-none cursor-pointer disabled:cursor-not-allowed"
            >
              <option value="ALL" className="bg-[#1A1C23]">ALL SYSTEMS (1 & 2)</option>
              <option value="acme" className="bg-[#1A1C23]">SYSTEM 1</option>
              <option value="globex" className="bg-[#1A1C23]">SYSTEM 2</option>
            </select>
          </div>

          {/* Time-Zone Mode (Simplified: UTC vs LOCAL) */}
          <div className="flex items-center bg-[#141721] p-0.5 rounded border border-white/10">
            {(['UTC', 'VIEWER'] as const).map((tz) => (
              <button
                key={tz}
                onClick={() => setTzMode(tz === 'VIEWER' ? 'VIEWER' : 'UTC')}
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  (tz === 'UTC' && tzMode === 'UTC') || (tz === 'VIEWER' && tzMode !== 'UTC')
                    ? 'bg-sky-500 text-black'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tz === 'VIEWER' ? 'LOCAL' : 'UTC'}
              </button>
            ))}
          </div>

          {/* UTC Clock */}
          <span className="text-slate-300 font-bold tabular-nums hidden md:inline">
            {utcClock}
          </span>

          {/* Mode Switch (LIVE / SIMULATED) */}
          <button
            onClick={() => (mode === 'LIVE' ? startDemoFeed() : stopDemoFeed())}
            className={`px-2 py-1 rounded text-[10px] font-bold tracking-wider border ${
              mode === 'LIVE'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
            }`}
          >
            {mode}
          </button>

          {/* User Button */}
          <button
            onClick={() => (currentUserId ? logout() : setLoginModalOpen(true))}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-white/10"
          >
            {currentUserId ? `${currentUserId}` : 'LOGIN'}
          </button>

          {/* Copilot Drawer Toggle */}
          <button
            onClick={() => setCopilotOpen(!copilotOpen)}
            className={`px-3 py-1 rounded text-xs font-bold tracking-wider border transition-colors ${
              copilotOpen
                ? 'bg-sky-500 text-black border-sky-400'
                : 'bg-sky-500/10 text-sky-400 border-sky-500/30 hover:bg-sky-500/20'
            }`}
          >
            AI COPILOT
          </button>
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
