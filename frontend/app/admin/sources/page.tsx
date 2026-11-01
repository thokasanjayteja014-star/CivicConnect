"use client";

import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { ActiveBadge, PageHeader, Stat, TableWrap, Tabs, VerificationBadge, tableCls, tdCls, thCls } from "@/components/ui";
import { Loadable } from "@/features/admin";
import { useApi } from "@/hooks/useApi";

type F = "" | "VERIFIED" | "PENDING_VERIFICATION" | "PROTOTYPE";

export default function SourcesPage() {
  const t = useT();
  const [status, setStatus] = useState<F>("");
  const all = useApi<any>("/api/admin/source-references");
  const q = useApi<any>(`/api/admin/source-references${status ? `?status=${status}` : ""}`, [status]);
  const c = all.data?.counts || {};
  return (
    <div className="space-y-4">
      <PageHeader title={t("Source References")} subtitle={t("Verified means a source reference has been recorded for the record. It is not independent government certification.")} />
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label={t("Verified")} value={c.VERIFIED || 0} tone="ok" />
        <Stat label={t("Pending verification")} value={c.PENDING_VERIFICATION || 0} tone={c.PENDING_VERIFICATION ? "warn" : undefined} />
        <Stat label={t("Prototype")} value={c.PROTOTYPE || 0} />
      </div>
      <Tabs value={status} onChange={setStatus} tabs={[{ id: "" as F, label: t("All") }, { id: "PENDING_VERIFICATION" as F, label: t("Pending verification") }, { id: "VERIFIED" as F, label: t("Verified") }, { id: "PROTOTYPE" as F, label: t("Prototype") }]} />
      <Loadable q={q} empty={(d) => d.items.length === 0} emptyTitle={t("Nothing in this list")}>{(d) => (
        <TableWrap>
          <table className={tableCls}>
            <thead><tr>{["Type", "Name", "Source reference", "Verification", "Status"].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
            <tbody className="divide-y divide-slate-100">{d.items.map((i: any) => (
              <tr key={i.type + i.id}>
                <td className={tdCls + " text-slate-600"}>{t(i.type)}</td>
                <td className={tdCls + " font-medium"}>{i.name}</td>
                <td className={tdCls + " max-w-md break-words text-xs"}>{i.source_reference ? (/^https?:\/\//.test(i.source_reference) ? <a href={i.source_reference} target="_blank" rel="noreferrer" className="text-navy-700 underline">{i.source_reference}</a> : i.source_reference) : <span className="text-slate-400">—</span>}</td>
                <td className={tdCls}><VerificationBadge status={i.verification_status} /></td>
                <td className={tdCls}><ActiveBadge active={i.active} /></td>
              </tr>
            ))}</tbody>
          </table>
        </TableWrap>
      )}</Loadable>
    </div>
  );
}
