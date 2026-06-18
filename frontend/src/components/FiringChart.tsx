import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Brush,
} from 'recharts';
import type { Reading } from '../types';

interface FiringChartProps {
  readings: Reading[];
  height?: number;
  cutoffTimestamp?: string | null;
}

export function FiringChart({ readings, height = 400, cutoffTimestamp }: FiringChartProps) {
  const data = readings.map((r, i) => ({
    index: i,
    time: new Date(r.timestamp).toLocaleTimeString(),
    PV: Math.round(r.pv),
    // Prefer the controller's dynamic ramp target when known; fall back to
    // the static SP for old readings / non-program firings.
    SP: Math.round(r.program_target_temp ?? r.sp),
    MV: Math.round(r.mv),
  }));

  // Find the chart index corresponding to the cutoff timestamp
  let cutoffIndex: number | null = null;
  if (cutoffTimestamp) {
    const cutoffTime = new Date(cutoffTimestamp).getTime();
    for (let i = 0; i < readings.length; i++) {
      if (new Date(readings[i].timestamp).getTime() >= cutoffTime) {
        cutoffIndex = i;
        break;
      }
    }
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="time" stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="temp" stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--chart-tooltip-bg)',
            border: '1px solid var(--chart-tooltip-border)',
            borderRadius: 8,
          }}
          labelStyle={{ color: 'var(--chart-text)' }}
        />
        <Legend />
        <Line yAxisId="temp" type="basis" dataKey="PV" stroke="#EF4444" dot={false} strokeWidth={2} />
        <Line yAxisId="temp" type="basis" dataKey="SP" stroke="#3B82F6" dot={false} strokeWidth={2} strokeDasharray="5 5" />
        <Line yAxisId="pct" type="basis" dataKey="MV" stroke="#10B981" dot={false} strokeWidth={1} />
        <Brush dataKey="time" height={40} stroke="var(--chart-text)" travellerWidth={24} />
        {cutoffIndex !== null && (
          <ReferenceLine
            yAxisId="temp"
            x={data[cutoffIndex].time}
            stroke="#F59E0B"
            strokeDasharray="6 4"
            strokeWidth={2}
            label={{ value: 'Sitter', position: 'top', fill: '#F59E0B', fontSize: 12 }}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
