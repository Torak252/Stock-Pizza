import { Company, Live, Traffic, Weather } from "@/services/api";
import { Panel, Pill, Stat, Unavailable } from "./Panel";

const CITY: Record<string, string> = {
  WMT: "Bentonville", AMZN: "Seattle", UNH: "Minnetonka", AAPL: "Cupertino", CVS: "Woonsocket",
  "BRK-B": "Omaha", GOOGL: "Mountain View", XOM: "Spring", MCK: "Irving", COR: "Conshohocken",
};

function trafficLine(t: Traffic, city: string) {
  if (t.closed) return "Road closed. Nobody's getting in or out.";
  const d = t.vs_free_flow_pct ?? 0;
  if (d >= 60) return "Gridlock. Someone is in a hurry.";
  if (d >= 25) return "Heavier than it should be.";
  return `An ordinary day in ${city}.`;
}

/** Open-Meteo returns HQ-local wall-clock times with no offset ("2026-09-29T18:51"); format without converting. */
function wallClock(iso: string) {
  const [h, m] = iso.slice(11, 16).split(":").map(Number);
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
}

function aqiLabel(a: number) { return a <= 50 ? "Good" : a <= 100 ? "Moderate" : a <= 150 ? "Unhealthy for some" : "Unhealthy"; }

export default function EnvironmentPanel({ c, traffic, weather }: { c: Company; traffic: Live<Traffic> | null; weather: Live<Weather> | null }) {
  const city = CITY[c.ticker] ?? "town";
  const t = traffic?.data;
  const w = weather?.data;
  const sunset = w?.sunset ? wallClock(w.sunset) : null;
  return (
    <Panel title={`Environment at HQ`}>
      {t ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={(t.vs_free_flow_pct ?? 0) >= 25 ? "warn" : "neutral"}>{(t.vs_free_flow_pct ?? 0) >= 25 ? "Heavy traffic" : "Normal traffic"}</Pill>
            <span className="text-sm text-ink">{trafficLine(t, city)}</span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Stat value={t.current_speed_mph ?? "–"} unit="mph" label="speed now" />
            <Stat value={t.free_flow_speed_mph ?? "–"} unit="mph" label="free-flowing" />
            <Stat value={`${(t.vs_free_flow_pct ?? 0) >= 0 ? "+" : ""}${t.vs_free_flow_pct ?? 0}`} unit="%" label="vs free-flow" />
          </div>
        </>
      ) : traffic ? <Unavailable error={traffic.error} setup={traffic.setup} /> : null}

      <div className="mt-4 border-t border-line pt-3">
        {w ? (
          <ul className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <li><span className="text-lg font-semibold text-ink">{Math.round(w.temp_f ?? 0)}</span><span className="text-xs text-ink-2">°F</span> {w.summary}</li>
            <li>{w.us_aqi != null ? <><span className="text-lg font-semibold text-ink">{w.us_aqi}</span> <span className="text-xs text-ink-2">AQI</span> {aqiLabel(w.us_aqi)}</> : <span className="text-ink-3">AQI –</span>}</li>
            <li><span className="text-lg font-semibold text-ink">{Math.round(w.wind_mph ?? 0)}</span><span className="text-xs text-ink-2">mph</span> {(w.wind_mph ?? 0) < 8 ? "Calm" : "Breezy"}</li>
            <li><span className="text-lg font-semibold text-ink">{w.humidity ?? "–"}</span><span className="text-xs text-ink-2">%RH</span> {(w.humidity ?? 0) > 80 ? "Muggy" : "Dry enough"}</li>
            <li><span className="text-lg font-semibold text-ink">{Math.round(w.pressure_hpa ?? 0)}</span><span className="text-xs text-ink-2">hPa</span></li>
            <li><span className="text-lg font-semibold text-ink">{w.cloud_pct ?? "–"}</span><span className="text-xs text-ink-2">% cloud</span></li>
            <li className="col-span-2 text-ink-2">Sunset <span className="text-ink">{sunset ?? "–"}</span> local</li>
            <li className="col-span-2 text-ink-2">
              <span className="text-lg font-semibold text-ink">{w.moon.illumination_pct}</span><span className="text-xs">%</span> {w.moon.phase}
              <div className="text-xs text-ink-3">The cosmos is noncommittal.</div>
            </li>
          </ul>
        ) : weather ? <Unavailable error={weather.error} setup={weather.setup} /> : <p className="text-xs text-ink-3">Loading…</p>}
      </div>
    </Panel>
  );
}
