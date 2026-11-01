"use client";

import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { Badge, Button, Card, PageHeader, TableWrap, inputCls, tableCls, tdCls, thCls } from "@/components/ui";
import { EscalationList } from "@/features/escalations";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

export default function EscalationsPage() {
  const t = useT();
  return (
    <div className="space-y-5">
      <PageHeader title={t("Escalation Management")}
        subtitle={t("Complaints not resolved within their deadline are escalated automatically: first to the department administrator, then to the main administration. Officers and department administrators can also escalate manually.")} />
      <Policies />
      <Card title={t("Escalations")}><EscalationList /></Card>
    </div>
  );
}

function Policies() {
  const t = useT();
  const q = useApi<any>("/api/admin/escalation-policies");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const s = useSubmit();
  return (
    <Card title={t("Resolution deadlines")} subtitle={t("Time allowed from submission to resolution, by priority. Set these to the authority's own service standards.")}>
      <Feedback s={s} />
      <Loadable q={q}>{(d) => (
        <TableWrap>
          <table className={tableCls}>
            <thead><tr>{["Priority", "Deadline (hours)", "Equivalent", "Source", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {d.policies.filter((p: any) => !p.department_id).map((p: any) => {
                const v = draft[p.priority_level] ?? String(p.resolve_within_hours);
                return (
                  <tr key={p.priority_level}>
                    <td className={tdCls + " font-medium"}>{p.priority_level === "UNSCORED" ? t("Not yet scored") : t(p.priority_level)}</td>
                    <td className={tdCls}><input aria-label={t("Deadline (hours)")} type="number" min={1} className={inputCls + " w-28"} value={v} onChange={(e) => setDraft({ ...draft, [p.priority_level]: e.target.value })} /></td>
                    <td className={tdCls + " text-slate-600"}>{(Number(v) / 24).toFixed(1)} {t("days")}</td>
                    <td className={tdCls}>{p.source === "configured" ? <Badge className="bg-green-50 text-green-800 ring-green-200">{t("Configured")}</Badge> : <Badge>{t("Default")}</Badge>}</td>
                    <td className={tdCls + " text-right"}>
                      <Button size="sm" variant="secondary" disabled={Number(v) === p.resolve_within_hours || Number(v) < 1} onClick={() => s.run(async () => {
                        await api("/api/admin/escalation-policies", { method: "PUT", body: { priority_level: p.priority_level, resolve_within_hours: Number(v) } });
                        setDraft({}); q.reload();
                      })}>{t("Save")}</Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableWrap>
      )}</Loadable>
      <p className="mt-2 text-xs text-slate-500">{t("New deadlines apply to complaints routed after the change.")}</p>
    </Card>
  );
}
