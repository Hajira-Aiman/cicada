import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { StatusBadge } from '@/components/StatusBadge';
import { TimeText } from '@/components/TimeText';
import { apiFetch } from '@/services/apiClient';
const SECURITY = new Set(['auth_failure_burst', 'login_after_failures', 'odd_hour_login', 'honeypot_hit', 'new_process', 'secret_redacted']);

export const SecurityTab: React.FC = () => {
  const alerts = useLiveStore((s) => s.alerts);

  const [securityEvents, setEvents] = React.useState<any[]>([]);
  React.useEffect(() => {
    const load = () => apiFetch<{ events: any[] }>('/api/events?limit=300').then((r) => setEvents(r.events.filter((e) => SECURITY.has(e.category)).slice(0, 24).map((e) => ({
      id: String(e.id), category: e.category, source: e.source, actor: e.actor || '—', count: e.count, window_s: e.window_s,
      risk: e.severity === 'critical' ? 'CRITICAL' : e.severity === 'high' ? 'HIGH' : 'MEDIUM', at: e.event_time,
      details: `${e.count} × ${e.category.replace(/_/g, ' ')} in ${e.window_s}s window` })))).catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

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
