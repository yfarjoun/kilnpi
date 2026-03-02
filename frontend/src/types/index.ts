export interface Segment {
  ramp_min: number;
  soak_min: number;
  target_temp: number;
}

export interface PIDParams {
  p: number;
  i: number;
  d: number;
  cycle_time: number;
}

export interface Status {
  pv: number;
  sp: number;
  mv: number;
  run_mode: string;
  segment: number;
  segment_elapsed_min: number;
  total_elapsed_min: number;
  alarm1: boolean;
  alarm2: boolean;
  timestamp: string;
}

export interface Program {
  id: number;
  name: string;
  description: string | null;
  segments: Segment[];
  created_at: string;
  updated_at: string;
}

export interface ProgramCreate {
  name: string;
  description?: string;
  segments: Segment[];
}

export interface Firing {
  id: number;
  program_id: number | null;
  program_name: string | null;
  started_at: string;
  ended_at: string | null;
  status: string;
  notes: string | null;
}

export interface Reading {
  timestamp: string;
  pv: number;
  sp: number;
  mv: number;
  segment: number | null;
}

export interface FiringDetail {
  firing: Firing;
  readings: Reading[];
}

export interface Slot {
  slot: string;
  program: Program | null;
}
