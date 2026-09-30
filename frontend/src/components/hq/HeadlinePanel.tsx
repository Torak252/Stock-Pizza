"use client";

import { Company, hqTime, Live, Quote, Wire } from "@/services/api";
import { ago } from "@/services/useLive";
import { Panel, Unavailable } from "./Panel";

function split(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600), m: Math.floor((s % 3600) / 60), s: s % 60 };
}
const two = (n: number) => String(n).padStart(2, "0");

/** Yoshi's "Time since last major patch", for filings: time since the last 8-K, and progress to next earnings. */
export default function HeadlinePanel({ c, wire, quote, now }: { c: Company; wire: Live<Wire> | null; quote: Live<Quote> | null; now: Date }) {
  const last8k = wire?.data?.last_8k;
  const t = last8k ? split(now.getTime() - new Date(last8k).getTime()) : null;
  const e = quote?.data?.earnings;
  const progress = e?.last && e?.next
    ? Math.min(1, Math.max(0, (now.getTime() - new Date(e.last).getTime()) / (new Date(e.next).getTime() - new Date(e.last).getTime())))
    : null;
  const recent = (wire?.data?.wire ?? []).slice(0, 4);

  return (
    <Panel title="Time since last 8-K" className="lg:col-span-2">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          {t ? (
            <div className="font-display text-5xl font-semibold tabular-nums tracking-tight text-ink">
              {t.d}<span className="text-2xl text-ink-2">d</span> {two(t.h)}<span className="text-ink-3">:</span>{two(t.m)}<span className="text-ink-3">:</span>{two(t.s)}
            </div>
          ) : wire && !wire.ok ? (
            <Unavailable error={wire.error} setup={wire.setup} />
          ) : (
            <div className="text-5xl font-semibold text-ink-3">–</div>
          )}
          {last8k && (
            <p className="mt-1 text-xs text-ink-2">
              Last 8-K filed {new Date(last8k).toLocaleDateString("en-US", { timeZone: c.timezone, weekday: "short", month: "short", day: "numeric" })}, {hqTime(last8k, c.timezone)} · {wire?.data?.eightk_sample} on record
            </p>
          )}
          {quote?.data?.last != null && (
            <p className="mt-1 text-xs text-ink-2">
              {c.ticker} <span className="font-semibold text-ink">${quote.data.last.toFixed(2)}</span>{" "}
              <span style={{ color: (quote.data.change_pct ?? 0) >= 0 ? "var(--color-quiet)" : "var(--color-fire)" }}>
                {(quote.data.change_pct ?? 0) >= 0 ? "+" : ""}{quote.data.change_pct?.toFixed(2)}%
              </span>
            </p>
          )}
        </div>
        <div className="min-w-[15rem] rounded border border-line bg-panel-2 p-3">
          <div className="text-[10px] uppercase tracking-wider text-ink-3">Filings wire · SEC EDGAR</div>
          <ul className="mt-1.5 space-y-1 font-mono text-[11px]">
            {recent.map((f) => (
              <li key={f.ts + f.form} className="flex justify-between gap-4">
                {f.url ? <a href={f.url} target="_blank" rel="noreferrer" className="text-cheese hover:underline">{f.form === "4" ? "Form 4" : f.form}</a> : <span>{f.form}</span>}
                <span className="text-ink-3">{ago(f.ts, now)}</span>
              </li>
            ))}
            {!recent.length && <li className="text-ink-3">{wire && !wire.ok ? "offline" : "…"}</li>}
          </ul>
        </div>
      </div>

      <div className="mt-4 border-t border-line pt-3">
        <div className="flex items-baseline justify-between text-sm">
          <span className="text-ink">
            {e?.next ? <>Next earnings expected {new Date(e.next).toLocaleDateString("en-US", { month: "long", day: "numeric", timeZone: c.timezone })}</> : "Next earnings date unknown"}
          </span>
          <span className="font-heading text-lg text-cheese">{progress != null ? `${Math.round(progress * 100)}%` : ""}</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
          <div className="h-full rounded-full bg-cheese" style={{ width: `${(progress ?? 0) * 100}%` }} />
        </div>
        {quote && !quote.ok && <p className="mt-2 text-[11px] text-ink-3">Prices offline: {quote.error}</p>}
      </div>
    </Panel>
  );
}
