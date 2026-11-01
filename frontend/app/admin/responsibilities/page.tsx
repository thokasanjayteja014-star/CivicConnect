"use client";

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL } from "@/components/labels";
import {
  ActiveBadge, Button, Checkbox, Field, IconButton, Modal, Notice, PageHeader, TableWrap, VerificationBadge, inputCls, tableCls, tdCls, thCls,
} from "@/components/ui";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import { CATEGORIES } from "@/types";

type R = {
  id: string; department_id: string; department_name: string; category: string; name: string | null; description: string | null;
  active: boolean; verification_status: string; is_prototype: boolean; source_reference: string | null;
};

export default function ResponsibilitiesPage() {
  const t = useT();
  const q = useApi<R[]>("/api/admin/responsibilities");
  const depts = useApi<any[]>("/api/admin/departments");
  const [editing, setEditing] = useState<R | "new" | null>(null);
  const [deleting, setDeleting] = useState<R | null>(null);
  const s = useSubmit();
  const save = (r: R, patch: Partial<R>) => s.run(async () => {
    await api("/api/admin/responsibilities", { body: { department_id: r.department_id, category: r.category, name: r.name, description: r.description,
      source_reference: r.source_reference, is_prototype: r.is_prototype, active: r.active, ...patch } });
    q.reload();
  });
  const conflicts = (q.data || []).reduce<Record<string, number>>((a, r) => { if (r.active) a[r.category] = (a[r.category] || 0) + 1; return a; }, {});

  return (
    <div className="space-y-4">
      <PageHeader title={t("Responsibility Management")}
        subtitle={t("Define which department handles each type of complaint. Routing uses only active responsibilities.")}
        actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> {t("Add responsibility")}</Button>} />
      <Feedback s={s} />
      {Object.entries(conflicts).some(([, n]) => n > 1) && (
        <Notice tone="warn">{t("Some categories have more than one active department. Where both operate in the same area, those complaints go to administrative review instead of being routed automatically.")}</Notice>
      )}
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No responsibilities yet")} emptyBody={t("Without responsibilities, complaints cannot be routed and wait in administrative review.")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Complaint category", "Department", "Responsibility", "Verification", "Status", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className={r.active ? "" : "bg-slate-50 text-slate-500"}>
                    <td className={tdCls + " font-medium text-slate-900"}>{t(CATEGORY_LABEL[r.category] || r.category)}{r.active && conflicts[r.category] > 1 && <span className="ml-1 text-xs text-amber-700">({t("shared")})</span>}</td>
                    <td className={tdCls}>{r.department_name}</td>
                    <td className={tdCls}>{r.name || "—"}{r.description && <div className="text-xs text-slate-500">{r.description}</div>}</td>
                    <td className={tdCls}><VerificationBadge status={r.verification_status} /></td>
                    <td className={tdCls}><ActiveBadge active={r.active} /></td>
                    <td className={tdCls + " whitespace-nowrap text-right"}>
                      <IconButton label={t("Edit")} onClick={() => setEditing(r)}><Pencil className="h-4 w-4" /></IconButton>
                      <Button variant="ghost" size="sm" onClick={() => save(r, { active: !r.active })}>{r.active ? t("Deactivate") : t("Activate")}</Button>
                      <IconButton label={t("Delete responsibility")} tone="danger" onClick={() => setDeleting(r)}><Trash2 className="h-4 w-4" /></IconButton>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {editing && <RuleForm depts={depts.data || []} initial={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); q.reload(); }} />}
      <Modal open={!!deleting} title={t("Delete responsibility")} onClose={() => setDeleting(null)}
        footer={<><Button variant="secondary" onClick={() => setDeleting(null)}>{t("Cancel")}</Button>
          <Button variant="danger" loading={s.busy} onClick={() => s.run(async () => { await api(`/api/admin/responsibilities/${deleting!.id}`, { method: "DELETE" }); setDeleting(null); q.reload(); }, "Responsibility deleted.")}>{t("Delete permanently")}</Button></>}>
        {deleting && <p>{t("{dept} will no longer receive new “{cat}” complaints. Existing complaints keep their department.", { dept: deleting.department_name, cat: t(CATEGORY_LABEL[deleting.category]) })}</p>}
      </Modal>
    </div>
  );
}

function RuleForm({ depts, initial, onClose, onSaved }: { depts: any[]; initial: R | null; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [form, setForm] = useState({
    department_id: initial?.department_id || "", category: initial?.category || "ROAD_INFRASTRUCTURE", name: initial?.name || "",
    description: initial?.description || "", source_reference: initial?.source_reference || "", is_prototype: initial?.is_prototype ?? false, active: initial?.active ?? true,
  });
  const s = useSubmit();
  return (
    <Modal open title={initial ? t("Edit responsibility") : t("Add responsibility")} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button>
        <Button loading={s.busy} disabled={!form.department_id} onClick={() => s.run(async () => {
          await api("/api/admin/responsibilities", { body: { ...form, name: form.name || null, description: form.description || null, source_reference: form.source_reference || null } });
          onSaved();
        })}>{t("Save")}</Button></>}>
      <Feedback s={s} />
      <Field label={t("Department")} htmlFor="rd" required>
        <select id="rd" className={inputCls} value={form.department_id} disabled={!!initial} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
          <option value="">{t("Choose…")}</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </Field>
      <Field label={t("Complaint category")} htmlFor="rc">
        <select id="rc" className={inputCls} value={form.category} disabled={!!initial} onChange={(e) => setForm({ ...form, category: e.target.value })}>
          {CATEGORIES.map((c) => <option key={c} value={c}>{t(CATEGORY_LABEL[c])}</option>)}
        </select>
      </Field>
      <Field label={t("Responsibility name")} htmlFor="rn"><input id="rn" className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("e.g. Pothole and road surface repair")} /></Field>
      <Field label={t("Description")} htmlFor="rde"><textarea id="rde" rows={2} className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      <Field label={t("Source reference")} htmlFor="rs"><input id="rs" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
      <Checkbox label={t("Prototype record")} hint={t("Tick only for sample or test data.")} checked={form.is_prototype} onChange={(v) => setForm({ ...form, is_prototype: v })} />
    </Modal>
  );
}
