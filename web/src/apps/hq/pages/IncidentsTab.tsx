import React, { useState } from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { IncidentCard } from '@/components/IncidentCard';
import { Incident } from '@/types';
import { api } from '@/services/apiClient';
import { SyncChip } from '@/components/SyncChip';
import { ExplainAI } from '@/components/ExplainAI';

export const IncidentsTab: React.FC = () => {
  const incidents = useLiveStore((s) => s.incidents);
  const alerts = useLiveStore((s) => s.alerts);
  const userId = useUiStore((s) => s.currentUserId) || 'operator';
  const [voted, setVoted] = useState<Record<string, boolean>>({});
  const [showAlertsDrawer, setShowAlertsDrawer] = useState(false);
  const counters = useLiveStore((s) => s.counters);
  const activeTenant = useUiStore((s) => s.activeTenant);
  const setActiveTenant = useUiStore((s) => s.setActiveTenant);
  const setCopilotOpen = useUiStore((s) => s.setCopilotOpen);

  const filtered: Incident[] = incidents.filter(
    (i: Incident) => activeTenant === 'ALL' || i.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const activeAlerts = alerts.filter(
    (a) => activeTenant === 'ALL' || a.tenant_id.toLowerCase() === activeTenant.toLowerCase()
  );

  const noiseCutPct = counters.raw_alerts > 0
    ? Math.round(((counters.raw_alerts - counters.incidents) / counters.raw_alerts) * 100)
    : 94;

  const handleSelectEvidence = () => {
    setCopilotOpen(true);
  };

  return (
    <div className="p-5 space-y-5 max-w-[1700px] mx-auto font-mono text-xs select-none">
      {/* KPI & Noise Reduction Banner */}
      <div className="hud-panel p-5 flex flex-col md:flex-row md:items-center justify-between border-sky-500/30 gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
            <span className="text-[10px] uppercase tracking-widest text-sky-400 font-bold">
              AIOPS NOISE REDUCTION & INCIDENT CORRELATION
            </span>
          </div>
          <div className="text-lg font-black text-white mt-1">
            RAW ALERTS {counters.raw_alerts} → INCIDENTS {counters.incidents} · <span className="text-emerald-400">{noiseCutPct}% NOISE CUT</span>
          </div>
          <p className="text-slate-400 text-[11px] mt-0.5">
            Dampens transient spikes and correlates multi-signal causal chains into actionable incidents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Contextual System Filter Pills */}
          <div className="flex items-center space-x-1 bg-black/40 p-1 rounded border border-white/10 text-xs">
            <span className="text-[10px] text-slate-400 font-bold px-1.5 uppercase">SYSTEM:</span>
            {(['ALL', 'acme', 'globex'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setActiveTenant(t)}
                className={`px-2 py-0.5 rounded text-[11px] font-bold transition-colors ${
                  activeTenant === t
                    ? 'bg-sky-500 text-black shadow-sm'
                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t === 'ALL' ? 'ALL' : t === 'acme' ? 'SYS 1' : 'SYS 2'}
              </button>
            ))}
          </div>

          <SyncChip />
          <div className="text-right px-4 py-2 rounded bg-black/40 border border-white/5">
            <span className="text-[10px] text-slate-400 uppercase font-bold block">FLAPS PREVENTED</span>
            <span className="text-base font-black text-emerald-400">{counters.flaps_prevented}</span>
          </div>
          <button
            onClick={() => setShowAlertsDrawer(!showAlertsDrawer)}
            className="px-3 py-2 rounded border border-white/10 hover:bg-white/5 text-slate-300 text-xs font-bold transition-colors"
          >
            {showAlertsDrawer ? '▲ HIDE RAW ALERTS' : `▼ VIEW RAW ALERTS (${activeAlerts.length})`}
          </button>
        </div>
      </div>

      {/* Collapsible Raw Alerts Section */}
      {showAlertsDrawer && (
        <div className="hud-panel p-4 space-y-2 border border-white/10 bg-[#0A0D15]">
          <div className="flex items-center justify-between border-b border-white/5 pb-2">
            <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">
              ACTIVE RAW ALERTS ({activeAlerts.length}) · THUMBS DOWN RAISES THRESHOLD (+0.5σ)
            </span>
            <span className="text-[10px] text-slate-500">Auto-correlated by AIOps</span>
          </div>
          <div className="divide-y divide-white/5 max-h-[28rem] overflow-y-auto pr-1">
            {activeAlerts.slice(0, 15).map((a) => {
              const sysLabel = a.tenant_id === 'acme' ? 'SYSTEM 1' : a.tenant_id === 'globex' ? 'SYSTEM 2' : a.tenant_id.toUpperCase();
              return (
                <div key={a.alert_id} className="flex flex-wrap items-center gap-2 py-2 text-[11px]">
                  <div className="flex items-center space-x-2 flex-1 min-w-0">
                    <span className="px-1.5 py-0.5 rounded text-[9px] bg-slate-800 text-sky-400 font-bold border border-white/5">
                      {sysLabel}
                    </span>
                    <span className="text-slate-200">{a.title}</span>
                    <span className="text-slate-500">[{a.severity}, {a.status}]</span>
                  </div>
                  <div className="contents">
                  <button
                    disabled={voted[a.alert_id]}
                    className="px-2 py-0.5 rounded border border-slate-700 hover:bg-slate-700 disabled:opacity-40 text-xs"
                    onClick={async () => {
                      await api.postFeedback(a.alert_id, a.tenant_id, userId).catch(() => {});
                      setVoted((v) => ({ ...v, [a.alert_id]: true }));
                    }}
                  >
                    {voted[a.alert_id] ? '✓ NOTED' : '👎 DAMP'}
                  </button>
                  <ExplainAI kind="alert" id={a.alert_id} tenant={a.tenant_id} />
                  </div>
                </div>
              );
            })}
            {activeAlerts.length === 0 && (
              <div className="py-4 text-center text-slate-500 text-xs">
                No active raw alerts for the selected system.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Active Incidents Feed */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs font-bold text-slate-400 uppercase tracking-wider">
          <span>CORRELATED INCIDENTS ({filtered.length})</span>
          <span className="text-[11px] text-slate-500 font-normal">
            Targeting: {activeTenant === 'ALL' ? 'ALL SYSTEMS (1 & 2)' : activeTenant === 'acme' ? 'SYSTEM 1' : 'SYSTEM 2'}
          </span>
        </div>

        {filtered.map((inc) => (
          <IncidentCard
            key={inc.incident_id}
            incident={inc}
            onSelectEvidence={handleSelectEvidence}
          />
        ))}

        {filtered.length === 0 && (
          <div className="hud-panel p-12 text-center text-slate-500 border border-dashed border-white/10">
            <span className="text-sm font-bold block text-slate-400">NO OPEN INCIDENTS DETECTED</span>
            <span className="text-xs text-slate-500 mt-1 block">All systems operating within baseline parameters.</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default IncidentsTab;
