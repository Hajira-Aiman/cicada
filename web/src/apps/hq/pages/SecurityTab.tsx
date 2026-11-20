import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { StatusBadge } from '@/components/StatusBadge';
import { TimeText } from '@/components/TimeText';

export const SecurityTab: React.FC = () => {
  const alerts = useLiveStore((s) => s.alerts);

  const securityEvents = [
    {
      id: 'sec-001',
      category: 'auth_failure_burst',
      source: 'host-7f3a1234',
      actor: 'src-9c2e0011',
      count: 50,
      window_s: 2,
      risk: 'HIGH',
      at: new Date(Date.now() - 300000).toISOString(),
      details: 'SSH brute force pattern: 50 failed attempts in 2.0s',
    },
    {
      id: 'sec-002',
      category: 'login_after_failures',
      source: 'host-7f3a1234',
      actor: 'src-9c2e0011',
      count: 1,
      window_s: 60,
      risk: 'CRITICAL',
      at: new Date(Date.now() - 240000).toISOString(),
      details: 'Sudden success following 50 consecutive failed logins',
    },
    {
      id: 'sec-003',
      category: 'honeypot_hit',
      source: 'host-1a2b3c4d',
      actor: 'src-4f5e6a7b',
      count: 1,
      window_s: 1,
      risk: 'CRITICAL',
      at: new Date(Date.now() - 720000).toISOString(),
      details: 'Trap port 2222 accessed; attacker probed decoy endpoint',
    },
    {
      id: 'sec-004',
      category: 'odd_hour_login',
      source: 'host-9c2e0011',
      actor: 'user-7f3a1234',
      count: 1,
      window_s: 1,
      risk: 'MEDIUM',
      at: new Date(Date.now() - 1440000).toISOString(),
      details: 'Admin shell accessed at 03:14 shop-local time (Asia/Kolkata)',
    },
  ];

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      <div className="hud-panel p-4 border border-rose-500/20 bg-rose-950/10 flex items-center justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-rose-400 font-bold block">
            PRIVACY GUARANTEE: PSEUDONYMIZED SECURITY STREAM
          </span>
          <span className="text-sm font-bold text-white mt-0.5 block">
            No cleartext usernames, IPs, or hostnames may ever cross the trust boundary.
          </span>
        </div>
        <span className="text-xs text-rose-400 font-bold px-3 py-1 rounded bg-rose-500/20 border border-rose-500/40">
          STRICT ALLOW-LIST ENFORCED
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {securityEvents.map((evt) => (
          <div key={evt.id} className="hud-panel p-4 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-sm font-bold text-white">{evt.category.toUpperCase()}</span>
                <span className="text-[10px] text-slate-500 block mt-0.5">ID: {evt.id}</span>
              </div>
              <StatusBadge status={evt.risk as any} />
            </div>

            <p className="text-slate-300 text-xs">{evt.details}</p>

            <div className="grid grid-cols-2 gap-2 p-2.5 rounded bg-[#121620] border border-white/5 text-[11px]">
              <div>
                <span className="text-slate-500 block">SOURCE TARGET</span>
                <span className="text-slate-200 font-bold">{evt.source}</span>
              </div>
              <div>
                <span className="text-slate-500 block">ATTACKER PSEUDONYM</span>
                <span className="text-rose-400 font-bold">{evt.actor}</span>
              </div>
              <div>
                <span className="text-slate-500 block">EVENT COUNT / WINDOW</span>
                <span className="text-slate-200">{evt.count} in {evt.window_s}s</span>
              </div>
              <div>
                <span className="text-slate-500 block">TIMESTAMP</span>
                <TimeText timestamp={evt.at} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
