import React from 'react';
import { NavLink } from 'react-router-dom';
import { useUiStore } from '../stores/uiStore';
import { useLiveStore } from '../stores/liveStore';

const TABS = [
  { path: '/overview', label: 'OVERVIEW' },
  { path: '/live-map', label: 'LIVE MAP' },
  { path: '/telemetry', label: 'TELEMETRY VIEW' },
  { path: '/incidents', label: 'INCIDENTS & ALERTS' },
  { path: '/privacy', label: 'PRIVACY & PROOF' },
  { path: '/database', label: 'DATABASE' },
];

export const TopNav: React.FC = () => {
  const connected = useLiveStore((s) => s.connected);
  const token = useUiStore((s) => s.authToken);
  const userId = useUiStore((s) => s.currentUserId);
  const logout = useUiStore((s) => s.logout);
  const tzMode = useUiStore((s) => s.tzMode);
  const setTzMode = useUiStore((s) => s.setTzMode);

  return (
    <>
      <header className="h-14 bg-[#080A10] border-b border-white/[0.08] px-5 flex items-center z-30 select-none">
        {/* Brand wordmark + live pulse */}
        <div className="flex items-center space-x-6">
          <div
            title="Airlock Cloud Dashboard"
            className="flex items-center space-x-3 group"
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
        <div className="ml-auto flex items-center space-x-2 text-xs font-mono">
          {/* time zone for every clock on the dashboard */}
          <div className="flex rounded border border-white/10 overflow-hidden" title="Time zone for every timestamp on the dashboard">
            {([['UTC', 'UTC'], ['VIEWER', 'LOCAL'], ['SHOP', 'SHOP']] as const).map(([m, label]) => (
              <button
                key={m}
                onClick={() => setTzMode(m)}
                className={`px-2.5 py-1.5 font-bold ${tzMode === m ? 'bg-sky-500/20 text-sky-300' : 'bg-slate-900 text-slate-400 hover:text-slate-200'}`}
              >
                {label}
              </button>
            ))}
          </div>
          <span className="text-slate-400">{userId}</span>
          <button
            onClick={logout}
            className="px-3 py-1.5 rounded border border-white/10 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold"
          >
            LOGOUT
          </button>
        </div>
      </header>

    </>
  );
};
