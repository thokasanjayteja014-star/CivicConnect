"use client";

import { AlertTriangle, Trash2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useT } from "@/components/I18nProvider";
import { Button, EmptyState, ErrorBox, IconButton, Modal, Notice, Spinner, inputCls } from "@/components/ui";
import { api } from "@/services/api";
import { AddressSearch } from "@/components/AddressSearch";
import { PolygonDrawer } from "@/components/map";

export function useSubmit() {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ok, setOk] = useState("");
  const run = async (fn: () => Promise<void>, success = "Saved.") => {
    setBusy(true); setError(null); setOk("");
    try { await fn(); setOk(t(success)); return true; } catch (e) { setError(e); return false; } finally { setBusy(false); }
  };
  return { busy, error, ok, run, clear: () => { setError(null); setOk(""); } };
}

export function Feedback({ s }: { s: ReturnType<typeof useSubmit> }) {
  return <>{s.ok && <Notice tone="success">{s.ok}</Notice>}<ErrorBox error={s.error} /></>;
}

export function Loadable<T>({ q, children, empty, emptyTitle, emptyBody }: {
  q: { data: T | null; error: unknown; loading: boolean; reload: () => void };
  children: (d: T) => ReactNode; empty?: (d: T) => boolean; emptyTitle?: string; emptyBody?: string;
}) {
  const t = useT();
  if (q.loading && !q.data) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data) return null;
  if (empty?.(q.data)) return <EmptyState title={emptyTitle || t("Nothing here yet")} body={emptyBody} />;
  return <>{children(q.data)}</>;
}

type Deps = {
  name: string; can_delete: boolean; blocking: { label: string; count: number }[];
  removed_with_it: { label: string; count: number }[]; audit_entries_preserved: number; recommendation: string | null;
};

/** Trash icon + confirmation modal. Loads the server-side dependency check first; deletion is
 *  only offered when nothing operational depends on the record, otherwise deactivation is. */
export function DeleteControl({ kind, path, name, onDeleted, onDeactivate, active }: {
  kind: string; path: string; name: string; onDeleted: () => void; onDeactivate?: () => Promise<void>; active?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [deps, setDeps] = useState<Deps | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setOpen(true); setDeps(null); setError(null);
    try { setDeps(await api<Deps>(`${path}/dependencies`)); } catch (e) { setError(e); }
  }
  async function confirm() {
    setBusy(true); setError(null);
    try { await api(path, { method: "DELETE" }); setOpen(false); onDeleted(); }
    catch (e: any) { if (e?.details?.blocking) setDeps(e.details); setError(e); }
    finally { setBusy(false); }
  }
  async function deactivate() {
    if (!onDeactivate) return;
    setBusy(true);
    try { await onDeactivate(); setOpen(false); } catch (e) { setError(e); } finally { setBusy(false); }
  }

  return (
    <>
      <IconButton label={t("Delete {kind}", { kind: t(kind) })} tone="danger" onClick={start}><Trash2 className="h-4 w-4" /></IconButton>
      <Modal open={open} title={t("Delete {kind}", { kind: t(kind) })} onClose={() => setOpen(false)}
        footer={<>
          <Button variant="secondary" onClick={() => setOpen(false)}>{t("Cancel")}</Button>
          {deps && !deps.can_delete && onDeactivate && active !== false && <Button onClick={deactivate} loading={busy}>{t("Deactivate instead")}</Button>}
          {deps?.can_delete && <Button variant="danger" onClick={confirm} loading={busy}>{t("Delete permanently")}</Button>}
        </>}>
        <p className="font-medium text-slate-900">{name}</p>
        {!deps && !error && <Spinner label={t("Checking what depends on this record…")} />}
        <ErrorBox error={error} />
        {deps && deps.can_delete && (
          <>
            <div className="flex gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-red-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <p>{t("This permanently removes the record. It cannot be undone.")}</p>
            </div>
            {deps.removed_with_it.length > 0 && (
              <div>
                <p className="text-slate-700">{t("These configuration items will be removed with it:")}</p>
                <ul className="mt-1 list-disc pl-5 text-slate-700">{deps.removed_with_it.map((d) => <li key={d.label}>{t(d.label)}: {d.count}</li>)}</ul>
              </div>
            )}
            {deps.audit_entries_preserved > 0 && <p className="text-xs text-slate-500">{t("{n} audit log entries are kept.", { n: deps.audit_entries_preserved })}</p>}
          </>
        )}
        {deps && !deps.can_delete && (
          <>
            <Notice tone="warn">{t("This record is still in use and cannot be deleted.")}</Notice>
            <ul className="list-disc pl-5 text-slate-700">{deps.blocking.map((d) => <li key={d.label}>{t(d.label)}: <strong>{d.count}</strong></li>)}</ul>
            <p className="text-slate-600">{t("Deactivate it instead. Historical complaints, assignments and audit records are preserved.")}</p>
          </>
        )}
      </Modal>
    </>
  );
}

// ---------------- boundary editor (optional geography) ----------------

export type Rings = { name: string; rings: [number, number][][] }[];

export function ringsOf(name: string, g: any): Rings[number] | null {
  if (!g) return null;
  const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
  return { name, rings: polys.map((p: number[][][]) => p[0].map(([lng, lat]) => [lat, lng] as [number, number])) };
}

/** Click to add vertices, or paste GeoJSON. Returns null when no boundary is drawn (geography is optional). */
export function BoundaryEditor({ existing, onChange, initial }: { existing: Rings; onChange: (b: any | null) => void; initial?: any }) {
  const t = useT();
  const [vertices, setVertices] = useState<[number, number][]>(() => ringsOf("", initial)?.rings[0]?.slice(0, -1) || []);
  const [geojson, setGeojson] = useState("");
  const [focus, setFocus] = useState<[number, number] | null>(vertices[0] || null);
  const emit = (v: [number, number][], gj: string) => {
    if (gj.trim()) {
      try { const g = JSON.parse(gj); onChange(g.type === "Feature" ? g.geometry : g); } catch { onChange({ invalid: true }); }
    } else if (v.length >= 3) {
      const ring = v.map(([lat, lng]) => [lng, lat]);
      onChange({ type: "Polygon", coordinates: [[...ring, ring[0]]] });
    } else onChange(null);
  };
  return (
    <div className="space-y-2">
      <AddressSearch onPick={(p) => setFocus([p.latitude, p.longitude])} />
      <PolygonDrawer vertices={vertices} existing={existing} focus={focus} height={300}
        onAdd={(lat, lng) => { const v = [...vertices, [lat, lng] as [number, number]]; setVertices(v); emit(v, geojson); }} />
      <div className="flex items-center gap-3 text-xs text-slate-600">
        <span>{t("Click the map to add boundary points ({n}). At least 3 are needed.", { n: vertices.length })}</span>
        {vertices.length > 0 && <button type="button" className="font-medium text-navy-700 underline" onClick={() => { setVertices([]); emit([], geojson); }}>{t("Clear")}</button>}
      </div>
      <details>
        <summary className="cursor-pointer text-xs font-medium text-navy-700">{t("Paste GeoJSON instead")}</summary>
        <textarea aria-label={t("GeoJSON boundary")} rows={4} className={inputCls + " mt-1 font-mono text-xs"} value={geojson}
          onChange={(e) => { setGeojson(e.target.value); emit(vertices, e.target.value); }} placeholder='{"type":"Polygon","coordinates":[...]}' />
      </details>
    </div>
  );
}
