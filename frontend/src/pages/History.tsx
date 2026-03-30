import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { FiringChart } from '../components/FiringChart';
import { PowerChart } from '../components/PowerChart';
import type { PowerDataPoint } from '../components/PowerChart';
import type { Firing, FiringDetail, FiringStats } from '../types';

export function History() {
  const [firings, setFirings] = useState<Firing[]>([]);
  const [selected, setSelected] = useState<FiringDetail | null>(null);
  const [stats, setStats] = useState<FiringStats | null>(null);
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);

  const loadFirings = () => {
    api.listFirings().then(setFirings).finally(() => setLoading(false));
  };

  useEffect(() => {
    loadFirings();
  }, []);

  const viewFiring = async (id: number) => {
    const [detail, firingStats] = await Promise.all([
      api.getFiring(id),
      api.getFiringStats(id),
    ]);
    setSelected(detail);
    setStats(firingStats);
    setNotes(detail.firing.notes || '');
  };

  const handleBack = () => {
    setSelected(null);
    setStats(null);
  };

  const handleSaveNotes = async () => {
    if (!selected) return;
    const updated = await api.updateFiringNotes(selected.firing.id, notes);
    setSelected({ ...selected, firing: updated });
    setFirings((prev) =>
      prev.map((f) => (f.id === updated.id ? updated : f)),
    );
  };

  const handleDeleteFiring = async (id: number) => {
    if (!window.confirm('Delete this firing and all its readings?')) return;
    await api.deleteFiring(id);
    if (selected?.firing.id === id) {
      setSelected(null);
      setStats(null);
    }
    setFirings((prev) => prev.filter((f) => f.id !== id));
  };

  if (loading) {
    return <div className="text-gray-500 dark:text-gray-400">Loading history...</div>;
  }

  if (selected) {
    const f = selected.firing;
    return (
      <div className="space-y-4">
        <button
          onClick={handleBack}
          className="text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 text-sm"
        >
          &larr; Back to list
        </button>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-lg font-semibold">
              {f.program_name || `Firing #${f.id}`}
            </h3>
            <button
              onClick={() => handleDeleteFiring(f.id)}
              className="px-3 py-1 bg-red-100 hover:bg-red-200 dark:bg-red-900 dark:hover:bg-red-800 text-red-700 dark:text-red-300 rounded text-sm"
            >
              Delete
            </button>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4">
            <div>
              <span className="text-gray-500 dark:text-gray-400">Started:</span>{' '}
              <span>{new Date(f.started_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Ended:</span>{' '}
              <span>
                {f.ended_at ? new Date(f.ended_at).toLocaleString() : 'In progress'}
              </span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Status:</span>{' '}
              <span className={f.status === 'completed' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}>
                {f.status}
              </span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Readings:</span>{' '}
              <span>{selected.readings.length}</span>
            </div>
          </div>
          {stats && stats.cutoff_timestamp && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm mb-4 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-3">
              <div>
                <span className="text-gray-500 dark:text-gray-400">Total duration:</span>{' '}
                <span>{stats.duration_min} min</span>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Active (before sitter):</span>{' '}
                <span className="font-medium text-amber-700 dark:text-amber-400">
                  {stats.active_duration_min} min
                </span>
              </div>
              <div>
                <span className="text-gray-500 dark:text-gray-400">Sitter tripped:</span>{' '}
                <span>{new Date(stats.cutoff_timestamp).toLocaleTimeString()}</span>
              </div>
            </div>
          )}
          <div className="flex gap-2 mb-4">
            <a
              href={`/api/firings/${f.id}/csv`}
              className="inline-block px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 rounded text-sm"
            >
              Download CSV
            </a>
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={handleSaveNotes}
            placeholder="Add notes about this firing..."
            rows={3}
            className="w-full p-3 border rounded-lg text-sm bg-white dark:bg-gray-700 dark:border-gray-600 dark:text-gray-200 mb-4 resize-y"
          />
          {selected.readings.length > 0 ? (
            <FiringChart
              readings={selected.readings}
              height={400}
              cutoffTimestamp={stats?.cutoff_timestamp}
            />
          ) : (
            <div className="text-gray-400 dark:text-gray-500 text-center py-8">No readings recorded</div>
          )}
          {selected.power_readings && selected.power_readings.length > 0 && (
            <div className="mt-4">
              <h4 className="text-md font-medium mb-2">Power</h4>
              <PowerChart
                data={selected.power_readings.map((pr): PowerDataPoint => ({
                  time: new Date(pr.timestamp).toLocaleTimeString(),
                  L1_A: Math.round(pr.l1_current * 10) / 10,
                  L2_A: Math.round(pr.l2_current * 10) / 10,
                  L1_W: Math.round(pr.l1_power),
                  L2_W: Math.round(pr.l2_power),
                }))}
                height={250}
              />
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">Firing History</h2>
      {firings.length === 0 ? (
        <div className="text-gray-400 dark:text-gray-500 text-center py-8">No firings recorded yet.</div>
      ) : (
        <div className="space-y-2">
          {firings.map((f) => (
            <div
              key={f.id}
              onClick={() => viewFiring(f.id)}
              className="bg-white dark:bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750 flex items-center justify-between shadow-sm dark:shadow-none"
            >
              <div className="min-w-0 flex-1">
                <div className="font-medium">
                  {f.program_name || `Firing #${f.id}`}
                </div>
                <div className="text-sm text-gray-500 dark:text-gray-400">
                  {new Date(f.started_at).toLocaleString()}
                  {f.ended_at && (
                    <>
                      {' '}
                      &rarr; {new Date(f.ended_at).toLocaleString()}
                    </>
                  )}
                </div>
                {f.notes && (
                  <div className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">
                    {f.notes}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 ml-4 shrink-0">
                <span
                  className={`px-2 py-1 rounded text-xs ${
                    f.status === 'completed'
                      ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                      : f.status === 'running'
                      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300'
                      : 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
                  }`}
                >
                  {f.status}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteFiring(f.id);
                  }}
                  className="p-1 text-gray-400 hover:text-red-500 dark:text-gray-500 dark:hover:text-red-400 text-sm"
                  title="Delete firing"
                >
                  &times;
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
