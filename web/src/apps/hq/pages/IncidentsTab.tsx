import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { IncidentCard } from '@/components/IncidentCard';
import { Incident } from '@/types';
import { api } from '@/services/apiClient';
import { DamageMap } from '@/components/DamageMap';

export const IncidentsTab: React.FC = () => {
  const incidents = useLiveStore((s) => s.incidents);
  const alerts = useLiveStore((s) => s.alerts);
  const userId = useUiStore((s) => s.currentUserId) || 'operator';
  const [voted, setVoted] = React.useState<Record<string, boolean>>({});
  const counters = useLiveStore((s) => s.counters);
  const activeTenant = useUiStore((s) => s.activeTenant);
  const setCopilotOpen = useUiStore((s) => s.setCopilotOpen);

  const filtered: Incident[] = incidents.filter(
    (i: Incident) => activeTenant === 'ALL' || i.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const noiseCutPct = counters.raw_alerts > 0
    ? Math.round(((counters.raw_alerts - counters.incidents) / counters.raw_alerts) * 100)
    : 94;

  const handleSelectEvidence = (evidenceId: string) => {
    setCopilotOpen(true);
  };

  return (
    <div className="p-4 space-y-4 max-w-[1920px] mx-auto font-mono text-xs">
      {/* Noise reduction banner */}
      <div className="hud-panel p-4 flex flex-col sm:flex-row sm:items-center justify-between border-sky-500/30">
        <div>
          <span className="text-[10px] uppercase tracking-widest text-sky-400 font-bold block">
            AIOPS NOISE REDUCTION ENGINE
          </span>
          <span className="text-base font-black text-white mt-1 block">
            RAW ALERTS {counters.raw_alerts} → INCIDENTS {counters.incidents} · {noiseCutPct}% NOISE CUT
          </span>
        </div>
        <div className="text-right mt-2 sm:mt-0">
          <span className="text-xs text-emerald-400 font-bold block">FLAPS PREVENTED: {counters.flaps_prevented}</span>
          <span className="text-[10px] text-slate-500">Automated damping prevents alarm fatigue</span>
        </div>
      </div>

      <DamageMap tenant={activeTenant === 'ALL' ? 'acme' : activeTenant} />

      {/* Raw alerts with thumbs-down: a 👎 raises that signal's flag level 3 -> 3.5 sigma for 30 min */}
      <div className="hud-panel p-3 space-y-1">
        <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">ALERTS ({alerts.filter((a) => activeTenant === 'ALL' || a.tenant_id === activeTenant).length})</span>
        {alerts.filter((a) => activeTenant === 'ALL' || a.tenant_id === activeTenant).slice(0, 8).map((a) => (
          <div key={a.alert_id} className="flex items-center justify-between text-[11px] border-t border-white/5 pt-1">
            <span className="text-slate-300">{a.tenant_id} · {a.title} <span className="text-slate-500">[{a.severity}, {a.status}]</span></span>
            <button disabled={voted[a.alert_id]} className="px-2 py-0.5 rounded border border-slate-600 hover:bg-slate-700 disabled:opacity-40"
              onClick={async () => { await api.postFeedback(a.alert_id, a.tenant_id, userId).catch(() => {}); setVoted((v) => ({ ...v, [a.alert_id]: true })); }}>
              {voted[a.alert_id] ? 'noted' : '👎'}
            </button>
          </div>
        ))}
      </div>

      {/* Incidents List */}
      <div className="space-y-4">
        {filtered.map((inc) => (
          <IncidentCard
            key={inc.incident_id}
            incident={inc}
            onSelectEvidence={handleSelectEvidence}
          />
        ))}

        {filtered.length === 0 && (
          <div className="hud-panel p-12 text-center text-slate-500">
            NO OPEN INCIDENTS DETECTED FOR CURRENT VIEW
          </div>
        )}
      </div>
    </div>
  );
};
