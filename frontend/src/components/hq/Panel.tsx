import { ReactNode } from "react";

export function Panel({ title, right, children, className = "" }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`flex flex-col rounded-lg border border-line bg-panel p-4 ${className}`}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h2 className="panel-title text-[15px]">{title}</h2>
        {right}
      </header>
      {children}
    </section>
  );
}

type Tone = "good" | "warn" | "bad" | "live" | "neutral";
const TONE: Record<Tone, string> = {
  good: "var(--color-quiet)",
  warn: "var(--color-warm)",
  bad: "var(--color-fire)",
  live: "var(--color-fire)",
  neutral: "var(--color-ink-3)",
};

export function Pill({ tone = "neutral", children, solid = false }: { tone?: Tone; children: ReactNode; solid?: boolean }) {
  const c = TONE[tone];
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium"
      style={solid
        ? { background: `color-mix(in srgb, ${c} 75%, black)`, borderColor: "transparent", color: "#f6efe4" }
        : { borderColor: `color-mix(in srgb, ${c} 55%, transparent)`, color: tone === "neutral" ? "var(--color-ink-2)" : c }}
    >
      {children}
    </span>
  );
}

/** What a panel shows when its source is unreachable or not configured, instead of fake numbers. */
export function Unavailable({ error, setup }: { error?: string; setup?: boolean }) {
  return (
    <div className="rounded border border-dashed border-line-2 p-3 text-xs text-ink-2">
      <Pill tone={setup ? "neutral" : "warn"}>{setup ? "not set up" : "source offline"}</Pill>
      <p className="mt-2 leading-relaxed">{error ?? "No data."}</p>
    </div>
  );
}

export function Stat({ value, unit, label }: { value: ReactNode; unit?: string; label: string }) {
  return (
    <div>
      <div className="text-xl font-semibold tabular-nums text-ink">
        {value}
        {unit && <span className="ml-0.5 text-xs font-normal text-ink-2">{unit}</span>}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-ink-3">{label}</div>
    </div>
  );
}
