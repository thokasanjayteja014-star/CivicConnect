"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { api } from "@/services/api";
import { useI18n } from "./I18nProvider";
import { Button, inputCls } from "./ui";

type Place = { display_name: string; latitude: number; longitude: number };

/** Address / landmark search (OpenStreetMap Nominatim via the backend). Picking a result moves the pin;
 *  the citizen can still adjust it by clicking the map. */
export function AddressSearch({ onPick }: { onPick: (p: Place) => void }) {
  const { lang, t } = useI18n();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Place[] | null>(null);
  const [error, setError] = useState("");

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    if (q.trim().length < 3) return;
    setBusy(true); setError(""); setResults(null);
    try {
      const r = await api<{ results: Place[] }>(`/api/geo/search?q=${encodeURIComponent(q.trim())}&lang=${lang}`);
      setResults(r.results);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <form onSubmit={search} className="flex gap-2" role="search">
        <label htmlFor="addr-search" className="sr-only">{t("Search for an address or landmark")}</label>
        <input id="addr-search" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={t("Search for an address or landmark")} />
        <Button type="submit" variant="secondary" loading={busy} disabled={q.trim().length < 3}><Search className="h-4 w-4" /> {t("Search")}</Button>
      </form>
      {error && <p className="text-xs text-red-700">{error}</p>}
      {results && results.length === 0 && <p className="text-xs text-slate-600">{t("No places found. Try a nearby landmark or pick the spot on the map.")}</p>}
      {results && results.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-md border border-slate-200 bg-white text-sm">
          {results.map((p) => (
            <li key={`${p.latitude},${p.longitude}`}>
              <button type="button" className="w-full px-3 py-2 text-left hover:bg-teal-50"
                onClick={() => { onPick(p); setResults(null); }}>{p.display_name}</button>
            </li>
          ))}
          <li className="px-3 py-1 text-[11px] text-slate-500">{t("Search data © OpenStreetMap contributors")}</li>
        </ul>
      )}
    </div>
  );
}

export async function reverseGeocode(lat: number, lng: number, lang: string): Promise<string | null> {
  try {
    const r = await api<{ display_name: string | null }>(`/api/geo/reverse?lat=${lat}&lng=${lng}&lang=${lang}`);
    return r.display_name;
  } catch {
    return null;
  }
}
