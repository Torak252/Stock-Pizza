import { LEVEL_STYLE, Spike } from "@/services/api";

// Show HQ-local time: "1:17 AM in Bentonville" is the whole point of an off-hours alert.
function hqTime(ts: string, timeZone: string) {
  return new Date(ts).toLocaleString(undefined, {
    timeZone, month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

export default function SpikeFeed({ spikes, onSelect }: { spikes: Spike[]; onSelect: (t: string) => void }) {
  if (!spikes.length) return <p className="text-sm text-slate-400">No off-hours anomalies yet.</p>;
  return (
    <ul className="divide-y divide-slate-800">
      {spikes.map((s) => (
        <li key={`${s.ticker}-${s.ts}`}>
          <button onClick={() => onSelect(s.ticker)} className="flex w-full items-center gap-3 py-2 text-left hover:bg-slate-800/50">
            <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${LEVEL_STYLE[s.level].badge}`}>{s.level}</span>
            <span className="w-14 font-mono font-bold">{s.ticker}</span>
            <span className="flex-1 truncate text-sm text-slate-400">{Object.keys(s.components).join(", ")}</span>
            <span className="font-mono text-sm">z {s.score.toFixed(1)}</span>
            <span className="w-36 text-right text-xs text-slate-500">{hqTime(s.ts, s.timezone)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
