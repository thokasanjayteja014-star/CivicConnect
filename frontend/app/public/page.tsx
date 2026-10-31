"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { CATEGORY_LABEL } from "@/components/labels";
import { MarkersMap } from "@/components/map";
import { Badge, Card, EmptyState, ErrorBox, PageHeader, Spinner, Stat, inputCls } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { CATEGORIES } from "@/types";

const PUBLIC_STATUSES: [string, string][] = [
  ["SUBMITTED", "Reported"], ["UNDER_REVIEW", "Under review"], ["ASSIGNED", "Assigned"], ["IN_PROGRESS", "In progress"],
  ["ON_HOLD", "On hold"], ["RESOLVED_AWAITING_VERIFICATION", "Resolved (authority-reported)"], ["VERIFIED_RESOLVED", "Verified resolved"],
];

function Bars({ data, labels }: { data: Record<string, number>; labels?: Record<string, string> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="text-sm text-slate-500">No data yet.</p>;
  return (
    <ul className="space-y-2 text-sm">
      {entries.map(([k, v]) => (
        <li key={k}>
          <div className="flex justify-between text-xs"><span>{labels?.[k] || k}</span><span className="font-medium">{v}</span></div>
          <div className="mt-1 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-navy-600" style={{ width: `${(v / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

function PublicDashboard() {
  const sp = useSearchParams();
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [area, setArea] = useState("");
  const [reference, setReference] = useState(sp.get("reference") || "");
  const filters = new URLSearchParams({ ...(category && { category }), ...(status && { status }), ...(area && { area_id: area }) }).toString();
  const listQs = new URLSearchParams({ ...(category && { category }), ...(status && { status }), ...(area && { area_id: area }), ...(reference.trim() && { reference: reference.trim() }) }).toString();
  const areas = useApi<any[]>("/api/public/areas");
  const stats = useApi<any>(`/api/public/analytics?${new URLSearchParams({ ...(category && { category }), ...(area && { area_id: area }) })}`, [category, area]);
  const map = useApi<any>(`/api/public/map?${filters}`, [filters]);
  const list = useApi<any>(`/api/public/complaints?${listQs}`, [listQs]);
  const s = stats.data;
  const statusLabels = Object.fromEntries(Object.entries(s?.by_status || {}).map(([k, v]: any) => [k, v.label]));

  return (
    <div className="space-y-6">
      <PageHeader title="Public issues" subtitle="Privacy-reviewed complaints only. Locations are approximate; no names, contact details, private photos or internal notes are shown." />
      <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600 sm:grid-cols-4">
        <label>Category<select className={inputCls + " mt-1"} value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All</option>{CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}</select></label>
        <label>Status<select className={inputCls + " mt-1"} value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{PUBLIC_STATUSES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label>Area<select className={inputCls + " mt-1"} value={area} onChange={(e) => setArea(e.target.value)}><option value="">All</option>{areas.data?.map((a) => <option key={a.id} value={a.id}>{a.name}{a.is_prototype ? " (prototype)" : ""}</option>)}</select></label>
        <label>Reference<input className={inputCls + " mt-1"} value={reference} onChange={(e) => setReference(e.target.value)} placeholder="CVC-…" /></label>
      </div>

      <ErrorBox error={stats.error} onRetry={stats.reload} />
      {s && (
        <div className="grid gap-4 lg:grid-cols-4">
          <Stat label="Publicly visible complaints" value={s.total_public} hint={s.source} />
          <Card title="By category"><Bars data={s.by_category} labels={CATEGORY_LABEL} /></Card>
          <Card title="By status"><Bars data={Object.fromEntries(Object.entries(s.by_status).map(([k, v]: any) => [k, v.count]))} labels={statusLabels} /></Card>
          <Card title="By area"><Bars data={s.by_area} /></Card>
        </div>
      )}
      {s && (
        <Card title="Weekly trend (last 12 weeks)">
          {s.trend_weekly ? <Bars data={Object.fromEntries(s.trend_weekly.map((t: any) => [`Week of ${t.week_start}`, t.count]))} /> : <p className="text-sm text-slate-500">{s.trend_note}</p>}
        </Card>
      )}

      <Card title="Issue map">
        {map.loading && !map.data ? <Spinner /> : (
          <>
            <MarkersMap points={(map.data?.features || []).map((f: any) => ({ id: f.public_reference, lat: f.latitude, lng: f.longitude, category: f.category,
              title: `${CATEGORY_LABEL[f.category]} · ${f.public_status}`, subtitle: f.public_summary }))} />
            <p className="mt-2 text-xs text-slate-500">{map.data?.approximation} Marker colour indicates category.</p>
            {map.data?.features?.length === 0 && <p className="mt-2 text-sm text-slate-600">No public issues match these filters.</p>}
          </>
        )}
      </Card>

      <Card title="Public complaint list">
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : list.data?.items.length === 0 ? (
          <EmptyState title="No public complaints to show" body={s?.total_public === 0 ? "No complaints have been approved for public display yet." : "Try different filters."} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {list.data?.items.map((c: any) => (
              <li key={c.public_reference} className="py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-navy-800">{c.public_reference}</span>
                  <span>{CATEGORY_LABEL[c.category]}</span>
                  <Badge className={c.resolution_type === "VERIFIED" ? "bg-green-50 text-green-800 ring-green-300" : c.resolution_type === "AUTHORITY_REPORTED" ? "bg-lime-50 text-lime-800 ring-lime-200" : "bg-slate-100 ring-slate-300"}>{c.public_status}</Badge>
                </div>
                <p className="mt-1">{c.public_summary}</p>
                <p className="text-xs text-slate-500">
                  {c.generalized_location.area || "Approximate location"} · reported {c.reported_on}
                  {c.department ? ` · ${c.department}` : ""}
                  {c.latest_public_update ? ` · latest: ${c.latest_public_update.status} (${c.latest_public_update.date})` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export default function PublicPage() {
  return <Suspense><PublicDashboard /></Suspense>;
}
