"use client";

import Link from "next/link";
import { useState } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { fmtDate } from "@/components/labels";
import { Badge, Button, Checkbox, EmptyState, ErrorBox, Notice, PageHeader, Spinner, StatusBadge, inputCls } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

export default function ReopenReviews() {
  const t = useT();
  const { allowed } = useRequireRole(["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]);
  const [showDecided, setShowDecided] = useState(false);
  const { data, error, loading, reload } = useApi<any[]>(allowed ? `/api/authority/reopen-requests?include_decided=${showDecided}` : null, [showDecided]);
  if (!allowed) return <Spinner />;
  return (
    <div className="space-y-6">
      <PageHeader title={t("Reopening reviews")} subtitle={t("Citizens who say their complaint was not resolved can ask to reopen it. The complaint changes only if you accept.")}
        actions={<Checkbox checked={showDecided} onChange={setShowDecided} label={t("Show decided")} />} />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Spinner /> : data && data.length === 0 ? <EmptyState title={t("No reopening requests")} body={t("Requests from citizens will appear here for review.")} /> : (
        <ul className="space-y-3">{data?.map((r) => <ReviewItem key={r.feedback_id} r={r} onDone={reload} />)}</ul>
      )}
    </div>
  );
}

function ReviewItem({ r, onDone }: { r: any; onDone: () => void }) {
  const t = useT();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const decide = async (decision: "ACCEPTED" | "REJECTED") => {
    setBusy(decision); setError(null);
    try { await api(`/api/authority/feedback/${r.feedback_id}/review`, { body: { decision, reason } }); onDone(); } catch (e) { setError(e); } finally { setBusy(null); }
  };
  return (
    <li className="rounded-md border border-slate-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/authority/complaints/${r.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{r.reference_id}</Link>
        <span className="font-medium">{r.title}</span><StatusBadge status={r.complaint_status} />
        <Badge className="bg-orange-50 text-orange-800 ring-orange-200">{t(r.feedback_type.replaceAll("_", " ").toLowerCase())}</Badge>
        <span className="text-xs text-slate-500">{fmtDate(r.created_at)}</span>
      </div>
      <p className="mt-2 whitespace-pre-wrap">{r.remarks}</p>
      {r.review_status !== "PENDING" ? (
        <Notice tone={r.review_status === "ACCEPTED" ? "success" : "info"}>{t(r.review_status.toLowerCase())} · {fmtDate(r.reviewed_at)}: {r.decision_reason}</Notice>
      ) : r.can_decide ? (
        <div className="mt-3 space-y-2">
          <ErrorBox error={error} />
          <textarea aria-label={t("Decision reason (required, shared with citizen)")} className={inputCls} rows={2} placeholder={t("Decision reason (required, shared with citizen)")} value={reason} onChange={(e) => setReason(e.target.value)} />
          <div className="flex gap-2">
            <Button disabled={reason.trim().length < 3} loading={busy === "ACCEPTED"} onClick={() => decide("ACCEPTED")}>{t("Accept and reopen")}</Button>
            <Button variant="secondary" disabled={reason.trim().length < 3} loading={busy === "REJECTED"} onClick={() => decide("REJECTED")}>{t("Reject")}</Button>
          </div>
        </div>
      ) : <p className="mt-2 text-xs text-slate-500">{t("Only the department administrator can decide.")}</p>}
    </li>
  );
}
