import { useMemo, useState } from 'react';
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

// Centered moving average over a 1-D array of numbers.
function movingAvgArr(values: number[], window: number): number[] {
  if (window < 2 || values.length === 0) return values;
  const half = Math.floor(window / 2);
  return values.map((_, i) => {
    let sum = 0, n = 0;
    for (let j = Math.max(0, i - half); j <= Math.min(values.length - 1, i + half); j++) {
      sum += values[j];
      n += 1;
    }
    return sum / n;
  });
}

export function FiringChart({ readings, height = 400, cutoffTimestamp }: FiringChartProps) {
  // Persist brush range across renders so live data updates don't reset zoom.
  const [brushRange, setBrushRange] = useState<{ startIndex?: number; endIndex?: number }>({});

  // Smooth only the MV (output) line — it's wildly bipolar because every
  // poll samples the SSR's bang-bang duty cycle at a random instant.
  // PV/SP are temperatures: actual smooth signals, leave them alone.
  const data = useMemo(() => {
    const smoothedMV = movingAvgArr(
      readings.map((r) => r.mv),
      30,
    );
    return readings.map((r, i) => ({
      index: i,
      time: new Date(r.timestamp).toLocaleTimeString(),
      PV: Math.round(r.pv),
      // Prefer the controller's dynamic ramp target when known; fall back to
      // the static SP for old readings / non-program firings.
      SP: Math.round(r.program_target_temp ?? r.sp),
      MV: Math.round(smoothedMV[i]),
    }));
  }, [readings]);

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
        <Line yAxisId="temp" type="basis" dataKey="PV" stroke="#EF4444" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line yAxisId="temp" type="basis" dataKey="SP" stroke="#3B82F6" dot={false} strokeWidth={2} strokeDasharray="5 5" isAnimationActive={false} />
        <Line yAxisId="pct" type="basis" dataKey="MV" stroke="#10B981" dot={false} strokeWidth={1} isAnimationActive={false} />
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
