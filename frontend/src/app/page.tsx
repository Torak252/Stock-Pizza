"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import CollectorChip from "@/components/CollectorChip";
import CompanyCard from "@/components/CompanyCard";
import DefconPanel from "@/components/DefconPanel";
import InterceptFeed from "@/components/InterceptFeed";
import UsMap from "@/components/UsMap";
import { api, Company, hqTime, LEVEL, pct, Spike, Status } from "@/services/api";

const REFRESH_MS = 60_000;

export default function Dashboard() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [spikes, setSpikes] = useState<Spike[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const router = useRouter();
  const open = (ticker: string) => router.push(`/hq/${ticker}`);
  const [error, setError] = useState<string | null>(null);
  // Starts null so the server render and the first client render match; the clock fills in after mount.
  const [now, setNow] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [c, s, st] = await Promise.all([api.companies(), api.spikes(40), api.status()]);
      setCompanies(c);
      setSpikes(s);
      setStatus(st);
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    setNow(new Date());
    const data = setInterval(refresh, REFRESH_MS);
    const clock = setInterval(() => setNow(new Date()), 1000);
    return () => { clearInterval(data); clearInterval(clock); };
  }, [refresh]);

  // Hottest first: last night's peak score, then Fortune rank.
  const ranked = useMemo(
    () => [...companies].sort((a, b) => (b.last_night?.score ?? -99) - (a.last_night?.score ?? -99) || a.rank - b.rank),
    [companies],
  );
  const leaders = ranked.filter((c) => c.last_night && c.last_night.level !== "normal").slice(0, 3);

  return (
    <main className="mx-auto flex min-h-screen max-w-[1480px] flex-col gap-4 px-4 py-5 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-cheese text-lg text-bg" aria-hidden>🍕</span>
          <div>
            <h1 className="font-heading text-2xl font-bold leading-none tracking-wide text-cheese">Stock Pizza Tracker</h1>
            <p className="mt-1 text-[12px] text-ink-3">Who&apos;s working late at Fortune 500 HQs, from public data.</p>
          </div>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px]">
          {status?.mode === "demo" && (
            <span className="rounded border border-warm/50 bg-warm/10 px-2 py-1 font-bold uppercase tracking-wider text-warm">
              Demo data · synthetic
            </span>
          )}
          <CollectorChip status={status} now={now} />
          <span className="flex items-center gap-1.5 rounded border border-line px-2 py-1 text-ink-2">
            <span className="blink inline-block h-1.5 w-1.5 rounded-full bg-quiet" />
            {now ? now.toISOString().slice(11, 19) : "--:--:--"} UTC
          </span>
        </div>
      </header>

      {error && <p className="rounded-lg border border-fire/40 bg-fire/10 p-3 font-mono text-xs text-red-200">API unreachable: {error}</p>}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
        <DefconPanel status={status} />
        <section className="rounded-xl border border-line bg-panel p-5">
          <div className="flex items-baseline justify-between"><span className="panel-title text-[15px]">Biggest all-nighters</span><span className="text-[11px] text-ink-3">last 24 h</span></div>
          <div className="mt-3 grid gap-3 sm:grid-cols-3">
            {leaders.map((c, i) => (
              <button key={c.ticker} onClick={() => open(c.ticker)}
                className="rounded-lg border border-line bg-panel-2 p-3 text-left hover:border-line-2">
                <div className="flex items-center justify-between font-mono text-[10px] text-ink-3">
                  <span>#{i + 1}</span>
                  <span style={{ color: LEVEL[c.last_night!.level].color }}>{LEVEL[c.last_night!.level].icon} {LEVEL[c.last_night!.level].label}</span>
                </div>
                <div className="mt-1 font-display text-5xl font-bold tabular-nums tracking-tight" style={{ color: LEVEL[c.last_night!.level].color }}>
                  {pct(c.last_night!.pct_normal)}
                </div>
                <div className="text-xs text-ink-3">of a normal night</div>
                <div className="mt-2 font-display text-lg font-bold leading-tight">{c.name}</div>
                <div className="font-mono text-[10px] text-ink-3">peaked {hqTime(c.last_night!.ts, c.timezone, true)}</div>
              </button>
            ))}
            {!leaders.length && (
              <p className="col-span-3 py-6 text-sm text-ink-2">
                {status?.calibrating
                  ? "Still learning each campus's normal. All-nighters show up here once there's enough history."
                  : "Nobody stayed late in the last 24 hours. Suspiciously normal."}
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.9fr)_minmax(0,1fr)]">
        <section className="flex flex-col overflow-hidden rounded-xl border border-line bg-panel">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 pt-3 font-mono text-[11px] text-ink-3">
            <span className="panel-title text-[15px]">Headquarters</span>
            <span className="flex flex-wrap gap-3 normal-case tracking-normal text-ink-2">
              {Object.entries(LEVEL).map(([k, l]) => (
                <span key={k} className="flex items-center gap-1"><span style={{ color: l.color }}>{l.icon}</span>{l.label}</span>
              ))}
            </span>
          </div>
          <div className="aspect-[960/560] w-full px-2 pb-2">
            <UsMap companies={companies} selected={null} onSelect={open} />
          </div>
        </section>
        <div className="h-[420px] lg:h-auto">
          <InterceptFeed spikes={spikes} onSelect={open} />
        </div>
      </div>

      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="panel-title text-[15px]">Watchlist · Fortune 10</h2>
          <span className="text-[11px] text-ink-3">sorted by last-24 h peak · click a card for the full HQ page</span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {ranked.map((c) => (
            <CompanyCard key={c.ticker} c={c} now={now} selected={false} onSelect={() => open(c.ticker)} />
          ))}
        </div>
      </section>

      <footer className="pb-4 pt-2 font-mono text-[10px] text-ink-3">
        Research tool. A spike is a statistical anomaly in public data, not a trading signal. &nbsp;·&nbsp; % of normal = activity vs the same weekday and hour over the past 8 weeks.
      </footer>

    </main>
  );
}
