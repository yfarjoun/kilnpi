import { useCallback, useEffect, useState } from 'react';
import { useStatus } from '../hooks/useStatus';
import { TempGauge } from '../components/TempGauge';
import { StatusBar } from '../components/StatusBar';
import { api } from '../api/client';
import type { Program, Slot } from '../types';

export function Dashboard() {
  const status = useStatus();
  const [spInput, setSpInput] = useState('');
  const [editing, setEditing] = useState(false);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [picking, setPicking] = useState<string | null>(null); // slot being changed
  const [loading, setLoading] = useState(false);
  const [optimisticRunning, setOptimisticRunning] = useState<boolean | null>(null);
  const [stopping, setStopping] = useState(false);

  const loadSlots = useCallback(async () => {
    try {
      const data = await api.getSlots();
      setSlots(data);
    } catch (err) {
      console.error('Failed to load slots:', err);
    }
  }, []);

  useEffect(() => {
    loadSlots();
    api.listPrograms().then(setPrograms).catch((err) => console.error('Failed to load programs:', err));
  }, [loadSlots]);

  const handleSetSP = async () => {
    const value = parseFloat(spInput);
    if (!isNaN(value)) {
      await api.setSetpoint(value);
      setEditing(false);
      setSpInput('');
    }
  };

  const handleFire = async (slot: string) => {
    setLoading(true);
    setOptimisticRunning(true);
    try {
      await api.fireSlot(slot);
    } catch (err) {
      setOptimisticRunning(null);
      alert(`Failed to fire: ${err instanceof Error ? err.message : err}`);
    } finally {
      setLoading(false);
    }
  };

  const [assigningSlot, setAssigningSlot] = useState<string | null>(null);

  const handleAssign = async (slot: string, programId: number) => {
    setAssigningSlot(slot);
    try {
      await api.assignSlot(slot, programId);
      setPicking(null);
      await loadSlots();
    } catch (err) {
      alert(`Failed to assign slot ${slot}: ${err instanceof Error ? err.message : err}`);
    } finally {
      setAssigningSlot(null);
    }
  };

  const realRunning = status?.run_mode === 'running';
  // Clear optimistic override once real status catches up
  useEffect(() => {
    if (optimisticRunning === true && realRunning) {
      setOptimisticRunning(null);
    }
    if (optimisticRunning === false && !realRunning) {
      setOptimisticRunning(null);
      setStopping(false);
    }
  }, [realRunning, optimisticRunning]);
  const isRunning = optimisticRunning ?? realRunning;

  if (!status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500 dark:text-gray-400 text-lg">Connecting to controller...</div>
      </div>
    );
  }
  const slotA = slots.find((s) => s.slot === 'A');
  const slotB = slots.find((s) => s.slot === 'B');

  return (
    <div className="space-y-6">
      <StatusBar status={status} />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* PV Display */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <TempGauge value={status.pv} label="Process Value" alarm={status.alarm1 || status.alarm2} />
        </div>

        {/* SP Display + Edit */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <TempGauge
            value={isRunning && status.program_target_temp != null ? status.program_target_temp : status.sp}
            label={isRunning && status.program_target_temp != null ? "Target" : "Setpoint"}
          />
          <div className="mt-4 flex justify-center">
            {editing ? (
              <div className="flex gap-2">
                <input
                  type="number"
                  value={spInput}
                  onChange={(e) => setSpInput(e.target.value)}
                  placeholder={status.sp.toString()}
                  className="w-24 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-2 py-1 text-gray-900 dark:text-white text-center"
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
                  className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-sm text-gray-700 dark:text-white"
                >
                  Cancel
                </button>
              </div>
            ) : !isRunning ? (
              <button
                onClick={() => { setSpInput(status.sp.toString()); setEditing(true); }}
                className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 rounded text-sm text-gray-700 dark:text-white"
              >
                Edit SP
              </button>
            ) : null}
          </div>
        </div>

        {/* MV Display */}
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <div className="text-center">
            <div className="text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wide">Output</div>
            <div className="text-5xl font-bold text-amber-500 dark:text-amber-400 tabular-nums">
              {status.mv.toFixed(1)}
              <span className="text-2xl text-gray-400">%</span>
            </div>
            <div className="mt-3 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
              <div
                className="bg-amber-500 dark:bg-amber-400 h-3 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, status.mv)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Slot Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {[slotA, slotB].map((slot, idx) => {
          const slotName = idx === 0 ? 'A' : 'B';
          const progName = slot?.program?.name;
          const slotLabel = `Slot ${slotName}${progName ? ` (${progName})` : ''}`;
          const assigned = slot?.program != null;

          return (
            <div key={slotName} className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-lg font-semibold">{slotLabel}</h3>
                <button
                  onClick={() => setPicking(picking === slotName ? null : slotName)}
                  className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-xs text-gray-700 dark:text-white"
                >
                  Change
                </button>
              </div>

              {assigned ? (
                <div className="space-y-2">
                  <div className="font-medium">{slot!.program!.name}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {slot!.program!.segments.length} segments
                    {slot!.program!.description && ` \u00b7 ${slot!.program!.description}`}
                  </div>
                  <button
                    onClick={() => handleFire(slotName)}
                    disabled={isRunning || loading}
                    className="mt-2 w-full px-4 py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-200 disabled:text-gray-400 dark:disabled:bg-gray-700 dark:disabled:text-gray-500 rounded-lg font-medium text-white"
                  >
                    {loading ? 'Starting...' : `Fire ${slotLabel}`}
                  </button>
                </div>
              ) : (
                <div className="text-gray-400 dark:text-gray-500 py-4 text-center">
                  Not assigned &mdash; pick a program below
                </div>
              )}

              {/* Program picker dropdown */}
              {picking === slotName && (
                <div className="mt-3 border-t border-gray-200 dark:border-gray-700 pt-3 space-y-1">
                  {programs.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => handleAssign(slotName, p.id)}
                      disabled={assigningSlot !== null}
                      className="w-full text-left px-3 py-2 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 rounded text-sm disabled:opacity-50"
                    >
                      {assigningSlot === slotName ? '...' : p.name}{' '}
                      <span className="text-gray-500 dark:text-gray-400">({p.segments.length} seg)</span>
                    </button>
                  ))}
                  {programs.length === 0 && (
                    <div className="text-gray-400 dark:text-gray-500 text-sm text-center py-2">
                      No programs in library yet
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Program Status */}
      {isRunning && (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 shadow-sm dark:shadow-none">
          <h3 className="text-lg font-semibold mb-2">
            {!realRunning && optimisticRunning ? 'Starting' : 'Running'}:{' '}
            {status.active_program_name || 'Program'}
          </h3>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-500 dark:text-gray-400">Segment:</span>{' '}
              <span>{status.segment}</span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Seg elapsed:</span>{' '}
              <span>{status.segment_elapsed_min} min</span>
            </div>
            <div>
              <span className="text-gray-500 dark:text-gray-400">Total elapsed:</span>{' '}
              <span>{status.total_elapsed_min} min</span>
            </div>
          </div>
        </div>
      )}

      {/* Stop button */}
      {isRunning && (
        <button
          onClick={async () => {
            setStopping(true);
            setOptimisticRunning(false);
            try {
              await api.stopProgram();
            } catch {
              setStopping(false);
              setOptimisticRunning(null);
            }
          }}
          disabled={stopping}
          className="w-full px-6 py-3 bg-red-600 hover:bg-red-500 disabled:bg-gray-400 rounded-lg font-medium text-white"
        >
          {stopping ? 'Stopping...' : 'Stop Program'}
        </button>
      )}
    </div>
  );
}
