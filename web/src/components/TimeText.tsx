import React from 'react';
import { useUiStore } from '../stores/uiStore';

interface TimeTextProps {
  timestamp: string | number | Date;
  sourceTz?: string; // e.g. "Asia/Kolkata", "Europe/Berlin"
  className?: string;
  showSeconds?: boolean;
}

export const TimeText: React.FC<TimeTextProps> = ({
  timestamp,
  sourceTz,
  className = '',
  showSeconds = true,
}) => {
  const tzMode = useUiStore((s) => s.tzMode);
  const date = new Date(timestamp);

  if (isNaN(date.getTime())) {
    return <span className={`font-mono ${className}`}>--:--:--</span>;
  }

  let formatted = '';
  let suffix = '';

  if (tzMode === 'UTC') {
    formatted = date.toISOString().replace('T', ' ').substring(11, showSeconds ? 19 : 16);
    suffix = 'Z';
  } else if (tzMode === 'SHOP' && sourceTz) {
    try {
      formatted = date.toLocaleTimeString('en-GB', {
        timeZone: sourceTz,
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: showSeconds ? '2-digit' : undefined,
      });
      suffix = sourceTz.includes('Kolkata') ? ' IST' : ' CET';
    } catch {
      formatted = date.toLocaleTimeString('en-GB', { hour12: false });
      suffix = ' LOCAL';
    }
  } else {
    // VIEWER (local browser time)
    formatted = date.toLocaleTimeString('en-GB', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: showSeconds ? '2-digit' : undefined,
    });
    suffix = ' LOCAL';
  }

  return (
    <span className={`font-mono tabular-nums text-slate-300 ${className}`} title={date.toISOString()}>
      {formatted}{suffix}
    </span>
  );
};
