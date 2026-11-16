import { useEffect, useMemo, useRef, useState } from 'react';
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

// Switch tooltips/axis to include the date when the visible span crosses a
// day boundary; otherwise just show the time of day so a short window stays
// compact.
const DAY_MS = 24 * 60 * 60 * 1000;

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString();
}

function formatDateTime(ts: number): string {
  return new Date(ts).toLocaleString();
}

export function FiringChart({ readings, height = 400, cutoffTimestamp }: FiringChartProps) {
  // Persist brush selection as (tsStart, tsEnd) across data-shape changes.
  // Storing raw array indices would silently alias to different timestamps
  // whenever the readings array is swapped (range change) or trimmed
  // (capBuffer, live append + retention). Mapping back to indices each
  // render keeps the user's zoom pointing at the same real-time window.
  const [brushBounds, setBrushBounds] = useState<{ start?: number; end?: number }>({});

  // Track whether the user has an active zoom — if they haven't touched the
  // brush, we leave it undefined so Recharts renders the default "follow all
  // data" view instead of pinning to a stale sub-range.
  const userZoomed = useRef(false);

  // Reset the zoom when the shape of the data changes drastically (e.g. the
  // range selector swapped in a new preload). A size change by 50% or more
  // is a reliable signal; incremental live appends stay far below that.
  const lastLenRef = useRef(readings.length);
  useEffect(() => {
    const prev = lastLenRef.current;
    const next = readings.length;
    if (prev > 0 && (next < prev * 0.5 || next > prev * 2)) {
      setBrushBounds({});
      userZoomed.current = false;
    }
    lastLenRef.current = next;
  }, [readings.length]);

  const data = useMemo(
    () =>
      readings.map((r) => ({
        // Unix ms used by the time-scale XAxis so each point lands at its real
        // moment. With the old category axis, live-appended points (2–5s
        // apart) got the same horizontal slot as preload buckets (~65s
        // apart), making new points land as visible jumps at the right edge.
        ts: new Date(r.timestamp).getTime(),
        PV: Math.round(r.pv),
        // Prefer the controller's dynamic ramp target when known; fall back
        // to the static SP for old readings and non-program firings.
        SP: Math.round(r.program_target_temp ?? r.sp),
        MV: Math.round(r.mv),
      })),
    [readings],
  );

  // Pick axis/tooltip formatter based on span. A single day of a firing is
  // the common case; a multi-day Whole-Run view (or a firing that ran past
  // midnight) needs the date to disambiguate "9:54 PM".
  const spanMs = data.length > 1 ? data[data.length - 1].ts - data[0].ts : 0;
  const multiDay = spanMs > DAY_MS;
  const tsTickFormatter = (ts: number) =>
    multiDay ? new Date(ts).toLocaleDateString() : formatTime(ts);
  const tooltipLabelFormatter = (label: unknown) =>
    multiDay ? formatDateTime(Number(label)) : formatTime(Number(label));

  // Memoized cutoff lookup: without this, the linear scan runs on every
  // live-tick render even when nothing relevant changed.
  const cutoffIndex = useMemo(() => {
    if (!cutoffTimestamp) return null;
    const target = new Date(cutoffTimestamp).getTime();
    for (let i = 0; i < data.length; i++) {
      if (data[i].ts >= target) return i;
    }
    return null;
  }, [data, cutoffTimestamp]);

  // Map persisted ts bounds → current indices. Clamp to the array edges so
  // a shrunk buffer can't leave the brush pointing past the end.
  const { startIndex, endIndex } = useMemo(() => {
    if (!userZoomed.current || data.length === 0) return { startIndex: undefined, endIndex: undefined };
    const findIndex = (ts: number | undefined, fallback: number) => {
      if (ts === undefined) return fallback;
      // Binary search since data is time-ordered.
      let lo = 0;
      let hi = data.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >>> 1;
        if (data[mid].ts < ts) lo = mid + 1;
        else hi = mid;
      }
      return lo;
    };
    return {
      startIndex: Math.max(0, findIndex(brushBounds.start, 0)),
      endIndex: Math.min(data.length - 1, findIndex(brushBounds.end, data.length - 1)),
    };
  }, [brushBounds, data]);

  const onBrushChange = (range: { startIndex?: number; endIndex?: number }) => {
    if (range.startIndex === undefined || range.endIndex === undefined) return;
    userZoomed.current = true;
    setBrushBounds({
      start: data[range.startIndex]?.ts,
      end: data[range.endIndex]?.ts,
    });
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis
          dataKey="ts"
          type="number"
          domain={['dataMin', 'dataMax']}
          scale="time"
          tickFormatter={tsTickFormatter}
          stroke="var(--chart-text)"
          tick={{ fontSize: 12 }}
        />
        <YAxis yAxisId="temp" stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
        <Tooltip
          contentStyle={{
            backgroundColor: 'var(--chart-tooltip-bg)',
            border: '1px solid var(--chart-tooltip-border)',
            borderRadius: 8,
          }}
          labelStyle={{ color: 'var(--chart-text)' }}
          labelFormatter={tooltipLabelFormatter}
        />
        <Legend />
        {/* monotone respects x spacing and passes through the points, so an
            uneven time axis (preload ~65s buckets abutting 2s live samples)
            doesn't produce the kinked under/overshoot that "basis" gives. */}
        <Line yAxisId="temp" type="monotone" dataKey="PV" stroke="#EF4444" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line yAxisId="temp" type="monotone" dataKey="SP" stroke="#3B82F6" dot={false} strokeWidth={2} strokeDasharray="5 5" isAnimationActive={false} />
        <Line yAxisId="pct" type="monotone" dataKey="MV" stroke="#10B981" dot={false} strokeWidth={1} isAnimationActive={false} />
        <Brush
          dataKey="ts"
          height={40}
          stroke="var(--chart-text)"
          travellerWidth={24}
          tickFormatter={tsTickFormatter}
          startIndex={startIndex}
          endIndex={endIndex}
          onChange={onBrushChange}
        />
        {cutoffIndex !== null && (
          <ReferenceLine
            yAxisId="temp"
            x={data[cutoffIndex].ts}
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
