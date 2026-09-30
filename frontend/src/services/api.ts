export type Level = "normal" | "elevated" | "high" | "extreme";

export interface Reading {
  ts: string;
  score: number;
  level: Level;
  off_hours: boolean;
  pct_normal: number | null;
  components: Record<string, number>;
}

export interface TrendPoint {
  ts: string;
  score: number;
  off_hours: boolean;
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
  last_night: Reading | null;
  trend_24h: TrendPoint[];
  sources: { cameras: number; venues: number };
}

export type LivePanel = "weather" | "skies" | "traffic" | "wire" | "quote";

export interface Live<T> {
  ok: boolean;
  fetched_at: string;
  data?: T;
  error?: string;
  setup?: boolean; // true = not configured yet (missing key), false = upstream failing
}

export interface Weather {
  temp_f: number | null;
  humidity: number | null;
  wind_mph: number | null;
  pressure_hpa: number | null;
  cloud_pct: number | null;
  summary: string;
  sunrise: string | null;
  sunset: string | null;
  us_aqi: number | null;
  moon: { phase: string; illumination_pct: number };
}

export interface Aircraft {
  hex: string;
  callsign: string | null;
  reg: string | null;
  type: string | null;
  kind: "bizjet" | "trainer" | "other";
  lat: number | null;
  lon: number | null;
  alt_ft: number | null;
  on_ground: boolean;
  track: number | null;
  approaching: boolean;
  dist_km: number | null;
}

export interface Skies {
  source: string;
  radius_nm: number;
  aircraft: Aircraft[];
  overhead: number;
  bizjets: number;
  bizjets_approaching: number;
  bizjets_on_ground: number;
}

export interface Traffic {
  current_speed_mph: number | null;
  free_flow_speed_mph: number | null;
  vs_free_flow_pct: number | null;
  closed: boolean;
}

export interface Wire {
  wire: { form: string; ts: string; url: string | null }[];
  last_8k: string | null;
  insider_filings_7d: number;
  eightk_by_weekday: Record<string, number>;
  eightk_sample: number;
}

export interface Quote {
  last: number | null;
  change_pct: number | null;
  earnings: { next: string | null; last: string | null } | null;
}

export interface Hourly {
  metric: string | null;
  now_hour?: number;
  hours: { hour: number; today: number | null; typical: number | null }[];
}

export interface Status {
  mode: "demo" | "live";
  defcon: 1 | 2 | 3 | 4 | 5;
  hqs_elevated: number;
  generated_at: string;
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
  video_url: string | null; // live HLS stream when the camera has one
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

/** Browser-loadable still: direct when it's a plain URL, else via the API (e.g. TxDOT's base64 snapshots). */
export function stillUrl(s: Source): string | null {
  if (!s.url) return null;
  return /^https?:\/\//.test(s.url) ? s.url : `${BASE}/sources/${s.id}/still`;
}

export const api = {
  companies: () => get<Company[]>("/companies"),
  status: () => get<Status>("/status"),
  company: async (ticker: string) => (await get<Company[]>("/companies")).find((c) => c.ticker === ticker.toUpperCase()) ?? null,
  live: <T,>(ticker: string, panel: LivePanel) => get<Live<T>>(`/companies/${ticker}/live/${panel}`),
  hourly: (ticker: string) => get<Hourly>(`/companies/${ticker}/hourly`),
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

// Status colors never carry meaning alone: every use pairs them with the icon and label.
export const LEVEL: Record<Level, { label: string; icon: string; color: string }> = {
  normal: { label: "Quiet", icon: "●", color: "var(--color-quiet)" },
  elevated: { label: "Warm", icon: "▲", color: "var(--color-warm)" },
  high: { label: "Hot", icon: "◆", color: "var(--color-hot)" },
  extreme: { label: "On fire", icon: "✶", color: "var(--color-fire)" },
};

export const METRIC_LABEL: Record<string, string> = {
  short_stops: "short stops at the gate",
  bizjet_count: "private jets nearby",
  venue_busyness: "pizza place busyness",
  vehicle_count: "cars at the gate",
  delivery_vehicle_count: "delivery vehicles",
  parking_occupancy: "parking lot",
};

export const METRIC_SHORT: Record<string, string> = {
  short_stops: "gate stops",
  bizjet_count: "private jets",
  venue_busyness: "pizza place",
  vehicle_count: "gate traffic",
  delivery_vehicle_count: "deliveries",
  parking_occupancy: "parking",
};

export function hqTime(ts: string | Date, timeZone: string, withDay = false) {
  return new Date(ts).toLocaleString("en-US", {
    timeZone, hour: "numeric", minute: "2-digit", timeZoneName: "short",
    ...(withDay ? { weekday: "short" } : {}),
  });
}

export function pct(value: number | null | undefined) {
  return value == null ? "–" : `${Math.round(value)}%`;
}
