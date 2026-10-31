"use client";

import dynamic from "next/dynamic";

// Leaflet touches `window`, so maps are client-only.
const loading = () => <div className="h-56 w-full animate-pulse rounded-md bg-slate-100" aria-label="Loading map" />;

export const LocationPicker = dynamic(() => import("./LeafletMaps").then((m) => m.LocationPicker), { ssr: false, loading });
export const PointMap = dynamic(() => import("./LeafletMaps").then((m) => m.PointMap), { ssr: false, loading });
export const MarkersMap = dynamic(() => import("./LeafletMaps").then((m) => m.MarkersMap), { ssr: false, loading });
export const PolygonDrawer = dynamic(() => import("./LeafletMaps").then((m) => m.PolygonDrawer), { ssr: false, loading });
export type { MapPoint } from "./LeafletMaps";
