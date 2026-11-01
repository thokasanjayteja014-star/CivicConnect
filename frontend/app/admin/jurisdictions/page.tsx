"use client";

import { MapPin, Pencil, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useT } from "@/components/I18nProvider";
import { JURISDICTION_TYPE_LABEL } from "@/components/labels";
import {
  ActiveBadge, Badge, Button, Checkbox, Field, IconButton, Modal, PageHeader, TableWrap, VerificationBadge,
  inputCls, tableCls, tdCls, thCls,
} from "@/components/ui";
import { BoundaryEditor, DeleteControl, Feedback, Loadable, ringsOf, useSubmit, type Rings } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

type J = {
  id: string; name: string; jurisdiction_type: string; parent_id: string | null; description: string | null; active: boolean;
  verification_status: string; is_prototype: boolean; source_reference: string | null; depth: number; path: string;
  departments: { id: string; name: string; unit_id: string; active: boolean }[]; has_boundary: boolean; boundary: any;
};

const EMPTY = { name: "", jurisdiction_type: "WARD", parent_id: "", description: "", source_reference: "", is_prototype: false, active: true };

export default function JurisdictionsPage() {
  const t = useT();
  const q = useApi<J[]>("/api/admin/jurisdictions");
  const types = useApi<string[]>("/api/admin/jurisdiction-types");
  const [editing, setEditing] = useState<J | "new" | null>(null);
  const [filter, setFilter] = useState("");
  const s = useSubmit();

  const rows = useMemo(() => (q.data || []).filter((j) => !filter || j.path.toLowerCase().includes(filter.toLowerCase())), [q.data, filter]);
  const toggle = (j: J) => s.run(async () => { await api(`/api/admin/jurisdictions/${j.id}`, { method: "PATCH", body: { active: !j.active } }); q.reload(); },
    j.active ? "Jurisdiction deactivated." : "Jurisdiction activated.");

  return (
    <div className="space-y-4">
      <PageHeader title={t("Jurisdiction Management")}
        subtitle={t("Build the administrative hierarchy (state, district, municipality, ward, village…). Any number of levels is supported.")}
        actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> {t("Add jurisdiction")}</Button>} />
      <Feedback s={s} />
      <input aria-label={t("Search jurisdictions")} className={inputCls + " max-w-sm"} placeholder={t("Search jurisdictions")} value={filter} onChange={(e) => setFilter(e.target.value)} />
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No jurisdictions yet")} emptyBody={t("Start with the top level (for example the state), then add districts, municipalities and wards under it.")}>
        {() => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Name", "Type", "Departments operating", "Boundary", "Verification", "Status", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((j) => (
                  <tr key={j.id} className={j.active ? "" : "bg-slate-50 text-slate-500"}>
                    <td className={tdCls}>
                      <div style={{ paddingLeft: filter ? 0 : j.depth * 20 }} className="flex items-center gap-1.5">
                        {j.depth > 0 && !filter && <span className="text-slate-300" aria-hidden>└</span>}
                        <span className="font-medium text-slate-900">{j.name}</span>
                      </div>
                      {filter && <div className="text-xs text-slate-500">{j.path}</div>}
                    </td>
                    <td className={tdCls}><Badge>{t(JURISDICTION_TYPE_LABEL[j.jurisdiction_type] || j.jurisdiction_type)}</Badge></td>
                    <td className={tdCls + " text-xs"}>{j.departments.length ? j.departments.map((d) => d.name).join(", ") : <span className="text-slate-400">—</span>}</td>
                    <td className={tdCls}>{j.has_boundary ? <MapPin className="h-4 w-4 text-navy-600" aria-label={t("Boundary drawn")} /> : <span className="text-xs text-slate-400">{t("None")}</span>}</td>
                    <td className={tdCls}><VerificationBadge status={j.verification_status} /></td>
                    <td className={tdCls}><ActiveBadge active={j.active} /></td>
                    <td className={tdCls + " whitespace-nowrap text-right"}>
                      <IconButton label={t("Edit")} onClick={() => setEditing(j)}><Pencil className="h-4 w-4" /></IconButton>
                      <Button variant="ghost" size="sm" onClick={() => toggle(j)}>{j.active ? t("Deactivate") : t("Activate")}</Button>
                      <DeleteControl kind="jurisdiction" path={`/api/admin/jurisdictions/${j.id}`} name={j.path} onDeleted={q.reload} active={j.active}
                        onDeactivate={async () => { await api(`/api/admin/jurisdictions/${j.id}`, { method: "PATCH", body: { active: false } }); q.reload(); }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {editing && <JurisdictionForm all={q.data || []} types={types.data || Object.keys(JURISDICTION_TYPE_LABEL)} initial={editing === "new" ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); q.reload(); }} />}
    </div>
  );
}

function JurisdictionForm({ all, types, initial, onClose, onSaved }: { all: J[]; types: string[]; initial: J | null; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [form, setForm] = useState(initial ? {
    name: initial.name, jurisdiction_type: initial.jurisdiction_type, parent_id: initial.parent_id || "", description: initial.description || "",
    source_reference: initial.source_reference || "", is_prototype: initial.is_prototype, active: initial.active,
  } : EMPTY);
  const [boundary, setBoundary] = useState<any | undefined>(undefined);
  const s = useSubmit();
  const existing: Rings = all.filter((j) => j.boundary && j.id !== initial?.id).map((j) => ringsOf(j.name, j.boundary)!).filter(Boolean);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm({ ...form, [k]: e.target.value });

  async function save() {
    if (boundary?.invalid) throw { message: t("The GeoJSON could not be read.") };
    const body: any = { ...form, parent_id: form.parent_id || null, description: form.description || null, source_reference: form.source_reference || null };
    if (boundary !== undefined) body.boundary = boundary;
    if (initial) await api(`/api/admin/jurisdictions/${initial.id}`, { method: "PATCH", body });
    else await api("/api/admin/jurisdictions", { body });
    onSaved();
  }

  return (
    <Modal open title={initial ? t("Edit jurisdiction") : t("Add jurisdiction")} onClose={onClose} width="max-w-3xl"
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button><Button loading={s.busy} disabled={form.name.trim().length < 2} onClick={() => s.run(save)}>{t("Save")}</Button></>}>
      <Feedback s={s} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("Name")} htmlFor="jn" required><input id="jn" className={inputCls} value={form.name} onChange={set("name")} placeholder={t("e.g. Ward 4 – Gandhi Nagar")} /></Field>
        <Field label={t("Type")} htmlFor="jt"><select id="jt" className={inputCls} value={form.jurisdiction_type} onChange={set("jurisdiction_type")}>
          {types.map((x) => <option key={x} value={x}>{t(JURISDICTION_TYPE_LABEL[x] || x)}</option>)}</select></Field>
        <Field label={t("Parent jurisdiction")} htmlFor="jp" hint={t("Leave empty for a top-level jurisdiction.")}>
          <select id="jp" className={inputCls} value={form.parent_id} onChange={set("parent_id")}>
            <option value="">{t("None (top level)")}</option>
            {all.filter((j) => j.id !== initial?.id).map((j) => <option key={j.id} value={j.id}>{j.path}</option>)}
          </select>
        </Field>
        <Field label={t("Source reference")} htmlFor="js" hint={t("Gazette notification, government order or official URL.")}>
          <input id="js" className={inputCls} value={form.source_reference} onChange={set("source_reference")} />
        </Field>
      </div>
      <Field label={t("Description")} htmlFor="jd"><textarea id="jd" rows={2} className={inputCls} value={form.description} onChange={set("description")} /></Field>
      <Checkbox label={t("Prototype record")} hint={t("Tick only for sample or test data.")} checked={form.is_prototype} onChange={(v) => setForm({ ...form, is_prototype: v })} />
      <div>
        <p className="mb-1 text-sm font-medium text-slate-800">{t("Boundary (optional)")}</p>
        <p className="mb-2 text-xs text-slate-500">{t("Complaints are matched to the deepest jurisdiction whose boundary contains their location. Levels without a boundary are reached through their sub-jurisdictions.")}</p>
        <BoundaryEditor existing={existing} onChange={setBoundary} initial={initial?.boundary} />
      </div>
    </Modal>
  );
}
