import { Level, LEVEL } from "@/services/api";

export default function StatusChip({ level, size = "sm" }: { level: Level; size?: "sm" | "lg" }) {
  const l = LEVEL[level];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-mono font-bold uppercase tracking-wider ${
        size === "lg" ? "px-3 py-1 text-xs" : "px-2 py-0.5 text-[10px]"
      }`}
      style={{ color: l.color, borderColor: `color-mix(in srgb, ${l.color} 45%, transparent)`, background: `color-mix(in srgb, ${l.color} 12%, transparent)` }}
    >
      <span aria-hidden>{l.icon}</span>
      {l.label}
    </span>
  );
}
