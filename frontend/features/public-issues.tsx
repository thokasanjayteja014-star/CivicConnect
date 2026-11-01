"use client";

import { ExternalLink, Plus, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, ISSUE_PROGRESS_LABEL, ISSUE_STATUS_LABEL, fmtDate } from "@/components/labels";
import {
  Badge, Button, Checkbox, Field, KeyValue, Modal, Notice, PageHeader, Spinner, StatusBadge, TableWrap, Tabs, inputCls, tableCls, tdCls, thCls,
} from "@/components/ui";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

const STATUS_STYLE: Record<string, string> = {
  DRAFT: "bg-slate-100 text-slate-700 ring-slate-300",
  VERIFIED: "bg-amber-50 text-amber-800 ring-amber-200",
  PUBLISHED: "bg-green-50 text-green-800 ring-green-200",
  UNPUBLISHED: "bg-slate-100 text-slate-500 ring-slate-300",
};

export function IssueStatusBadge({ status }: { status: string }) {
  const t = useT();
  return <Badge className={STATUS_STYLE[status]}>{t(ISSUE_STATUS_LABEL[status] || status)}</Badge>;
}

type Filter = "" | "DRAFT" | "VERIFIED" | "PUBLISHED" | "UNPUBLISHED";

/** Staff workspace: group complaints into a public issue, verify impact, approve publication. */
export function PublicIssuesManager() {
  const t = useT();
  const sp = useSearchParams();
  const [status, setStatus] = useState<Filter>("");
  const q = useApi<any[]>(`/api/authority/public-issues${status ? `?status=${status}` : ""}`, [status]);
  const [creating, setCreating] = useState<string[] | null>(sp.get("from") ? [sp.get("from")!] : null);
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader title={t("Public Issues")}
        subtitle={t("Publish verified issues of wider public impact so residents can follow progress. Several complaints can be linked to one issue. Citizens' personal details are never shown publicly.")}
        actions={<><Link href="/public" className="inline-flex items-center gap-1 text-sm font-medium text-navy-700 underline"><ExternalLink className="h-4 w-4" /> {t("Public page")}</Link>
          <Button onClick={() => setCreating([])}><Plus className="h-4 w-4" /> {t("New public issue")}</Button></>} />
      <ol className="flex flex-wrap gap-2 text-xs text-slate-600">
        {["Complaints received", "Department reviews and verifies", "Impact assessed", "Administrator approves", "Published for residents"].map((s, i) => (
          <li key={s} className="flex items-center gap-2"><span className="grid h-5 w-5 place-items-center rounded bg-navy-700 text-2xs font-semibold text-white">{i + 1}</span>{t(s)}{i < 4 && <span className="text-slate-300">→</span>}</li>
        ))}
      </ol>
      <Tabs value={status} onChange={setStatus} tabs={[{ id: "" as Filter, label: t("All") }, { id: "DRAFT" as Filter, label: t("Draft") }, { id: "VERIFIED" as Filter, label: t("Awaiting publication") },
        { id: "PUBLISHED" as Filter, label: t("Published") }, { id: "UNPUBLISHED" as Filter, label: t("Unpublished") }]} />
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No public issues here")} emptyBody={t("Create one from related complaints that affect many residents, such as several potholes on the same road.")}>
        {(rows) => (
          <TableWrap>
            <table className={tableCls}>
              <thead><tr>{["Issue", "Department", "Related complaints", "Progress", "Publication", "Last updated"].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">{rows.map((i) => (
                <tr key={i.id} className="cursor-pointer hover:bg-slate-50" onClick={() => setOpenId(i.id)}>
                  <td className={tdCls}><div className="font-medium text-navy-800 underline">{i.title}</div><div className="text-xs text-slate-500">{i.general_location || i.jurisdiction}</div></td>
                  <td className={tdCls}>{i.department}</td>
                  <td className={tdCls}>{i.related_complaints}</td>
                  <td className={tdCls}>{t(ISSUE_PROGRESS_LABEL[i.progress])}</td>
                  <td className={tdCls}><IssueStatusBadge status={i.status} /></td>
                  <td className={tdCls + " whitespace-nowrap text-xs text-slate-600"}>{fmtDate(i.updated_at)}</td>
                </tr>
              ))}</tbody>
            </table>
          </TableWrap>
        )}
      </Loadable>
      {creating && <CreateIssue preselected={creating} onClose={() => setCreating(null)} onCreated={(id) => { setCreating(null); q.reload(); setOpenId(id); }} />}
      {openId && <IssueDetail id={openId} onClose={() => setOpenId(null)} onChanged={q.reload} />}
    </div>
  );
}

function ComplaintPicker({ selected, onChange, exclude = [] }: { selected: string[]; onChange: (v: string[]) => void; exclude?: string[] }) {
  const t = useT();
  const [search, setSearch] = useState("");
  const q = useApi<any>(`/api/authority/complaints?limit=100&sort=newest${search ? `&q=${encodeURIComponent(search)}` : ""}`, [search]);
  const items = (q.data?.items || []).filter((c: any) => c.routing_status === "ROUTED" && !exclude.includes(c.complaint_id));
  return (
    <div className="space-y-2">
      <input aria-label={t("Search complaints")} className={inputCls} placeholder={t("Search by reference or title")} value={search} onChange={(e) => setSearch(e.target.value)} />
      <div className="max-h-64 overflow-y-auto rounded-md border border-slate-200">
        {q.loading && !q.data ? <Spinner /> : items.length === 0 ? <p className="p-3 text-sm text-slate-500">{t("No complaints found.")}</p> : (
          <ul className="divide-y divide-slate-100">{items.map((c: any) => (
            <li key={c.complaint_id} className="px-3 py-2">
              <Checkbox checked={selected.includes(c.complaint_id)} onChange={(v) => onChange(v ? [...selected, c.complaint_id] : selected.filter((x) => x !== c.complaint_id))}
                label={`${c.reference_id} · ${c.title}`} hint={`${c.jurisdiction?.name || ""} ${c.location.landmark ? `· ${c.location.landmark}` : ""} · ${t(CATEGORY_LABEL[c.category])}`} />
            </li>
          ))}</ul>
        )}
      </div>
      <p className="text-xs text-slate-500">{t("{n} selected. All linked complaints must belong to the same department unit.", { n: selected.length })}</p>
    </div>
  );
}

function CreateIssue({ preselected, onClose, onCreated }: { preselected: string[]; onClose: () => void; onCreated: (id: string) => void }) {
  const t = useT();
  const [form, setForm] = useState({ title: "", description: "", general_location: "" });
  const [ids, setIds] = useState<string[]>(preselected);
  const s = useSubmit();
  return (
    <Modal open title={t("New public issue")} onClose={onClose} width="max-w-2xl"
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button>
        <Button loading={s.busy} disabled={form.title.trim().length < 5 || form.description.trim().length < 10 || ids.length === 0}
          onClick={() => s.run(async () => { const r = await api("/api/authority/public-issues", { body: { ...form, general_location: form.general_location || null, complaint_ids: ids } }); onCreated(r.id); })}>{t("Create draft")}</Button></>}>
      <Feedback s={s} />
      <Notice>{t("Write for the public. Do not include names, phone numbers, house numbers or other personal details.")}</Notice>
      <Field label={t("Public title")} htmlFor="it" required><input id="it" className={inputCls} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder={t("e.g. Potholes on Station Road")} /></Field>
      <Field label={t("Public description")} htmlFor="id" required><textarea id="id" rows={3} className={inputCls} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
      <Field label={t("General location")} htmlFor="il" hint={t("A street or area name, not an exact address.")}><input id="il" className={inputCls} value={form.general_location} onChange={(e) => setForm({ ...form, general_location: e.target.value })} /></Field>
      <div><p className="mb-1 text-sm font-medium text-slate-800">{t("Related complaints")}</p><ComplaintPicker selected={ids} onChange={setIds} /></div>
    </Modal>
  );
}

function IssueDetail({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const t = useT();
  const { user } = useAuth();
  const q = useApi<any>(`/api/authority/public-issues/${id}`);
  const s = useSubmit();
  const [panel, setPanel] = useState<"" | "verify" | "update" | "unpublish" | "link">("");
  const [verify, setVerify] = useState({ impact_level: "MODERATE", impact_assessment: "" });
  const [upd, setUpd] = useState({ message: "", progress: "", resolution_info: "" });
  const [reason, setReason] = useState("");
  const [link, setLink] = useState<string[]>([]);
  useEffect(() => { if (q.data) setVerify({ impact_level: q.data.impact_level || "MODERATE", impact_assessment: q.data.impact_assessment || "" }); }, [q.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const act = (fn: () => Promise<any>, msg: string) => s.run(async () => { await fn(); setPanel(""); await q.reload(); onChanged(); }, msg);
  const d = q.data;
  return (
    <Modal open title={d?.title || t("Public issue")} onClose={onClose} width="max-w-3xl"
      footer={d && <>
        {d.can_approve && d.status === "DRAFT" && <Button variant="secondary" onClick={() => setPanel("verify")}>{t("Verify and assess impact")}</Button>}
        {d.can_approve && (d.status === "VERIFIED" || d.status === "UNPUBLISHED") && <Button onClick={() => act(() => api(`/api/authority/public-issues/${id}/publish`, { method: "POST" }), "Published.")}>{t("Approve and publish")}</Button>}
        {d.can_approve && d.status === "PUBLISHED" && <Button variant="secondary" onClick={() => setPanel("unpublish")}>{t("Unpublish")}</Button>}
        <Button variant="secondary" onClick={() => setPanel("link")}>{t("Link complaints")}</Button>
        <Button onClick={() => setPanel("update")}>{t("Post progress update")}</Button>
      </>}>
      {!d ? <Spinner /> : (
        <>
          <Feedback s={s} />
          <div className="flex flex-wrap items-center gap-2"><IssueStatusBadge status={d.status} /><Badge>{t(ISSUE_PROGRESS_LABEL[d.progress])}</Badge>{d.impact_level && <Badge>{t("Impact")}: {t(d.impact_level)}</Badge>}</div>
          <p className="text-slate-800">{d.description}</p>
          <KeyValue items={[
            [t("General location"), d.general_location], [t("Department"), d.department], [t("Jurisdiction"), d.jurisdiction],
            [t("Impact assessment"), d.impact_assessment], [t("Verified"), d.verified_at ? fmtDate(d.verified_at) : t("Not yet")],
            [t("Published"), d.published_at ? fmtDate(d.published_at) : t("Not yet")], [t("Resolution"), d.resolution_info],
          ]} />
          {!d.can_approve && user?.role === "OFFICER" && <p className="text-xs text-slate-500">{t("Your department administrator verifies and approves publication.")}</p>}

          {panel === "verify" && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <Field label={t("Impact level")} htmlFor="vl"><select id="vl" className={inputCls} value={verify.impact_level} onChange={(e) => setVerify({ ...verify, impact_level: e.target.value })}>
                {["LOW", "MODERATE", "HIGH"].map((x) => <option key={x} value={x}>{t(x)}</option>)}</select></Field>
              <Field label={t("Impact assessment")} htmlFor="va" hint={t("Who is affected and why it matters publicly.")}><textarea id="va" rows={3} className={inputCls} value={verify.impact_assessment} onChange={(e) => setVerify({ ...verify, impact_assessment: e.target.value })} /></Field>
              <Button disabled={verify.impact_assessment.trim().length < 10} loading={s.busy} onClick={() => act(() => api(`/api/authority/public-issues/${id}/verify`, { body: verify }), "Issue verified.")}>{t("Save verification")}</Button>
            </div>
          )}
          {panel === "update" && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <Field label={t("Public update")} htmlFor="um"><textarea id="um" rows={2} className={inputCls} value={upd.message} onChange={(e) => setUpd({ ...upd, message: e.target.value })} /></Field>
              <Field label={t("Progress")} htmlFor="up"><select id="up" className={inputCls} value={upd.progress} onChange={(e) => setUpd({ ...upd, progress: e.target.value })}>
                <option value="">{t("No change")}</option>{Object.entries(ISSUE_PROGRESS_LABEL).map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select></Field>
              {upd.progress === "RESOLVED" && <Field label={t("How was it resolved?")} htmlFor="ur"><textarea id="ur" rows={2} className={inputCls} value={upd.resolution_info} onChange={(e) => setUpd({ ...upd, resolution_info: e.target.value })} /></Field>}
              <Button disabled={upd.message.trim().length < 5} loading={s.busy} onClick={() => act(() => api(`/api/authority/public-issues/${id}/updates`, { body: { message: upd.message, progress: upd.progress || null, resolution_info: upd.resolution_info || null } }), "Update posted.")}>{t("Post update")}</Button>
            </div>
          )}
          {panel === "unpublish" && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <Field label={t("Reason")} htmlFor="ur2"><input id="ur2" className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
              <Button disabled={reason.trim().length < 5} loading={s.busy} onClick={() => act(() => api(`/api/authority/public-issues/${id}/unpublish`, { body: { reason } }), "Unpublished.")}>{t("Unpublish")}</Button>
            </div>
          )}
          {panel === "link" && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
              <ComplaintPicker selected={link} onChange={setLink} exclude={d.complaints.map((c: any) => c.complaint_id)} />
              <Button disabled={!link.length} loading={s.busy} onClick={() => act(async () => { await api(`/api/authority/public-issues/${id}/complaints`, { body: { complaint_ids: link } }); setLink([]); }, "Complaints linked.")}>{t("Link selected")}</Button>
            </div>
          )}

          <div>
            <h3 className="mb-1 text-sm font-semibold text-slate-900">{t("Related complaints")} ({d.complaints.length})</h3>
            <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">{d.complaints.map((c: any) => (
              <li key={c.complaint_id} className="flex items-center gap-2 px-3 py-1.5">
                <Link href={`/authority/complaints/${c.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{c.reference_id}</Link>
                <span className="min-w-0 flex-1 truncate">{c.title}</span><StatusBadge status={c.status} />
                {d.complaints.length > 1 && <button type="button" aria-label={t("Unlink")} className="rounded p-1 text-slate-400 hover:text-red-700"
                  onClick={() => act(() => api(`/api/authority/public-issues/${id}/complaints/${c.complaint_id}`, { method: "DELETE" }), "Complaint unlinked.")}><X className="h-3.5 w-3.5" /></button>}
              </li>
            ))}</ul>
          </div>
          <div>
            <h3 className="mb-1 text-sm font-semibold text-slate-900">{t("Update history")}</h3>
            {d.updates.length === 0 ? <p className="text-xs text-slate-500">{t("No updates yet.")}</p> : (
              <ul className="space-y-2">{d.updates.map((u: any) => (
                <li key={u.id} className="border-l-2 border-navy-200 pl-3"><div className="text-xs text-slate-500">{fmtDate(u.created_at)} · {u.author}{u.progress ? ` · ${t(ISSUE_PROGRESS_LABEL[u.progress])}` : ""}</div><p>{u.message}</p></li>
              ))}</ul>
            )}
          </div>
        </>
      )}
    </Modal>
  );
}
