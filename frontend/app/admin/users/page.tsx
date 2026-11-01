"use client";

import { Pencil, Plus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { useT } from "@/components/I18nProvider";
import { ROLE_LABEL } from "@/components/labels";
import {
  Badge, Button, Checkbox, Field, FilterBar, IconButton, Modal, PageHeader, Spinner, TableWrap, filterQuery, inputCls, tableCls, tdCls, thCls,
} from "@/components/ui";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

type Unit = { id: string; label: string; jurisdiction_id: string; active: boolean };
type J = { id: string; name: string; parent_id: string | null; path: string; depth: number };

function subtree(all: J[], rootId: string | undefined): J[] {
  if (!rootId) return [];
  const ids = new Set([rootId]);
  let grew = true;
  while (grew) { grew = false; for (const j of all) if (j.parent_id && ids.has(j.parent_id) && !ids.has(j.id)) { ids.add(j.id); grew = true; } }
  return all.filter((j) => ids.has(j.id));
}

export default function UsersPage() {
  return <Suspense fallback={<Spinner />}><Users /></Suspense>;
}

function Users() {
  const t = useT();
  const sp = useSearchParams();
  const [f, setF] = useState<Record<string, string>>(sp.get("unit_id") ? { unit_id: sp.get("unit_id")! } : {});
  const qs = filterQuery(f);
  const q = useApi<any>(`/api/admin/users?limit=200&${qs}`, [qs]);
  const units = useApi<Unit[]>("/api/admin/units");
  const juris = useApi<J[]>("/api/admin/jurisdictions?boundaries=false");
  const [editing, setEditing] = useState<any | "new" | null>(null);
  const s = useSubmit();

  return (
    <div className="space-y-4">
      <PageHeader title={t("User & Officer Management")}
        subtitle={t("Create department administrators and officers for a department unit, and set each officer's operational areas.")}
        actions={<Button onClick={() => setEditing("new")}><Plus className="h-4 w-4" /> {t("Add staff account")}</Button>} />
      <Feedback s={s} />
      <FilterBar value={f} onChange={setF} total={q.data?.total}
        defs={[
          { key: "q", label: t("Search"), type: "search", placeholder: t("Name or email") },
          { key: "role", label: t("Role"), type: "select", options: Object.entries(ROLE_LABEL).map(([v, l]) => ({ value: v, label: t(l) })) },
          { key: "unit_id", label: t("Department unit"), type: "select", options: (units.data || []).map((u) => ({ value: u.id, label: u.label })) },
        ]} />
      <Loadable q={q} empty={(d) => d.items.length === 0} emptyTitle={t("No accounts match")}>
        {(d) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Name", "Role", "Department unit", "Operational areas", "Account", ""].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">
                {d.items.map((u: any) => (
                  <tr key={u.id} className={u.account_status === "ACTIVE" ? "" : "bg-slate-50 text-slate-500"}>
                    <td className={tdCls}><div className="font-medium text-slate-900">{u.full_name}</div><div className="text-xs text-slate-500">{u.email}</div>{u.officer?.designation && <div className="text-xs text-slate-500">{u.officer.designation}</div>}</td>
                    <td className={tdCls}><Badge>{t(ROLE_LABEL[u.role])}</Badge>{u.permissions.includes("VERIFY_RESOLUTION") && u.role === "OFFICER" && <div className="mt-1 text-xs text-slate-500">{t("Can verify resolutions")}</div>}</td>
                    <td className={tdCls}>{u.officer?.unit_label || "—"}{u.officer && !u.officer.active && <div className="text-xs text-amber-700">{t("Removed from duty")}</div>}</td>
                    <td className={tdCls + " text-xs"}>{u.role === "OFFICER" ? (u.officer?.areas?.length ? u.officer.areas.map((a: any) => a.name).join(", ") : t("Whole unit")) : "—"}</td>
                    <td className={tdCls}>{u.account_status === "ACTIVE" ? <Badge className="bg-white text-green-800 ring-green-300">{t("Active")}</Badge> : <Badge className="bg-red-50 text-red-800 ring-red-200">{t("Disabled")}</Badge>}</td>
                    <td className={tdCls + " text-right"}>{u.role !== "CITIZEN" && <IconButton label={t("Edit")} onClick={() => setEditing(u)}><Pencil className="h-4 w-4" /></IconButton>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {editing && <StaffForm initial={editing === "new" ? null : editing} units={units.data || []} juris={juris.data || []}
        onClose={() => setEditing(null)} onSaved={() => { setEditing(null); q.reload(); }} />}
    </div>
  );
}

function StaffForm({ initial, units, juris, onClose, onSaved }: { initial: any | null; units: Unit[]; juris: J[]; onClose: () => void; onSaved: () => void }) {
  const t = useT();
  const [form, setForm] = useState({
    full_name: initial?.full_name || "", email: initial?.email || "", password: "", role: initial?.role || "OFFICER",
    unit_id: initial?.officer?.unit_id || "", designation: initial?.officer?.designation || "",
    areas: (initial?.officer?.areas || []).map((a: any) => a.jurisdiction_id) as string[],
    account_status: initial?.account_status || "ACTIVE", officer_active: initial?.officer?.active ?? true,
    can_verify: (initial?.permissions || []).includes("VERIFY_RESOLUTION"),
  });
  const s = useSubmit();
  const unit = units.find((u) => u.id === form.unit_id);
  const areaOptions = useMemo(() => subtree(juris, unit?.jurisdiction_id), [juris, unit?.jurisdiction_id]);
  const staffRole = form.role === "OFFICER" || form.role === "DEPARTMENT_ADMIN";

  async function save() {
    if (initial) {
      const had = (initial.permissions || []).includes("VERIFY_RESOLUTION");
      await api(`/api/admin/users/${initial.id}`, { method: "PATCH", body: {
        full_name: form.full_name, role: form.role, account_status: form.account_status, designation: form.designation || null,
        unit_id: staffRole ? form.unit_id || null : null, officer_active: staffRole ? form.officer_active : undefined,
        area_jurisdiction_ids: form.role === "OFFICER" ? form.areas : undefined,
        grant_permissions: form.role === "OFFICER" && form.can_verify && !had ? ["VERIFY_RESOLUTION"] : [],
        revoke_permissions: had && (!form.can_verify || form.role !== "OFFICER") ? ["VERIFY_RESOLUTION"] : [],
      } });
    } else {
      await api("/api/admin/users", { body: {
        full_name: form.full_name, email: form.email, password: form.password, role: form.role, designation: form.designation || null,
        unit_id: staffRole ? form.unit_id : null, area_jurisdiction_ids: form.role === "OFFICER" ? form.areas : [],
      } });
    }
    onSaved();
  }

  return (
    <Modal open title={initial ? t("Edit staff account") : t("Add staff account")} onClose={onClose} width="max-w-2xl"
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button>
        <Button loading={s.busy} disabled={form.full_name.trim().length < 2 || (!initial && (!form.email || form.password.length < 8)) || (staffRole && !form.unit_id)} onClick={() => s.run(save)}>{t("Save")}</Button></>}>
      <Feedback s={s} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("Full name")} htmlFor="uf" required><input id="uf" className={inputCls} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
        <Field label={t("Email")} htmlFor="ue" required><input id="ue" type="email" disabled={!!initial} className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        {!initial && <Field label={t("Initial password")} htmlFor="up" required hint={t("At least 8 characters. Share it privately.")}><input id="up" type="password" autoComplete="new-password" className={inputCls} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>}
        <Field label={t("Role")} htmlFor="ur">
          <select id="ur" className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"].map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
          </select>
        </Field>
        {staffRole && <>
          <Field label={t("Department unit")} htmlFor="uu" required hint={t("Department and jurisdiction this person works for.")}>
            <select id="uu" className={inputCls} value={form.unit_id} onChange={(e) => setForm({ ...form, unit_id: e.target.value, areas: [] })}>
              <option value="">{t("Choose…")}</option>{units.filter((u) => u.active || u.id === form.unit_id).map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}
            </select>
          </Field>
          <Field label={t("Designation")} htmlFor="ud"><input id="ud" className={inputCls} value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} placeholder={t("e.g. Assistant Engineer")} /></Field>
        </>}
      </div>
      {form.role === "OFFICER" && unit && (
        <fieldset className="rounded-md border border-slate-200 p-3">
          <legend className="px-1 text-sm font-medium text-slate-800">{t("Operational areas")}</legend>
          <p className="mb-2 text-xs text-slate-500">{t("Complaints located in these areas (and their sub-areas) are assigned to this officer automatically. Leave all unticked to cover the whole unit.")}</p>
          <div className="grid max-h-56 gap-1 overflow-y-auto sm:grid-cols-2">
            {areaOptions.map((j) => (
              <Checkbox key={j.id} label={j.name} checked={form.areas.includes(j.id)}
                onChange={(c) => setForm({ ...form, areas: c ? [...form.areas, j.id] : form.areas.filter((x) => x !== j.id) })} />
            ))}
          </div>
        </fieldset>
      )}
      {initial && (
        <div className="space-y-2 border-t border-slate-200 pt-3">
          {form.role === "OFFICER" && <Checkbox label={t("Can verify resolutions")} hint={t("Normally only department administrators verify resolved work.")} checked={form.can_verify} onChange={(v) => setForm({ ...form, can_verify: v })} />}
          {staffRole && <Checkbox label={t("On duty")} hint={t("Officers off duty receive no new automatic assignments.")} checked={form.officer_active} onChange={(v) => setForm({ ...form, officer_active: v })} />}
          <Checkbox label={t("Account enabled")} checked={form.account_status === "ACTIVE"} onChange={(v) => setForm({ ...form, account_status: v ? "ACTIVE" : "DISABLED" })} />
        </div>
      )}
    </Modal>
  );
}
