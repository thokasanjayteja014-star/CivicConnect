"use client";

import { FilePlus2 } from "lucide-react";
import { useState } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { CATEGORY_LABEL, STATUS_LABEL } from "@/components/labels";
import { useI18n } from "@/components/I18nProvider";
import { EmptyState, ErrorBox, LinkButton, PageHeader, Spinner, Stat, inputCls } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { CATEGORIES, STATUSES, type ComplaintListItem } from "@/types";

export default function CitizenDashboard() {
  const { user, allowed } = useRequireRole(["CITIZEN"]);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [q, setQ] = useState("");
  const { t } = useI18n();
  const qs = new URLSearchParams({ ...(status && { status }), ...(category && { category }), ...(q && { q }) }).toString();
  const summary = useApi<any>(allowed ? "/api/complaints/summary" : null);
  const list = useApi<{ total: number; items: ComplaintListItem[] }>(allowed ? `/api/complaints?${qs}` : null, [qs]);

  if (!allowed) return <Spinner />;
  const s = summary.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={t("Hello, {name}", { name: user!.full_name.split(" ")[0] })}
        subtitle={t("Report an issue in a few steps: describe it, pin the location, review, and confirm. You can follow every update here.")}
        actions={<LinkButton href="/report"><FilePlus2 className="h-4 w-4" /> {t("Report a civic issue")}</LinkButton>}
      />
      <ErrorBox error={summary.error} onRetry={summary.reload} />
      {s && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label={t("Total submitted")} value={s.total} />
          <Stat label={t("Under review")} value={s.under_review} hint={t("Submitted, under review or reopened")} />
          <Stat label={t("In progress")} value={s.in_progress} hint={t("Assigned, in progress or on hold")} />
          <Stat label={t("Awaiting verification")} value={s.awaiting_verification} />
          <Stat label={t("Verified resolved")} value={s.verified_resolved} />
        </div>
      )}

      <section className="space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <h2 className="mr-auto text-lg font-semibold text-navy-900">{t("My complaints")}</h2>
          <label className="text-xs text-slate-600">{t("Search")}
            <input className={inputCls + " mt-1 w-48"} value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Reference or title")} />
          </label>
          <label className="text-xs text-slate-600">{t("Status")}
            <select className={inputCls + " mt-1"} value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("All")}</option>
              {STATUSES.map((x) => <option key={x} value={x}>{t(STATUS_LABEL[x])}</option>)}
            </select>
          </label>
          <label className="text-xs text-slate-600">{t("Category")}
            <select className={inputCls + " mt-1"} value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">{t("All")}</option>
              {CATEGORIES.map((x) => <option key={x} value={x}>{t(CATEGORY_LABEL[x])}</option>)}
            </select>
          </label>
        </div>
        <ErrorBox error={list.error} onRetry={list.reload} />
        {list.loading && !list.data ? <Spinner label={t("Loading your complaints…")} /> :
          list.data && list.data.items.length === 0 ? (
            s?.total === 0 ? (
              <EmptyState title={t("You haven't reported any issues yet")} body={t("When you report a civic issue, it will appear here with its reference ID and live status.")}
                action={<LinkButton href="/report">{t("Report your first issue")}</LinkButton>} />
            ) : <EmptyState title={t("No complaints match these filters")} />
          ) : list.data && <ComplaintTable items={list.data.items} hrefBase="/complaints" />}
      </section>
    </div>
  );
}
