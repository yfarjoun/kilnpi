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

export interface PowerDataPoint {
  time: string;
  ts?: number;  // epoch ms; used by Monitor for time-based retention, ignored by recharts
  L1_A: number;
  L1_W: number;
}

interface PowerChartProps {
  data: PowerDataPoint[];
  height?: number;
  showPower?: boolean;
}

export function PowerChart({ data, height = 250, showPower = true }: PowerChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="time" stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="amps" stroke="var(--chart-text)" tick={{ fontSize: 12 }}
          label={{ value: 'A', position: 'insideLeft', offset: -5, fill: 'var(--chart-text)' }} />
        {showPower && (
          <YAxis yAxisId="watts" orientation="right" stroke="var(--chart-text)" tick={{ fontSize: 12 }}
            label={{ value: 'W', position: 'insideRight', offset: 5, fill: 'var(--chart-text)' }} />
        )}
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--chart-tooltip-bg)',
            border: '1px solid var(--chart-tooltip-border)',
            borderRadius: 8,
          }}
          labelStyle={{ color: 'var(--chart-text)' }}
        />
        <Legend />
        <Line yAxisId="amps" type="monotone" dataKey="L1_A" name="Current"
          stroke="#F59E0B" dot={false} strokeWidth={2} />
        {showPower && (
          <Line yAxisId="watts" type="monotone" dataKey="L1_W" name="Power"
            stroke="#F59E0B" dot={false} strokeWidth={1} strokeDasharray="5 5" />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
