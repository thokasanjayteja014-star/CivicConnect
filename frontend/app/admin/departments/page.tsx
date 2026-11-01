"use client";

import { Pencil, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL } from "@/components/labels";
import {
  ActiveBadge, Button, Checkbox, Field, IconButton, Modal, PageHeader, TableWrap, VerificationBadge, inputCls, tableCls, tdCls, thCls,
} from "@/components/ui";
import { DeleteControl, Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

type D = {
  id: string; name: string; description: string | null; category: string | null; active: boolean; verification_status: string;
  is_prototype: boolean; source_reference: string | null; supported_categories: string[]; personnel_count: number;
  units: { id: string; jurisdiction_name: string; active: boolean }[];
};

export default function DepartmentsPage() {
  const t = useT();
  const q = useApi<D[]>("/api/admin/departments");
  const [editing, setEditing] = useState<D | "new" | null>(null);
  const s = useSubmit();
  const toggle = (d: D) => s.run(async () => { await api(`/api/admin/departments/${d.id}`, { method: "PATCH", body: { active: !d.active } }); q.reload(); },
    d.active ? "Department deactivated." : "Department activated.");

  return (
    <div className="space-y-4">
      <PageHeader title={t("Department Registry")}
        subtitle={t("Each department is registered once. Activate it in specific jurisdictions under Department–Jurisdiction Mapping.")}
        actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> {t("Register department")}</Button>} />
      <Feedback s={s} />
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No departments registered")} emptyBody={t("Register the departments that handle civic complaints, for example Roads, Water Supply or Sanitation.")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Department", "Category", "Responsibilities", "Operating in", "Personnel", "Verification", "Status", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((d) => (
                  <tr key={d.id} className={d.active ? "" : "bg-slate-50 text-slate-500"}>
                    <td className={tdCls}><div className="font-medium text-slate-900">{d.name}</div>{d.description && <div className="max-w-xs text-xs text-slate-500">{d.description}</div>}</td>
                    <td className={tdCls}>{d.category || "—"}</td>
                    <td className={tdCls + " text-xs"}>{d.supported_categories.length ? d.supported_categories.map((c) => t(CATEGORY_LABEL[c] || c)).join(", ") : <Link href="/admin/responsibilities" className="text-navy-700 underline">{t("Add")}</Link>}</td>
                    <td className={tdCls + " text-xs"}>{d.units.length ? d.units.map((u) => u.jurisdiction_name + (u.active ? "" : ` (${t("inactive")})`)).join(", ") : <Link href="/admin/mapping" className="text-navy-700 underline">{t("Map to a jurisdiction")}</Link>}</td>
                    <td className={tdCls}>{d.personnel_count}</td>
                    <td className={tdCls}><VerificationBadge status={d.verification_status} /></td>
                    <td className={tdCls}><ActiveBadge active={d.active} /></td>
                    <td className={tdCls + " whitespace-nowrap text-right"}>
                      <IconButton label={t("Edit")} onClick={() => setEditing(d)}><Pencil className="h-4 w-4" /></IconButton>
                      <Button variant="ghost" size="sm" onClick={() => toggle(d)}>{d.active ? t("Deactivate") : t("Activate")}</Button>
                      <DeleteControl kind="department" path={`/api/admin/departments/${d.id}`} name={d.name} onDeleted={q.reload} active={d.active}
                        onDeactivate={async () => { await api(`/api/admin/departments/${d.id}`, { method: "PATCH", body: { active: false } }); q.reload(); }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {editing && <DepartmentForm initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); q.reload(); }} />}
    </div>
  );
}

function DepartmentForm({ initial, onClose, onSaved }: { initial: D | null; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [form, setForm] = useState({
    name: initial?.name || "", category: initial?.category || "", description: initial?.description || "",
    source_reference: initial?.source_reference || "", is_prototype: initial?.is_prototype ?? false,
  });
  const s = useSubmit();
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });
  async function save() {
    const body = { ...form, category: form.category || null, description: form.description || null, source_reference: form.source_reference || null };
    if (initial) await api(`/api/admin/departments/${initial.id}`, { method: "PATCH", body });
    else await api("/api/admin/departments", { body });
    onSaved();
  }
  return (
    <Modal open title={initial ? t("Edit department") : t("Register department")} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button><Button loading={s.busy} disabled={form.name.trim().length < 2} onClick={() => s.run(save)}>{t("Save")}</Button></>}>
      <Feedback s={s} />
      <Field label={t("Department name")} htmlFor="dn" required><input id="dn" className={inputCls} value={form.name} onChange={set("name")} placeholder={t("e.g. Roads & Infrastructure")} /></Field>
      <Field label={t("Category")} htmlFor="dc" hint={t("A grouping such as Engineering, Utilities or Public health.")}><input id="dc" className={inputCls} value={form.category} onChange={set("category")} /></Field>
      <Field label={t("Description")} htmlFor="dd"><textarea id="dd" rows={2} className={inputCls} value={form.description} onChange={set("description")} /></Field>
      <Field label={t("Source reference")} htmlFor="ds" hint={t("Act, government order or official URL that establishes this department.")}><input id="ds" className={inputCls} value={form.source_reference} onChange={set("source_reference")} /></Field>
      <Checkbox label={t("Prototype record")} hint={t("Tick only for sample or test data.")} checked={form.is_prototype} onChange={(v) => setForm({ ...form, is_prototype: v })} />
    </Modal>
  );
}
