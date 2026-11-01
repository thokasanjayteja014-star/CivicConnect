"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, ISSUE_PROGRESS_LABEL, fmtDate } from "@/components/labels";
import { MarkersMap } from "@/components/map";
import { Badge, Card, EmptyState, ErrorBox, PageHeader, Spinner, Stat, Tabs, inputCls } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { CATEGORIES } from "@/types";

const PUBLIC_STATUSES: [string, string][] = [
  ["SUBMITTED", "Reported"], ["UNDER_REVIEW", "Under review"], ["ASSIGNED", "Assigned"], ["IN_PROGRESS", "In progress"],
  ["ON_HOLD", "On hold"], ["RESOLVED_AWAITING_VERIFICATION", "Resolved (authority-reported)"], ["VERIFIED_RESOLVED", "Verified resolved"],
];

function Bars({ data, labels }: { data: Record<string, number>; labels?: Record<string, string> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="text-sm text-slate-500">—</p>;
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

function PublishedComplaints() {
  const t = useT();
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
      <p className="text-sm text-slate-600">{t("Individual complaints whose reporters allowed public display, after privacy review. Locations are approximate.")}</p>
      <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600 sm:grid-cols-4">
        <label>{t("Category")}<select className={inputCls + " mt-1"} value={category} onChange={(e) => setCategory(e.target.value)}><option value="">{t("All")}</option>{CATEGORIES.map((c) => <option key={c} value={c}>{t(CATEGORY_LABEL[c])}</option>)}</select></label>
        <label>{t("Status")}<select className={inputCls + " mt-1"} value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("All")}</option>{PUBLIC_STATUSES.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select></label>
        <label>{t("Area")}<select className={inputCls + " mt-1"} value={area} onChange={(e) => setArea(e.target.value)}><option value="">{t("All")}</option>{areas.data?.map((a) => <option key={a.id} value={a.id}>{a.name}{a.is_prototype ? " (prototype)" : ""}</option>)}</select></label>
        <label>{t("Reference")}<input className={inputCls + " mt-1"} value={reference} onChange={(e) => setReference(e.target.value)} placeholder="CVC-…" /></label>
      </div>

      <ErrorBox error={stats.error} onRetry={stats.reload} />
      {s && (
        <div className="grid gap-4 lg:grid-cols-4">
          <Stat label={t("Publicly visible complaints")} value={s.total_public} hint={s.source} />
          <Card title={t("By category")}><Bars data={s.by_category} labels={CATEGORY_LABEL} /></Card>
          <Card title={t("By status")}><Bars data={Object.fromEntries(Object.entries(s.by_status).map(([k, v]: any) => [k, v.count]))} labels={statusLabels} /></Card>
          <Card title={t("By area")}><Bars data={s.by_area} /></Card>
        </div>
      )}
      {s && (
        <Card title={t("Weekly trend (last 12 weeks)")}>
          {s.trend_weekly ? <Bars data={Object.fromEntries(s.trend_weekly.map((t: any) => [`Week of ${t.week_start}`, t.count]))} /> : <p className="text-sm text-slate-500">{s.trend_note}</p>}
        </Card>
      )}

      <Card title={t("Issue map")}>
        {map.loading && !map.data ? <Spinner /> : (
          <>
            <MarkersMap points={(map.data?.features || []).map((f: any) => ({ id: f.public_reference, lat: f.latitude, lng: f.longitude, category: f.category,
              title: `${CATEGORY_LABEL[f.category]} · ${f.public_status}`, subtitle: f.public_summary }))} />
            <p className="mt-2 text-xs text-slate-500">{map.data?.approximation} Marker colour indicates category.</p>
            {map.data?.features?.length === 0 && <p className="mt-2 text-sm text-slate-600">{t("Nothing matches these filters.")}</p>}
          </>
        )}
      </Card>

      <Card title={t("Public complaint list")}>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner /> : list.data?.items.length === 0 ? (
          <EmptyState title={t("No public complaints to show")} body={s?.total_public === 0 ? t("No complaints have been approved for public display yet.") : t("Try different filters.")} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {list.data?.items.map((c: any) => (
              <li key={c.public_reference} className="py-3 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-navy-800">{c.public_reference}</span>
                  <span>{CATEGORY_LABEL[c.category]}</span>
                  <Badge className={c.resolution_type === "VERIFIED" ? "bg-green-50 text-green-800 ring-green-300" : c.resolution_type === "AUTHORITY_REPORTED" ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-slate-100 ring-slate-300"}>{c.public_status}</Badge>
                </div>
                <p className="mt-1">{c.public_summary}</p>
                <p className="text-xs text-slate-500">
                  {c.generalized_location.area || t("Approximate location")} · {t("reported {date}", { date: c.reported_on })}
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

function PublicIssuesList() {
  const t = useT();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [progress, setProgress] = useState("");
  const qs = new URLSearchParams({ ...(q.trim() && { q: q.trim() }), ...(category && { category }), ...(progress && { progress }) }).toString();
  const list = useApi<{ total: number; items: any[] }>(`/api/public/issues?${qs}`, [qs]);
  return (
    <div className="space-y-4">
      <div className="grid gap-3 rounded-md border border-slate-200 bg-white p-4 text-xs text-slate-600 sm:grid-cols-3">
        <label>{t("Search")}<input className={inputCls + " mt-1"} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Road or area name")} /></label>
        <label>{t("Category")}<select className={inputCls + " mt-1"} value={category} onChange={(e) => setCategory(e.target.value)}><option value="">{t("All")}</option>{CATEGORIES.map((c) => <option key={c} value={c}>{t(CATEGORY_LABEL[c])}</option>)}</select></label>
        <label>{t("Progress")}<select className={inputCls + " mt-1"} value={progress} onChange={(e) => setProgress(e.target.value)}><option value="">{t("All")}</option>{Object.entries(ISSUE_PROGRESS_LABEL).map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select></label>
      </div>
      <ErrorBox error={list.error} onRetry={list.reload} />
      {list.loading && !list.data ? <Spinner /> : !list.data?.items.length ? (
        <EmptyState title={t("No public issues to show")} body={qs ? t("Try different filters.") : t("No public issues have been published yet.")} />
      ) : (
        <>
          <p className="text-xs text-slate-500">{t("{n} published issues", { n: list.data.total })}</p>
          <ul className="space-y-3">{list.data.items.map((i) => (
            <li key={i.id} className="rounded-md border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link href={`/public/issues/${i.id}`} className="font-semibold text-navy-800 underline">{i.title}</Link>
                  <p className="text-xs text-slate-500">{[i.general_location, i.area, i.department].filter(Boolean).join(" · ")}</p>
                </div>
                <Badge className={i.progress === "RESOLVED" ? "bg-green-50 text-green-800 ring-green-200" : "bg-slate-50 text-slate-700 ring-slate-300"}>{t(ISSUE_PROGRESS_LABEL[i.progress])}</Badge>
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-slate-700">{i.description}</p>
              <p className="mt-2 text-xs text-slate-500">{t(CATEGORY_LABEL[i.category] || "")} · {t("{n} related complaints", { n: i.related_complaints })} · {t("updated {date}", { date: fmtDate(i.last_update, false) })}</p>
            </li>
          ))}</ul>
        </>
      )}
    </div>
  );
}

function PublicTabs() {
  const t = useT();
  const sp = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState<"issues" | "complaints">(sp.get("tab") === "complaints" || sp.get("reference") ? "complaints" : "issues");
  return (
    <div className="space-y-4">
      <PageHeader title={t("Public Issues")} subtitle={t("Issues verified by departments and published for residents. No personal details of any citizen are shown.")} />
      <Tabs value={tab} onChange={(v) => { setTab(v); router.replace(`/public${v === "complaints" ? "?tab=complaints" : ""}`, { scroll: false }); }}
        tabs={[{ id: "issues", label: t("Public issues") }, { id: "complaints", label: t("Published complaints") }]} />
      {tab === "issues" ? <PublicIssuesList /> : <PublishedComplaints />}
    </div>
  );
}

export default function PublicPage() {
  return <Suspense fallback={<Spinner />}><PublicTabs /></Suspense>;
}
