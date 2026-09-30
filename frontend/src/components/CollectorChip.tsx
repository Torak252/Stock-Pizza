import { Status } from "@/services/api";
import { ago } from "@/services/useLive";

const STALL_MS = 15 * 60_000; // the worker samples every 2-5 min; 15 min of silence means it's down

/** Is the background worker actually collecting? Shown in every page header. */
export default function CollectorChip({ status, now }: { status: Status | null; now: Date | null }) {
  if (!status || !now) return null;
  const last = status.last_sample_at ? new Date(status.last_sample_at) : null;
  const stale = !last || now.getTime() - last.getTime() > STALL_MS;
  const color = status.mode === "demo" ? "var(--color-ink-3)" : stale ? "var(--color-fire)" : "var(--color-quiet)";
  const label = status.mode === "demo" ? "Collector: demo data"
    : !last ? "Collector: no data yet · run cli worker"
    : stale ? `Collector stalled · last sample ${ago(last, now)}`
    : `Collector live · ${ago(last, now)}`;
  return (
    <span className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]"
      style={{ borderColor: `color-mix(in srgb, ${color} 50%, transparent)`, color }}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${stale ? "" : "blink"}`} style={{ background: color }} />
      {label}
    </span>
  );
}
