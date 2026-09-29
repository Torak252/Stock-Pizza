"use client";

import { useEffect, useState } from "react";
import RoiEditor from "@/components/RoiEditor";
import { api, Company, hqTime, LEVEL, METRIC_LABEL, pct, Reading, Source } from "@/services/api";
import StatusChip from "./StatusChip";
import TrendChart from "./TrendChart";

export default function CompanyDrawer({ company, onClose }: { company: Company; onClose: () => void }) {
  const [readings, setReadings] = useState<Reading[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [editing, setEditing] = useState<Source | null>(null);

  const loadSources = () => api.sources(company.ticker).then(setSources).catch(() => setSources([]));
  useEffect(() => {
    api.readings(company.ticker).then(setReadings).catch(() => setReadings([]));
    loadSources();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company.ticker]);

  const cameras = sources.filter((s) => s.kind === "camera" && s.url);
  const venues = sources.filter((s) => s.kind === "venue");
  const peak = company.last_night;
  const nights = readings.filter((r) => r.off_hours && r.level !== "normal").length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-[2px]" onClick={onClose}>
      <aside className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-panel p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">Fortune #{company.rank}</div>
            <h2 className="font-display text-3xl font-bold tracking-tight">
              {company.name} <span className="text-ink-3">{company.ticker}</span>
            </h2>
            <p className="mt-1 text-xs text-ink-2">
              {company.hq_address}
              {!company.coords_verified && <span className="text-ink-3"> · location not yet verified</span>}
            </p>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 text-ink-3 hover:bg-panel-2 hover:text-ink">✕</button>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-3">
          {[
            { k: "Last 24 h peak", v: pct(peak?.pct_normal), sub: peak ? hqTime(peak.ts, company.timezone) : "–", color: peak && peak.level !== "normal" ? LEVEL[peak.level].color : undefined },
            { k: "Right now", v: pct(company.latest?.pct_normal), sub: hqTime(new Date(), company.timezone) },
            { k: "Spike hours · 7 d", v: String(nights), sub: "off-hours readings above z 2" },
          ].map((s) => (
            <div key={s.k} className="rounded-lg border border-line bg-panel-2 p-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-ink-3">{s.k}</div>
              <div className="mt-1 font-display text-2xl font-bold tabular-nums" style={{ color: s.color }}>{s.v}</div>
              <div className="font-mono text-[10px] text-ink-3">{s.sub}</div>
            </div>
          ))}
        </div>
        {peak && <div className="mt-3"><StatusChip level={peak.level} size="lg" /></div>}

        <section className="mt-6">
          <h3 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-2">Pizza &amp; Overtime Index · 7 days</h3>
          <TrendChart points={readings} timeZone={company.timezone} height={170} axis />
          <p className="mt-2 font-mono text-[10px] text-ink-3">
            Shaded = 7 PM–3 AM at HQ · dashed = alert threshold (z 2) · dots = off-hours spikes
          </p>
          {company.latest && Object.keys(company.latest.components).length > 0 && (
            <p className="mt-2 text-xs text-ink-2">
              Driven by: {Object.keys(company.latest.components).map((m) => METRIC_LABEL[m] ?? m).join(", ")}
            </p>
          )}
        </section>

        <section className="mt-6">
          <h3 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-2">Cameras</h3>
          {cameras.length ? (
            <div className="grid grid-cols-2 gap-2">
              {cameras.map((c) => (
                <button key={c.id} onClick={() => setEditing(c)}
                  className={`overflow-hidden rounded-lg border border-line text-left hover:border-cheese/70 ${c.enabled ? "" : "opacity-50"}`}>
                  <span className="relative block bg-black">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={c.url!} alt={c.name} className="aspect-video w-full object-cover" loading="lazy" />
                    <span className="absolute right-1 top-1 rounded bg-black/70 px-1.5 font-mono text-[10px]">
                      {!c.enabled ? "off" : c.roi ? "lanes set" : "no lanes"}
                    </span>
                  </span>
                  <span className="block truncate px-2 py-1 font-mono text-[10px] text-ink-2">
                    {c.name} · {(c.distance_m / 1000).toFixed(1)} km
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-line-2 p-4 text-xs text-ink-2">
              No cameras yet. Run <code className="font-mono text-ink">cli map</code>, or add a public camera still with{" "}
              <code className="font-mono text-ink">cli add-camera</code>.
            </div>
          )}
        </section>

        <section className="mt-6">
          <h3 className="mb-2 font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-ink-2">Nearby pizza</h3>
          <ul className="divide-y divide-line rounded-lg border border-line">
            {venues.map((v) => (
              <li key={v.id} className="flex justify-between px-3 py-2 text-sm">
                <span>{v.name}</span>
                <span className="font-mono text-xs text-ink-3">{Math.round(v.distance_m)} m</span>
              </li>
            ))}
            {!venues.length && <li className="px-3 py-2 text-xs text-ink-3">None mapped yet. Run <code className="font-mono">cli map</code>.</li>}
          </ul>
        </section>

        {editing && <RoiEditor source={editing} onClose={() => setEditing(null)} onSaved={loadSources} />}
      </aside>
    </div>
  );
}
