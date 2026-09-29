export type Level = "normal" | "elevated" | "high" | "extreme";

export interface Reading {
  ts: string;
  score: number;
  level: Level;
  off_hours: boolean;
  components: Record<string, number>;
}

export interface Company {
  ticker: string;
  name: string;
  rank: number;
  hq_address: string;
  lat: number;
  lon: number;
  timezone: string;
  coords_verified: boolean;
  latest: Reading | null;
}

export interface Spike extends Reading {
  ticker: string;
  name: string;
  timezone: string;
}

export interface Source {
  kind: "venue" | "camera" | "traffic";
  provider: string;
  name: string;
  lat: number;
  lon: number;
  distance_m: number;
  url: string | null;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  companies: () => get<Company[]>("/companies"),
  spikes: (limit = 50) => get<Spike[]>(`/spikes?limit=${limit}`),
  readings: (ticker: string, hours = 168) => get<Reading[]>(`/companies/${ticker}/readings?hours=${hours}`),
  sources: (ticker: string) => get<Source[]>(`/companies/${ticker}/sources`),
};

export const LEVEL_STYLE: Record<Level, { hex: string; badge: string }> = {
  normal: { hex: "#64748b", badge: "bg-slate-700 text-slate-200" },
  elevated: { hex: "#f59e0b", badge: "bg-amber-500/20 text-amber-300" },
  high: { hex: "#f97316", badge: "bg-orange-500/20 text-orange-300" },
  extreme: { hex: "#ef4444", badge: "bg-red-500/20 text-red-300" },
};
