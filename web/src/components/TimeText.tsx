import React from 'react';
import { useUiStore } from '../stores/uiStore';
import { TzMode } from '../types';

interface TimeTextProps {
  timestamp: string | number | Date;
  sourceTz?: string; // e.g. "Asia/Kolkata", "Europe/Berlin"
  className?: string;
  showSeconds?: boolean;
}

// One place that turns an instant into a clock string for the chosen zone, so text, charts and incident paths always agree.
export function formatClock(timestamp: string | number | Date, mode: TzMode, sourceTz?: string, showSeconds = true): string {
  const date = new Date(timestamp);
  if (isNaN(date.getTime())) return '--:--:--';
  const opts: Intl.DateTimeFormatOptions = { hour12: false, hour: '2-digit', minute: '2-digit', second: showSeconds ? '2-digit' : undefined };
  if (mode === 'UTC') return date.toISOString().substring(11, showSeconds ? 19 : 16) + 'Z';
  if (mode === 'SHOP' && sourceTz) {
    try {
      return date.toLocaleTimeString('en-GB', { ...opts, timeZone: sourceTz }) + (sourceTz.includes('Kolkata') ? ' IST' : ' CET');
    } catch { /* unknown zone name: fall through to the viewer's zone */ }
  }
  return date.toLocaleTimeString('en-GB', opts) + ' LOCAL';
}

export const TimeText: React.FC<TimeTextProps> = ({ timestamp, sourceTz, className = '', showSeconds = true }) => {
  const tzMode = useUiStore((s) => s.tzMode);
  const date = new Date(timestamp);
  return (
    <span className={`font-mono tabular-nums text-slate-300 ${className}`} title={isNaN(date.getTime()) ? '' : date.toISOString()}>
      {formatClock(timestamp, tzMode, sourceTz, showSeconds)}
    </span>
  );
};
