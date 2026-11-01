"use client";

import Link from "next/link";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { REASON_LABEL, fmtDate } from "@/components/labels";
import { Badge, Button, Field, Modal, StatusBadge, TableWrap, Tabs, inputCls, tableCls, tdCls, thCls } from "@/components/ui";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

/** Escalations visible to the current user (scoped by the backend), with resolve actions. */
export function EscalationList() {
  const t = useT();
  const [status, setStatus] = useState<"OPEN" | "RESOLVED">("OPEN");
  const q = useApi<any[]>(`/api/authority/escalations?status=${status}`, [status]);
  const [resolving, setResolving] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const s = useSubmit();
  return (
    <div className="space-y-3">
      <Tabs value={status} onChange={setStatus} tabs={[{ id: "OPEN", label: t("Open") }, { id: "RESOLVED", label: t("Closed") }]} />
      <Feedback s={s} />
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={status === "OPEN" ? t("No open escalations") : t("No closed escalations")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Complaint", "Level", "Reason", "Department unit", "Deadline", "Raised", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((e) => (
                  <tr key={e.id}>
                    <td className={tdCls}>
                      <Link href={`/authority/complaints/${e.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{e.reference_id}</Link>
                      <div className="font-medium text-slate-900">{e.title}</div>
                      <StatusBadge status={e.complaint_status} />
                    </td>
                    <td className={tdCls}><Badge className={e.level === 2 ? "bg-red-50 text-red-800 ring-red-200" : "bg-amber-50 text-amber-800 ring-amber-200"}>
                      {e.level === 2 ? t("Level 2 · Main administration") : t("Level 1 · Department administrator")}</Badge></td>
                    <td className={tdCls}><div className="font-medium">{t(REASON_LABEL[e.reason_code] || e.reason_code)}</div><div className="max-w-xs text-xs text-slate-600">{e.reason}</div>
                      {e.resolution_note && <div className="mt-1 text-xs text-green-800">{t("Closed")}: {e.resolution_note}</div>}</td>
                    <td className={tdCls + " text-xs"}>{e.unit ? `${e.unit.department} — ${e.unit.jurisdiction}` : "—"}</td>
                    <td className={tdCls + " whitespace-nowrap text-xs"}>{fmtDate(e.due_at, false)}</td>
                    <td className={tdCls + " whitespace-nowrap text-xs"}>{fmtDate(e.created_at)}</td>
                    <td className={tdCls + " text-right"}>{e.can_resolve && <Button size="sm" variant="secondary" onClick={() => { setResolving(e); setNote(""); }}>{t("Close escalation")}</Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      <Modal open={!!resolving} title={t("Close escalation")} onClose={() => setResolving(null)}
        footer={<><Button variant="secondary" onClick={() => setResolving(null)}>{t("Cancel")}</Button>
          <Button loading={s.busy} onClick={() => s.run(async () => { await api(`/api/authority/escalations/${resolving.id}/resolve`, { body: { note } }); setResolving(null); q.reload(); }, "Escalation closed.")}>{t("Close escalation")}</Button></>}>
        <p>{t("Record what was done. The complaint itself stays open until its work is resolved.")}</p>
        <Field label={t("Action taken")} htmlFor="en"><textarea id="en" rows={3} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </Modal>
    </div>
  );
}
