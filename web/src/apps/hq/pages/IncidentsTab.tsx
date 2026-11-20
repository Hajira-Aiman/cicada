import React from 'react';
import { useLiveStore } from '@/stores/liveStore';
import { useUiStore } from '@/stores/uiStore';
import { IncidentCard } from '@/components/IncidentCard';
import { Incident } from '@/types';

export const IncidentsTab: React.FC = () => {
  const incidents = useLiveStore((s) => s.incidents);
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
