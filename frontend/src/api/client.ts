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
};
