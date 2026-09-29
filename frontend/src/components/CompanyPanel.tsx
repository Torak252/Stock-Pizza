"use client";

import { useEffect, useState } from "react";
import RoiEditor from "@/components/RoiEditor";
import { api, Company, LEVEL_STYLE, Reading, Source } from "@/services/api";

function Sparkline({ readings }: { readings: Reading[] }) {
  if (readings.length < 2) return <p className="text-sm text-slate-400">Not enough history yet.</p>;
  const w = 480, h = 120, pad = 4;
  const scores = readings.map((r) => r.score);
  const lo = Math.min(-2, ...scores), hi = Math.max(4, ...scores);
  const x = (i: number) => pad + (i / (readings.length - 1)) * (w - 2 * pad);
  const y = (v: number) => h - pad - ((v - lo) / (hi - lo)) * (h - 2 * pad);
  const path = readings.map((r, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(r.score).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-32 w-full">
      <line x1={pad} x2={w - pad} y1={y(2)} y2={y(2)} stroke="#f59e0b" strokeDasharray="4 4" strokeWidth={1} />
      <line x1={pad} x2={w - pad} y1={y(0)} y2={y(0)} stroke="#334155" strokeWidth={1} />
      <path d={path} fill="none" stroke="#94a3b8" strokeWidth={1.5} />
      {readings.map((r, i) =>
        r.off_hours && r.level !== "normal" ? (
          <circle key={r.ts} cx={x(i)} cy={y(r.score)} r={3.5} fill={LEVEL_STYLE[r.level].hex} />
        ) : null,
      )}
    </svg>
  );
}

export default function CompanyPanel({ company }: { company: Company }) {
  const [readings, setReadings] = useState<Reading[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [editing, setEditing] = useState<Source | null>(null);

  const loadSources = () => api.sources(company.ticker).then(setSources).catch(() => setSources([]));

  useEffect(() => {
    api.readings(company.ticker).then(setReadings).catch(() => setReadings([]));
    loadSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company.ticker]);

  const cameras = sources.filter((s) => s.kind === "camera" && s.url);
  const venues = sources.filter((s) => s.kind === "venue");

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">
          {company.name} <span className="font-mono text-slate-400">{company.ticker}</span>
        </h2>
        <p className="text-xs text-slate-500">
          #{company.rank} · {company.hq_address} · {company.timezone}
          {!company.coords_verified && " · coords unverified"}
        </p>
      </div>

      <section>
        <h3 className="mb-1 text-sm font-medium text-slate-300">Pizza & Overtime Index · 7 days</h3>
        <Sparkline readings={readings} />
        <p className="text-xs text-slate-500">Dashed line = z 2.0 alert threshold. Dots = off-hours spikes.</p>
      </section>

      {cameras.length > 0 && (
        <section>
          <h3 className="mb-1 text-sm font-medium text-slate-300">DOT cameras</h3>
          <p className="mb-2 text-xs text-slate-500">Click a camera to mark the gate lanes to count.</p>
          <div className="grid grid-cols-2 gap-2">
            {cameras.slice(0, 4).map((c) => (
              <button key={c.id} onClick={() => setEditing(c)}
                className="overflow-hidden rounded border border-slate-800 text-left hover:border-orange-400">
                <span className="relative block">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={c.url!} alt={c.name} className="aspect-video w-full object-cover" loading="lazy" />
                  <span className={`absolute right-1 top-1 rounded px-1 text-[10px] ${c.roi ? "bg-green-600/80" : "bg-slate-700/80"}`}>
                    {c.roi ? "lanes set" : "no lanes"}
                  </span>
                </span>
                <span className="block truncate px-1 py-0.5 text-xs text-slate-400">
                  {c.name} · {(c.distance_m / 1000).toFixed(1)} km
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {editing && (
        <RoiEditor
          source={editing}
          onClose={() => setEditing(null)}
          onSaved={loadSources}
        />
      )}

      <section>
        <h3 className="mb-1 text-sm font-medium text-slate-300">Tracked venues</h3>
        <ul className="text-sm text-slate-400">
          {venues.map((v) => (
            <li key={v.name + v.distance_m}>
              {v.name} <span className="text-slate-600">· {Math.round(v.distance_m)} m</span>
            </li>
          ))}
          {!venues.length && <li>None mapped yet — run <code>cli map</code>.</li>}
        </ul>
      </section>
    </div>
  );
}
