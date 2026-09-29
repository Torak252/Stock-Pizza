"use client";

import { CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet";
import { Company, LEVEL_STYLE } from "@/services/api";

interface Props {
  companies: Company[];
  selected: string | null;
  onSelect: (ticker: string) => void;
}

export default function HqMap({ companies, selected, onSelect }: Props) {
  return (
    <MapContainer center={[39.5, -98.35]} zoom={4} className="h-full w-full rounded-lg" scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      {companies.map((c) => {
        const level = c.latest?.level ?? "normal";
        const alert = c.latest?.off_hours && level !== "normal";
        return (
          <CircleMarker
            key={c.ticker}
            center={[c.lat, c.lon]}
            radius={selected === c.ticker ? 14 : alert ? 11 : 8}
            pathOptions={{ color: LEVEL_STYLE[level].hex, fillColor: LEVEL_STYLE[level].hex, fillOpacity: 0.6, weight: 2 }}
            eventHandlers={{ click: () => onSelect(c.ticker) }}
          >
            <Tooltip direction="top">
              <b>{c.ticker}</b> · {c.name}
              <br />
              POI {c.latest ? c.latest.score.toFixed(2) : "–"} ({level})
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
