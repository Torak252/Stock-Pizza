import { Status } from "@/services/api";

const LEVELS = {
  5: { color: "#3987e5", line: "All quiet. Everyone went home at five." },
  4: { color: "#0ca30c", line: "Somebody ordered a large. Probably nothing." },
  3: { color: "#fab219", line: "Pies are moving after dark. Worth watching." },
  2: { color: "#d03b3b", line: "Lots full, lights on, delivery cars circling." },
  1: { color: "#ffffff", line: "Nobody is going home tonight." },
} as const;

const WARMUP_HOURS = 96; // hour-of-day baselines need ~4 samples per hour: about four days

function Calibrating({ status }: { status: Status }) {
  const hours = status.first_sample_at ? (Date.now() - new Date(status.first_sample_at).getTime()) / 3.6e6 : 0;
  const pct = Math.min(100, Math.round((100 * hours) / WARMUP_HOURS));
  return (
    <section className="relative overflow-hidden rounded-xl border border-line bg-panel p-5">
      <div className="flex items-center justify-between">
        <span className="panel-title text-[15px]">Pizza readiness</span>
        <span className="text-[11px] text-ink-3">calibrating</span>
      </div>
      <div className="mt-3 font-display text-4xl font-bold text-cheese">Learning what normal looks like</div>
      <p className="mt-2 max-w-md text-sm text-ink-2">
        {status.first_sample_at
          ? `Collecting for ${hours < 1 ? `${Math.max(1, Math.round(hours * 60))} min` : hours < 24 ? `${Math.round(hours)} h` : `${(hours / 24).toFixed(1)} days`}. `
          : "No samples yet: start the collector (cli worker). "}
        It needs about four days of history before it can call a night unusual, and gets sharper after four weeks.
      </p>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-line" role="img" aria-label={`${pct}% of warm-up collected`}>
        <div className="h-full rounded-full bg-cheese" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-[10px] text-ink-3">{pct}% of the 4-day warm-up</div>
    </section>
  );
}

export default function DefconPanel({ status }: { status: Status | null }) {
  if (status?.mode === "live" && status.calibrating) return <Calibrating status={status} />;
  const level = status?.defcon ?? 5;
  const cfg = LEVELS[level];
  return (
    <section className="relative overflow-hidden rounded-xl border border-line bg-panel p-5">
      <div className="scanlines pointer-events-none absolute inset-0" />
      <div className="relative flex items-center justify-between">
        <span className="panel-title text-[15px]">Pizza readiness</span>
        <span className="text-[11px] text-ink-3">{status ? `${status.hqs_elevated} of 10 HQs above normal · last 24 h` : "…"}</span>
      </div>
      <div className="relative mt-3 flex items-end gap-4">
        <div className="font-display text-[88px] font-bold leading-[0.8] tracking-tight" style={{ color: cfg.color }}>
          {level}
        </div>
        <div className="pb-1">
          <div className="font-mono text-sm font-bold uppercase tracking-[0.3em]" style={{ color: cfg.color }}>DEFCON</div>
          <p className="mt-1 max-w-xs text-lg leading-snug text-ink">{cfg.line}</p>
        </div>
      </div>
      <div className="relative mt-5 grid grid-cols-5 gap-1.5" role="img" aria-label={`DEFCON ${level} of 5`}>
        {([5, 4, 3, 2, 1] as const).map((n) => (
          <div key={n}>
            <div
              className="h-2 rounded-full"
              style={{ background: n >= level ? LEVELS[n].color : "var(--color-line)", opacity: n === level ? 1 : n > level ? 0.45 : 1 }}
            />
            <div className={`mt-1 text-center font-mono text-[10px] ${n === level ? "text-ink" : "text-ink-3"}`}>{n}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
