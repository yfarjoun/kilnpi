import { useState, useEffect } from 'react';
import { useStatus } from '../hooks/useStatus';
import { FiringChart } from '../components/FiringChart';
import { PowerChart } from '../components/PowerChart';
import { StatusBar } from '../components/StatusBar';
import { api } from '../api/client';
import type { Reading } from '../types';
import type { PowerDataPoint } from '../components/PowerChart';

export function Monitor() {
  const status = useStatus();
  const [readings, setReadings] = useState<Reading[]>([]);
  const [powerData, setPowerData] = useState<PowerDataPoint[]>([]);
  const [paused, setPaused] = useState(false);
  // Time-based retention: keep the last 2 hours of points regardless of
  // how fast the websocket broadcasts. The chart's brush at the bottom
  // lets you zoom to any sub-range. For a full firing's worth of
  // history, use the History tab.
  const retentionMs = 2 * 60 * 60 * 1000;

  // On mount, back-fill the buffer from the most recent firing's
  // persisted readings so you don't stare at an empty chart while live
  // data trickles in.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const firings = await api.listFirings();
        if (!firings.length) return;
        const detail = await api.getFiring(firings[0].id);
        if (cancelled) return;
        const cutoff = Date.now() - retentionMs;
        const recentReadings = detail.readings.filter(
          (r) => new Date(r.timestamp).getTime() >= cutoff,
        );
        if (recentReadings.length) setReadings(recentReadings);
        const recentPower: PowerDataPoint[] = detail.power_readings
          .filter((p) => new Date(p.timestamp).getTime() >= cutoff)
          .map((p) => ({
            time: new Date(p.timestamp).toLocaleTimeString(),
            ts: new Date(p.timestamp).getTime(),
            L1_A: Math.round(p.l1_current * 10) / 10,
            L1_W: Math.round(p.l1_power),
          }));
        if (recentPower.length) setPowerData(recentPower);
      } catch (e) {
        console.error('Monitor preload failed:', e);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one-shot mount preload
  }, []);

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
        const cutoff = Date.now() - retentionMs;
        return [...prev, newReading].filter((r) => new Date(r.timestamp).getTime() >= cutoff);
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
        const cutoff = Date.now() - retentionMs;
        return [...prev, point].filter((p) => (p.ts ?? 0) >= cutoff);
      });
    }
  }, [status, paused]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Live Monitor</h2>
        <div className="flex items-center gap-4">
          <StatusBar status={status} />
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
        <div className="grid grid-cols-4 gap-4 text-center">
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
