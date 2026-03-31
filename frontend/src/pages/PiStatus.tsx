import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { useStatus } from '../hooks/useStatus';
import type { SystemInfo } from '../types';

function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min(100, (value / max) * 100);
  const color = pct > 90 ? 'bg-red-500' : pct > 70 ? 'bg-yellow-500' : 'bg-green-500';
  return (
    <div className="w-full bg-gray-200 dark:bg-gray-700 rounded h-2">
      <div className={`${color} h-2 rounded`} style={{ width: `${pct}%` }} />
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-red-500'}`}
    />
  );
}

export function PiStatus() {
  const status = useStatus();
  const [sys, setSys] = useState<SystemInfo | null>(null);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const data = await api.getSystemInfo();
        if (active) setSys(data);
      } catch {
        /* ignore */
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  const running = status?.run_mode === 'running' || status?.run_mode === 'standby';

  // Build compact OLED-style line
  const compactLines = sys
    ? [
        `D:${sys.disk_usage_pct}% M:${sys.memory_usage_pct}% CPU:${sys.cpu_temp.toFixed(0)}C`,
        `.${sys.ip_address.split('.').pop() ?? '--'} ${sys.wifi_connected ? 'W+' : 'W-'} ${sys.ws_client_count > 0 ? 'B+' : 'B-'} ${sys.last_poll_ok ? 'MB+' : 'MB-'}`,
        sys.poll_age_sec < 0 ? 'Poll: --' : `Poll: ${sys.poll_age_sec}s ago`,
        running && status
          ? `${status.active_program_name ?? 'Program'} S${status.segment} ${status.pv.toFixed(0)}/${(status.program_target_temp ?? status.sp).toFixed(0)}`
          : 'Idle',
      ]
    : null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Pi Status</h1>

      {/* Compact OLED mirror */}
      <div className="bg-black rounded-lg p-4 font-mono text-green-400 text-sm leading-6 border border-gray-700">
        {compactLines ? (
          compactLines.map((line, i) => <div key={i}>{line}</div>)
        ) : (
          <div className="text-gray-500">Loading...</div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* System card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h2 className="font-semibold mb-3">System</h2>
          {sys ? (
            <div className="space-y-3 text-sm">
              <div>
                <div className="flex justify-between mb-1">
                  <span>Disk</span><span>{sys.disk_usage_pct}%</span>
                </div>
                <ProgressBar value={sys.disk_usage_pct} />
              </div>
              <div>
                <div className="flex justify-between mb-1">
                  <span>Memory</span><span>{sys.memory_usage_pct}%</span>
                </div>
                <ProgressBar value={sys.memory_usage_pct} />
              </div>
              <div className="flex justify-between">
                <span>CPU Temp</span><span>{sys.cpu_temp.toFixed(1)}&deg;C</span>
              </div>
              <div className="flex justify-between">
                <span>Uptime</span><span>{sys.uptime}</span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading...</p>
          )}
        </div>

        {/* Network card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h2 className="font-semibold mb-3">Network</h2>
          {sys ? (
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span>IP</span><span className="font-mono">{sys.ip_address}</span>
              </div>
              <div className="flex justify-between items-center">
                <span>WiFi</span>
                <span className="flex items-center gap-1.5">
                  <StatusDot ok={sys.wifi_connected} />
                  {sys.wifi_connected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Browsers</span><span>{sys.ws_client_count}</span>
              </div>
              <div className="flex justify-between items-center">
                <span>Modbus</span>
                <span className="flex items-center gap-1.5">
                  <StatusDot ok={sys.last_poll_ok} />
                  {sys.last_poll_ok
                    ? sys.poll_age_sec >= 0
                      ? `OK (${sys.poll_age_sec}s ago)`
                      : 'No data'
                    : 'Error'}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Loading...</p>
          )}
        </div>

        {/* Program card */}
        <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
          <h2 className="font-semibold mb-3">Program</h2>
          {status ? (
            running ? (
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span>Name</span>
                  <span>{status.active_program_name ?? 'Unknown'}</span>
                </div>
                <div className="flex justify-between">
                  <span>Segment</span><span>{status.segment}</span>
                </div>
                <div className="flex justify-between">
                  <span>PV / SP</span>
                  <span className="font-mono">
                    {status.pv.toFixed(0)} / {(status.program_target_temp ?? status.sp).toFixed(0)}&deg;C
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Elapsed</span><span>{status.segment_elapsed_min} min</span>
                </div>
                {status.run_mode === 'standby' && (
                  <div className="text-yellow-500 font-medium">PAUSED</div>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-500">Idle — no program running</p>
            )
          ) : (
            <p className="text-sm text-gray-500">Loading...</p>
          )}
        </div>
      </div>
    </div>
  );
}
