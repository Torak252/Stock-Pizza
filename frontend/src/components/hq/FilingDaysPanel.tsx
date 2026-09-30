import { Live, Wire } from "@/services/api";
import { Panel, Unavailable } from "./Panel";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FULL: Record<string, string> = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };

/** Yoshi's "Which day they ship", for 8-Ks. */
export default function FilingDaysPanel({ wire, timeZone }: { wire: Live<Wire> | null; timeZone: string }) {
  const d = wire?.data;
  if (!d) return <Panel title="Which day they file">{wire ? <Unavailable error={wire.error} setup={wire.setup} /> : null}</Panel>;
  const counts = DAYS.map((k) => d.eightk_by_weekday[k] ?? 0);
  const total = counts.reduce((a, b) => a + b, 0) || 1;
  const max = Math.max(1, ...counts);
  const ranked = DAYS.map((k, i) => [k, counts[i]] as const).sort((a, b) => b[1] - a[1]);
  const [top, second] = ranked;
  const today = new Date().toLocaleDateString("en-US", { weekday: "short", timeZone });
  const verdict = top[1] === 0 ? "No 8-Ks on record." : `${FULL[top[0]]}${top[1] >= 1.5 * second[1] ? ", and it is not close." : ", narrowly."}`;
  return (
    <Panel title="Which day they file" right={<span className="text-[10px] text-ink-3">8-Ks · n={d.eightk_sample}</span>}>
      <div className="flex h-28 items-end gap-2">
        {DAYS.map((k, i) => (
          <div key={k} className="flex flex-1 flex-col items-center justify-end gap-1">
            <span className="text-[10px] text-ink-2">{Math.round((100 * counts[i]) / total)}%</span>
            <div className="w-full rounded-t-sm" style={{ height: `${(counts[i] / max) * 80}px`, background: k === today ? "var(--color-cheese)" : "color-mix(in srgb, var(--color-cheese) 40%, transparent)" }} />
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-2 text-center text-[10px] text-ink-3">{DAYS.map((k) => <span key={k} className="flex-1">{k}</span>)}</div>
      <p className="mt-3 text-xs text-ink-2">{verdict} Today is {FULL[today]}.</p>
    </Panel>
  );
}
