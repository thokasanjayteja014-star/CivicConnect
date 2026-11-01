"use client";

import Link from "next/link";
import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { Card, ErrorBox, Notice, PageHeader, Spinner, Stat, TableWrap, tableCls, tdCls, thCls } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import type { ComplaintListItem } from "@/types";

export default function AuthorityOverview() {
  const t = useT();
  const { user } = useAuth();
  const officer = user?.role === "OFFICER";
  const admin = user?.role === "SYSTEM_ADMIN";
  const dash = useApi<any>("/api/authority/dashboard");
  const upcoming = useApi<{ total: number; items: ComplaintListItem[] }>(
    officer ? "/api/authority/complaints?assignment=mine&status_group=open&sort=due&limit=8" : "/api/authority/complaints?status_group=open&sort=due&limit=8");
  const verify = useApi<{ total: number; items: ComplaintListItem[] }>(
    officer ? "/api/authority/complaints?assignment=mine&status=RESOLVED_AWAITING_VERIFICATION&sort=oldest&limit=8" : "/api/authority/complaints?status=RESOLVED_AWAITING_VERIFICATION&sort=oldest&limit=8");
  const d = dash.data;
  const unitLabel = d?.unit ? `${d.unit.department} · ${d.unit.jurisdiction_path}` : admin ? t("All departments") : "";

  return (
    <div className="space-y-5">
      <PageHeader title={officer ? t("My work") : t("Department overview")} subtitle={unitLabel} />
      {!admin && !user?.unit_id && <Notice tone="warn">{t("Your account is not linked to a department unit yet. Ask the main administration to configure it.")}</Notice>}
      <ErrorBox error={dash.error} onRetry={dash.reload} />
      {!d ? <Spinner /> : officer ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label={t("Assigned to me")} value={d.assigned_to_me} href="/authority/complaints?assignment=mine" />
          <Stat label={t("Awaiting my acceptance")} value={d.awaiting_acceptance} tone={d.awaiting_acceptance ? "warn" : undefined} href="/authority/complaints?assignment=awaiting_acceptance" />
          <Stat label={t("Overdue")} value={d.my_overdue} tone={d.my_overdue ? "danger" : undefined} href="/authority/complaints?assignment=mine&overdue=true" />
          <Stat label={t("Awaiting verification")} value={d.awaiting_verification} hint={t("Resolved by you, pending review")} href="/authority/complaints?assignment=mine&status=RESOLVED_AWAITING_VERIFICATION" />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          <Stat label={t("Open complaints")} value={d.total - d.verified_resolved - d.rejected - d.awaiting_verification} href="/authority/complaints?status_group=open" />
          <Stat label={t("Awaiting assignment")} value={d.awaiting_assignment} tone={d.awaiting_assignment ? "warn" : undefined} href="/authority/queue" />
          <Stat label={t("In progress")} value={d.assigned + d.in_progress} hint={t("{n} on hold", { n: d.on_hold })} />
          <Stat label={t("Awaiting verification")} value={d.awaiting_verification} tone={d.awaiting_verification ? "warn" : undefined} href="/authority/complaints?status=RESOLVED_AWAITING_VERIFICATION" />
          <Stat label={t("Overdue")} value={d.overdue} tone={d.overdue ? "danger" : undefined} href="/authority/complaints?overdue=true" />
          <Stat label={t("Escalated")} value={d.escalated} tone={d.escalated ? "warn" : undefined} href="/authority/escalations" />
          <Stat label={t("Reopening requests")} value={d.pending_reopen_reviews} href="/authority/reopen" />
          <Stat label={t("Safety reviews")} value={d.prompt_safety_reviews} tone={d.prompt_safety_reviews ? "danger" : undefined} hint={t("Possible immediate danger")} />
          <Stat label={t("Verified resolved")} value={d.verified_resolved} tone="ok" />
          <Stat label={t("Total handled")} value={d.total} />
        </div>
      )}

      {verify.data && verify.data.items.length > 0 && (
        <Card title={officer ? t("Resolved by you, awaiting verification") : t("Waiting for your verification")}
          subtitle={officer ? t("Your department administrator verifies resolutions.") : t("Open each complaint, review the evidence and the citizen's response, then approve or reject under Verify resolution.")}
          padded={false} actions={<Link href="/authority/complaints?status=RESOLVED_AWAITING_VERIFICATION" className="text-xs font-medium text-navy-700 underline">{t("View all")}</Link>}>
          <ComplaintTable items={verify.data.items} hrefBase="/authority/complaints" staff />
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-3">
        <Card title={officer ? t("My open complaints, nearest deadline first") : t("Open complaints, nearest deadline first")} className="xl:col-span-2" padded={false}
          actions={<Link href="/authority/complaints" className="text-xs font-medium text-navy-700 underline">{t("View all")}</Link>}>
          {upcoming.loading && !upcoming.data ? <Spinner /> : upcoming.data?.items.length ? <ComplaintTable items={upcoming.data.items} hrefBase="/authority/complaints" staff />
            : <p className="p-4 text-sm text-slate-500">{t("No open complaints.")}</p>}
        </Card>
        {!officer && d?.officer_workload && (
          <Card title={t("Officer workload")} padded={false} actions={!admin && <Link href="/authority/officers" className="text-xs font-medium text-navy-700 underline">{t("Details")}</Link>}>
            {d.officer_workload.length === 0 ? <p className="p-4 text-sm text-slate-500">{t("No officers in this unit yet.")}</p> : (
              <TableWrap><table className={tableCls}>
                <thead><tr><th className={thCls}>{t("Officer")}</th><th className={thCls}>{t("Active")}</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{d.officer_workload.map((o: any) => (
                  <tr key={o.officer_id}><td className={tdCls}>{o.full_name}<div className="text-xs text-slate-500">{o.designation}</div></td><td className={tdCls + " font-semibold tabular-nums"}>{o.active_assignments}</td></tr>
                ))}</tbody>
              </table></TableWrap>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
