import type { Status } from '../types';

interface StatusBarProps {
  status: Status | null;
}

export function StatusBar({ status }: StatusBarProps) {
  if (!status) {
    return (
      <div className="bg-yellow-100 border border-yellow-400 text-yellow-700 dark:bg-yellow-900/50 dark:border-yellow-600 dark:text-yellow-300 px-4 py-2 rounded text-sm">
        Connecting to controller...
      </div>
    );
  }

  const isRunning = status.run_mode === 'running';

  return (
    <div className="flex items-center gap-4 text-sm">
      <div className="flex items-center gap-1">
        <span className={`w-2 h-2 rounded-full ${(status.alarm1 || status.alarm2) ? 'bg-red-500 animate-pulse' : 'bg-green-500'}`} />
        <span className="text-gray-500 dark:text-gray-400">
          {status.alarm1 && status.alarm2 ? 'AL1+AL2' : status.alarm1 ? 'AL1' : status.alarm2 ? 'AL2' : 'OK'}
        </span>
      </div>
      <div className="text-gray-500 dark:text-gray-400">
        Mode: <span className={isRunning ? 'text-green-600 dark:text-green-400' : 'text-gray-600 dark:text-gray-300'}>{status.run_mode.toUpperCase()}</span>
      </div>
      {isRunning && (
        <div className="text-gray-500 dark:text-gray-400">
          Seg {status.segment} &middot; {status.segment_elapsed_min}m &middot; Total {status.total_elapsed_min}m
        </div>
      )}
    </div>
  );
}
