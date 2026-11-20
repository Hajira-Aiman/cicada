import React, { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useUiStore } from '../stores/uiStore';
import { useLiveStore } from '../stores/liveStore';
import { api } from '../services/apiClient';

const TABS = [
  { path: '/overview', label: 'OVERVIEW' },
  { path: '/live-map', label: 'LIVE MAP' },
  { path: '/fleet', label: 'FLEET' },
  { path: '/incidents', label: 'INCIDENTS' },
  { path: '/security', label: 'SECURITY' },
  { path: '/privacy', label: 'PRIVACY' },
  { path: '/actions', label: 'ACTIONS' },
  { path: '/history', label: 'HISTORY' },
  { path: '/settings', label: 'SETTINGS' },
];

export const TopNav: React.FC = () => {
  const [utcClock, setUtcClock] = useState('');
  const [loginModalOpen, setLoginModalOpen] = useState(!useUiStore.getState().authToken);  // live data needs a login
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
      <header className="h-14 bg-[#080A10] border-b border-white/[0.08] px-4 flex items-center justify-between z-30 select-none">
        {/* Brand wordmark + live pulse */}
        <div className="flex items-center space-x-6">
          <div className="flex items-center space-x-2.5">
            <span className="font-mono text-xl font-black tracking-widest text-white">
              AIRLOCK
            </span>
            <span
              className={`w-2.5 h-2.5 rounded-full ${
                connected ? 'bg-emerald-400 animate-pulse shadow-[0_0_8px_#10B981]' : 'bg-rose-500'
              }`}
              title={connected ? 'Connected to live ingest stream' : 'Disconnected'}
            />
          </div>

          {/* Nav Tabs */}
          <nav className="hidden lg:flex items-center space-x-1">
            {TABS.map((tab) => (
              <NavLink
                key={tab.path}
                to={tab.path}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-xs font-mono font-bold tracking-wider transition-colors ${
                    isActive
                      ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>

        {/* Controls: Tenant, TZ, Clock, Mode, Copilot */}
        <div className="flex items-center space-x-3 text-xs font-mono">
          {/* Tenant Switcher */}
          <div className="flex items-center space-x-1.5 bg-[#141721] px-2.5 py-1 rounded border border-white/10">
            <span className="text-[10px] uppercase text-slate-500 font-bold">TENANT</span>
            <select
              value={activeTenant}
              disabled={authRole === 'customer'}
              onChange={(e) => setActiveTenant(e.target.value as any)}
              className="bg-transparent text-slate-200 font-bold focus:outline-none cursor-pointer disabled:cursor-not-allowed"
            >
              <option value="ALL" className="bg-[#1A1C23]">ALL (ENGINEER)</option>
              <option value="acme" className="bg-[#1A1C23]">ACME (INDIA)</option>
              <option value="globex" className="bg-[#1A1C23]">GLOBEX (EUROPE)</option>
              <option value="contoso" className="bg-[#1A1C23]">CONTOSO (ORG)</option>
            </select>
          </div>

          {/* Time-Zone Mode */}
          <div className="flex items-center bg-[#141721] p-0.5 rounded border border-white/10">
            {(['UTC', 'VIEWER', 'SHOP'] as const).map((tz) => (
              <button
                key={tz}
                onClick={() => setTzMode(tz)}
                className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                  tzMode === tz ? 'bg-sky-500 text-black' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tz}
              </button>
            ))}
          </div>

          {/* UTC Clock */}
          <span className="text-slate-300 font-bold tabular-nums hidden sm:inline">
            {utcClock}
          </span>

          {/* Backend connection (no simulated mode: every number on screen comes from the backend) */}
          <span
            className={`px-2 py-1 rounded text-[10px] font-bold tracking-wider border ${
              connected
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-rose-500/10 text-rose-400 border-rose-500/30'
            }`}
          >
            {connected ? 'LIVE' : 'OFFLINE'}
          </span>

          {/* User / Login */}
          <button
            onClick={() => (currentUserId ? logout() : setLoginModalOpen(true))}
            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-white/10"
          >
            {currentUserId ? `${currentUserId} (${authRole})` : 'LOGIN'}
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
        <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
          <form
            onSubmit={handleLoginSubmit}
            className="hud-panel p-6 max-w-sm w-full bg-[#121620] border border-white/10 space-y-4"
          >
            <h3 className="text-base font-mono font-bold text-white">LOGIN TO AIRLOCK HQ</h3>
            <p className="text-xs text-slate-400">
              Admin sees all tenants; customer logins isolate strictly to their data residency region.
            </p>

            {loginError && <div className="text-xs font-mono text-rose-400">{loginError}</div>}

            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-slate-400">Username</label>
              <input
                type="text"
                value={loginUsername}
                onChange={(e) => setLoginUsername(e.target.value)}
                placeholder="admin / user-acme / user-globex"
                className="w-full bg-[#080A10] border border-slate-700 p-2 text-xs font-mono text-white rounded"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-slate-400">Password</label>
              <input
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="admin123 / acme123 / globex123"
                className="w-full bg-[#080A10] border border-slate-700 p-2 text-xs font-mono text-white rounded"
              />
            </div>

            <div className="flex justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setLoginModalOpen(false)}
                className="px-3 py-1 text-xs font-mono rounded bg-slate-800 text-slate-300"
              >
                CANCEL
              </button>
              <button
                type="submit"
                className="px-4 py-1 text-xs font-mono font-bold rounded bg-sky-500 text-black hover:bg-sky-400"
              >
                SIGN IN
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
};
