import React from 'react';
import { HealthState, SeverityLevel } from '../types';

interface StatusBadgeProps {
  status: HealthState | SeverityLevel | 'MATCH' | 'MISMATCH' | 'STORED' | 'DUPLICATE' | 'REJECTED' | 'PAUSED' | 'ACTIVE';
  label?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, className = '' }) => {
  const normalized = status.toUpperCase();
  let colorClass = 'bg-slate-500/10 text-slate-400 border-slate-500/20';

  switch (normalized) {
    case 'EXCELLENT':
    case 'MATCH':
    case 'STORED':
    case 'ACTIVE':
      colorClass = 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      break;
    case 'GOOD':
    case 'INFO':
    case 'LOW':
      colorClass = 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
      break;
    case 'FAIR':
    case 'MEDIUM':
    case 'PAUSED':
      colorClass = 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      break;
    case 'HIGH':
      colorClass = 'bg-orange-500/10 text-orange-400 border-orange-500/20';
      break;
    case 'POOR':
    case 'CRITICAL':
    case 'MISMATCH':
    case 'REJECTED':
      colorClass = 'bg-rose-500/10 text-rose-400 border-rose-500/20';
      break;
    case 'OFFLINE':
    case 'DUPLICATE':
    default:
      colorClass = 'bg-slate-500/10 text-slate-400 border-slate-500/20';
      break;
  }

  const text = label || (
    normalized === 'MATCH' ? '✓ MATCH' :
    normalized === 'MISMATCH' ? '✕ MISMATCH' :
    normalized
  );

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold tracking-wider border ${colorClass} ${className}`}
    >
      {text}
    </span>
  );
};
