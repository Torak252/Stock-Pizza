"use client";

import { useEffect, useState } from "react";
import RoiEditor from "@/components/RoiEditor";
import { Source } from "@/services/api";
import { ago } from "@/services/useLive";
import { Panel, Pill } from "./Panel";

const REFRESH_MS = 30_000; // DOT stills refresh every 1-5 min; re-pull often so we show each new frame promptly

/** Yoshi's "Traffic cams": tabbed stills that re-pull themselves, with lane editing one click away. */
export default function CamsPanel({ cameras, onChanged, now }: { cameras: Source[]; onChanged: () => void; now: Date }) {
  const [idx, setIdx] = useState(0);
  const [tick, setTick] = useState(() => Date.now());
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  useEffect(() => { const id = setInterval(() => setTick(Date.now()), REFRESH_MS); return () => clearInterval(id); }, []);
  useEffect(() => { setFailed(false); setLoadedAt(null); }, [idx]);

  const cam = cameras[Math.min(idx, cameras.length - 1)];
  const src = cam?.url ? `${cam.url}${cam.url.includes("?") ? "&" : "?"}_=${tick}` : null;

  return (
    <Panel title="Traffic cams" className="lg:col-span-2">
      {cameras.length ? (
        <>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {cameras.map((c, i) => (
              <button key={c.id} onClick={() => setIdx(i)}
                className={`rounded-full border px-3 py-1 text-xs ${i === idx ? "border-cheese bg-cheese text-bg" : "border-line-2 text-ink-2 hover:text-ink"} ${c.enabled ? "" : "opacity-50"}`}>
                {c.name}
              </button>
            ))}
          </div>
          <div className="relative overflow-hidden rounded-md border border-line bg-black">
            {src && !failed ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={src} alt={cam.name} className="aspect-video w-full object-contain"
                onLoad={() => setLoadedAt(new Date())} onError={() => setFailed(true)} />
            ) : (
              <div className="grid aspect-video place-items-center text-sm text-ink-3">
                {failed ? "Camera image unavailable right now (offline or blocked)." : "No image URL."}
              </div>
            )}
            {!failed && (
              <div className="absolute left-2 top-2"><Pill tone="live" solid>● LIVE · {loadedAt ? ago(loadedAt, now) : "loading"}</Pill></div>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
            <span>
              {cam.name} · {(cam.distance_m / 1000).toFixed(1)} km from HQ · {cam.provider}
              {!cam.enabled && " · counting off"}
            </span>
            <button onClick={() => setEditing(true)} className="rounded border border-line-2 px-2 py-0.5 hover:border-cheese hover:text-ink">
              {cam.roi ? "Edit gate lanes" : "Mark gate lanes"}
            </button>
          </div>
          {editing && <RoiEditor source={cam} onClose={() => setEditing(false)} onSaved={onChanged} />}
        </>
      ) : (
        <div className="grid aspect-video place-items-center rounded-md border border-dashed border-line-2 p-6 text-center text-sm text-ink-2">
          <div>
            No cameras near this HQ yet.
            <div className="mt-1 text-xs text-ink-3">Run <code className="text-ink">cli map</code>, or add a public camera still with <code className="text-ink">cli add-camera</code>.</div>
          </div>
        </div>
      )}
    </Panel>
  );
}
