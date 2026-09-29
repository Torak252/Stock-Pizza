"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import CompanyPanel from "@/components/CompanyPanel";
import SpikeFeed from "@/components/SpikeFeed";
import { api, Company, LEVEL_STYLE, Spike } from "@/services/api";

// Leaflet touches `window`, so the map renders client-side only.
const HqMap = dynamic(() => import("@/components/HqMap"), { ssr: false });

const REFRESH_MS = 60_000;

export default function Dashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [spikes, setSpikes] = useState<Spike[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([api.companies(), api.spikes(30)]);
      setCompanies(c);
      setSpikes(s);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const current = companies.find((c) => c.ticker === selected) ?? null;
  const alerts = companies.filter((c) => c.latest?.off_hours && c.latest.level !== "normal").length;

  return (
    <main className="flex min-h-screen flex-col gap-4 p-4">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold tracking-tight">🍕 Stock Pizza Tracker</h1>
        <div className="flex items-center gap-4 text-sm text-slate-400">
          <span>{companies.length} HQs tracked</span>
          <span className={alerts ? "text-red-400" : ""}>{alerts} active off-hours alerts</span>
          {(["normal", "elevated", "high", "extreme"] as const).map((l) => (
            <span key={l} className="flex items-center gap-1">
              <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: LEVEL_STYLE[l].hex }} />
              {l}
            </span>
          ))}
        </div>
      </header>

      {error && <p className="rounded bg-red-900/40 p-2 text-sm text-red-200">API unreachable: {error}</p>}

      <div className="grid flex-1 gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="min-h-[420px] overflow-hidden rounded-lg border border-slate-800">
          <HqMap companies={companies} selected={selected} onSelect={setSelected} />
        </div>
        <aside className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
          {current ? (
            <CompanyPanel company={current} />
          ) : (
            <p className="text-sm text-slate-400">Select an HQ on the map or in the spike feed.</p>
          )}
        </aside>
      </div>

      <section className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
        <h2 className="mb-2 font-semibold">Spike Feed</h2>
        <SpikeFeed spikes={spikes} onSelect={setSelected} />
      </section>

      <footer className="text-xs text-slate-600">
        Research tool. Signals are statistical anomalies in public data, not trading advice.
      </footer>
    </main>
  );
}
