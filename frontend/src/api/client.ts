const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  getStatus: () => request<import('../types').Status>('/status'),

  setSetpoint: (value: number) =>
    request<{ ok: boolean }>('/setpoint', {
      method: 'POST',
      body: JSON.stringify({ value }),
    }),

  startProgram: () =>
    request<{ ok: boolean }>('/program/start', { method: 'POST' }),

  stopProgram: () =>
    request<{ ok: boolean }>('/program/stop', { method: 'POST' }),

  pauseProgram: () =>
    request<{ ok: boolean }>('/program/pause', { method: 'POST' }),

  resumeProgram: () =>
    request<{ ok: boolean }>('/program/resume', { method: 'POST' }),

  getPID: () => request<import('../types').PIDParams>('/pid'),

  setPID: (params: import('../types').PIDParams) =>
    request<{ ok: boolean }>('/pid', {
      method: 'PUT',
      body: JSON.stringify(params),
    }),

  startAutotune: () =>
    request<{ ok: boolean }>('/autotune', {
      method: 'POST',
      body: JSON.stringify({ start: true }),
    }),

  stopAutotune: () =>
    request<{ ok: boolean }>('/autotune', {
      method: 'POST',
      body: JSON.stringify({ start: false }),
    }),

  getControllerProgram: () =>
    request<import('../types').Segment[]>('/controller/program'),

  setControllerProgram: (segments: import('../types').Segment[]) =>
    request<{ ok: boolean }>('/controller/program', {
      method: 'PUT',
      body: JSON.stringify(segments),
    }),

  listPrograms: () => request<import('../types').Program[]>('/programs'),

  getProgram: (id: number) =>
    request<import('../types').Program>(`/programs/${id}`),

  createProgram: (data: import('../types').ProgramCreate) =>
    request<import('../types').Program>('/programs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProgram: (id: number, data: Partial<import('../types').ProgramCreate>) =>
    request<import('../types').Program>(`/programs/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteProgram: (id: number) =>
    request<{ ok: boolean }>(`/programs/${id}`, { method: 'DELETE' }),

  listFirings: () => request<import('../types').Firing[]>('/firings'),

  getFiring: (id: number) =>
    request<import('../types').FiringDetail>(`/firings/${id}`),

  deleteFiring: (id: number) =>
    request<{ ok: boolean }>(`/firings/${id}`, { method: 'DELETE' }),

  updateFiringNotes: (id: number, notes: string) =>
    request<import('../types').Firing>(`/firings/${id}/notes`, {
      method: 'PATCH',
      body: JSON.stringify({ notes }),
    }),

  // Slots
  getSlots: () => request<import('../types').Slot[]>('/slots'),

  assignSlot: (slot: string, programId: number) =>
    request<import('../types').Slot>(`/slots/${slot}/assign`, {
      method: 'PUT',
      body: JSON.stringify({ program_id: programId }),
    }),

  unassignSlot: (slot: string) =>
    request<{ ok: boolean }>(`/slots/${slot}/assign`, { method: 'DELETE' }),

  fireSlot: (slot: string) =>
    request<{ ok: boolean; slot: string; program: string; start_segment: number }>(
      `/slots/${slot}/fire`,
      { method: 'POST' },
    ),

  // Program CSV import
  importProgram: async (file: File): Promise<import('../types').Program> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/programs/import`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
  },

  // Statistics
  getStatsSummary: () => request<import('../types').FiringSummary>('/stats/summary'),

  getFiringStats: (id: number) =>
    request<import('../types').FiringStats>(`/stats/firing/${id}`),

  getHealthTrend: () => request<import('../types').HealthTrend[]>('/stats/health'),

  getSystemInfo: () => request<import('../types').SystemInfo>('/system'),
};
