import { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { PIDParams } from '../types';

export function Settings() {
  const [pid, setPid] = useState<PIDParams | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api.getPID()
      .then(setPid)
      .catch((err) => {
        console.error('Failed to load PID:', err);
        setError('Failed to load PID parameters from controller');
      });
  }, []);

  const savePID = async () => {
    if (!pid) return;
    setSaving(true);
    setMessage('');
    try {
      await api.setPID(pid);
      setMessage('PID parameters saved');
    } catch {
      setMessage('Failed to save PID parameters');
    } finally {
      setSaving(false);
    }
  };

  const handleAutotune = async () => {
    if (!confirm('Start auto-tuning? This will temporarily disrupt temperature control.')) return;
    await api.startAutotune();
    setMessage('Auto-tuning started');
  };

  if (error) {
    return <div className="text-red-500">{error}</div>;
  }

  if (!pid) {
    return <div className="text-gray-500 dark:text-gray-400">Loading settings...</div>;
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold">Settings</h2>

      {/* PID Parameters */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 space-y-4 shadow-sm dark:shadow-none">
        <h3 className="text-lg font-medium">PID Parameters</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">P (Proportional)</label>
            <input
              type="number"
              value={pid.p}
              onChange={(e) => setPid({ ...pid, p: Number(e.target.value) })}
              className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">I (Integral)</label>
            <input
              type="number"
              value={pid.i}
              onChange={(e) => setPid({ ...pid, i: Number(e.target.value) })}
              className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">D (Derivative)</label>
            <input
              type="number"
              value={pid.d}
              onChange={(e) => setPid({ ...pid, d: Number(e.target.value) })}
              className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">Cycle Time (s)</label>
            <input
              type="number"
              value={pid.cycle_time}
              onChange={(e) => setPid({ ...pid, cycle_time: Number(e.target.value) })}
              className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
            />
          </div>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={savePID}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-300 dark:disabled:bg-gray-700 rounded text-sm text-white"
          >
            {saving ? 'Saving...' : 'Save PID'}
          </button>
          {message && <span className="text-sm text-green-600 dark:text-green-400">{message}</span>}
        </div>
      </div>

      {/* Auto-tune */}
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 space-y-4 shadow-sm dark:shadow-none">
        <h3 className="text-lg font-medium">Auto-Tune</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Auto-tuning will automatically determine optimal PID parameters for your kiln.
          The process temporarily disrupts temperature control.
        </p>
        <button
          onClick={handleAutotune}
          className="px-4 py-2 bg-amber-600 hover:bg-amber-500 rounded text-sm text-white"
        >
          Start Auto-Tune
        </button>
      </div>
    </div>
  );
}
