import { useState, useCallback, useEffect, useRef } from 'react';
import { usePrograms } from '../hooks/usePrograms';
import { ProfileEditor } from '../components/ProfileEditor';
import type { Segment, Slot } from '../types';
import { api } from '../api/client';

export function Programs() {
  const { programs, loading, refresh, create, update, remove } = usePrograms();
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSlots = useCallback(() => {
    api.getSlots().then(setSlots).catch(() => {});
  }, []);

  useEffect(() => { loadSlots(); }, [loadSlots]);

  const assignToSlot = async (slot: string, programId: number) => {
    await api.assignSlot(slot, programId);
    loadSlots();
  };

  const startNew = () => {
    setEditing('new');
    setName('');
    setDescription('');
    setSegments([{ ramp_min: 30, soak_min: 60, target_temp: 500 }]);
  };

  const startEdit = (id: number) => {
    const prog = programs.find((p) => p.id === id);
    if (!prog) return;
    setEditing(id);
    setName(prog.name);
    setDescription(prog.description || '');
    setSegments(prog.segments);
  };

  const save = async () => {
    if (editing === 'new') {
      await create({ name, description: description || undefined, segments });
    } else if (typeof editing === 'number') {
      await update(editing, { name, description: description || undefined, segments });
    }
    setEditing(null);
  };

  const duplicate = async (id: number) => {
    const prog = programs.find((p) => p.id === id);
    if (!prog) return;
    await create({
      name: `${prog.name} (copy)`,
      description: prog.description || undefined,
      segments: prog.segments,
    });
  };

  const confirmDelete = async (id: number) => {
    const prog = programs.find((p) => p.id === id);
    if (!prog) return;
    if (!window.confirm(`Delete "${prog.name}"? This cannot be undone.`)) return;
    await remove(id);
  };

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await api.importProgram(file);
      await refresh();
    } catch (err) {
      alert(`Import failed: ${err instanceof Error ? err.message : err}`);
    }
    // Reset input so the same file can be re-selected
    e.target.value = '';
  };


  if (loading) {
    return <div className="text-gray-500 dark:text-gray-400">Loading programs...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Programs</h2>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            onChange={handleImport}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-sm text-gray-700 dark:text-white"
          >
            Import CSV
          </button>
          <button
            onClick={startNew}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white"
          >
            New Program
          </button>
        </div>
      </div>

      {editing !== null ? (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 space-y-4 shadow-sm dark:shadow-none">
          <h3 className="text-lg font-medium">
            {editing === 'new' ? 'New Program' : 'Edit Program'}
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-500 dark:text-gray-400 mb-1">Description</label>
              <input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded px-3 py-2 text-gray-900 dark:text-white"
              />
            </div>
          </div>
          <ProfileEditor segments={segments} onChange={setSegments} />
          <div className="flex gap-2">
            <button
              onClick={save}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 rounded text-sm text-white"
            >
              Save
            </button>
            <button
              onClick={() => setEditing(null)}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-sm text-gray-700 dark:text-white"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {programs.length === 0 ? (
            <div className="text-gray-400 dark:text-gray-500 text-center py-8">
              No programs yet. Create one to get started.
            </div>
          ) : (
            programs.map((prog) => (
              <div
                key={prog.id}
                className="bg-white dark:bg-gray-800 rounded-lg p-4 flex items-center justify-between shadow-sm dark:shadow-none"
              >
                <div>
                  <div className="font-medium">{prog.name}</div>
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    {prog.segments.length} segments &middot; Updated{' '}
                    {new Date(prog.updated_at).toLocaleDateString()}
                  </div>
                  {prog.description && (
                    <div className="text-sm text-gray-400 dark:text-gray-500 mt-1">{prog.description}</div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => assignToSlot('A', prog.id)}
                    className={`px-3 py-1 rounded text-xs text-white ${
                      slots.find((s) => s.slot === 'A')?.program?.id === prog.id
                        ? 'bg-green-700' : 'bg-indigo-600 hover:bg-indigo-500'
                    }`}
                  >
                    {slots.find((s) => s.slot === 'A')?.program?.id === prog.id ? 'Slot A \u2713' : '\u2192 Slot A'}
                  </button>
                  <button
                    onClick={() => assignToSlot('B', prog.id)}
                    className={`px-3 py-1 rounded text-xs text-white ${
                      slots.find((s) => s.slot === 'B')?.program?.id === prog.id
                        ? 'bg-green-700' : 'bg-indigo-600 hover:bg-indigo-500'
                    }`}
                  >
                    {slots.find((s) => s.slot === 'B')?.program?.id === prog.id ? 'Slot B \u2713' : '\u2192 Slot B'}
                  </button>
                  <button
                    onClick={() => window.open(`/api/programs/${prog.id}/csv`)}
                    className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-xs text-gray-700 dark:text-white"
                  >
                    Export
                  </button>
                  <button
                    onClick={() => startEdit(prog.id)}
                    className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-xs text-gray-700 dark:text-white"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => duplicate(prog.id)}
                    className="px-3 py-1 bg-gray-200 hover:bg-gray-300 dark:bg-gray-600 dark:hover:bg-gray-500 rounded text-xs text-gray-700 dark:text-white"
                  >
                    Duplicate
                  </button>
                  <button
                    onClick={() => confirmDelete(prog.id)}
                    className="px-3 py-1 bg-red-600 hover:bg-red-500 rounded text-xs text-white"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
