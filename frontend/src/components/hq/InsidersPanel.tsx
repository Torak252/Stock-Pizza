import { Live, Wire } from "@/services/api";
import { ago } from "@/services/useLive";
import { Panel, Pill, Unavailable } from "./Panel";

/** Yoshi's "Informants": insider Form 4 filings, the people who actually know. */
export default function InsidersPanel({ wire, now }: { wire: Live<Wire> | null; now: Date }) {
  const d = wire?.data;
  if (!d) return <Panel title="Informants">{wire ? <Unavailable error={wire.error} setup={wire.setup} /> : null}</Panel>;
  const n = d.insider_filings_7d;
  const forms = d.wire.filter((f) => f.form === "4").slice(0, 5);
  return (
    <Panel title="Informants">
      <Pill tone={n >= 3 ? "bad" : n ? "warn" : "good"} solid={n >= 3}>{n} insider filing{n === 1 ? "" : "s"} this week</Pill>
      <ul className="mt-3 space-y-1.5 text-sm">
        {forms.map((f) => (
          <li key={f.ts} className="flex items-center justify-between">
            <span>{f.url ? <a href={f.url} target="_blank" rel="noreferrer" className="text-cheese hover:underline">Form 4</a> : "Form 4"} <span className="text-xs text-ink-3">insider trade</span></span>
            <span className="text-xs text-ink-3">{ago(f.ts, now)}</span>
          </li>
        ))}
        {!forms.length && <li className="text-xs text-ink-3">No recent insider filings.</li>}
      </ul>
      <p className="mt-3 text-xs text-ink-2">{n >= 3 ? "All of them at once. They know something." : n ? "Someone's paperwork is moving." : "Insiders are keeping quiet."}</p>
    </Panel>
  );
}
