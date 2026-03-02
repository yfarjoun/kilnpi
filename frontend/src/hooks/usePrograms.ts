import { useState, useEffect, useCallback } from 'react';
import type { Program, ProgramCreate } from '../types';
import { api } from '../api/client';

export function usePrograms() {
  const [programs, setPrograms] = useState<Program[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listPrograms();
      setPrograms(data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = async (data: ProgramCreate) => {
    const program = await api.createProgram(data);
    setPrograms((prev) => [program, ...prev]);
    return program;
  };

  const update = async (id: number, data: Partial<ProgramCreate>) => {
    const program = await api.updateProgram(id, data);
    setPrograms((prev) => prev.map((p) => (p.id === id ? program : p)));
    return program;
  };

  const remove = async (id: number) => {
    await api.deleteProgram(id);
    setPrograms((prev) => prev.filter((p) => p.id !== id));
  };

  return { programs, loading, refresh, create, update, remove };
}
