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

export type Roi = [number, number, number, number]; // x1, y1, x2, y2 as fractions of the frame

export interface Source {
  id: number;
  kind: "venue" | "camera" | "traffic";
  provider: string;
  name: string;
  lat: number;
  lon: number;
  distance_m: number;
  url: string | null;
  roi: Roi | null;
  enabled: boolean;
}

export interface Preview {
  imageUrl: string; // object URL; caller revokes it
  vehicles: number;
  delivery: number;
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

  async setRoi(sourceId: number, roi: Roi | null): Promise<Roi | null> {
    const body = roi ? { x1: roi[0], y1: roi[1], x2: roi[2], y2: roi[3] } : undefined;
    const res = await fetch(`${BASE}/sources/${sourceId}/roi`, {
      method: "PUT",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`save ROI: HTTP ${res.status} ${await res.text()}`);
    return (await res.json()).roi;
  },

  async setEnabled(sourceId: number, enabled: boolean): Promise<void> {
    const res = await fetch(`${BASE}/sources/${sourceId}/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) throw new Error(`toggle camera: HTTP ${res.status}`);
  },

  async preview(sourceId: number): Promise<Preview> {
    const res = await fetch(`${BASE}/sources/${sourceId}/preview`, { cache: "no-store" });
    if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? `HTTP ${res.status}`);
    return {
      imageUrl: URL.createObjectURL(await res.blob()),
      vehicles: Number(res.headers.get("X-Vehicle-Count") ?? 0),
      delivery: Number(res.headers.get("X-Delivery-Count") ?? 0),
    };
  },
};

export const LEVEL_STYLE: Record<Level, { hex: string; badge: string }> = {
  normal: { hex: "#64748b", badge: "bg-slate-700 text-slate-200" },
  elevated: { hex: "#f59e0b", badge: "bg-amber-500/20 text-amber-300" },
  high: { hex: "#f97316", badge: "bg-orange-500/20 text-orange-300" },
  extreme: { hex: "#ef4444", badge: "bg-red-500/20 text-red-300" },
};
