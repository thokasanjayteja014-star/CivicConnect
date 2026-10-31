"use client";

import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { CATEGORY_LABEL, FACTOR_LABEL, STATUS_LABEL, fmtDate } from "@/components/labels";
import { MediaGrid, MediaView } from "@/components/Media";
import { PointMap } from "@/components/map";
import { Badge, Button, Card, ErrorBox, Field, Notice, PageHeader, Spinner, StatusBadge, inputCls } from "@/components/ui";
import { PriorityPanel, ResolutionNotice, RoutingPanel, Timeline } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import type { ComplaintDetail } from "@/types";

export default function AuthorityComplaint() {
  const { allowed } = useRequireRole(["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]);
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading, reload, setData } = useApi<ComplaintDetail>(allowed ? `/api/authority/complaints/${id}` : null);
  const officers = useApi<any[]>(allowed && c ? `/api/authority/officers${c.department ? `?department_id=${c.department.id}` : ""}` : null, [c?.department?.id]);

  if (!allowed || (loading && !c)) return <Spinner label="Loading complaint…" />;
  if (error && !c) return <ErrorBox error={error} onRetry={reload} />;
  if (!c) return null;
  const pa = c.permitted_actions!;

  return (
    <div className="space-y-6">
      <PageHeader title={c.title} subtitle={<span className="font-mono">{c.reference_id}</span>}
        actions={<div className="flex items-center gap-2"><StatusBadge status={c.status} /><Link href="/authority" className="text-sm text-teal-700 underline">Back to dashboard</Link></div>} />
      {c.priority.needs_prompt_review && <Notice tone="warn"><AlertTriangle className="mr-1 inline h-4 w-4" /> Citizen reported a potentially immediate safety concern. Review promptly.</Notice>}
      <ResolutionNotice status={c.status} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Complaint">
            <dl className="grid gap-3 text-sm sm:grid-cols-3">
              <div><dt className="text-xs text-slate-500">Category</dt><dd>{CATEGORY_LABEL[c.category]}</dd></div>
              <div><dt className="text-xs text-slate-500">Submitted</dt><dd>{fmtDate(c.created_at)}</dd></div>
              <div><dt className="text-xs text-slate-500">First noticed</dt><dd>{c.occurred_at ? fmtDate(c.occurred_at, false) : "Unknown"}</dd></div>
              {Object.entries(c.citizen_observations).map(([k, v]) => (
                <div key={k}><dt className="text-xs text-slate-500">Citizen: {k.replaceAll("_", " ")}</dt><dd>{v ? v.replaceAll("_", " ").toLowerCase() : "not provided"}</dd></div>
              ))}
            </dl>
            <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
              <div><h3 className="text-xs font-semibold uppercase text-slate-500">Original citizen description</h3><p className="whitespace-pre-wrap">{c.original_description || <span className="text-slate-400">None (media-only report)</span>}</p></div>
              <div><h3 className="text-xs font-semibold uppercase text-slate-500">Citizen-confirmed description</h3><p className="whitespace-pre-wrap">{c.description}</p></div>
            </div>
            {c.additional_details && <p className="mt-3 text-sm"><span className="text-xs font-semibold uppercase text-slate-500">Additional details: </span>{c.additional_details}</p>}
          </Card>
          <Card title="Original media"><MediaGrid items={c.media} /></Card>
          <Card title="AI analysis">
            {c.ai_analysis ? (
              <div className="space-y-2 text-sm">
                <Notice tone="info">AI output is a suggestion. It was shown to the citizen before they confirmed.</Notice>
                {c.ai_analysis.requires_human_review && <Notice tone="warn">Flagged for human review: {(c.ai_analysis.structured_output?.review_reasons || []).join(" ")}</Notice>}
                <p><strong>Summary:</strong> {c.ai_analysis.summary}</p>
                <p><strong>Suggested category:</strong> {CATEGORY_LABEL[c.ai_analysis.suggested_category]} · confidence {c.ai_analysis.confidence_band}{c.ai_analysis.classification_confidence != null ? ` (${c.ai_analysis.classification_confidence})` : ""}</p>
                <p className="text-xs text-slate-500">Model {c.ai_analysis.model_identifier} · {fmtDate(c.ai_analysis.created_at)}</p>
              </div>
            ) : <p className="text-sm text-slate-500">No AI analysis was used for this complaint (manual submission or AI not configured).</p>}
          </Card>
          <Card title="Activity & status history"><Timeline entries={c.timeline} /></Card>
          <Card title="Resolution evidence">
            {c.resolution_evidence.length ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{c.resolution_evidence.map((e) => <div key={e.evidence_id}><MediaView item={e.media} /><p className="mt-1 text-xs text-slate-600">{e.description}</p></div>)}</div>
            ) : <p className="text-sm text-slate-500">No evidence uploaded yet.</p>}
            {c.verification_decisions.map((v, i) => <p key={i} className="mt-2 text-sm">Verification {v.decision.toLowerCase()} · {fmtDate(v.created_at)} · {v.reason} {v.citizen_responded ? "" : "(citizen had not responded)"}</p>)}
            {c.feedback.length > 0 && <div className="mt-3 space-y-1 text-sm">{c.feedback.map((f) => <p key={f.feedback_id}><Badge className="bg-slate-100 ring-slate-300">{f.feedback_type}</Badge> {f.remarks} <span className="text-xs text-slate-500">({f.review_status})</span></p>)}</div>}
          </Card>
          <RelatedCard c={c} onChange={reload} />
        </div>

        <div className="space-y-6">
          <Card title="Actions">
            <Actions c={c} officers={officers.data || []} onUpdated={setData} reload={reload} />
          </Card>
          <Card title="Location & jurisdiction">
            <PointMap lat={c.location.latitude} lng={c.location.longitude} />
            <p className="mt-2 text-xs text-slate-500">{c.location.latitude.toFixed(5)}, {c.location.longitude.toFixed(5)} · {c.location.location_source}{c.location.accuracy_meters != null ? ` ±${c.location.accuracy_meters} m` : ""}</p>
            <p className="text-xs text-slate-600">{[c.location.landmark, c.location.address_text].filter(Boolean).join(" · ")}</p>
            <div className="mt-3"><RoutingPanel r={c.routing} /></div>
          </Card>
          <Card title="Priority"><PriorityPanel p={c.priority} /><PriorityConfirm c={c} onUpdated={setData} /></Card>
          <Card title="Public display"><Publication c={c} onDone={reload} /></Card>
        </div>
      </div>
    </div>
  );
}

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

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <div className="space-y-2 border-t border-slate-100 pt-3 first:border-0 first:pt-0"><h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>{children}</div>;
}

function Actions({ c, officers, onUpdated, reload }: { c: ComplaintDetail; officers: any[]; onUpdated: (d: ComplaintDetail) => void; reload: () => void }) {
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
  const eligible = officers.filter((o) => o.eligible);

  return (
    <div className="space-y-4 text-sm">
      {ok && <Notice tone="success">{ok}</Notice>}
      <ErrorBox error={error} />
      <Section title="Update status">
        {pa.status_targets.length === 0 ? <p className="text-xs text-slate-500">No direct status change is available from {STATUS_LABEL[c.status]}. {pa.can_assign ? "Assign an officer to continue." : pa.can_verify ? "Use verification below." : ""}</p> : (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("status", async () => {
            onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/status`, { body: { status: target, reason: reason || null, remarks: visible || null, internal_note: internal || null, expected_version: c.version } }));
            setTarget(""); setReason(""); setVisible(""); setInternal("");
          }, "Status updated."); }}>
            <select aria-label="New status" className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Choose new status…</option>
              {pa.status_targets.map((s) => <option key={s} value={s} disabled={s === "RESOLVED_AWAITING_VERIFICATION" && !pa.has_evidence}>{s === "UNDER_REVIEW" ? "Accept for review" : STATUS_LABEL[s]}{s === "RESOLVED_AWAITING_VERIFICATION" && !pa.has_evidence ? " (upload evidence first)" : ""}</option>)}
            </select>
            {needsReason && <textarea aria-label="Reason (required)" required className={inputCls} rows={2} placeholder="Reason (required, shown to citizen)" value={reason} onChange={(e) => setReason(e.target.value)} />}
            {target && <textarea aria-label="Citizen-visible remark" className={inputCls} rows={2} placeholder="Citizen-visible remark (optional)" value={visible} onChange={(e) => setVisible(e.target.value)} />}
            {target && <textarea aria-label="Internal note" className={inputCls} rows={2} placeholder="Internal note (never shown to citizen)" value={internal} onChange={(e) => setInternal(e.target.value)} />}
            <Button type="submit" disabled={!target || (needsReason && !reason.trim())} loading={busy === "status"} variant={target === "REJECTED" ? "danger" : "primary"}>Apply</Button>
          </form>
        )}
      </Section>

      {(pa.can_assign || pa.can_reassign) && (
        <Section title={pa.can_assign ? "Assign officer" : "Reassign officer"}>
          {active && <p className="text-xs text-slate-600">Currently: {active.officer?.full_name} ({active.officer?.designation})</p>}
          {eligible.length === 0 ? <p className="text-xs text-slate-500">No active officers are configured for this department.</p> : (
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("assign", async () => {
              onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/assign`, { body: { officer_id: officer, reason: assignReason || null, expected_version: c.version } }));
              setOfficer(""); setAssignReason("");
            }, pa.can_assign ? "Officer assigned." : "Complaint reassigned."); }}>
              <select aria-label="Officer" className={inputCls} value={officer} onChange={(e) => setOfficer(e.target.value)}>
                <option value="">Choose officer…</option>
                {eligible.map((o) => <option key={o.officer_id} value={o.officer_id}>{o.full_name} — {o.designation}</option>)}
              </select>
              {pa.can_reassign && <textarea aria-label="Reassignment reason" className={inputCls} rows={2} placeholder="Reason for reassignment (required)" value={assignReason} onChange={(e) => setAssignReason(e.target.value)} />}
              <Button type="submit" disabled={!officer || (pa.can_reassign && !assignReason.trim())} loading={busy === "assign"}>{pa.can_assign ? "Assign" : "Reassign"}</Button>
            </form>
          )}
        </Section>
      )}

      {pa.can_upload_evidence && (
        <Section title="Upload resolution evidence">
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); run("evidence", async () => {
            const fd = new FormData(); fd.append("file", evFile!); if (evDesc) fd.append("description", evDesc);
            await api(`/api/authority/complaints/${c.complaint_id}/evidence`, { form: fd });
            setEvFile(null); setEvDesc(""); reload();
          }, "Evidence uploaded. This does not mark the complaint as verified."); }}>
            <input aria-label="Evidence file" type="file" accept="image/jpeg,image/png,image/webp,video/mp4" onChange={(e) => setEvFile(e.target.files?.[0] || null)} className="text-xs" />
            <input aria-label="Evidence description" className={inputCls} placeholder="What was done (optional)" value={evDesc} onChange={(e) => setEvDesc(e.target.value)} />
            <Button type="submit" variant="secondary" disabled={!evFile} loading={busy === "evidence"}>Upload</Button>
          </form>
        </Section>
      )}

      {c.status === "RESOLVED_AWAITING_VERIFICATION" && (
        <Section title="Verify resolution">
          {pa.can_verify ? (
            <form className="space-y-2" onSubmit={(e) => e.preventDefault()}>
              <p className="text-xs text-slate-600">Review all {c.resolution_evidence.length} evidence item(s) and citizen feedback ({c.feedback.length ? c.feedback.map((f) => f.feedback_type).join(", ") : "no response yet"}) before deciding.</p>
              <textarea aria-label="Verification reason" className={inputCls} rows={2} placeholder="Reason / what you reviewed (required)" value={vReason} onChange={(e) => setVReason(e.target.value)} />
              <div className="flex gap-2">
                {(["APPROVED", "REJECTED"] as const).map((d) => (
                  <Button key={d} variant={d === "APPROVED" ? "primary" : "danger"} disabled={vReason.trim().length < 3} loading={busy === d}
                    onClick={() => run(d, async () => {
                      onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/verify`, { body: { decision: d, reason: vReason, evidence_reviewed: c.resolution_evidence.map((x) => x.evidence_id), expected_version: c.version } }));
                      setVReason("");
                    }, d === "APPROVED" ? "Marked verified resolved." : "Verification rejected; complaint reopened.")}>
                    {d === "APPROVED" ? "Approve verification" : "Reject & reopen"}
                  </Button>
                ))}
              </div>
            </form>
          ) : <p className="text-xs text-slate-500">You do not have the VERIFY_RESOLUTION permission for this department. A department admin must verify.</p>}
        </Section>
      )}

      <Section title="Add remark">
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); const clar = (e.nativeEvent as SubmitEvent).submitter?.getAttribute("data-clar") === "1"; run("remark", async () => {
          await api(`/api/authority/complaints/${c.complaint_id}/remarks${clar ? "?clarification=true" : ""}`, { body: { text: remark, visibility: clar ? "CITIZEN" : remarkVis } });
          setRemark(""); reload();
        }, clar ? "Clarification requested from citizen." : "Remark added."); }}>
          <textarea aria-label="Remark" className={inputCls} rows={2} value={remark} onChange={(e) => setRemark(e.target.value)} />
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="flex items-center gap-1"><input type="radio" checked={remarkVis === "CITIZEN"} onChange={() => setRemarkVis("CITIZEN")} /> Citizen-visible</label>
            <label className="flex items-center gap-1"><input type="radio" checked={remarkVis === "INTERNAL"} onChange={() => setRemarkVis("INTERNAL")} /> Internal only</label>
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="secondary" disabled={!remark.trim()} loading={busy === "remark"}>Add remark</Button>
            <Button type="submit" variant="ghost" data-clar="1" disabled={!remark.trim()}>Request clarification</Button>
          </div>
        </form>
      </Section>
    </div>
  );
}

function PriorityConfirm({ c, onUpdated }: { c: ComplaintDetail; onUpdated: (d: ComplaintDetail) => void }) {
  const [open, setOpen] = useState(false);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [explanation, setExplanation] = useState("");
  const { busy, error, run } = useAction();
  const missing = Object.entries(c.priority.factors || {}).filter(([, f]) => f.value == null).map(([k]) => k);
  if (!open) return <Button variant="secondary" className="mt-3" onClick={() => setOpen(true)}>{missing.length ? `Confirm missing factors (${missing.length})` : "Adjust factors"}</Button>;
  return (
    <form className="mt-3 space-y-2 text-sm" onSubmit={(e) => { e.preventDefault(); run("p", async () => {
      const body: Record<string, unknown> = { explanation };
      Object.entries(vals).forEach(([k, v]) => { if (v !== "") body[k] = Number(v); });
      onUpdated(await api(`/api/authority/complaints/${c.complaint_id}/priority`, { body }));
      setOpen(false);
    }, ""); }}>
      <ErrorBox error={error} />
      <p className="text-xs text-slate-600">Enter human-confirmed values (0–100) using the rubric. The backend recalculates the score; you cannot set it directly.</p>
      {Object.keys(FACTOR_LABEL).map((k) => (
        <label key={k} className="flex items-center justify-between gap-2 text-xs">{FACTOR_LABEL[k]}
          <input type="number" min={0} max={100} step="0.01" className={inputCls + " w-24"} value={vals[k] ?? ""} placeholder={c.priority.factors?.[k]?.value?.toString() ?? "unknown"} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} />
        </label>
      ))}
      <Field label="Evidence / explanation" htmlFor="pexp" required><input id="pexp" className={inputCls} value={explanation} onChange={(e) => setExplanation(e.target.value)} /></Field>
      <div className="flex gap-2"><Button type="submit" loading={!!busy} disabled={explanation.trim().length < 3 || !Object.values(vals).some((v) => v !== "")}>Save</Button><Button type="button" variant="secondary" onClick={() => setOpen(false)}>Cancel</Button></div>
    </form>
  );
}

function Publication({ c, onDone }: { c: ComplaintDetail; onDone: () => void }) {
  const [summary, setSummary] = useState(c.public_summary || "");
  const { busy, error, ok, run } = useAction();
  if (!c.allow_public_display) return <p className="text-sm text-slate-500">The citizen chose not to allow public display.</p>;
  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs text-slate-600">Status: <strong>{c.publication_status.replaceAll("_", " ").toLowerCase()}</strong>. Write a summary with no names, phone numbers or private details. Location is shown approximately.</p>
      {ok && <Notice tone="success">{ok}</Notice>}
      <ErrorBox error={error} />
      <textarea aria-label="Public summary" className={inputCls} rows={2} maxLength={500} value={summary} onChange={(e) => setSummary(e.target.value)} />
      <div className="flex gap-2">
        <Button variant="secondary" disabled={summary.trim().length < 10} loading={busy === "a"} onClick={() => run("a", async () => { await api(`/api/authority/complaints/${c.complaint_id}/publication`, { body: { approve: true, public_summary: summary } }); onDone(); }, "Approved for public display.")}>Approve public display</Button>
        <Button variant="ghost" loading={busy === "d"} onClick={() => run("d", async () => { await api(`/api/authority/complaints/${c.complaint_id}/publication`, { body: { approve: false } }); onDone(); }, "Kept private.")}>Keep private</Button>
      </div>
    </div>
  );
}

function RelatedCard({ c, onChange }: { c: ComplaintDetail; onChange: () => void }) {
  const { busy, error, run } = useAction();
  return (
    <Card title="Potentially related complaints">
      <ErrorBox error={error} />
      {c.related.length === 0 ? <p className="text-sm text-slate-500">No candidates were found within the configured distance and time window.</p> : (
        <ul className="space-y-3 text-sm">
          {c.related.map((r: any) => (
            <li key={r.complaint_id} className="rounded border border-slate-200 p-3">
              <div className="flex flex-wrap items-center gap-2">
                {r.in_scope ? <Link href={`/authority/complaints/${r.complaint_id}`} className="font-mono text-xs text-teal-700 underline">{r.reference_id}</Link> : <span className="font-mono text-xs">{r.reference_id}</span>}
                <span>{r.title}</span><StatusBadge status={r.status} />
                <Badge className="bg-white ring-slate-300">{r.relationship_status.replaceAll("_", " ").toLowerCase()}</Badge>
              </div>
              <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{r.match_reasons.map((m: string) => <li key={m}>{m}</li>)}</ul>
              <p className="mt-1 text-xs text-slate-500">Ranking score {r.similarity_score?.toFixed(2)} · text similarity {r.text_similarity?.toFixed(2)} ({r.text_similarity_method})</p>
              <div className="mt-2 flex gap-2">
                {(["CONFIRMED_RELATED", "NOT_RELATED"] as const).map((s) => (
                  <Button key={s} variant="secondary" loading={busy === r.complaint_id + s} disabled={r.relationship_status === s}
                    onClick={() => run(r.complaint_id + s, async () => { await api(`/api/complaints/${c.complaint_id}/relationships`, { body: { related_complaint_id: r.complaint_id, relationship_status: s } }); onChange(); }, "")}>
                    {s === "CONFIRMED_RELATED" ? "Mark related" : "Not related"}
                  </Button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-500">Suggestions never merge, delete or reject complaints.</p>
    </Card>
  );
}
