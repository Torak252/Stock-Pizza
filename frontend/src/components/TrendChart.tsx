"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { hqTime, LEVEL, Level } from "@/services/api";

export interface Point {
  ts: string;
  score: number;
  off_hours: boolean;
  level?: Level;
}

interface Props {
  points: Point[];
  timeZone: string;
  height: number;
  threshold?: number;
  axis?: boolean; // day labels along the bottom (detail view)
}

/** Index over time. Shaded columns = off-hours (7 PM-3 AM at the HQ); dashed line = alert threshold. */
export default function TrendChart({ points, timeZone, height, threshold = 2, axis = false }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const pad = { l: 2, r: 2, t: 6, b: axis ? 18 : 2 };
  const geo = useMemo(() => {
    if (points.length < 2 || width === 0) return null;
    const t = points.map((p) => new Date(p.ts).getTime());
    const t0 = t[0], t1 = t[t.length - 1];
    const scores = points.map((p) => p.score);
    const lo = Math.min(-2, ...scores), hi = Math.max(threshold + 2, ...scores);
    const x = (v: number) => pad.l + ((v - t0) / (t1 - t0 || 1)) * (width - pad.l - pad.r);
    const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (height - pad.t - pad.b);
    const step = (t1 - t0) / Math.max(points.length - 1, 1);
    const bands: [number, number][] = [];
    points.forEach((p, i) => {
      if (!p.off_hours) return;
      const a = x(t[i] - step / 2), b = x(t[i] + step / 2);
      const last = bands[bands.length - 1];
      if (last && Math.abs(last[1] - a) < 1) last[1] = b;
      else bands.push([a, b]);
    });
    const line = points.map((p, i) => `${i ? "L" : "M"}${x(t[i]).toFixed(1)},${y(p.score).toFixed(1)}`).join("");
    const area = `${line}L${x(t1).toFixed(1)},${y(lo)}L${x(t0).toFixed(1)},${y(lo)}Z`;
    const days: { x: number; label: string }[] = [];
    if (axis) {
      let prev = "";
      points.forEach((p, i) => {
        const d = new Date(p.ts).toLocaleDateString("en-US", { timeZone, weekday: "short" });
        if (d !== prev) days.push({ x: x(t[i]), label: d });
        prev = d;
      });
    }
    return { t, x, y, bands, line, area, days, lo };
  }, [points, width, height, threshold, axis, timeZone, pad.l, pad.r, pad.t, pad.b]);

  const onMove = (e: React.MouseEvent) => {
    if (!geo) return;
    const mx = e.clientX - wrap.current!.getBoundingClientRect().left;
    let best = 0;
    geo.t.forEach((v, i) => { if (Math.abs(geo.x(v) - mx) < Math.abs(geo.x(geo.t[best]) - mx)) best = i; });
    setHover(best);
  };

  if (points.length < 2) {
    return <div ref={wrap} style={{ height }} className="flex items-center font-mono text-[11px] text-ink-3">Not enough history yet</div>;
  }

  const h = hover != null && geo ? points[hover] : null;
  const gid = `g${Math.round(height)}${points.length}`;

  return (
    <div ref={wrap} className="relative" style={{ height }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      {geo && (
        <svg width={width} height={height} className="block overflow-visible">
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="var(--color-cheese)" stopOpacity="0.28" />
              <stop offset="1" stopColor="var(--color-cheese)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {geo.bands.map(([a, b], i) => (
            <rect key={i} x={a} y={pad.t} width={Math.max(b - a, 1)} height={height - pad.t - pad.b} fill="rgb(120 140 255 / 0.07)" />
          ))}
          <line x1={pad.l} x2={width - pad.r} y1={geo.y(threshold)} y2={geo.y(threshold)}
            stroke="var(--color-warm)" strokeOpacity="0.55" strokeDasharray="3 4" />
          <path d={geo.area} fill={`url(#${gid})`} />
          <path d={geo.line} fill="none" stroke="var(--color-cheese)" strokeWidth={2} strokeLinejoin="round" />
          {points.map((p, i) =>
            p.off_hours && p.score >= threshold ? (
              <circle key={p.ts} cx={geo.x(geo.t[i])} cy={geo.y(p.score)} r={4}
                fill={LEVEL[p.level ?? (p.score >= 4 ? "extreme" : p.score >= 3 ? "high" : "elevated")].color}
                stroke="var(--color-panel)" strokeWidth={2} />
            ) : null,
          )}
          {geo.days.map((d) => (
            <text key={d.x} x={d.x + 3} y={height - 4} className="fill-ink-3 font-mono text-[10px]">{d.label}</text>
          ))}
          {h && (
            <>
              <line x1={geo.x(geo.t[hover!])} x2={geo.x(geo.t[hover!])} y1={pad.t} y2={height - pad.b} stroke="var(--color-line-2)" />
              <circle cx={geo.x(geo.t[hover!])} cy={geo.y(h.score)} r={4} fill="var(--color-ink)" stroke="var(--color-panel)" strokeWidth={2} />
            </>
          )}
        </svg>
      )}
      {h && geo && (
        <div
          className="pointer-events-none absolute top-0 z-10 whitespace-nowrap rounded border border-line-2 bg-panel-2 px-1.5 py-0.5 font-mono text-[10px] text-ink"
          style={{ left: Math.min(Math.max(geo.x(geo.t[hover!]) - 60, 0), width - 130) }}
        >
          {hqTime(h.ts, timeZone, axis)} · z {h.score.toFixed(1)}
        </div>
      )}
    </div>
  );
}
