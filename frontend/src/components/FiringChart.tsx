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
    PV: r.pv,
    SP: r.sp,
    MV: r.mv,
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
        <Line yAxisId="temp" type="monotone" dataKey="PV" stroke="#EF4444" dot={false} strokeWidth={2} />
        <Line yAxisId="temp" type="monotone" dataKey="SP" stroke="#3B82F6" dot={false} strokeWidth={2} strokeDasharray="5 5" />
        <Line yAxisId="pct" type="monotone" dataKey="MV" stroke="#10B981" dot={false} strokeWidth={1} />
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
