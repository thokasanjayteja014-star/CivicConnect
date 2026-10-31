"use client";

import "leaflet/dist/leaflet.css";
import { useEffect } from "react";
import { CircleMarker, MapContainer, Polygon, Polyline, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";

const TILE = process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = process.env.NEXT_PUBLIC_MAP_ATTRIBUTION || "&copy; OpenStreetMap contributors";

export function defaultView(): { center: [number, number]; zoom: number } {
  const [lat, lng, zoom] = (process.env.NEXT_PUBLIC_MAP_DEFAULT_VIEW || "20.5937,78.9629,5").split(",").map(Number);
  return { center: [lat, lng], zoom };
}

export const CATEGORY_COLOR: Record<string, string> = {
  ROAD_INFRASTRUCTURE: "#1f3a6b",
  WATER_SUPPLY: "#0284c7",
  SANITATION: "#65a30d",
  DRAINAGE: "#0f8579",
  STREETLIGHT: "#d97706",
  PUBLIC_INFRASTRUCTURE: "#7c3aed",
  OTHER: "#64748b",
};

function Recenter({ center, zoom }: { center: [number, number] | null; zoom?: number }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.setView(center, zoom ?? Math.max(map.getZoom(), 15));
  }, [center?.[0], center?.[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

function ClickHandler({ onClick }: { onClick: (lat: number, lng: number) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng.lat, e.latlng.lng) });
  return null;
}

export function LocationPicker({ value, onChange, height = 320 }: {
  value: { lat: number; lng: number } | null;
  onChange: (lat: number, lng: number) => void;
  height?: number;
}) {
  const dv = defaultView();
  return (
    <MapContainer center={value ? [value.lat, value.lng] : dv.center} zoom={value ? 16 : dv.zoom} style={{ height }} className="z-0 w-full rounded-md">
      <TileLayer url={TILE} attribution={ATTR} />
      <ClickHandler onClick={onChange} />
      <Recenter center={value ? [value.lat, value.lng] : null} />
      {value && <CircleMarker center={[value.lat, value.lng]} radius={10} pathOptions={{ color: "#0f8579", fillColor: "#14a394", fillOpacity: 0.6 }} />}
    </MapContainer>
  );
}

export function PointMap({ lat, lng, height = 220 }: { lat: number; lng: number; height?: number }) {
  return (
    <MapContainer center={[lat, lng]} zoom={16} style={{ height }} className="z-0 w-full rounded-md" scrollWheelZoom={false}>
      <TileLayer url={TILE} attribution={ATTR} />
      <CircleMarker center={[lat, lng]} radius={10} pathOptions={{ color: "#0f8579", fillColor: "#14a394", fillOpacity: 0.6 }} />
    </MapContainer>
  );
}

export type MapPoint = { id: string; lat: number; lng: number; category: string; title: string; subtitle?: string; href?: string };

export function MarkersMap({ points, height = 420 }: { points: MapPoint[]; height?: number }) {
  const dv = defaultView();
  const center: [number, number] = points.length ? [points[0].lat, points[0].lng] : dv.center;
  return (
    <MapContainer center={center} zoom={points.length ? 13 : dv.zoom} style={{ height }} className="z-0 w-full rounded-md">
      <TileLayer url={TILE} attribution={ATTR} />
      {points.map((p) => (
        <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={8}
          pathOptions={{ color: CATEGORY_COLOR[p.category] || "#334155", fillColor: CATEGORY_COLOR[p.category] || "#334155", fillOpacity: 0.55 }}>
          <Popup>
            <div className="text-sm">
              <div className="font-semibold">{p.title}</div>
              {p.subtitle && <div className="text-slate-600">{p.subtitle}</div>}
              {p.href && <a href={p.href} className="text-teal-700 underline">Open</a>}
            </div>
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}

export function PolygonDrawer({ vertices, onAdd, existing = [], height = 380, focus = null }: {
  vertices: [number, number][];
  onAdd: (lat: number, lng: number) => void;
  existing?: { name: string; rings: [number, number][][] }[];
  height?: number;
  /** Map centre to fly to, e.g. after an address search. */
  focus?: [number, number] | null;
}) {
  const dv = defaultView();
  return (
    <MapContainer center={vertices[0] || dv.center} zoom={vertices.length ? 14 : dv.zoom} style={{ height }} className="z-0 w-full rounded-md">
      <TileLayer url={TILE} attribution={ATTR} />
      <ClickHandler onClick={onAdd} />
      <Recenter center={focus} zoom={16} />
      {existing.map((e, i) => e.rings.map((ring, k) => (
        <Polygon key={`${i}-${k}`} positions={ring} pathOptions={{ color: "#64748b", weight: 1, fillOpacity: 0.08 }}>
          <Popup>{e.name}</Popup>
        </Polygon>
      )))}
      {vertices.length >= 3 ? (
        <Polygon positions={vertices} pathOptions={{ color: "#0f8579", fillOpacity: 0.2 }} />
      ) : vertices.length > 1 ? (
        <Polyline positions={vertices} pathOptions={{ color: "#0f8579" }} />
      ) : null}
      {vertices.map((v, i) => <CircleMarker key={i} center={v} radius={4} pathOptions={{ color: "#0d6b62" }} />)}
    </MapContainer>
  );
}
