"use client";

import Link from "next/link";
import { useT } from "@/components/I18nProvider";
import { Badge, PageHeader, TableWrap, tableCls, tdCls, thCls } from "@/components/ui";
import { Loadable } from "@/features/admin";
import { useApi } from "@/hooks/useApi";

export default function OfficersPage() {
  const t = useT();
  const q = useApi<any[]>("/api/authority/officers");
  return (
    <div className="space-y-4">
      <PageHeader title={t("Officers & workload")} subtitle={t("Officers in your unit, their operational areas and current active assignments. Officer accounts and areas are managed by the main administration.")} />
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No officers in this unit yet")} emptyBody={t("Ask the main administration to add officers. Until then, complaints wait in the unassigned queue.")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Officer", "Operational areas", "Active assignments", "Status", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">{rows.map((o) => (
                <tr key={o.officer_id}>
                  <td className={tdCls}><div className="font-medium text-slate-900">{o.full_name}</div><div className="text-xs text-slate-500">{o.designation}</div></td>
                  <td className={tdCls + " text-xs"}>{o.areas.length ? o.areas.map((a: any) => a.name).join(", ") : t("Whole unit")}</td>
                  <td className={tdCls}><span className="text-lg font-semibold tabular-nums">{o.active_assignments}</span></td>
                  <td className={tdCls}>{o.eligible ? <Badge className="bg-white text-green-800 ring-green-300">{t("On duty")}</Badge> : <Badge>{t("Off duty")}</Badge>}</td>
                  <td className={tdCls + " text-right"}><Link className="text-xs font-medium text-navy-700 underline" href={`/authority/complaints?officer_id=${o.officer_id}`}>{t("View complaints")}</Link></td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
    </div>
  );
}
