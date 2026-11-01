"use client";

import { AlertTriangle, ArrowLeft, CheckCircle2, Flag } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useAuth, useRequireRole } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, FACTOR_LABEL, REASON_LABEL, STATUS_LABEL, fmtDate, relDays } from "@/components/labels";
import { MediaGrid, MediaView } from "@/components/Media";
import { PointMap } from "@/components/map";
import { Badge, Button, Card, ErrorBox, Field, KeyValue, Modal, Notice, Spinner, StatusBadge, inputCls } from "@/components/ui";
import { PriorityPanel, ResolutionNotice, RoutingPanel, Timeline } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ComplaintDetail } from "@/types";

function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [ok, setOk] = useState("");
  const run = async (name: string, fn: () => Promise<void>, success: string) => {
    setBusy(name); setError(null); setOk("");
    try { await fn(); setOk(success); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return { busy, error, ok, run };
}

export default function AuthorityComplaint() {
  const t = useT();
  const { allowed } = useRequireRole(["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]);
  const { user } = useAuth();
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading, reload, setData } = useApi<ComplaintDetail>(allowed ? `/api/authority/complaints/${id}` : null);
  const canManage = user?.role === "DEPARTMENT_ADMIN" || user?.role === "SYSTEM_ADMIN";
  const officers = useApi<any[]>(allowed && c && canManage ? `/api/authority/officers${c.unit ? `?unit_id=${c.unit.id}` : c.department ? `?department_id=${c.department.id}` : ""}` : null, [c?.unit?.id, c?.department?.id]);
  const accept = useAction();
  const [escOpen, setEscOpen] = useState(false);

  if (!allowed || (loading && !c)) return <Spinner label={t("Loading complaint…")} />;
  if (error && !c) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return null;
  const pa = c.permitted_actions!;
  const due = relDays(c.due_at);
  const openEsc = (c.escalations || []).filter((e) => e.status === "OPEN");

  return (
    <div className="space-y-5">
      <Link href="/authority/complaints" className="inline-flex items-center gap-1 text-sm text-navy-700 underline"><ArrowLeft className="h-4 w-4" /> {t("Back to complaints")}</Link>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
        <div className="min-w-0">
          <p className="font-mono text-xs text-slate-500">{c.reference_id}</p>
          <h1 className="text-xl font-semibold text-slate-900">{c.title}</h1>
          <p className="mt-1 text-sm text-slate-600">{c.jurisdiction_path || t("Jurisdiction not determined")}{c.unit ? ` · ${c.unit.department}` : ""}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={c.status} />
          {due && <Badge className={c.overdue ? "bg-red-50 text-red-800 ring-red-200" : "bg-slate-50 text-slate-700 ring-slate-300"}>
            {c.overdue ? t("Overdue by {n} days", { n: due.days }) : t("Due {date}", { date: fmtDate(c.due_at, false) })}</Badge>}
          {openEsc.length > 0 && <Badge className="bg-amber-50 text-amber-800 ring-amber-200">{t("Escalated, level {n}", { n: Math.max(...openEsc.map((e) => e.level)) })}</Badge>}
          {pa.can_accept && <Button loading={accept.busy === "a"} onClick={() => accept.run("a", async () => setData(await api(`/api/authority/complaints/${c.complaint_id}/accept`, { method: "POST" })), t("Assignment accepted."))}>
            <CheckCircle2 className="h-4 w-4" /> {t("Accept assignment")}</Button>}
          {pa.can_escalate && <Button variant="secondary" onClick={() => setEscOpen(true)}><Flag className="h-4 w-4" /> {t("Escalate")}</Button>}
        </div>
      </div>
      {accept.ok && <Notice tone="success">{accept.ok}</Notice>}
      <ErrorBox error={accept.error} />
      {pa.can_accept && <Notice tone="warn">{t("This complaint was assigned to you. Accept it to confirm you are working on it.")}</Notice>}
      {c.priority.needs_prompt_review && <Notice tone="warn"><AlertTriangle className="mr-1 inline h-4 w-4" /> {t("The citizen reported a possible immediate safety concern. Review promptly.")}</Notice>}
      <ResolutionNotice status={c.status} />

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title={t("Complaint")}>
            <KeyValue items={[
              [t("Category"), t(CATEGORY_LABEL[c.category])], [t("Submitted"), fmtDate(c.created_at)],
              [t("First noticed"), c.occurred_at ? fmtDate(c.occurred_at, false) : t("Unknown")],
              ...Object.entries(c.citizen_observations).map(([k, v]) => [t(k.replaceAll("_", " ")), v ? t(v.replaceAll("_", " ").toLowerCase()) : t("Not provided")] as [ReactNode, ReactNode]),
            ]} />
            <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
              <div><h3 className="text-xs font-semibold text-slate-500">{t("Citizen's original words")}</h3><p className="whitespace-pre-wrap">{c.original_description || <span className="text-slate-400">{t("None (photo or video only)")}</span>}</p></div>
              <div><h3 className="text-xs font-semibold text-slate-500">{t("Description confirmed by citizen")}</h3><p className="whitespace-pre-wrap">{c.description}</p></div>
            </div>
            {c.additional_details && <p className="mt-3 text-sm"><span className="text-xs font-semibold text-slate-500">{t("Additional details")}: </span>{c.additional_details}</p>}
          </Card>
          <Card title={t("Photos and videos from the citizen")}><MediaGrid items={c.media} /></Card>
          {c.ai_analysis && (
            <Card title={t("Reporting assistant summary")} subtitle={t("A suggestion shown to the citizen before they confirmed. Not an official finding.")}>
              {c.ai_analysis.requires_human_review && <Notice tone="warn">{t("Flagged for human review")}: {(c.ai_analysis.structured_output?.review_reasons || []).join(" ")}</Notice>}
              <p className="text-sm">{c.ai_analysis.summary}</p>
              <p className="mt-1 text-xs text-slate-500">{t("Suggested category")}: {t(CATEGORY_LABEL[c.ai_analysis.suggested_category])} · {t("confidence")} {t(c.ai_analysis.confidence_band || "")}</p>
            </Card>
          )}
          <Card title={t("Activity and status history")}><Timeline entries={c.timeline} /></Card>
          <Card title={t("Resolution evidence")}>
            {c.resolution_evidence.length ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{c.resolution_evidence.map((e) => <div key={e.evidence_id}><MediaView item={e.media} /><p className="mt-1 text-xs text-slate-600">{e.description}</p></div>)}</div>
            ) : <p className="text-sm text-slate-500">{t("No evidence uploaded yet.")}</p>}
            {c.verification_decisions.map((v, i) => <p key={i} className="mt-2 text-sm">{t(v.decision === "APPROVED" ? "Verification approved" : "Verification rejected")} · {fmtDate(v.created_at)} · {v.reason}</p>)}
            {c.feedback.length > 0 && <div className="mt-3 space-y-1 text-sm">{c.feedback.map((f) => <p key={f.feedback_id}><Badge>{t(f.feedback_type.replaceAll("_", " ").toLowerCase())}</Badge> {f.remarks} <span className="text-xs text-slate-500">({t(f.review_status.toLowerCase())})</span></p>)}</div>}
          </Card>
          <RelatedCard c={c} onChange={reload} />
        </div>

        <div className="space-y-5">
          <Card title={t("Actions")}><Actions c={c} officers={officers.data || []} onUpdated={setData} reload={reload} /></Card>
          <Card title={t("Assignment")}><Assignments c={c} /></Card>
          {(c.escalations || []).length > 0 && (
            <Card title={t("Escalations")}>
              <ul className="space-y-2 text-sm">{c.escalations!.map((e) => (
                <li key={e.id} className="border-l-2 border-amber-400 pl-3">
                  <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{t("Level {n}", { n: e.level })}</span><Badge>{t(e.status === "OPEN" ? "Open" : "Closed")}</Badge><span className="text-xs text-slate-500">{fmtDate(e.created_at)}</span></div>
                  <p className="text-xs text-slate-600">{t(REASON_LABEL[e.reason_code] || e.reason_code)}{e.reason ? `: ${e.reason}` : ""}</p>
                  {e.resolution_note && <p className="text-xs text-slate-500">{t("Closed")}: {e.resolution_note}</p>}
                </li>
              ))}</ul>
            </Card>
          )}
          <Card title={t("Location and jurisdiction")}>
            <PointMap lat={c.location.latitude} lng={c.location.longitude} />
            <p className="mt-2 text-xs text-slate-600">{[c.location.landmark, c.location.address_text].filter(Boolean).join(" · ")}</p>
            <p className="text-xs text-slate-500">{c.location.latitude.toFixed(5)}, {c.location.longitude.toFixed(5)}{c.location.accuracy_meters != null ? ` · ±${Math.round(c.location.accuracy_meters)} m` : ""}</p>
            <div className="mt-3"><RoutingPanel r={c.routing} /></div>
          </Card>
          <Card title={t("Priority")}><PriorityPanel p={c.priority} /><PriorityConfirm c={c} onUpdated={setData} /></Card>
          <Card title={t("Public display")}><Publication c={c} onDone={reload} /></Card>
        </div>
      </div>
      {escOpen && <EscalateModal c={c} onClose={() => setEscOpen(false)} onDone={() => { setEscOpen(false); reload(); }} />}
    </div>
  );
}

function EscalateModal({ c, onClose, onDone }: { c: ComplaintDetail; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const { user } = useAuth();
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();
  return (
    <Modal open title={t("Escalate complaint")} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t("Cancel")}</Button>
        <Button disabled={reason.trim().length < 5} loading={!!busy} onClick={() => run("e", async () => { await api(`/api/authority/complaints/${c.complaint_id}/escalate`, { body: { reason } }); onDone(); }, "")}>{t("Escalate")}</Button></>}>
      <ErrorBox error={error} />
      <p className="text-sm text-slate-700">{user?.role === "OFFICER"
        ? t("This sends the complaint to your department administrator (level 1) with your reason.")
        : t("This sends the complaint to the main administration (level 2) with your reason.")}</p>
      <Field label={t("Reason")} htmlFor="er" required hint={t("For example: needs equipment or approval beyond your authority.")}>
        <textarea id="er" rows={3} className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Field>
    </Modal>
  );
}

function Assignments({ c }: { c: ComplaintDetail }) {
  const t = useT();
  const list = c.assignments || [];
  if (!list.length) return <p className="text-sm text-slate-500">{c.unit ? t("Awaiting assignment. No officer covers this area yet, so the department administrator assigns it.") : t("Not yet routed to a department unit.")}</p>;
  return (
    <ul className="space-y-3 text-sm">{[...list].reverse().map((a, i) => (
      <li key={i} className={a.assignment_status === "ACTIVE" ? "" : "text-slate-500"}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{a.officer?.full_name}</span>
          {a.assignment_status === "ACTIVE" ? (a.accepted_at ? <Badge className="bg-green-50 text-green-800 ring-green-200">{t("Accepted")}</Badge> : <Badge className="bg-amber-50 text-amber-800 ring-amber-200">{t("Awaiting acceptance")}</Badge>) : <Badge>{t("Previous")}</Badge>}
        </div>
        <p className="text-xs text-slate-500">{a.officer?.designation}</p>
        <p className="text-xs text-slate-500">{fmtDate(a.assigned_at)} · {a.automatic ? t("Assigned automatically by area") : t("Assigned by {name}", { name: a.assigned_by_name })}</p>
        {a.reason && <p className="text-xs text-slate-600">{a.reason}</p>}
      </li>
    ))}</ul>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <div className="space-y-2 border-t border-slate-100 pt-3 first:border-0 first:pt-0"><h3 className="text-xs font-semibold text-slate-600">{title}</h3>{children}</div>;
}

function Actions({ c, officers, onUpdated, reload }: { c: ComplaintDetail; officers: any[]; onUpdated: (d: ComplaintDetail) => void; reload: () => void }) {
  const t = useT();
  const pa = c.permitted_actions!;
  const { busy, error, ok, run } = useAction();
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [visible, setVisible] = useState("");
  const [internal, setInternal] = useState("");
  const [officer, setOfficer] = useState("");
  const [assignReason, setAssignReason] = useState("");
  const [remark, setRemark] = useState("");
  const [remarkVis, setRemarkVis] = useState<"CITIZEN" | "INTERNAL">("CITIZEN");
  const [evFile, setEvFile] = useState<File | null>(null);
  const [evDesc, setEvDesc] = useState("");
  const [vReason, setVReason] = useState("");
  const needsReason = target === "REJECTED" || target === "ON_HOLD";
  const active = c.assignments?.find((a) => a.assignment_status === "ACTIVE");
  const eligible = officers.filter((o) => o.eligible && o.officer_id !== active?.officer?.officer_id);
  const jid = c.jurisdiction?.id || c.routing.jurisdiction?.id;

  return (
    <div className="space-y-4 text-sm">
      {ok && <Notice tone="success">{ok}</Notice>}
      <ErrorBox error={error} />
      <Section title={t("Update status")}>
        {pa.status_targets.length === 0 ? <p className="text-xs text-slate-500">{t("No status change is available right now.")} {pa.can_assign ? t("Assign an officer to continue.") : pa.can_verify ? t("Use verification below.") : ""}</p> : (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("status", async () => {
            onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/status`, { body: { status: target, reason: reason || null, remarks: visible || null, internal_note: internal || null, expected_version: c.version } }));
            setTarget(""); setReason(""); setVisible(""); setInternal("");
          }, t("Status updated.")); }}>
            <select aria-label={t("New status")} className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">{t("Choose new status…")}</option>
              {pa.status_targets.map((s) => <option key={s} value={s} disabled={s === "RESOLVED_AWAITING_VERIFICATION" && !pa.has_evidence}>{s === "UNDER_REVIEW" ? t("Accept for review") : t(STATUS_LABEL[s])}{s === "RESOLVED_AWAITING_VERIFICATION" && !pa.has_evidence ? ` (${t("upload evidence first")})` : ""}</option>)}
            </select>
            {needsReason && <textarea aria-label={t("Reason (required, shown to citizen)")} required className={inputCls} rows={2} placeholder={t("Reason (required, shown to citizen)")} value={reason} onChange={(e) => setReason(e.target.value)} />}
            {target && <textarea aria-label={t("Remark for the citizen (optional)")} className={inputCls} rows={2} placeholder={t("Remark for the citizen (optional)")} value={visible} onChange={(e) => setVisible(e.target.value)} />}
            {target && <textarea aria-label={t("Internal note (never shown to the citizen)")} className={inputCls} rows={2} placeholder={t("Internal note (never shown to the citizen)")} value={internal} onChange={(e) => setInternal(e.target.value)} />}
            <Button type="submit" disabled={!target || (needsReason && !reason.trim())} loading={busy === "status"} variant={target === "REJECTED" ? "danger" : "primary"}>{t("Apply")}</Button>
          </form>
        )}
      </Section>

      {(pa.can_assign || pa.can_reassign) && (
        <Section title={pa.can_assign ? t("Assign officer") : t("Reassign officer")}>
          {active && <p className="text-xs text-slate-600">{t("Currently")}: {active.officer?.full_name}</p>}
          {eligible.length === 0 ? <p className="text-xs text-slate-500">{t("No other active officers in this unit.")}</p> : (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("assign", async () => {
              onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/assign`, { body: { officer_id: officer, reason: assignReason || null, expected_version: c.version } }));
              setOfficer(""); setAssignReason("");
            }, pa.can_assign ? t("Officer assigned.") : t("Complaint reassigned.")); }}>
              <select aria-label={t("Officer")} className={inputCls} value={officer} onChange={(e) => setOfficer(e.target.value)}>
                <option value="">{t("Choose officer…")}</option>
                {eligible.map((o) => {
                  const covers = jid && o.areas?.some((a: any) => a.jurisdiction_id === jid);
                  return <option key={o.officer_id} value={o.officer_id}>{o.full_name} · {t("{n} active", { n: o.active_assignments })}{covers ? ` · ${t("covers this area")}` : ""}</option>;
                })}
              </select>
              {pa.can_reassign && <textarea aria-label={t("Reason for reassignment (required)")} className={inputCls} rows={2} placeholder={t("Reason for reassignment (required)")} value={assignReason} onChange={(e) => setAssignReason(e.target.value)} />}
              <Button type="submit" disabled={!officer || (pa.can_reassign && !assignReason.trim())} loading={busy === "assign"}>{pa.can_assign ? t("Assign") : t("Reassign")}</Button>
            </form>
          )}
        </Section>
      )}

      {pa.can_upload_evidence && (
        <Section title={t("Upload resolution evidence")}>
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("evidence", async () => {
            const fd = new FormData(); fd.append("file", evFile!); if (evDesc) fd.append("description", evDesc);
            await api(`/api/authority/complaints/${c.complaint_id}/evidence`, { form: fd });
            setEvFile(null); setEvDesc(""); reload();
          }, t("Evidence uploaded.")); }}>
            <input aria-label={t("Evidence file")} type="file" accept="image/jpeg,image/png,image/webp,video/mp4" onChange={(e) => setEvFile(e.target.files?.[0] || null)} className="text-xs" />
            <input aria-label={t("What was done (optional)")} className={inputCls} placeholder={t("What was done (optional)")} value={evDesc} onChange={(e) => setEvDesc(e.target.value)} />
            <Button type="submit" variant="secondary" disabled={!evFile} loading={busy === "evidence"}>{t("Upload")}</Button>
          </form>
        </Section>
      )}

      {c.status === "RESOLVED_AWAITING_VERIFICATION" && (
        <Section title={t("Verify resolution")}>
          {pa.can_verify ? (
            <div className="space-y-2">
              <p className="text-xs text-slate-600">{t("Review the evidence and the citizen's response before deciding.")}</p>
              <textarea aria-label={t("What you reviewed (required)")} className={inputCls} rows={2} placeholder={t("What you reviewed (required)")} value={vReason} onChange={(e) => setVReason(e.target.value)} />
              <div className="flex gap-2">
                {(["APPROVED", "REJECTED"] as const).map((d) => (
                  <Button key={d} variant={d === "APPROVED" ? "primary" : "danger"} disabled={vReason.trim().length < 3} loading={busy === d}
                    onClick={() => run(d, async () => {
                      onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/verify`, { body: { decision: d, reason: vReason, evidence_reviewed: c.resolution_evidence.map((x) => x.evidence_id), expected_version: c.version } }));
                      setVReason("");
                    }, d === "APPROVED" ? t("Marked as verified resolved.") : t("Verification rejected; complaint reopened."))}>
                    {d === "APPROVED" ? t("Approve") : t("Reject and reopen")}
                  </Button>
                ))}
              </div>
            </div>
          ) : <p className="text-xs text-slate-500">{t("Your department administrator verifies resolutions.")}</p>}
        </Section>
      )}

      <Section title={t("Add remark")}>
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); const clar = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-clar") === "1"; run("remark", async () => {
          await api(`/api/authority/complaints/${c.complaint_id}/remarks${clar ? "?clarification=true" : ""}`, { body: { text: remark, visibility: clar ? "CITIZEN" : remarkVis } });
          setRemark(""); reload();
        }, clar ? t("Clarification requested from the citizen.") : t("Remark added.")); }}>
          <textarea aria-label={t("Remark")} className={inputCls} rows={2} value={remark} onChange={(e) => setRemark(e.target.value)} />
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1"><input type="radio" checked={remarkVis === "CITIZEN"} onChange={() => setRemarkVis("CITIZEN")} /> {t("Visible to citizen")}</label>
            <label className="flex items-center gap-1"><input type="radio" checked={remarkVis === "INTERNAL"} onChange={() => setRemarkVis("INTERNAL")} /> {t("Internal only")}</label>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="secondary" disabled={!remark.trim()} loading={busy === "remark"}>{t("Add remark")}</Button>
            <Button type="submit" variant="ghost" data-clar="1" disabled={!remark.trim()}>{t("Request clarification")}</Button>
          </div>
        </form>
      </Section>
    </div>
  );
}

function PriorityConfirm({ c, onUpdated }: { c: ComplaintDetail; onUpdated: (d: ComplaintDetail) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [explanation, setExplanation] = useState("");
  const { busy, error, run } = useAction();
  const missing = Object.entries(c.priority.factors || {}).filter(([, f]) => f.value == null).map(([k]) => k);
  if (!open) return <Button variant="secondary" size="sm" className="mt-3" onClick={() => setOpen(true)}>{missing.length ? t("Confirm missing factors ({n})", { n: missing.length }) : t("Adjust factors")}</Button>;
  return (
    <form className="mt-3 space-y-2 text-sm" onSubmit={(e) => { e.preventDefault(); run("p", async () => {
      const body: Record<string, unknown> = { explanation };
      Object.entries(vals).forEach(([k, v]) => { if (v !== "") body[k] = Number(v); });
      onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/priority`, { body }));
      setOpen(false);
    }, ""); }}>
      <ErrorBox error={error} />
      <p className="text-xs text-slate-600">{t("Enter confirmed values from 0 to 100. The score is recalculated by the system; it cannot be set directly.")}</p>
      {Object.keys(FACTOR_LABEL).map((k) => (
        <label key={k} className="flex items-center justify-between gap-2 text-xs">{t(FACTOR_LABEL[k])}
          <input type="number" min={0} max={100} step="0.01" className={inputCls + " w-24"} value={vals[k] ?? ""} placeholder={c.priority.factors?.[k]?.value?.toString() ?? t("unknown")} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />
        </label>
      ))}
      <Field label={t("Evidence or explanation")} htmlFor="pexp" required><input id="pexp" className={inputCls} value={explanation} onChange={(e) => setExplanation(e.target.value)} /></Field>
      <div className="flex gap-2"><Button type="submit" loading={!!busy} disabled={explanation.trim().length < 3 || !Object.values(vals).some((v) => v !== "")}>{t("Save")}</Button><Button variant="secondary" onClick={() => setOpen(false)}>{t("Cancel")}</Button></div>
    </form>
  );
}

function Publication({ c, onDone }: { c: ComplaintDetail; onDone: () => void }) {
  const t = useT();
  const [summary, setSummary] = useState(c.public_summary || "");
  const { busy, error, ok, run } = useAction();
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-slate-600">{t("Issues affecting many residents are published as Public Issues, which can group several complaints.")}{" "}
        <Link href={`/authority/public-issues?from=${c.complaint_id}`} className="font-medium text-navy-700 underline">{t("Create a public issue from this complaint")}</Link></p>
      {c.allow_public_display ? (
        <>
          <p className="text-xs text-slate-600">{t("Single complaint display")}: <strong>{t(c.publication_status.replaceAll("_", " ").toLowerCase())}</strong>. {t("Write a summary with no names, phone numbers or private details.")}</p>
          {ok && <Notice tone="success">{ok}</Notice>}
          <ErrorBox error={error} />
          <textarea aria-label={t("Public summary")} className={inputCls} rows={2} maxLength={500} value={summary} onChange={(e) => setSummary(e.target.value)} />
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" disabled={summary.trim().length < 10} loading={busy === "a"} onClick={() => run("a", async () => { await api(`/api/authority/complaints/${c.complaint_id}/publication`, { body: { approve: true, public_summary: summary } }); onDone(); }, t("Approved for public display."))}>{t("Approve public display")}</Button>
            <Button variant="ghost" size="sm" loading={busy === "d"} onClick={() => run("d", async () => { await api(`/api/authority/complaints/${c.complaint_id}/publication`, { body: { approve: false } }); onDone(); }, t("Kept private."))}>{t("Keep private")}</Button>
          </div>
        </>
      ) : <p className="text-xs text-slate-500">{t("The citizen chose not to allow public display of this complaint.")}</p>}
    </div>
  );
}

function RelatedCard({ c, onChange }: { c: ComplaintDetail; onChange: () => void }) {
  const t = useT();
  const { busy, error, run } = useAction();
  return (
    <Card title={t("Possibly related complaints")} subtitle={t("Suggestions never merge, delete or reject complaints.")}>
      <ErrorBox error={error} />
      {c.related.length === 0 ? <p className="text-sm text-slate-500">{t("No nearby complaints of the same kind were found.")}</p> : (
        <ul className="space-y-3 text-sm">
          {c.related.map((r: any) => (
            <li key={r.complaint_id} className="rounded-md border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                {r.in_scope ? <Link href={`/authority/complaints/${r.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{r.reference_id}</Link> : <span className="font-mono text-xs">{r.reference_id}</span>}
                <span>{r.title}</span><StatusBadge status={r.status} />
                <Badge>{t(r.relationship_status.replaceAll("_", " ").toLowerCase())}</Badge>
              </div>
              <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{r.match_reasons.map((m: string) => <li key={m}>{m}</li>)}</ul>
              <div className="mt-2 flex gap-2">
                {(["CONFIRMED_RELATED", "NOT_RELATED"] as const).map((s) => (
                  <Button key={s} variant="secondary" size="sm" loading={busy === r.complaint_id + s} disabled={r.relationship_status === s}
                    onClick={() => run(r.complaint_id + s, async () => { await api(`/api/complaints/${c.complaint_id}/relationships`, { body: { related_complaint_id: r.complaint_id, relationship_status: s } }); onChange(); }, "")}>
                    {s === "CONFIRMED_RELATED" ? t("Mark related") : t("Not related")}
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
