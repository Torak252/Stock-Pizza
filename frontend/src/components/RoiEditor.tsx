"use client";

import { PointerEvent, useEffect, useRef, useState } from "react";
import { api, Preview, Roi, Source } from "@/services/api";

const clamp = (v: number) => Math.min(1, Math.max(0, v));

/** Drag a box over the lanes into the campus gate; only vehicles inside it are counted. */
export default function RoiEditor({ source, onClose, onSaved }: { source: Source; onClose: () => void; onSaved: () => void }) {
  const [roi, setRoi] = useState<Roi | null>(source.roi);
  const [saved, setSaved] = useState<Roi | null>(source.roi);
  const [enabled, setEnabled] = useState(source.enabled);
  const [start, setStart] = useState<[number, number] | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [status, setStatus] = useState<string>("");
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.imageUrl); }, [preview]);

  const toFrac = (e: PointerEvent): [number, number] => {
    const r = box.current!.getBoundingClientRect();
    return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)];
  };
  const onDown = (e: PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = toFrac(e);
    setStart(p);
    setRoi([p[0], p[1], p[0], p[1]]);
  };
  const onMove = (e: PointerEvent) => {
    if (!start) return;
    const [x, y] = toFrac(e);
    setRoi([Math.min(start[0], x), Math.min(start[1], y), Math.max(start[0], x), Math.max(start[1], y)]);
  };
  const onUp = () => setStart(null);

  const save = async (value: Roi | null) => {
    setStatus("Saving…");
    try {
      const stored = await api.setRoi(source.id, value);
      setRoi(stored);
      setSaved(stored);
      setPreview(null);
      setStatus(value ? "Saved. Future counts only include vehicles inside the box." : "Cleared. The whole frame is counted.");
      onSaved();
    } catch (e) {
      setStatus(String(e));
    }
  };

  const runPreview = async () => {
    setStatus("Fetching a live frame and running YOLO…");
    try {
      const p = await api.preview(source.id);
      setPreview(p);
      setStatus(`${p.vehicles} vehicles counted inside the saved box (${p.delivery} delivery-type). Green = counted, grey = ignored.`);
    } catch (e) {
      setStatus(`Preview failed: ${e instanceof Error ? e.message : e}`);
    }
  };

  const toggleEnabled = async () => {
    const next = !enabled;
    setEnabled(next); // optimistic; reverted below if the save fails
    try {
      await api.setEnabled(source.id, next);
      setStatus(next ? "Camera turned on." : "Camera turned off: the worker will skip it. Past counts are kept.");
      onSaved();
    } catch (e) {
      setEnabled(!next);
      setStatus(String(e));
    }
  };

  const dirty = JSON.stringify(roi) !== JSON.stringify(saved);

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-[95vh] w-full max-w-3xl space-y-3 overflow-y-auto rounded-lg border border-slate-700 bg-slate-900 p-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-semibold">{source.name}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200" aria-label="Close">✕</button>
        </div>
        <p className="text-xs text-slate-400">
          Drag a box around the lanes that lead into the campus. Leave out the main road, or its traffic will drown the signal.
        </p>

        <div className="flex justify-center">
        <div
          ref={box}
          className="relative inline-block cursor-crosshair touch-none select-none overflow-hidden rounded border border-slate-700"
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={preview?.imageUrl ?? source.url!} alt={source.name} className="block max-h-[60vh] max-w-full" draggable={false} />
          {roi && !preview && (
            <div
              className="pointer-events-none absolute border-2 border-orange-400 bg-orange-400/15"
              style={{ left: `${roi[0] * 100}%`, top: `${roi[1] * 100}%`, width: `${(roi[2] - roi[0]) * 100}%`, height: `${(roi[3] - roi[1]) * 100}%` }}
            />
          )}
        </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <button disabled={!roi || !dirty} onClick={() => save(roi)}
            className="rounded bg-orange-500 px-3 py-1 font-medium text-slate-950 disabled:opacity-40">Save box</button>
          <button disabled={!saved && !roi} onClick={() => save(null)}
            className="rounded border border-slate-600 px-3 py-1 disabled:opacity-40">Clear</button>
          <button onClick={runPreview} disabled={dirty}
            title={dirty ? "Save the box first" : undefined}
            className="rounded border border-slate-600 px-3 py-1 disabled:opacity-40">Preview detections</button>
          {preview && <button onClick={() => setPreview(null)} className="rounded border border-slate-600 px-3 py-1">Back to editing</button>}
          <label className="ml-auto flex cursor-pointer items-center gap-2 text-slate-300"
            title="Turn off cameras that show no campus entrance">
            <input type="checkbox" checked={enabled} onChange={toggleEnabled} className="accent-orange-500" />
            Count this camera
          </label>
        </div>
        {status && <p className="text-xs text-slate-300">{status}</p>}
      </div>
    </div>
  );
}
