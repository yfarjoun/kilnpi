import { useState, useEffect } from 'react';
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
import { api } from '../api/client';
import type { FiringSummary, HealthTrend } from '../types';

const BAND_COLORS: Record<string, string> = {
  '0-200': '#60a5fa',
  '200-400': '#34d399',
  '400-600': '#fbbf24',
  '600-800': '#fb923c',
  '800-1000': '#f87171',
  '1000+': '#c084fc',
  'Cooling': '#818cf8',
};

export function Statistics() {
  const [summary, setSummary] = useState<FiringSummary | null>(null);
  const [health, setHealth] = useState<HealthTrend[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getStatsSummary(), api.getHealthTrend()])
      .then(([s, h]) => {
        setSummary(s);
        setHealth(h);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-gray-500 dark:text-gray-400">Loading statistics...</div>;
  }

  // Build chart data: merge all bands into rows keyed by date
  const chartMap = new Map<string, Record<string, number | string>>();
  for (const trend of health) {
    for (const dp of trend.datapoints) {
      const key = dp.date;
      if (!chartMap.has(key)) {
        chartMap.set(key, { date: new Date(dp.date).toLocaleDateString() });
      }
      chartMap.get(key)![trend.band] = dp.rate;
    }
  }
  const chartData = Array.from(chartMap.values());
  const activeBands = health.map((h) => h.band);

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Kiln Statistics</h2>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 text-center shadow-sm dark:shadow-none">
            <div className="text-3xl font-bold">{summary.total_firings}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">Total Firings</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 text-center shadow-sm dark:shadow-none">
            <div className="text-3xl font-bold">{summary.total_hours}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">Total Hours</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-5 text-center shadow-sm dark:shadow-none">
            <div className="text-3xl font-bold">
              {summary.by_program.length}
            </div>
            <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">Programs Used</div>
          </div>
        </div>
      )}

      {/* By-program table */}
      {summary && summary.by_program.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <h3 className="text-lg font-medium mb-4">Firings by Program</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2">Program</th>
                <th className="text-right py-2">Firings</th>
                <th className="text-right py-2">Avg Duration (min)</th>
                <th className="text-right py-2">Avg Max Temp</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_program.map((p) => (
                <tr key={p.name} className="border-b border-gray-100 dark:border-gray-700/50">
                  <td className="py-2">{p.name}</td>
                  <td className="py-2 text-right text-gray-600 dark:text-gray-300">{p.count}</td>
                  <td className="py-2 text-right text-gray-600 dark:text-gray-300">{p.avg_duration_min}</td>
                  <td className="py-2 text-right text-gray-600 dark:text-gray-300">{p.avg_max_temp}&deg;C</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Health trend chart */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
        <h3 className="text-lg font-medium mb-4">
          Kiln Health — Heating &amp; Cooling Rate Trend
        </h3>
        {chartData.length === 0 ? (
          <div className="text-gray-400 dark:text-gray-500 text-center py-8">
            No firing data yet. Complete some firings to see health trends.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="date" stroke="var(--chart-text)" tick={{ fontSize: 12 }} />
              <YAxis
                stroke="var(--chart-text)"
                tick={{ fontSize: 12 }}
                label={{
                  value: 'Rate (\u00B0C/min)',
                  angle: -90,
                  position: 'insideLeft',
                  fill: 'var(--chart-text)',
                  fontSize: 12,
                }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--chart-tooltip-bg)',
                  border: '1px solid var(--chart-tooltip-border)',
                  borderRadius: 8,
                }}
                labelStyle={{ color: 'var(--chart-text)' }}
              />
              <Legend />
              {activeBands.map((band) => (
                <Line
                  key={band}
                  type="monotone"
                  dataKey={band}
                  stroke={BAND_COLORS[band] || '#888'}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
          Declining heating rates indicate element degradation. Each line represents a
          temperature band. The Cooling line tracks overall cooling rate from peak temperature.
        </p>
      </div>
    </div>
  );
}
