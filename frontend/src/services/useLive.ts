"use client";

import { useEffect, useState } from "react";
import { api, Live, LivePanel } from "./api";

/** Poll one live panel. Each panel refreshes on its own clock, matched to how fast its source changes. */
export function useLive<T>(ticker: string, panel: LivePanel, everyMs: number) {
  const [state, setState] = useState<Live<T> | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      api.live<T>(ticker, panel)
        .then((r) => alive && setState(r))
        .catch((e) => alive && setState({ ok: false, fetched_at: new Date().toISOString(), error: String(e) }));
    load();
    const id = setInterval(load, everyMs);
    return () => { alive = false; clearInterval(id); };
  }, [ticker, panel, everyMs]);
  return state;
}

export function ago(ts: string | Date | null | undefined, now: Date = new Date()): string {
  if (!ts) return "–";
  const s = Math.max(0, Math.round((now.getTime() - new Date(ts).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
