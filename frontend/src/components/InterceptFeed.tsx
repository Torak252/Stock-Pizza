import { hqTime, LEVEL, METRIC_SHORT, pct, Spike } from "@/services/api";

/** Terminal-style log of off-hours spikes, newest first. */
export default function InterceptFeed({ spikes, onSelect }: { spikes: Spike[]; onSelect: (t: string) => void }) {
  return (
    <section className="flex h-full min-h-0 flex-col rounded-xl border border-line bg-panel">
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <h2 className="panel-title text-[15px]">Intercepts</h2>
        <span className="flex items-center gap-1.5 font-mono text-[10px] text-ink-3">
          <span className="blink inline-block h-1.5 w-1.5 rounded-full bg-fire" /> off-hours spikes
        </span>
      </header>
      <ol className="min-h-0 flex-1 overflow-y-auto px-2 py-1 font-mono text-[12px]">
        {spikes.map((s) => {
          const l = LEVEL[s.level];
          const why = Object.entries(s.components).sort((a, b) => b[1] - a[1])[0]?.[0];
          return (
            <li key={`${s.ticker}-${s.ts}`}>
              <button onClick={() => onSelect(s.ticker)} className="grid w-full grid-cols-[8.6rem_3.6rem_4.8rem_1fr] items-baseline gap-2 rounded px-2 py-1.5 text-left hover:bg-panel-2">
                <span className="whitespace-nowrap text-ink-3">{hqTime(s.ts, s.timezone, true)}</span>
                <span className="font-bold text-ink">{s.ticker}</span>
                <span className="font-bold uppercase" style={{ color: l.color }}>{l.icon} {l.label}</span>
                <span className="truncate text-ink-2">
                  {pct(s.pct_normal)} · {METRIC_SHORT[why ?? ""] ?? why}
                </span>
              </button>
            </li>
          );
        })}
        {!spikes.length && <li className="px-2 py-3 text-ink-3">No off-hours spikes yet.</li>}
      </ol>
    </section>
  );
}
