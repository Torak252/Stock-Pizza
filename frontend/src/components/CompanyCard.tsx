import { Company, hqTime, LEVEL, pct } from "@/services/api";
import StatusChip from "./StatusChip";
import TrendChart from "./TrendChart";

export default function CompanyCard({ c, now, selected, onSelect }: { c: Company; now: Date | null; selected: boolean; onSelect: () => void }) {
  const peak = c.last_night;
  const level = peak?.level ?? "normal";
  const hot = level !== "normal";
  return (
    <button
      onClick={onSelect}
      className={`group relative flex flex-col overflow-hidden rounded-xl border bg-panel p-4 text-left transition hover:border-line-2 hover:bg-panel-2 ${
        selected ? "border-cheese/70" : "border-line"
      }`}
    >
      {hot && <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: LEVEL[level].color }} />}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-xl font-bold tracking-tight">{c.ticker}</span>
            <span className="font-mono text-[10px] text-ink-3">#{c.rank}</span>
          </div>
          <div className="truncate text-xs text-ink-2">{c.name}</div>
        </div>
        <StatusChip level={level} />
      </div>

      <div className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">Peak after 7 PM</div>
      <div className="flex items-baseline gap-2">
        <span className="font-display text-4xl font-bold tabular-nums tracking-tight" style={{ color: hot ? LEVEL[level].color : "var(--color-ink-2)" }}>
          {pct(peak?.pct_normal)}
        </span>
        <span className="text-xs text-ink-3">of normal</span>
      </div>
      <div className="h-4 font-mono text-[10px] text-ink-3">
        {peak ? `at ${hqTime(peak.ts, c.timezone)} · z ${peak.score.toFixed(1)}` : "no off-hours reading yet"}
      </div>

      <div className="mt-3">
        <TrendChart points={c.trend_24h} timeZone={c.timezone} height={46} />
      </div>

      <div className="mt-3 flex items-center justify-between border-t border-line pt-2 font-mono text-[10px] text-ink-3">
        <span className="tabular-nums">{now ? hqTime(now, c.timezone) : "--:--"} local</span>
        <span>
          {c.sources.cameras} cam · {c.sources.venues} venue
        </span>
      </div>
    </button>
  );
}
