"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, STATUS_LABEL } from "@/components/labels";
import { EmptyState, ErrorBox, FilterBar, Spinner, filterQuery, type FilterDef } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { CATEGORIES, STATUSES, type ComplaintListItem } from "@/types";

const KEYS = ["q", "status", "status_group", "category", "priority", "department_id", "jurisdiction_id", "officer_id", "assignment",
  "overdue", "escalated", "due_within_hours", "date_from", "date_to", "sort"];

/** Complaint list with role-specific filters. `fixed` filters are always applied and hidden. */
export function ComplaintsBrowser({ fixed = {}, defaults = {}, emptyTitle, emptyBody }: {
  fixed?: Record<string, string>; defaults?: Record<string, string>; emptyTitle?: string; emptyBody?: string;
}) {
  const t = useT();
  const { user } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  const role = user?.role;
  const isAdmin = role === "SYSTEM_ADMIN";
  const isOfficer = role === "OFFICER";

  const [f, setF] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = { ...defaults };
    KEYS.forEach((k) => { const v = sp.get(k); if (v) init[k] = v; });
    return init;
  });
  const [limit, setLimit] = useState(50);
  // Keep the URL shareable without adding history entries on every keystroke.
  useEffect(() => {
    const qs = filterQuery(Object.fromEntries(Object.entries(f).filter(([k]) => !k.startsWith("date"))));
    router.replace(`${window.location.pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [f]); // eslint-disable-line react-hooks/exhaustive-deps

  const qs = filterQuery({ ...f, ...fixed });
  const list = useApi<{ total: number; items: ComplaintListItem[] }>(`/api/authority/complaints?limit=${limit}&${qs}`, [qs, limit]);
  const depts = useApi<any[]>(isAdmin ? "/api/admin/departments" : null);
  const juris = useApi<any[]>(isAdmin ? "/api/admin/jurisdictions?boundaries=false" : null);
  const officers = useApi<any[]>(role === "DEPARTMENT_ADMIN" ? "/api/authority/officers" : null);

  const statusOpts = STATUSES.map((s) => ({ value: s, label: t(STATUS_LABEL[s]) }));
  const catOpts = CATEGORIES.map((c) => ({ value: c, label: t(CATEGORY_LABEL[c]) }));
  const prioOpts = [...["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((p) => ({ value: p, label: t(p) }))];
  const sortOpts = [{ value: "newest", label: t("Newest first") }, { value: "oldest", label: t("Oldest first") }, { value: "priority", label: t("Highest priority first") }, { value: "due", label: t("Nearest deadline first") }];
  const assignOpts = isOfficer
    ? [{ value: "mine", label: t("Assigned to me") }, { value: "awaiting_acceptance", label: t("Awaiting my acceptance") }]
    : [{ value: "unassigned", label: t("Unassigned") }, { value: "assigned", label: t("Assigned") }];

  const defs: FilterDef[] = [
    { key: "q", label: t("Search"), type: "search", placeholder: t("Reference or title") },
    { key: "status", label: t("Status"), type: "select", options: statusOpts },
    ...(fixed.assignment ? [] : [{ key: "assignment", label: isOfficer ? t("View") : t("Assignment"), type: "select" as const, options: assignOpts }]),
    isAdmin ? { key: "department_id", label: t("Department"), type: "select", options: (depts.data || []).map((d) => ({ value: d.id, label: d.name })) }
      : { key: "priority", label: t("Priority"), type: "select", options: prioOpts },
    // advanced
    { key: "status_group", label: t("Open or closed"), type: "select", options: [{ value: "open", label: t("Open") }, { value: "closed", label: t("Closed") }], advanced: true },
    { key: "category", label: t("Category"), type: "select", options: catOpts, advanced: true },
    ...(isAdmin ? [{ key: "priority", label: t("Priority"), type: "select" as const, options: prioOpts, advanced: true },
      { key: "jurisdiction_id", label: t("Jurisdiction"), type: "select" as const, options: (juris.data || []).map((j) => ({ value: j.id, label: j.path })), advanced: true }] : []),
    ...(role === "DEPARTMENT_ADMIN" ? [{ key: "officer_id", label: t("Assigned officer"), type: "select" as const, options: (officers.data || []).map((o) => ({ value: o.officer_id, label: o.full_name })), advanced: true }] : []),
    { key: "due_within_hours", label: t("Deadline within"), type: "select", options: [{ value: "24", label: t("24 hours") }, { value: "72", label: t("3 days") }, { value: "168", label: t("7 days") }], advanced: true },
    { key: "date_from", label: t("Submitted from"), type: "date", advanced: true },
    { key: "date_to", label: t("Submitted to"), type: "date", advanced: true },
    { key: "sort", label: t("Sort"), type: "select", options: sortOpts, advanced: true },
    { key: "overdue", label: t("Overdue only"), type: "toggle", advanced: true },
    { key: "escalated", label: t("Escalated only"), type: "toggle", advanced: true },
  ];

  return (
    <div className="space-y-3">
      <FilterBar defs={defs} value={f} onChange={setF} total={list.data?.total} />
      <ErrorBox error={list.error} onRetry={list.reload} />
      {list.loading && !list.data ? <Spinner /> : list.data && list.data.items.length === 0 ? (
        <EmptyState title={emptyTitle || t("No complaints match")} body={emptyBody || (Object.keys(f).length ? t("Try removing some filters.") : undefined)} />
      ) : list.data && (
        <>
          <ComplaintTable items={list.data.items} hrefBase="/authority/complaints" staff />
          {list.data.total > list.data.items.length && (
            <button type="button" className="text-sm font-medium text-navy-700 underline" onClick={() => setLimit(Math.min(200, limit + 50))}>{t("Show more")}</button>
          )}
        </>
      )}
    </div>
  );
}
