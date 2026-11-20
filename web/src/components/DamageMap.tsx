import React, { useEffect, useState } from 'react';
import { api } from '../services/apiClient';

type Node = { id: string; state: 'ok' | 'impacted' | 'affected' };
const POS: Record<string, [number, number]> = { host: [50, 40], 'shop-api': [170, 40], login: [290, 15], checkout: [290, 55], db: [290, 95] };
const FILL = { ok: '#10B981', impacted: '#F59E0B', affected: '#EF4444' };

// Per-tenant topology from GET /api/damage-map/{tenant}: affected = red, impacted dependents = amber.
export const DamageMap: React.FC<{ tenant: string }> = ({ tenant }) => {
  const [map, setMap] = useState<{ nodes: Node[]; edges: { from: string; to: string }[] }>({ nodes: [], edges: [] });
  useEffect(() => {
    let live = true;
    const load = () => api.getDamageMap(tenant).then((m) => live && setMap(m)).catch(() => {});
    load();
    const id = setInterval(load, 2000);
    return () => { live = false; clearInterval(id); };
  }, [tenant]);
  const st = Object.fromEntries(map.nodes.map((n) => [n.id, n.state]));
  return (
    <div className="hud-panel p-3">
      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-400 font-bold">DAMAGE MAP · {tenant.toUpperCase()}</span>
      <svg viewBox="0 0 340 110" className="w-full mt-2">
        {map.edges.map((e) => POS[e.from] && POS[e.to] && (
          <line key={e.from + e.to} x1={POS[e.from][0] + 28} y1={POS[e.from][1]} x2={POS[e.to][0] - 28} y2={POS[e.to][1]} stroke="#475569" strokeWidth="1.5" />
        ))}
        {map.nodes.map((n) => POS[n.id] && (
          <g key={n.id}>
            <rect x={POS[n.id][0] - 28} y={POS[n.id][1] - 12} width="56" height="24" rx="5" fill={FILL[st[n.id] || 'ok']} fillOpacity="0.2" stroke={FILL[st[n.id] || 'ok']} strokeWidth="1.5" />
            <text x={POS[n.id][0]} y={POS[n.id][1] + 4} textAnchor="middle" fontSize="10" fill="#E2E8F0" fontFamily="monospace">{n.id}</text>
          </g>
        ))}
      </svg>
    </div>
  );
};
