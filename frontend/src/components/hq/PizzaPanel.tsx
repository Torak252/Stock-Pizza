import { Hourly, METRIC_LABEL, Source } from "@/services/api";
import { Panel, Pill } from "./Panel";

function Bars({ h }: { h: Hourly }) {
  const vals = h.hours.flatMap((x) => [x.today ?? 0, x.typical ?? 0]);
  const max = Math.max(1, ...vals);
  return (
    <div>
      <div className="flex h-20 items-end gap-[3px]" role="img" aria-label="Today by hour vs typical">
        {h.hours.map((x) => {
          const isNow = x.hour === h.now_hour;
          const v = x.today ?? x.typical ?? 0;
          return (
            <div key={x.hour} className="relative flex h-full flex-1 flex-col justify-end" title={`${x.hour}:00 · today ${x.today ?? "–"} · typical ${x.typical ?? "–"}`}>
              {x.typical != null && (
                <div className="absolute inset-x-0 bottom-0 rounded-t-sm bg-line-2/60" style={{ height: `${(x.typical / max) * 100}%` }} />
              )}
              <div className="relative rounded-t-sm" style={{
                height: `${(v / max) * 100}%`,
                background: isNow ? "var(--color-cheese)" : x.today != null ? "color-mix(in srgb, var(--color-cheese) 35%, transparent)" : "transparent",
              }} />
            </div>
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-ink-3">
        <span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>11p</span>
      </div>
    </div>
  );
}

/** Yoshi's "Pizza near HQ": today by hour against the usual level, with a one-line verdict. */
export default function PizzaPanel({ hourly, venues }: { hourly: Hourly | null; venues: Source[] }) {
  const nowRow = hourly?.hours.find((x) => x.hour === hourly.now_hour);
  const lastRow = hourly?.hours.find((x) => x.hour === ((hourly.now_hour ?? 0) + 23) % 24);
  const row = nowRow?.today != null ? nowRow : lastRow;
  const ratio = row?.today != null && row.typical ? row.today / row.typical : null;
  const verdict = ratio == null ? null : ratio > 1.25 ? "Busier than usual" : ratio < 0.8 ? "Quieter than usual" : "About usual";
  const tone = ratio == null ? "neutral" : ratio > 1.25 ? "bad" : ratio < 0.8 ? "good" : "neutral";
  return (
    <Panel title="Pizza near HQ">
      {hourly?.metric ? (
        <>
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-semibold text-ink">{METRIC_LABEL[hourly.metric] ?? hourly.metric}</span>
            {verdict && <Pill tone={tone as "bad" | "good" | "neutral"}>{verdict}</Pill>}
          </div>
          {row?.today != null && (
            <p className="mt-0.5 text-xs text-ink-2">
              {row.today.toFixed(1)} {row === nowRow ? "this hour" : "last hour"} · typically {row.typical?.toFixed(1) ?? "–"}
            </p>
          )}
          <div className="mt-3"><Bars h={hourly} /></div>
          <p className="mt-2 text-[10px] text-ink-3">Gold = today (bright = this hour) · grey = typical for this weekday</p>
        </>
      ) : (
        <p className="text-xs text-ink-2">No activity recorded yet. Counts appear once the worker has cameras to watch.</p>
      )}
      {venues.length > 0 && (
        <>
          <h3 className="panel-title mt-4 text-[12px]">Pizza places nearby</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {venues.slice(0, 5).map((v) => (
              <li key={v.id} className="flex justify-between"><span className="text-ink">{v.name}</span><span className="text-xs text-ink-3">{Math.round(v.distance_m)} m</span></li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
