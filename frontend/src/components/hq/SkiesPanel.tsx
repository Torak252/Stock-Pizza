import { Aircraft, Live, Skies } from "@/services/api";
import { Panel, Pill, Unavailable } from "./Panel";

const KM_PER_NM = 1.852;

function bearingXY(hq: [number, number], a: Aircraft, radiusKm: number, R: number): [number, number] | null {
  if (a.lat == null || a.lon == null) return null;
  const dx = (a.lon - hq[1]) * 111.32 * Math.cos((hq[0] * Math.PI) / 180);
  const dy = (a.lat - hq[0]) * 110.57;
  const k = R / radiusKm;
  return [dx * k, -dy * k];
}

const COLOR = { bizjet: "var(--color-cheese)", approach: "var(--color-quiet)", other: "var(--color-ink-3)", trainer: "var(--color-hot)" };

/** Yoshi's "Skies over HQ": radar of aircraft within the radius, business jets called out. */
export default function SkiesPanel({ hq, skies }: { hq: [number, number]; skies: Live<Skies> | null }) {
  const d = skies?.data;
  const R = 110;
  const radiusKm = (d?.radius_nm ?? 25) * KM_PER_NM;
  const jets = d?.aircraft.filter((a) => a.kind === "bizjet") ?? [];
  const inbound = jets.filter((a) => a.approaching);
  return (
    <Panel title="Skies over HQ">
      {d ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={inbound.length ? "good" : "neutral"} solid={inbound.length > 0}>
              {inbound.length ? `${inbound.length} private jet${inbound.length > 1 ? "s" : ""} on approach` : "No private jets inbound"}
            </Pill>
            <span className="text-sm text-ink">{d.overhead} aircraft overhead</span>
          </div>
          {jets.length > 0 && (
            <p className="mt-2 text-xs text-ink-2">
              Business jets: {jets.slice(0, 5).map((a) => (
                <span key={a.hex} className="mr-2 font-mono text-ink">{a.callsign ?? a.reg ?? a.hex}<span className="text-ink-3"> {a.type}</span></span>
              ))}
            </p>
          )}
          <svg viewBox={`${-R - 10} ${-R - 10} ${2 * R + 20} ${2 * R + 20}`} className="mx-auto mt-3 w-full max-w-[260px]">
            {[1, 2 / 3, 1 / 3].map((f) => <circle key={f} r={R * f} fill="none" stroke="var(--color-line)" />)}
            <line x1={-R} x2={R} y1={0} y2={0} stroke="var(--color-line)" />
            <line y1={-R} y2={R} x1={0} x2={0} stroke="var(--color-line)" />
            <text y={-R - 2} textAnchor="middle" className="fill-ink-3 text-[9px]">N</text>
            <text x={R * (2 / 3) + 3} y={-3} className="fill-ink-3 text-[8px]">{Math.round(radiusKm * 2 / 3)} km</text>
            <circle r={4} fill="var(--color-cheese)" />
            {d.aircraft.map((a) => {
              const p = bearingXY(hq, a, radiusKm, R);
              if (!p || Math.hypot(p[0], p[1]) > R) return null;
              const color = a.kind === "bizjet" ? COLOR.bizjet : a.approaching ? COLOR.approach : a.kind === "trainer" ? COLOR.trainer : COLOR.other;
              return (
                <g key={a.hex} transform={`translate(${p[0]},${p[1]}) rotate(${a.track ?? 0})`}>
                  <title>{`${a.callsign ?? a.hex} ${a.type ?? ""} ${a.alt_ft != null ? a.alt_ft + " ft" : "on ground"}`}</title>
                  <path d={a.kind === "bizjet" ? "M0,-6 L4,5 L0,3 L-4,5 Z" : "M0,-4 L3,4 L-3,4 Z"} fill={color} opacity={a.on_ground ? 0.5 : 1} />
                </g>
              );
            })}
          </svg>
          <div className="mt-2 flex flex-wrap justify-center gap-3 text-[10px] text-ink-2">
            <span><span style={{ color: COLOR.approach }}>▲</span> on approach</span>
            <span><span style={{ color: COLOR.bizjet }}>▲</span> private jet</span>
            <span><span style={{ color: COLOR.other }}>▲</span> overflying</span>
            <span><span style={{ color: COLOR.trainer }}>▲</span> trainer</span>
          </div>
          <p className="mt-2 text-[10px] text-ink-3">{d.radius_nm} nm radius · ADS-B via {d.source}</p>
        </>
      ) : skies ? <Unavailable error={skies.error} setup={skies.setup} /> : <p className="text-xs text-ink-3">Loading…</p>}
    </Panel>
  );
}
