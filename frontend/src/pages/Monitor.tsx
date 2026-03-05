import { useState, useEffect } from 'react';
import { useStatus } from '../hooks/useStatus';
import { FiringChart } from '../components/FiringChart';
import { StatusBar } from '../components/StatusBar';
import type { Reading } from '../types';

export function Monitor() {
  const status = useStatus();
  const [readings, setReadings] = useState<Reading[]>([]);
  const [paused, setPaused] = useState(false);
  const maxPoints = 500;

  useEffect(() => {
    if (status && !paused) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- accumulating streaming WebSocket data
      setReadings((prev) => {
        const newReading: Reading = {
          timestamp: status.timestamp,
          pv: status.pv,
          sp: status.sp,
          mv: status.mv,
          segment: status.segment,
        };
        const updated = [...prev, newReading];
        return updated.length > maxPoints ? updated.slice(-maxPoints) : updated;
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
            onClick={() => setReadings([])}
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

      {status && (
        <div className="grid grid-cols-4 gap-4 text-center">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">PV</div>
            <div className="text-2xl font-bold text-red-500 dark:text-red-400">{status.pv.toFixed(1)}&deg;C</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">SP</div>
            <div className="text-2xl font-bold text-blue-500 dark:text-blue-400">{status.sp.toFixed(1)}&deg;C</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Output</div>
            <div className="text-2xl font-bold text-green-600 dark:text-green-400">{status.mv.toFixed(1)}%</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg p-3 shadow-sm dark:shadow-none">
            <div className="text-sm text-gray-500 dark:text-gray-400">Points</div>
            <div className="text-2xl font-bold text-gray-600 dark:text-gray-300">{readings.length}</div>
          </div>
        </div>
      )}
    </div>
  );
}
