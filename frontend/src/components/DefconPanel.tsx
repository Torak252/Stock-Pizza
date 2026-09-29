import { Status } from "@/services/api";

const LEVELS = {
  5: { color: "#3987e5", line: "All quiet. Everyone went home at five." },
  4: { color: "#0ca30c", line: "Somebody ordered a large. Probably nothing." },
  3: { color: "#fab219", line: "Pies are moving after dark. Worth watching." },
  2: { color: "#d03b3b", line: "Lots full, lights on, delivery cars circling." },
  1: { color: "#ffffff", line: "Nobody is going home tonight." },
} as const;

export default function DefconPanel({ status }: { status: Status | null }) {
  const level = status?.defcon ?? 5;
  const cfg = LEVELS[level];
  return (
    <section className="relative overflow-hidden rounded-xl border border-line bg-panel p-5">
      <div className="scanlines pointer-events-none absolute inset-0" />
      <div className="relative flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.2em] text-ink-3">
        <span>Pizza readiness · last 24 h</span>
        <span>{status ? `${status.hqs_elevated} of 10 HQs above normal` : "…"}</span>
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
