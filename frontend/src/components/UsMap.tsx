"use client";

import { geoAlbersUsa, geoPath } from "d3-geo";
import type { FeatureCollection, MultiLineString } from "geojson";
import { useMemo } from "react";
import { feature, mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import statesTopo from "us-atlas/states-10m.json";
import { Company, LEVEL, Level } from "@/services/api";

const W = 960, H = 560;
const topo = statesTopo as unknown as Topology<{ states: GeometryCollection; nation: GeometryCollection }>;

interface Props {
  companies: Company[];
  selected: string | null;
  onSelect: (ticker: string) => void;
}

function peakLevel(c: Company): Level {
  return c.last_night?.level ?? "normal";
}

/** Albers USA outline drawn from bundled TopoJSON: no tile server, works offline. */
export default function UsMap({ companies, selected, onSelect }: Props) {
  const { land, borders, projection } = useMemo(() => {
    const projection = geoAlbersUsa().scale(1220).translate([W / 2, H / 2]);
    const path = geoPath(projection);
    const nation = feature(topo, topo.objects.nation) as unknown as FeatureCollection;
    const borders = mesh(topo, topo.objects.states, (a, b) => a !== b) as MultiLineString;
    return { land: path(nation) ?? "", borders: path(borders) ?? "", projection };
  }, []);

  // Place labels, nudging any that collide with an earlier one (Apple and Alphabet are 10 km apart).
  const placed = useMemo(() => {
    const out: { c: Company; x: number; y: number; lx: number; ly: number }[] = [];
    [...companies].sort((a, b) => b.lat - a.lat).forEach((c) => {
      const p = projection([c.lon, c.lat]);
      if (!p) return;
      const [x, y] = p;
      let ly = y + 4;
      while (out.some((o) => Math.abs(o.ly - ly) < 15 && Math.abs(o.lx - (x + 14)) < 60)) ly += 15;
      out.push({ c, x, y, lx: x + 14, ly });
    });
    return out;
  }, [companies, projection]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="Map of tracked headquarters">
      <defs>
        <pattern id="dots" width="8" height="8" patternUnits="userSpaceOnUse">
          <circle cx="1" cy="1" r="0.9" fill="rgb(154 167 184 / 0.22)" />
        </pattern>
        <radialGradient id="glow">
          <stop offset="0" stopColor="white" stopOpacity="0.5" />
          <stop offset="1" stopColor="white" stopOpacity="0" />
        </radialGradient>
      </defs>
      <path d={land} fill="url(#dots)" stroke="var(--color-line-2)" strokeWidth={1.2} />
      <path d={borders} fill="none" stroke="var(--color-line)" strokeWidth={0.8} />
      {placed.map(({ c, x, y, lx, ly }) => {
        const lv = peakLevel(c);
        const color = LEVEL[lv].color;
        const hot = lv !== "normal";
        const sel = selected === c.ticker;
        return (
          <g key={c.ticker} className="cursor-pointer" onClick={() => onSelect(c.ticker)} role="button"
            aria-label={`${c.name}: ${LEVEL[lv].label}`}>
            {hot && <circle cx={x} cy={y} r={5} fill="none" stroke={color} strokeWidth={2} className="ping" />}
            {hot && <circle cx={x} cy={y} r={18} fill={color} opacity={0.12} />}
            <circle cx={x} cy={y} r={sel ? 7 : 5.5} fill={color} stroke="var(--color-bg)" strokeWidth={2} />
            {sel && <circle cx={x} cy={y} r={11} fill="none" stroke="var(--color-ink)" strokeWidth={1.2} />}
            {ly !== y + 4 && <line x1={x + 4} y1={y} x2={lx - 2} y2={ly - 4} stroke="var(--color-line-2)" />}
            <text x={lx} y={ly} className={`font-mono text-[13px] font-bold ${sel ? "fill-ink" : "fill-ink-2"}`}>
              {c.ticker}
            </text>
            <circle cx={x} cy={y} r={16} fill="transparent" />
          </g>
        );
      })}
    </svg>
  );
}
