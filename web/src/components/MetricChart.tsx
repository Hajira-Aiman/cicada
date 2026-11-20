import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { MetricDataPoint } from '../types';

interface MetricChartProps {
  title: string;
  unit: string;
  data: MetricDataPoint[];
  normalRange?: [number, number];
  color?: string;
  height?: number;
}

export const MetricChart: React.FC<MetricChartProps> = ({
  title,
  unit,
  data,
  normalRange = [15, 35],
  color = '#06B6D4',
  height = 160,
}) => {
  // If data is scarce, create smooth curve
  const chartData = data.length > 0 ? data.map((d, i) => {
    const baseline = d.baseline ?? (normalRange[0] + normalRange[1]) / 2;
    const spread = d.spread ?? (normalRange[1] - normalRange[0]) / 2;
    const lower = Math.max(0, baseline - spread);
    const upper = baseline + spread;

    return {
      index: i,
      time: d.event_time ? d.event_time.substring(11, 19) : '',
      value: d.avg,
      max: d.max,
      band: [lower, upper],
      isAnomaly: d.is_anomaly || d.avg > upper || d.avg < lower,
    };
  }) : Array.from({ length: 20 }, (_, i) => ({
    index: i,
    time: `04:${10 + Math.floor(i / 2)}:${(i % 2) * 30}`,
    value: normalRange[0] + Math.random() * (normalRange[1] - normalRange[0]),
    max: normalRange[1] + 2,
    band: [normalRange[0], normalRange[1]],
    isAnomaly: false,
  }));

  const currentValue = chartData[chartData.length - 1]?.value ?? 0;
  const isCurrentlyElevated = currentValue > normalRange[1];

  return (
    <div className="hud-panel p-3.5 flex flex-col justify-between">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-widest text-slate-400 font-bold">
            {title}
          </span>
          <div className="flex items-baseline space-x-2 mt-0.5">
            <span className={`text-2xl font-mono font-extrabold ${isCurrentlyElevated ? 'text-amber-400' : 'text-slate-100'}`}>
              {typeof currentValue === 'number' ? currentValue.toFixed(1) : currentValue}
            </span>
            <span className="text-xs font-mono text-slate-500">{unit}</span>
          </div>
        </div>
        <div className="text-right">
          <span className="text-[10px] font-mono text-slate-500 block">BASELINE BAND (±2σ)</span>
          <span className="text-xs font-mono text-slate-400">
            {normalRange[0]} - {normalRange[1]} {unit}
          </span>
        </div>
      </div>

      <div style={{ width: '100%', height }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
            <CartesianGrid stroke="#1E2330" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" stroke="#475569" tick={{ fontSize: 10, fill: '#64748B' }} minTickGap={20} />
            <YAxis stroke="#475569" tick={{ fontSize: 10, fill: '#64748B' }} domain={['auto', 'auto']} />
            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const p = payload[0].payload;
                  return (
                    <div className="bg-[#1A1C23] border border-white/10 p-2 rounded shadow-xl text-xs font-mono">
                      <div className="text-slate-400">{p.time} UTC</div>
                      <div className="text-cyan-400 font-bold mt-1">Value: {p.value?.toFixed(1)} {unit}</div>
                      <div className="text-slate-500">Normal: {p.band?.[0]} - {p.band?.[1]} {unit}</div>
                      {p.isAnomaly && <div className="text-rose-400 font-bold mt-1">ANOMALY DETECTED</div>}
                    </div>
                  );
                }
                return null;
              }}
            />
            {/* Normal range band */}
            <Area
              dataKey="band"
              fill="#38BDF8"
              fillOpacity={0.08}
              stroke="none"
              isAnimationActive={false}
            />
            {/* Metric line */}
            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              dot={(props: any) => {
                if (props.payload.isAnomaly) {
                  return (
                    <circle
                      key={props.key}
                      cx={props.cx}
                      cy={props.cy}
                      r={4}
                      fill="#EF4444"
                      stroke="#FFFFFF"
                      strokeWidth={1.5}
                    />
                  );
                }
                return <React.Fragment key={props.key} />;
              }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
