import { useEffect, useState } from 'react';
import { useStatus } from '../hooks/useStatus';
import { TempGauge } from '../components/TempGauge';
import { StatusBar } from '../components/StatusBar';
import { api } from '../api/client';
import type { Program } from '../types';

export function Dashboard() {
  const status = useStatus();
  const [spInput, setSpInput] = useState('');
  const [editing, setEditing] = useState(false);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listPrograms().then(setPrograms).catch(() => {});
  }, []);

  const handleSetSP = async () => {
    const value = parseFloat(spInput);
    if (!isNaN(value)) {
      await api.setSetpoint(value);
      setEditing(false);
      setSpInput('');
    }
  };

  const handleStart = async () => {
    if (!selectedProgramId) return;
    setLoading(true);
    try {
      const program = programs.find((p) => p.id === selectedProgramId);
      if (program) {
        await api.setControllerProgram(program.segments);
        await api.startProgram();
      }
    } finally {
      setLoading(false);
    }
  };

  if (!status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400 text-lg">Connecting to controller...</div>
      </div>
    );
  }

  const isRunning = status.run_mode === 'running';

  return (
    <div className="space-y-6">
      <StatusBar status={status} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* PV Display */}
        <div className="bg-gray-800 rounded-xl p-6">
          <TempGauge value={status.pv} label="Process Value" alarm={status.alarm1 || status.alarm2} />
        </div>

        {/* SP Display + Edit */}
        <div className="bg-gray-800 rounded-xl p-6">
          <TempGauge value={status.sp} label="Setpoint" />
          <div className="mt-4 flex justify-center">
            {editing ? (
              <div className="flex gap-2">
                <input
                  type="number"
                  value={spInput}
                  onChange={(e) => setSpInput(e.target.value)}
                  placeholder={status.sp.toString()}
                  className="w-24 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-center"
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleSetSP()}
                />
                <button
                  onClick={handleSetSP}
                  className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white"
                >
                  Set
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="px-3 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm text-white"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => { setSpInput(status.sp.toString()); setEditing(true); }}
                className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-sm text-white"
              >
                Edit SP
              </button>
            )}
          </div>
        </div>

        {/* MV Display */}
        <div className="bg-gray-800 rounded-xl p-6">
          <div className="text-center">
            <div className="text-sm text-gray-400 uppercase tracking-wide">Output</div>
            <div className="text-5xl font-bold text-amber-400 tabular-nums">
              {status.mv.toFixed(1)}
              <span className="text-2xl text-gray-400">%</span>
            </div>
            <div className="mt-3 w-full bg-gray-700 rounded-full h-3">
              <div
                className="bg-amber-400 h-3 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, status.mv)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Program Status */}
      {isRunning && (
        <div className="bg-gray-800 rounded-xl p-6">
          <h3 className="text-lg font-semibold text-white mb-2">
            Program Running{selectedProgramId ? `: ${programs.find((p) => p.id === selectedProgramId)?.name ?? ''}` : ''}
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-400">Segment:</span>{' '}
              <span className="text-white">{status.segment}</span>
            </div>
            <div>
              <span className="text-gray-400">Elapsed:</span>{' '}
              <span className="text-white">{status.segment_elapsed_min} min</span>
            </div>
          </div>
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center gap-4">
        {!isRunning && (
          <select
            value={selectedProgramId ?? ''}
            onChange={(e) => setSelectedProgramId(e.target.value ? Number(e.target.value) : null)}
            className="px-3 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white"
          >
            <option value="">Select program...</option>
            {programs.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        )}
        <button
          onClick={handleStart}
          disabled={isRunning || !selectedProgramId || loading}
          className="px-6 py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-white"
        >
          {loading ? 'Loading...' : 'Start Program'}
        </button>
        <button
          onClick={() => api.stopProgram()}
          disabled={!isRunning}
          className="px-6 py-3 bg-red-600 hover:bg-red-500 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg font-medium text-white"
        >
          Stop Program
        </button>
      </div>
    </div>
  );
}
