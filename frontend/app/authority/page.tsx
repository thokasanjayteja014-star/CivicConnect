"use client";

import { useState } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { CATEGORY_LABEL, STATUS_LABEL } from "@/components/labels";
import { EmptyState, ErrorBox, PageHeader, Spinner, Stat, inputCls } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { CATEGORIES, STATUSES, type ComplaintListItem } from "@/types";

export default function AuthorityDashboard() {
  const { user, allowed } = useRequireRole(["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]);
  const [f, setF] = useState({ category: "", priority: "", status: "", date_from: "", date_to: "", officer_id: "", q: "", sort: "priority",
    min_lat: "", max_lat: "", min_lng: "", max_lng: "" });
  const params = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => {
    if (!v) return;
    if (k === "priority" && v === "UNSCORED") params.set("unscored", "true");
    else if (k === "date_from" || k === "date_to") params.set(k, new Date(v + (k === "date_to" ? "T23:59:59" : "T00:00:00")).toISOString());
    else params.set(k, v);
  });
  const qs = params.toString();
  const dash = useApi<any>(allowed ? "/api/authority/dashboard" : null);
  const list = useApi<{ total: number; items: ComplaintListItem[] }>(allowed ? `/api/authority/complaints?${qs}` : null, [qs]);
  const officers = useApi<any[]>(allowed && user?.role !== "SYSTEM_ADMIN" ? "/api/authority/officers" : null);

  if (!allowed) return <Spinner />;
  const d = dash.data;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const noDept = user?.role !== "SYSTEM_ADMIN" && !user?.department_id;

  return (
    <div className="space-y-6">
      <PageHeader title={user?.role === "SYSTEM_ADMIN" ? "All routed complaints" : `${user?.department_name ?? "Department"} dashboard`}
        subtitle="Figures are computed live from complaint records in your authorized scope." />
      {noDept && <ErrorBox error={{ message: "Your account is not linked to an active department. Ask a system administrator to configure it." }} />}
      <ErrorBox error={dash.error} onRetry={dash.reload} />
      {d && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-7">
          <Stat label="Total in scope" value={d.total} />
          <Stat label="Awaiting review" value={d.awaiting_review} hint="New or reopened" />
          <Stat label="Assigned" value={d.assigned} />
          <Stat label="In progress" value={d.in_progress} />
          <Stat label="On hold" value={d.on_hold} />
          <Stat label="Awaiting verification" value={d.awaiting_verification} />
          <Stat label="Safety reviews" value={d.prompt_safety_reviews} hint="Potentially immediate danger" />
        </div>
      )}
      {d?.officer_workload?.length > 0 && (
        <details className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <summary className="cursor-pointer font-medium text-navy-900">Officer workload ({d.officer_workload.length})</summary>
          <ul className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
            {d.officer_workload.map((o: any) => <li key={o.officer_id}>{o.full_name} <span className="text-slate-500">({o.designation})</span>: {o.active_assignments} active</li>)}
          </ul>
        </details>
      )}

      <section className="space-y-3">
        <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-600 sm:grid-cols-3 lg:grid-cols-6">
          <label>Search<input className={inputCls + " mt-1"} value={f.q} onChange={set("q")} placeholder="Reference or title" /></label>
          <label>Category<select className={inputCls + " mt-1"} value={f.category} onChange={set("category")}><option value="">All</option>{CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}</select></label>
          <label>Priority<select className={inputCls + " mt-1"} value={f.priority} onChange={set("priority")}><option value="">All</option>{["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => <option key={p}>{p}</option>)}<option value="UNSCORED">Provisional / unscored</option></select></label>
          <label>Status<select className={inputCls + " mt-1"} value={f.status} onChange={set("status")}><option value="">All</option>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select></label>
          <label>From<input type="date" className={inputCls + " mt-1"} value={f.date_from} onChange={set("date_from")} /></label>
          <label>To<input type="date" className={inputCls + " mt-1"} value={f.date_to} onChange={set("date_to")} /></label>
          {officers.data && <label>Assigned officer<select className={inputCls + " mt-1"} value={f.officer_id} onChange={set("officer_id")}><option value="">Any</option>{officers.data.map((o) => <option key={o.officer_id} value={o.officer_id}>{o.full_name}</option>)}</select></label>}
          <label>Sort<select className={inputCls + " mt-1"} value={f.sort} onChange={set("sort")}><option value="priority">Priority first</option><option value="newest">Newest</option><option value="oldest">Oldest</option></select></label>
          <fieldset className="col-span-2 grid grid-cols-4 gap-1 sm:col-span-3 lg:col-span-4">
            <legend className="mb-1">Geographic area (bounding box, optional)</legend>
            <input aria-label="Min latitude" className={inputCls} placeholder="min lat" value={f.min_lat} onChange={set("min_lat")} />
            <input aria-label="Max latitude" className={inputCls} placeholder="max lat" value={f.max_lat} onChange={set("max_lat")} />
            <input aria-label="Min longitude" className={inputCls} placeholder="min lng" value={f.min_lng} onChange={set("min_lng")} />
            <input aria-label="Max longitude" className={inputCls} placeholder="max lng" value={f.max_lng} onChange={set("max_lng")} />
          </fieldset>
        </div>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner label="Loading complaints…" /> : list.data && list.data.items.length === 0 ? (
          <EmptyState title="No complaints in your scope" body={d?.total ? "No complaints match these filters." : "Complaints routed to your department will appear here once citizens report them."} />
        ) : list.data && (
          <>
            <p className="text-xs text-slate-500">{list.data.total} complaint(s)</p>
            <ComplaintTable items={list.data.items} hrefBase="/authority/complaints" staff />
          </>
        )}
      </section>
    </div>
  );
}
