"use client";

import { useEffect, useRef } from "react";

/** Plays an HLS stream (Caltrans cameras publish 1280x720 live video). Calls onFail so the caller can fall back to stills. */
export default function LiveVideo({ src, onFail, onPlaying }: { src: string; onFail: () => void; onPlaying: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    let destroyed = false;
    let hls: { destroy: () => void } | null = null;
    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src; // Safari plays HLS natively
    } else {
      import("hls.js").then(({ default: Hls }) => {
        if (destroyed) return;
        if (!Hls.isSupported()) return onFail();
        const h = new Hls({ liveSyncDurationCount: 2 });
        h.on(Hls.Events.ERROR, (_e, data) => { if (data.fatal) onFail(); });
        h.loadSource(src);
        h.attachMedia(video);
        hls = h;
      }).catch(onFail);
    }
    return () => { destroyed = true; hls?.destroy(); };
  }, [src, onFail]);
  return (
    <video ref={ref} className="aspect-video w-full bg-black object-contain" muted autoPlay playsInline
      onPlaying={onPlaying} onError={onFail} />
  );
}
