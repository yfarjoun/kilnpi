import { useState, useEffect, useRef } from 'react';
import { useStatus } from '../hooks/useStatus';
import { FiringChart } from '../components/FiringChart';
import { PowerChart } from '../components/PowerChart';
import { StatusBar } from '../components/StatusBar';
import { api } from '../api/client';
import type { Reading } from '../types';
import type { PowerDataPoint } from '../components/PowerChart';

type TimeRange = '2h' | '24h' | 'all';

// `maxPoints` on 2h/24h matches the server DEFAULT_MAX_POINTS so the preload
// payload is the same size regardless of window. "Whole run" fetches more so
// a long firing's shape stays recognizable at zoom.
const RANGES: {
  id: TimeRange;
  label: string;
  retentionMs: number | null;
  maxPoints: number;
}[] = [
  { id: '2h', label: '2h', retentionMs: 2 * 60 * 60 * 1000, maxPoints: 500 },
  { id: '24h', label: '24h', retentionMs: 24 * 60 * 60 * 1000, maxPoints: 500 },
  // retentionMs=null keeps everything from the server preload and lets live
  // appends accumulate up to BUFFER_HARD_CAP — see the live-append effects.
  { id: 'all', label: 'Whole run', retentionMs: null, maxPoints: 2000 },
];

// Hard ceiling on the in-memory arrays. Prevents the "Whole run" buffer from
// growing without bound while a long firing runs with the tab open — at 2s
// polls that would be 1800 pts/hour on top of the ~2000 preload. Recharts
// redraws the full array every tick, so an unbounded buffer janks on phones.
// When exceeded we drop the oldest 20% so there's slack before the next trim.
const BUFFER_HARD_CAP = 3000;
const BUFFER_TRIM_TO = 2400;

const RANGE_STORAGE_KEY = 'monitor.timeRange';
// Debounce preload refetch on rapid toggle (2h→24h→all mashing). Preload
// hits the Pi's single core and shouldn't queue three overlapping NTILE
// scans; the client-side `cancelled` flag only drops the stale response.
const PRELOAD_DEBOUNCE_MS = 150;

function loadRange(): TimeRange {
  try {
    const v = localStorage.getItem(RANGE_STORAGE_KEY);
    if (RANGES.some((r) => r.id === v)) return v as TimeRange;
  } catch {
    // Private-mode or storage-blocked browsers throw. Fall through.
  }
  return '2h';
}

function capBuffer<T>(next: T[]): T[] {
  return next.length > BUFFER_HARD_CAP ? next.slice(next.length - BUFFER_TRIM_TO) : next;
}

export function Monitor() {
  const status = useStatus();
  const [readings, setReadings] = useState<Reading[]>([]);
  const [powerData, setPowerData] = useState<PowerDataPoint[]>([]);
  const [paused, setPaused] = useState(false);
  const [range, setRange] = useState<TimeRange>(loadRange);

  const activeRange = RANGES.find((r) => r.id === range) ?? RANGES[0];
  const retentionMs = activeRange.retentionMs;
  // retentionMs is also needed inside the live-append effects, but we don't
  // want those effects to re-run and append a duplicate point every time
  // the user switches range. Read through a ref instead of listing it as a
  // dep.
  const retentionRef = useRef(retentionMs);
  retentionRef.current = retentionMs;

  useEffect(() => {
    try {
      localStorage.setItem(RANGE_STORAGE_KEY, range);
    } catch {
      // ignore
    }
  }, [range]);

  // Preload from the most recent firing. Server bucket-means to maxPoints,
  // so "whole run" of a long firing still returns ~2000 pts. `since` turns
  // into a server-side range filter via the COALESCE trick and the
  // (firing_id, timestamp) composite index.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const firings = await api.listFirings();
        if (cancelled || !firings.length) return;
        const since =
          activeRange.retentionMs !== null
            ? new Date(Date.now() - activeRange.retentionMs).toISOString()
            : undefined;
        const detail = await api.getFiring(firings[0].id, {
          maxPoints: activeRange.maxPoints,
          since,
        });
        if (cancelled) return;
        // Only replace if there's actually data — otherwise we'd wipe live
        // points that accumulated while the fetch was in flight (e.g. the
        // latest firing has nothing in a narrow `since` window).
        if (detail.readings.length) setReadings(detail.readings);
        if (detail.power_readings.length) {
          setPowerData(
            detail.power_readings.map((p) => ({
              time: new Date(p.timestamp).toLocaleTimeString(),
              ts: new Date(p.timestamp).getTime(),
              L1_A: Math.round(p.l1_current * 10) / 10,
              L1_W: Math.round(p.l1_power),
            })),
          );
        }
      } catch (e) {
        console.error('Monitor preload failed:', e);
      }
    }, PRELOAD_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [activeRange]);

  useEffect(() => {
    if (status && !paused) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- accumulating streaming WebSocket data
      setReadings((prev) => {
        const newReading: Reading = {
          timestamp: status.timestamp,
          pv: status.pv,
          sp: status.program_target_temp ?? status.sp,
          mv: status.mv,
          segment: status.segment,
        };
        const next = [...prev, newReading];
        const rMs = retentionRef.current;
        const trimmed =
          rMs === null
            ? next
            : next.filter((r) => new Date(r.timestamp).getTime() >= Date.now() - rMs);
        return capBuffer(trimmed);
      });
    }
  }, [status, paused]);

  useEffect(() => {
    if (status && !paused && status.l1_current !== null) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- accumulating streaming WebSocket data
      setPowerData((prev) => {
        const point: PowerDataPoint = {
          time: new Date(status.timestamp).toLocaleTimeString(),
          ts: new Date(status.timestamp).getTime(),
          L1_A: Math.round(status.l1_current! * 10) / 10,
          L1_W: Math.round(status.l1_power!),
        };
        const next = [...prev, point];
        const rMs = retentionRef.current;
        const trimmed =
          rMs === null ? next : next.filter((p) => (p.ts ?? 0) >= Date.now() - rMs);
        return capBuffer(trimmed);
      });
    }
  }, [status, paused]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Live Monitor</h2>
        <div className="flex items-center gap-4 flex-wrap">
          <StatusBar status={status} />
          <div className="inline-flex rounded-md overflow-hidden border border-gray-300 dark:border-gray-600">
            {RANGES.map((r) => (
              <button
                key={r.id}
                onClick={() => setRange(r.id)}
                className={`px-3 py-1 text-sm ${
                  range === r.id
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => setPaused(!paused)}
            className={`px-3 py-1 rounded text-sm ${
              paused
                ? 'bg-green-600 hover:bg-green-500 text-white'
                : 'bg-yellow-600 hover:bg-yellow-500 text-white'
            }`}
          >
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button
            onClick={() => { setReadings([]); setPowerData([]); }}
            className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 rounded text-sm text-gray-700 dark:text-white"
          >
            Clear Chart
          </button>
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm dark:shadow-none">
        {readings.length > 0 ? (
          <FiringChart readings={readings} height={500} />
        ) : (
          <div className="flex items-center justify-center h-[500px] text-gray-400 dark:text-gray-500">
            Waiting for data...
          </div>
        )}
      </div>

      {powerData.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 shadow-sm dark:shadow-none">
          <h3 className="text-lg font-medium mb-2">Power</h3>
          <PowerChart data={powerData} height={250} />
        </div>
      )}

      {status && status.l1_current !== null && (
        <div className="grid grid-cols-3 gap-4 text-center">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Current</div>
            <div className="text-2xl font-bold text-amber-500 dark:text-amber-400">{status.l1_current?.toFixed(1)}A</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Voltage</div>
            <div className="text-2xl font-bold text-gray-600 dark:text-gray-300">{status.l1_voltage?.toFixed(0)}V</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Power</div>
            <div className="text-2xl font-bold text-gray-600 dark:text-gray-300">{status.l1_power?.toFixed(0)}W</div>
          </div>
        </div>
      )}

      {status && (
        <div className="grid grid-cols-3 gap-4 text-center">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">PV</div>
            <div className="text-2xl font-bold text-red-500 dark:text-red-400">{status.pv.toFixed(1)}&deg;C</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">SP</div>
            <div className="text-2xl font-bold text-blue-500 dark:text-blue-400">{(status.program_target_temp ?? status.sp).toFixed(1)}&deg;C</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Output</div>
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">{status.mv.toFixed(1)}%</div>
          </div>
        </div>
      )}
    </div>
  );
}
