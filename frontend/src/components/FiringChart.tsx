import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { Reading } from '../types';

interface FiringChartProps {
  readings: Reading[];
  height?: number;
}

export function FiringChart({ readings, height = 400 }: FiringChartProps) {
  const data = readings.map((r, i) => ({
    index: i,
    time: new Date(r.timestamp).toLocaleTimeString(),
    PV: r.pv,
    SP: r.sp,
    MV: r.mv,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
        <XAxis dataKey="time" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="temp" stroke="#9CA3AF" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} stroke="#9CA3AF" tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
          labelStyle={{ color: '#9CA3AF' }}
        />
        <Legend />
        <Line yAxisId="temp" type="monotone" dataKey="PV" stroke="#EF4444" dot={false} strokeWidth={2} />
        <Line yAxisId="temp" type="monotone" dataKey="SP" stroke="#3B82F6" dot={false} strokeWidth={2} strokeDasharray="5 5" />
        <Line yAxisId="pct" type="monotone" dataKey="MV" stroke="#10B981" dot={false} strokeWidth={1} />
      </LineChart>
    </ResponsiveContainer>
  );
}
