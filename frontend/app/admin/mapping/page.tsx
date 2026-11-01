"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { ActiveBadge, Button, Field, Modal, PageHeader, TableWrap, inputCls, tableCls, tdCls, thCls } from "@/components/ui";
import { DeleteControl, Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

type U = {
  id: string; department_id: string; department_name: string; department_active: boolean; jurisdiction_id: string;
  jurisdiction_name: string; jurisdiction_path: string; active: boolean; administrators: number; officers: number; label: string;
};

export default function MappingPage() {
  const t = useT();
  const [dept, setDept] = useState("");
  const q = useApi<U[]>(`/api/admin/units${dept ? `?department_id=${dept}` : ""}`, [dept]);
  const depts = useApi<any[]>("/api/admin/departments");
  const juris = useApi<any[]>("/api/admin/jurisdictions?boundaries=false");
  const [adding, setAdding] = useState(false);
  const s = useSubmit();
  const toggle = (u: U) => s.run(async () => { await api(`/api/admin/units/${u.id}`, { method: "PATCH", body: { active: !u.active } }); q.reload(); },
    u.active ? "Mapping deactivated." : "Mapping activated.");

  return (
    <div className="space-y-4">
      <PageHeader title={t("Department–Jurisdiction Mapping")}
        subtitle={t("A mapping activates a department in a jurisdiction and creates its own unit there, with its own administrators, officers and complaints. A unit also covers every sub-jurisdiction below it.")}
        actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" /> {t("Add mapping")}</Button>} />
      <Feedback s={s} />
      <select aria-label={t("Filter by department")} className={inputCls + " max-w-xs"} value={dept} onChange={(e) => setDept(e.target.value)}>
        <option value="">{t("All departments")}</option>
        {(depts.data || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
      </select>
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No mappings yet")} emptyBody={t("Map a registered department to the jurisdiction where it operates, for example Roads → Municipal Corporation.")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Department", "Jurisdiction", "Administrators", "Officers", "Status", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((u) => (
                  <tr key={u.id} className={u.active ? "" : "bg-slate-50 text-slate-500"}>
                    <td className={tdCls + " font-medium text-slate-900"}>{u.department_name}{!u.department_active && <span className="ml-1 text-xs font-normal text-slate-500">({t("department inactive")})</span>}</td>
                    <td className={tdCls}>{u.jurisdiction_path}</td>
                    <td className={tdCls}>{u.administrators || <span className="text-amber-700">0</span>}</td>
                    <td className={tdCls}>{u.officers || <span className="text-amber-700">0</span>}</td>
                    <td className={tdCls}><ActiveBadge active={u.active} /></td>
                    <td className={tdCls + " whitespace-nowrap text-right"}>
                      <Link href={`/admin/users?unit_id=${u.id}`} className="mr-2 text-xs font-medium text-navy-700 underline">{t("Personnel")}</Link>
                      <Button variant="ghost" size="sm" onClick={() => toggle(u)}>{u.active ? t("Deactivate") : t("Activate")}</Button>
                      <DeleteControl kind="mapping" path={`/api/admin/units/${u.id}`} name={u.label} onDeleted={q.reload} active={u.active}
                        onDeactivate={async () => { await api(`/api/admin/units/${u.id}`, { method: "PATCH", body: { active: false } }); q.reload(); }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {adding && <AddMapping depts={depts.data || []} juris={juris.data || []} onClose={() => setAdding(false)} onSaved={() => { setAdding(false); q.reload(); }} />}
    </div>
  );
}

function AddMapping({ depts, juris, onClose, onSaved }: { depts: any[]; juris: any[]; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [form, setForm] = useState({ department_id: "", jurisdiction_id: "" });
  const s = useSubmit();
  return (
    <Modal open title={t("Add mapping")} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button>
        <Button loading={s.busy} disabled={!form.department_id || !form.jurisdiction_id} onClick={() => s.run(async () => { await api("/api/admin/units", { body: form }); onSaved(); })}>{t("Save")}</Button></>}>
      <Feedback s={s} />
      <Field label={t("Department")} htmlFor="md" required>
        <select id="md" className={inputCls} value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
          <option value="">{t("Choose…")}</option>{depts.filter((d) => d.active).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </Field>
      <Field label={t("Jurisdiction")} htmlFor="mj" required hint={t("The department will handle complaints in this jurisdiction and all of its sub-jurisdictions, unless a closer unit exists.")}>
        <select id="mj" className={inputCls} value={form.jurisdiction_id} onChange={(e) => setForm({ ...form, jurisdiction_id: e.target.value })}>
          <option value="">{t("Choose…")}</option>{juris.filter((j) => j.active).map((j) => <option key={j.id} value={j.id}>{j.path}</option>)}
        </select>
      </Field>
    </Modal>
  );
}
