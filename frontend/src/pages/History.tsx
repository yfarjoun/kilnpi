import { useState, useEffect } from 'react';
import { api } from '../api/client';
import { FiringChart } from '../components/FiringChart';
import type { Firing, FiringDetail } from '../types';

export function History() {
  const [firings, setFirings] = useState<Firing[]>([]);
  const [selected, setSelected] = useState<FiringDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listFirings().then(setFirings).finally(() => setLoading(false));
  }, []);

  const viewFiring = async (id: number) => {
    const detail = await api.getFiring(id);
    setSelected(detail);
  };

  if (loading) {
    return <div className="text-gray-400">Loading history...</div>;
  }

  if (selected) {
    const f = selected.firing;
    return (
      <div className="space-y-4">
        <button
          onClick={() => setSelected(null)}
          className="text-blue-400 hover:text-blue-300 text-sm"
        >
          &larr; Back to list
        </button>
        <div className="bg-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-white mb-2">
            {f.program_name || `Firing #${f.id}`}
          </h3>
          <div className="grid grid-cols-4 gap-4 text-sm mb-4">
            <div>
              <span className="text-gray-400">Started:</span>{' '}
              <span className="text-white">{new Date(f.started_at).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-400">Ended:</span>{' '}
              <span className="text-white">
                {f.ended_at ? new Date(f.ended_at).toLocaleString() : 'In progress'}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Status:</span>{' '}
              <span className={f.status === 'completed' ? 'text-green-400' : 'text-yellow-400'}>
                {f.status}
              </span>
            </div>
            <div>
              <span className="text-gray-400">Readings:</span>{' '}
              <span className="text-white">{selected.readings.length}</span>
            </div>
          </div>
          <a
            href={`/api/firings/${f.id}/csv`}
            className="inline-block px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white mb-4"
          >
            Download CSV
          </a>
          {selected.readings.length > 0 ? (
            <FiringChart readings={selected.readings} height={400} />
          ) : (
            <div className="text-gray-500 text-center py-8">No readings recorded</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-white">Firing History</h2>
      {firings.length === 0 ? (
        <div className="text-gray-500 text-center py-8">No firings recorded yet.</div>
      ) : (
        <div className="space-y-2">
          {firings.map((f) => (
            <div
              key={f.id}
              onClick={() => viewFiring(f.id)}
              className="bg-gray-800 rounded-lg p-4 cursor-pointer hover:bg-gray-750 flex items-center justify-between"
            >
              <div>
                <div className="font-medium text-white">
                  {f.program_name || `Firing #${f.id}`}
                </div>
                <div className="text-sm text-gray-400">
                  {new Date(f.started_at).toLocaleString()}
                  {f.ended_at && (
                    <>
                      {' '}
                      &rarr; {new Date(f.ended_at).toLocaleString()}
                    </>
                  )}
                </div>
              </div>
              <span
                className={`px-2 py-1 rounded text-xs ${
                  f.status === 'completed'
                    ? 'bg-green-900 text-green-300'
                    : f.status === 'running'
                    ? 'bg-blue-900 text-blue-300'
                    : 'bg-red-900 text-red-300'
                }`}
              >
                {f.status}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
