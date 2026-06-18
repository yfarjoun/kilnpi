import { useState, useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush,
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

// Simple centered moving average over `window` points. Smooths fast PZEM jitter
// before the chart renders so the lines look like actual averages rather than
// staircase steps. Returns a new array with smoothed L1_A / L1_W; non-numeric
// fields are copied through unchanged.
function movingAverage(data: PowerDataPoint[], window: number): PowerDataPoint[] {
  if (window < 2 || data.length === 0) return data;
  const half = Math.floor(window / 2);
  return data.map((_, i) => {
    let aSum = 0, wSum = 0, n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(data.length - 1, i + half); j++) {
      aSum += data[j].L1_A;
      wSum += data[j].L1_W;
      n += 1;
    }
    return {
      ...data[i],
      L1_A: aSum / n,
      L1_W: wSum / n,
    };
  });
}

export function PowerChart({ data, height = 250, showPower = true }: PowerChartProps) {
  // Pre-smooth the data so the chart lines aren't dominated by PZEM-cycle noise.
  const smoothed = useMemo(() => movingAverage(data, 5), [data]);
  // Persist brush range across renders so new datapoints don't reset the zoom.
  const [brushRange, setBrushRange] = useState<{ startIndex?: number; endIndex?: number }>({});
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={smoothed}>
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
        <Line yAxisId="amps" type="basis" dataKey="L1_A" name="Current"
          stroke="#F59E0B" dot={false} strokeWidth={2} isAnimationActive={false} />
        {showPower && (
          <Line yAxisId="watts" type="basis" dataKey="L1_W" name="Power"
            stroke="#F59E0B" dot={false} strokeWidth={1} strokeDasharray="5 5" isAnimationActive={false} />
        )}
        <Brush
          dataKey="time"
          height={40}
          stroke="var(--chart-text)"
          travellerWidth={24}
          startIndex={brushRange.startIndex}
          endIndex={brushRange.endIndex}
          onChange={(range: { startIndex?: number; endIndex?: number }) =>
            setBrushRange({ startIndex: range.startIndex, endIndex: range.endIndex })
          }
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
