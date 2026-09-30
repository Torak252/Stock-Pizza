import { Company, hqTime, LEVEL, pct, Reading } from "@/services/api";
import { ago } from "@/services/useLive";
import StatusChip from "../StatusChip";
import { Panel, Pill } from "./Panel";

/** Yoshi's "forum activity / recent history", for the index: current state plus each level change. */
export default function HistoryPanel({ c, readings, now }: { c: Company; readings: Reading[]; now: Date }) {
  const changes: Reading[] = [];
  readings.forEach((r, i) => { if (i === 0 || r.level !== readings[i - 1].level) changes.push(r); });
  const recent = changes.slice(-6).reverse();
  const latest = c.latest;
  return (
    <Panel title="Index activity">
      <div className="flex flex-wrap gap-2">
        {latest ? <StatusChip level={latest.level} /> : <Pill>no readings</Pill>}
        <Pill tone={c.sources.cameras ? "good" : "neutral"}>{c.sources.cameras} camera{c.sources.cameras === 1 ? "" : "s"}</Pill>
        <Pill>{c.sources.venues} venue{c.sources.venues === 1 ? "" : "s"}</Pill>
      </div>
      <p className="mt-3 text-xs text-ink-2">
        Now <span className="font-semibold text-ink">{pct(latest?.pct_normal)}</span> of normal · last reading {ago(latest?.ts, now)}
        {c.last_night && <> · 24 h peak <span className="font-semibold text-ink">{pct(c.last_night.pct_normal)}</span> at {hqTime(c.last_night.ts, c.timezone)}</>}
      </p>
      <h3 className="panel-title mt-4 text-[12px]">Recent history</h3>
      <ul className="mt-1 divide-y divide-line">
        {recent.map((r) => (
          <li key={r.ts} className="flex items-baseline gap-3 py-2 text-sm">
            <span className="w-16 shrink-0 text-[11px] text-ink-3">{ago(r.ts, now)}</span>
            <span className="text-[10px] uppercase tracking-wider text-ink-3">status</span>
            <span style={{ color: LEVEL[r.level].color }}>{LEVEL[r.level].icon}</span>
            <span className="text-ink">{r.level === "normal" ? "Calmed down" : `Went ${LEVEL[r.level].label.toLowerCase()}`}</span>
          </li>
        ))}
        {!recent.length && <li className="py-2 text-xs text-ink-3">Nothing yet.</li>}
      </ul>
    </Panel>
  );
}
