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
  L1_A: number;
  L2_A: number;
  L1_W: number;
  L2_W: number;
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
        <Line yAxisId="amps" type="monotone" dataKey="L1_A" name="L1 Current"
          stroke="#F59E0B" dot={false} strokeWidth={2} />
        <Line yAxisId="amps" type="monotone" dataKey="L2_A" name="L2 Current"
          stroke="#8B5CF6" dot={false} strokeWidth={2} />
        {showPower && (
          <>
            <Line yAxisId="watts" type="monotone" dataKey="L1_W" name="L1 Power"
              stroke="#F59E0B" dot={false} strokeWidth={1} strokeDasharray="5 5" />
            <Line yAxisId="watts" type="monotone" dataKey="L2_W" name="L2 Power"
              stroke="#8B5CF6" dot={false} strokeWidth={1} strokeDasharray="5 5" />
          </>
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
