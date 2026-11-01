"use client";

import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { fmtDate } from "@/components/labels";
import { Button, FilterBar, PageHeader, TableWrap, filterQuery, tableCls, tdCls, thCls } from "@/components/ui";
import { Loadable } from "@/features/admin";
import { useApi } from "@/hooks/useApi";

const ACTIONS = [
  "COMPLAINT_CREATED", "ROUTING_DECISION", "COMPLAINT_ASSIGNED", "COMPLAINT_REASSIGNED", "ASSIGNMENT_ACCEPTED", "STATUS_CHANGED",
  "COMPLAINT_ESCALATED", "ESCALATION_RESOLVED", "EVIDENCE_UPLOADED", "RESOLUTION_VERIFICATION", "REOPEN_REVIEW_DECISION",
  "PUBLIC_ISSUE_CREATED", "PUBLIC_ISSUE_PUBLISHED", "PUBLIC_ISSUE_UNPUBLISHED", "DEPARTMENT_CREATED", "DEPARTMENT_UPDATED",
  "DEPARTMENT_DELETED", "JURISDICTION_CREATED", "JURISDICTION_UPDATED", "JURISDICTION_DELETED", "DEPARTMENT_MAPPED",
  "DEPARTMENT_UNMAPPED", "RESPONSIBILITY_RULE_SAVED", "RESPONSIBILITY_RULE_DELETED", "USER_CREATED", "USER_UPDATED",
  "ESCALATION_POLICY_SAVED", "PRIORITY_CONFIG_CHANGED", "USER_LOGIN",
];
const ENTITIES = ["complaint", "department", "jurisdiction", "department_unit", "responsibility_rule", "user", "public_issue", "escalation_policy", "sensitive_location"];

function humanize(code: string) {
  const s = (code || "").replace(/_/g, " ").toLowerCase();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function summary(l: any): string {
  const d = l.details || {};
  if (d.before && d.after) return "Updated";
  const parts: string[] = [];
  for (const k of ["name", "label", "to", "role", "level", "reason", "category", "routing_status"]) {
    const v = d[k];
    if ((typeof v === "string" || typeof v === "number") && v !== "") parts.push(k === "name" || k === "label" ? String(v) : `${humanize(k)}: ${humanize(String(v))}`);
  }
  return parts.slice(0, 3).join(" · ");
}

export default function AuditPage() {
  const t = useT();
  const [f, setF] = useState<Record<string, string>>({});
  const [limit, setLimit] = useState(100);
  const qs = filterQuery(f);
  const q = useApi<any>(`/api/admin/audit-logs?limit=${limit}&${qs}`, [qs, limit]);
  return (
    <div className="space-y-4">
      <PageHeader title={t("Audit Logs")} subtitle={t("Every change made in CivicConnect: who made it, when, and to what. Entries cannot be edited or deleted.")} />
      <FilterBar value={f} onChange={setF} total={q.data?.total}
        defs={[
          { key: "action", label: t("Action"), type: "select", options: ACTIONS.map((a) => ({ value: a, label: t(humanize(a)) })) },
          { key: "entity_type", label: t("Record type"), type: "select", options: ENTITIES.map((e) => ({ value: e, label: t(humanize(e)) })) },
          { key: "date_from", label: t("From date"), type: "date", advanced: true },
          { key: "date_to", label: t("To date"), type: "date", advanced: true },
        ]} />
      <Loadable q={q} empty={(d) => d.items.length === 0} emptyTitle={t("No entries match")}>{(d) => (
        <>
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["When", "Who", "Action", "Record", "Details"].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">{d.items.map((l: any) => (
                <tr key={l.id}>
                  <td className={tdCls + " whitespace-nowrap text-slate-600"}>{fmtDate(l.created_at)}</td>
                  <td className={tdCls}>{l.actor_name || (l.actor_label?.startsWith("system") ? t("CivicConnect (automatic)") : l.actor_label || "—")}</td>
                  <td className={tdCls + " font-medium"}>{t(humanize(l.action))}</td>
                  <td className={tdCls}>{l.entity_name || <span className="text-slate-500">{t(humanize(l.entity_type || ""))}</span>}</td>
                  <td className={tdCls + " max-w-sm truncate text-slate-500"} title={JSON.stringify(l.details)}>{summary(l)}</td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
          {d.total > d.items.length && <Button variant="secondary" onClick={() => setLimit(Math.min(500, limit + 100))}>{t("Show more")}</Button>}
        </>
      )}</Loadable>
    </div>
  );
}
