"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import CamsPanel from "@/components/hq/CamsPanel";
import EnvironmentPanel from "@/components/hq/EnvironmentPanel";
import FilingDaysPanel from "@/components/hq/FilingDaysPanel";
import HeadlinePanel from "@/components/hq/HeadlinePanel";
import HistoryPanel from "@/components/hq/HistoryPanel";
import InsidersPanel from "@/components/hq/InsidersPanel";
import { Panel } from "@/components/hq/Panel";
import PizzaPanel from "@/components/hq/PizzaPanel";
import SkiesPanel from "@/components/hq/SkiesPanel";
import TrendChart from "@/components/TrendChart";
import { api, Company, Hourly, Quote, Reading, Skies, Source, Status, Traffic, Weather, Wire } from "@/services/api";
import { ago, useLive } from "@/services/useLive";

export default function HqPage() {
  const { ticker: raw } = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(raw).toUpperCase();
  const [company, setCompany] = useState<Company | null | undefined>(undefined);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [hourly, setHourly] = useState<Hourly | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [now, setNow] = useState<Date | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);

  // Each live panel polls at the pace its source actually changes.
  const skies = useLive<Skies>(ticker, "skies", 15_000);
  const traffic = useLive<Traffic>(ticker, "traffic", 120_000);
  const weather = useLive<Weather>(ticker, "weather", 600_000);
  const wire = useLive<Wire>(ticker, "wire", 300_000);
  const quote = useLive<Quote>(ticker, "quote", 60_000);

  const loadSources = useCallback(() => api.sources(ticker).then(setSources).catch(() => setSources([])), [ticker]);
  const refresh = useCallback(async () => {
    const [c, r, h, st] = await Promise.all([
      api.company(ticker), api.readings(ticker, 24 * 7).catch(() => []), api.hourly(ticker).catch(() => null), api.status().catch(() => null),
    ]);
    setCompany(c); setReadings(r); setHourly(h); setStatus(st); setUpdated(new Date());
  }, [ticker]);

  useEffect(() => {
    refresh().catch(() => setCompany(null));
    loadSources();
    setNow(new Date());
    const data = setInterval(() => refresh().catch(() => {}), 60_000);
    const clock = setInterval(() => setNow(new Date()), 1000);
    return () => { clearInterval(data); clearInterval(clock); };
  }, [refresh, loadSources]);

  if (company === null) {
    return <main className="mx-auto max-w-3xl p-8 text-ink-2">Unknown ticker {ticker}. <Link href="/" className="text-cheese underline">Back to all HQs</Link></main>;
  }
  const t = now ?? new Date(0);

  return (
    <main className="mx-auto flex max-w-[1180px] flex-col gap-4 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-3">
        <div>
          <Link href="/" className="text-[11px] text-ink-3 hover:text-cheese">← All headquarters</Link>
          <h1 className="font-heading text-3xl font-bold tracking-wide text-cheese">{company?.name ?? ticker} Tracker</h1>
          <p className="text-[13px] text-ink-2">Is {company?.name ?? ticker} working late tonight? Everything here is live public data.</p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-ink-2">
          {status?.mode === "demo" && <span className="rounded-full border border-warm/50 px-2 py-0.5 text-warm">Index: demo data</span>}
          <span className="rounded-full border border-line-2 px-2 py-0.5">{company?.hq_address ?? "…"}</span>
          <span className="flex items-center gap-1.5"><span className="blink inline-block h-1.5 w-1.5 rounded-full bg-quiet" />Updated {now && updated ? ago(updated, t) : "…"}</span>
        </div>
      </header>

      {company && (
        <div className="grid gap-4 lg:grid-cols-3">
          <HeadlinePanel c={company} wire={wire} quote={quote} now={t} />
          <HistoryPanel c={company} readings={readings} now={t} />

          <CamsPanel cameras={sources.filter((s) => s.kind === "camera" && s.url)} onChanged={loadSources} now={t} />
          <PizzaPanel hourly={hourly} venues={sources.filter((s) => s.kind === "venue")} />

          <EnvironmentPanel c={company} traffic={traffic} weather={weather} />
          <SkiesPanel hq={[company.lat, company.lon]} skies={skies} />
          <InsidersPanel wire={wire} now={t} />

          <Panel title="Pizza & Overtime Index" className="lg:col-span-2">
            <TrendChart points={readings} timeZone={company.timezone} height={180} axis />
            <p className="mt-2 text-[10px] text-ink-3">7 days · shaded = 7 PM–3 AM at HQ · dashed = alert threshold (z 2) · dots = off-hours spikes</p>
          </Panel>
          <FilingDaysPanel wire={wire} timeZone={company.timezone} />
        </div>
      )}

      <footer className="pt-2 text-[11px] text-ink-3">
        Research tool, not trading advice. Sources: DOT cameras, SEC EDGAR, Open-Meteo, adsb.lol / airplanes.live ADS-B, TomTom, Yahoo Finance.
      </footer>
    </main>
  );
}
