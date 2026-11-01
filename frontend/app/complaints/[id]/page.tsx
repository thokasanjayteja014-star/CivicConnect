"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, fmtDate } from "@/components/labels";
import { MediaGrid, MediaView } from "@/components/Media";
import { PointMap } from "@/components/map";
import { Badge, Button, Card, ErrorBox, Field, Notice, PageHeader, Spinner, StatusBadge, inputCls } from "@/components/ui";
import { PriorityPanel, ResolutionNotice, RoutingPanel, Timeline } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ComplaintDetail } from "@/types";

export default function CitizenComplaint() {
  const t = useT();
  const { allowed } = useRequireRole(["CITIZEN"]);
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading, reload, setData } = useApi<ComplaintDetail>(allowed ? `/api/complaints/${id}` : null);

  if (!allowed || (loading && !c)) return <Spinner label={t("Loading complaint…")} />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={c.title}
        subtitle={<span className="font-mono">{c.reference_id}</span>}
        actions={<div className="flex items-center gap-2"><StatusBadge status={c.status} /><Link href="/dashboard" className="text-sm text-navy-700 underline">{t("All complaints")}</Link></div>}
      />
      <ResolutionNotice status={c.status} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title={t("Complaint")}>
            <dl className="grid gap-4 text-sm sm:grid-cols-2">
              <div><dt className="text-xs text-slate-500">{t("Category")}</dt><dd>{t(CATEGORY_LABEL[c.category])}</dd></div>
              <div><dt className="text-xs text-slate-500">{t("Submitted")}</dt><dd>{fmtDate(c.created_at)}</dd></div>
              <div><dt className="text-xs text-slate-500">{t("First noticed")}</dt><dd>{c.occurred_at ? fmtDate(c.occurred_at, false) : t("Not provided")}</dd></div>
              <div><dt className="text-xs text-slate-500">{t("Landmark / address")}</dt><dd>{[c.location.landmark, c.location.address_text].filter(Boolean).join(" · ") || "—"}</dd></div>
            </dl>
            <div className="mt-4 space-y-3 text-sm">
              <div><h3 className="text-xs font-semibold text-slate-500">{t("Description submitted")}</h3><p className="whitespace-pre-wrap">{c.description}</p></div>
              {c.original_description && c.original_description !== c.description && (
                <div><h3 className="text-xs font-semibold text-slate-500">{t("Your original text")}</h3><p className="whitespace-pre-wrap text-slate-600">{c.original_description}</p></div>
              )}
              {c.additional_details && <div><h3 className="text-xs font-semibold text-slate-500">{t("Additional details")}</h3><p>{c.additional_details}</p></div>}
            </div>
            {c.citizen_actions?.can_edit && <EditBox c={c} onSaved={setData} />}
          </Card>
          <Card title={t("Media you submitted")}><MediaGrid items={c.media} /></Card>
          <Card title={t("Status timeline")}><Timeline entries={c.timeline} /></Card>
          <ReplyBox id={c.complaint_id} onDone={reload} />
          {(c.resolution_evidence.length > 0 || c.citizen_actions?.can_confirm_resolution || c.feedback.length > 0) && (
            <Card title={t("Resolution")}>
              <div className="space-y-4">
                {c.resolution_evidence.length > 0 ? (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {c.resolution_evidence.map((e) => <div key={e.evidence_id}><MediaView item={e.media} />{e.description && <p className="mt-1 text-xs text-slate-600">{e.description}</p>}</div>)}
                  </div>
                ) : <p className="text-sm text-slate-500">{t("No resolution evidence has been shared yet.")}</p>}
                {c.verification_decisions.map((v, i) => (
                  <Notice key={i} tone={v.decision === "APPROVED" ? "success" : "warn"}>{t(v.decision === "APPROVED" ? "Verification approved" : "Verification rejected")} · {fmtDate(v.created_at)}: {v.reason}</Notice>
                ))}
                {c.feedback.map((f) => (
                  <div key={f.feedback_id} className="rounded-md border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2"><Badge className="bg-slate-100 ring-slate-300">{t(f.feedback_type.replaceAll("_", " ").toLowerCase())}</Badge>
                      <span className="text-xs text-slate-500">{fmtDate(f.created_at)}</span>
                      {f.review_status !== "NOT_REQUIRED" && <Badge className="bg-white ring-slate-300">{t("Review")}: {t(f.review_status.toLowerCase())}</Badge>}</div>
                    {f.remarks && <p className="mt-1">{f.remarks}</p>}
                    {f.decision_reason && <p className="mt-1 text-xs text-slate-600">{t("Decision reason")}: {f.decision_reason}</p>}
                  </div>
                ))}
                {c.citizen_actions?.can_confirm_resolution && <FeedbackBox c={c} onDone={reload} />}
              </div>
            </Card>
          )}
        </div>
        <div className="space-y-6">
          <Card title={t("Location")}>
            <PointMap lat={c.location.latitude} lng={c.location.longitude} />
            <p className="mt-2 text-xs text-slate-500">{c.location.latitude.toFixed(5)}, {c.location.longitude.toFixed(5)} · {c.location.location_source === "GPS" ? `GPS ±${c.location.accuracy_meters ?? "?"} m` : t("selected on map")}</p>
          </Card>
          <Card title={t("Department")}><RoutingPanel r={c.routing} /></Card>
          <Card title={t("Priority")}><PriorityPanel p={c.priority} /></Card>
          {c.related.length > 0 && (
            <Card title={t("Related reports")}>
              <ul className="space-y-2 text-sm">{c.related.map((r: any) => <li key={r.public_reference}><span className="font-mono text-xs">{r.public_reference}</span> · {r.public_status}<div className="text-slate-600">{r.public_summary}</div></li>)}</ul>
            </Card>
          )}
          <p className="text-xs text-slate-500">{t(c.workflow_notice)}</p>
        </div>
      </div>
    </div>
  );
}

function EditBox({ c, onSaved }: { c: ComplaintDetail; onSaved: (d: ComplaintDetail) => void }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(c.title);
  const [details, setDetails] = useState(c.additional_details || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  if (!open) return <Button variant="secondary" className="mt-4" onClick={() => setOpen(true)}>{t("Edit details (before review starts)")}</Button>;
  return (
    <form className="mt-4 space-y-3 rounded-md border border-slate-200 p-3" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError(null);
      try { onSaved(await api(`/api/complaints/${c.complaint_id}`, { method: "PATCH", body: { title, additional_details: details } })); setOpen(false); }
      catch (err) { setError(err); } finally { setBusy(false); }
    }}>
      <ErrorBox error={error} />
      <Field label={t("Title")} htmlFor="et"><input id="et" className={inputCls} value={title} minLength={5} maxLength={150} onChange={(e) => setTitle(e.target.value)} /></Field>
      <Field label={t("Additional details")} htmlFor="ed"><textarea id="ed" className={inputCls} rows={3} maxLength={2000} value={details} onChange={(e) => setDetails(e.target.value)} /></Field>
      <div className="flex gap-2"><Button type="submit" loading={busy}>{t("Save")}</Button><Button type="button" variant="secondary" onClick={() => setOpen(false)}>{t("Cancel")}</Button></div>
    </form>
  );
}

function ReplyBox({ id, onDone }: { id: string; onDone: () => void }) {
  const t = useT();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  return (
    <Card title={t("Reply to the department")}>
      <form className="space-y-2" onSubmit={async (e) => {
        e.preventDefault(); setBusy(true); setError(null);
        try { await api(`/api/complaints/${id}/remarks`, { body: { text } }); setText(""); onDone(); } catch (err) { setError(err); } finally { setBusy(false); }
      }}>
        <ErrorBox error={error} />
        <label htmlFor="reply" className="sr-only">{t("Reply")}</label>
        <textarea id="reply" rows={2} className={inputCls} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("Answer a clarification request or add information")} />
        <Button type="submit" variant="secondary" loading={busy} disabled={!text.trim()}>{t("Send reply")}</Button>
      </form>
    </Card>
  );
}

function FeedbackBox({ c, onDone }: { c: ComplaintDetail; onDone: () => void }) {
  const t = useT();
  const [type, setType] = useState<"CONFIRMED_RESOLVED" | "NOT_RESOLVED" | "REOPEN_REQUEST" | "">("");
  const [remarks, setRemarks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ok, setOk] = useState("");
  const needsReason = type === "NOT_RESOLVED" || type === "REOPEN_REQUEST";
  return (
    <form className="space-y-3 rounded-md bg-slate-50 p-3" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError(null);
      try {
        const r = await api(`/api/complaints/${c.complaint_id}/feedback`, { body: { feedback_type: type, remarks: remarks || null } });
        setOk(r.review_status === "PENDING" ? t("Your request was recorded and is awaiting review by the department. The status will not change until they decide.") : t("Thank you. Your confirmation was recorded."));
        setType(""); setRemarks(""); onDone();
      } catch (err) { setError(err); } finally { setBusy(false); }
    }}>
      <h3 className="text-sm font-semibold text-navy-900">{t("Is the issue fixed?")}</h3>
      {ok && <Notice tone="success">{ok}</Notice>}
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-3 text-sm">
        <label className="flex items-center gap-1"><input type="radio" name="fb" checked={type === "CONFIRMED_RESOLVED"} onChange={() => setType("CONFIRMED_RESOLVED")} /> {t("Yes, it looks resolved")}</label>
        {c.citizen_actions?.can_request_reopen && <>
          <label className="flex items-center gap-1"><input type="radio" name="fb" checked={type === "NOT_RESOLVED"} onChange={() => setType("NOT_RESOLVED")} /> {t("No, it is not resolved")}</label>
          <label className="flex items-center gap-1"><input type="radio" name="fb" checked={type === "REOPEN_REQUEST"} onChange={() => setType("REOPEN_REQUEST")} /> {t("It came back — reopen")}</label>
        </>}
      </div>
      {!c.citizen_actions?.can_request_reopen && <p className="text-xs text-slate-500">{t("A reopening request is already awaiting review.")}</p>}
      {type && <Field label={needsReason ? t("What is still wrong?") : t("Comments (optional)")} htmlFor="fbr" required={needsReason}>
        <textarea id="fbr" rows={2} className={inputCls} maxLength={2000} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </Field>}
      <Button type="submit" disabled={!type || (needsReason && !remarks.trim())} loading={busy}>{t("Submit feedback")}</Button>
    </form>
  );
}
