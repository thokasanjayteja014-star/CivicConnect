"use client";

import { AlertTriangle, CheckCircle2, CircleDot, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, FACTOR_LABEL, STATUS_LABEL, fmtDate, relDays } from "@/components/labels";
import { Badge, Notice, PriorityBadge, RoutingBadge, StatusBadge } from "@/components/ui";
import type { ComplaintDetail, ComplaintListItem } from "@/types";

function Deadline({ c }: { c: ComplaintListItem }) {
  const t = useT();
  const r = relDays(c.due_at);
  if (!r || ["VERIFIED_RESOLVED", "REJECTED", "RESOLVED_AWAITING_VERIFICATION"].includes(c.status)) return <span className="text-slate-400">—</span>;
  return r.overdue
    ? <span className="font-medium text-red-700">{t("Overdue {n} d", { n: r.days })}</span>
    : <span className="text-slate-600">{r.days === 0 ? t("Due today") : t("{n} d left", { n: r.days })}</span>;
}

export function ComplaintTable({ items, hrefBase, staff = false }: { items: ComplaintListItem[]; hrefBase: string; staff?: boolean }) {
  const t = useT();
  return (
    <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold text-slate-600">
          <tr>
            <th className="px-3 py-2">{t("Reference")}</th>
            <th className="px-3 py-2">{t("Complaint")}</th>
            {staff && <th className="px-3 py-2">{t("Location")}</th>}
            <th className="px-3 py-2">{t("Priority")}</th>
            <th className="px-3 py-2">{t("Status")}</th>
            {staff && <th className="px-3 py-2">{t("Deadline")}</th>}
            <th className="px-3 py-2">{staff ? t("Assigned officer") : t("Department")}</th>
            <th className="px-3 py-2">{t("Submitted")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((c) => (
            <tr key={c.complaint_id} className="hover:bg-slate-50">
              <td className="whitespace-nowrap px-3 py-2"><Link href={`${hrefBase}/${c.complaint_id}`} className="font-mono text-xs font-medium text-navy-700 underline">{c.reference_id}</Link></td>
              <td className="px-3 py-2">
                <Link href={`${hrefBase}/${c.complaint_id}`} className="font-medium text-slate-900 hover:underline">{c.title}</Link>
                <div className="text-xs text-slate-500">{t(CATEGORY_LABEL[c.category])}{staff && c.department ? ` · ${c.department.name}` : ""}</div>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {c.needs_prompt_review && <Badge className="bg-red-50 text-red-800 ring-red-200"><AlertTriangle className="h-3 w-3" /> {t("Safety review")}</Badge>}
                  {staff && c.escalated ? <Badge className="bg-amber-50 text-amber-800 ring-amber-200">{t("Escalated L{n}", { n: c.escalated })}</Badge> : null}
                  {staff && c.routing_status !== "ROUTED" && <RoutingBadge status={c.routing_status} />}
                </div>
              </td>
              {staff && <td className="px-3 py-2 text-xs text-slate-600">{c.jurisdiction?.name && <div className="font-medium text-slate-700">{c.jurisdiction.name}</div>}{c.location.landmark || c.location.address_text || `${c.location.latitude.toFixed(4)}, ${c.location.longitude.toFixed(4)}`}</td>}
              <td className="px-3 py-2"><PriorityBadge level={c.priority_level} status={c.priority_assessment_status} score={c.priority_score} /></td>
              <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
              {staff && <td className="whitespace-nowrap px-3 py-2 text-xs"><Deadline c={c} /></td>}
              <td className="px-3 py-2 text-slate-700">
                {staff ? (c.assigned_officer ? <>{c.assigned_officer.full_name}{!c.assignment_accepted && <div className="text-xs text-amber-700">{t("Not yet accepted")}</div>}</>
                  : (c.routing_status === "ROUTED" && ["SUBMITTED", "UNDER_REVIEW", "REOPENED"].includes(c.status) ? <span className="text-xs font-medium text-amber-700">{t("Awaiting assignment")}</span> : "—"))
                  : c.department ? c.department.name : <RoutingBadge status={c.routing_status} />}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-xs text-slate-600">{fmtDate(c.created_at, false)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Timeline({ entries }: { entries: ComplaintDetail["timeline"] }) {
  const t = useT();
  return (
    <ol className="relative space-y-4 border-l border-slate-200 pl-6">
      {entries.map((e, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-white ring-1 ring-slate-300">
            {e.type === "STATUS" ? <CircleDot className="h-3 w-3 text-navy-600" /> : <MessageSquare className="h-3 w-3 text-navy-600" />}
          </span>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {e.type === "STATUS" ? (
              <span className="font-medium text-slate-900">{e.previous_status ? `${t(STATUS_LABEL[e.previous_status])} → ` : ""}{t(STATUS_LABEL[e.new_status!])}</span>
            ) : (
              <span className="font-medium text-slate-900">
                {e.type === "CLARIFICATION_REQUEST" ? t("Clarification requested") : e.type === "CITIZEN_REPLY" ? t("Citizen reply") : t("Remark")}
                {e.visibility === "INTERNAL" && <Badge className="ml-2 bg-slate-800 text-white ring-slate-800">{t("Internal")}</Badge>}
              </span>
            )}
            <span className="text-xs text-slate-500">{e.author_name ? `${e.author_name} · ` : ""}{t(e.actor_role)} · {fmtDate(e.created_at)}</span>
          </div>
          {e.remarks && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{e.remarks}</p>}
        </li>
      ))}
    </ol>
  );
}

export function PriorityPanel({ p }: { p: ComplaintDetail["priority"] }) {
  const t = useT();
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <PriorityBadge level={p.priority_level} status={p.priority_assessment_status} score={p.priority_score} />
        <Badge className="bg-white text-slate-600 ring-slate-300">{t("Assessment")}: {t(p.priority_assessment_status)}</Badge>
        {p.needs_prompt_review && <Badge className="bg-red-50 text-red-800 ring-red-200">{t("Prompt safety review")}</Badge>}
      </div>
      {p.factors && (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs text-slate-500"><th className="py-1">{t("Factor")}</th><th>{t("Value")}</th><th>{t("Weight")}</th><th>{t("Evidence")}</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {Object.entries(p.factors).map(([k, f]) => (
              <tr key={k}>
                <td className="py-1.5 pr-2 font-medium text-slate-800">{t(FACTOR_LABEL[k] || k)}</td>
                <td className="pr-2">{f.value == null ? <span className="text-slate-400">{t("unknown")}</span> : f.value}</td>
                <td className="pr-2 text-slate-500">{p.weights?.[k] != null ? p.weights[k].toFixed(2) : ""}</td>
                <td className="text-xs text-slate-600">{f.explanation} <span className="text-slate-400">({f.source.replaceAll("_", " ").toLowerCase()})</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {p.community && p.community.other_reporters > 0 && (
        <p className="rounded-md border border-navy-200 bg-navy-50 px-3 py-2 text-sm text-navy-900">
          <strong>{t("Reported by {n} other residents", { n: p.community.other_reporters })}</strong>{" · "}
          {t("+{points} priority points", { points: p.community.boost })}
          {p.community.base_score != null && <span className="text-xs text-navy-700"> ({t("base score {score}", { score: p.community.base_score })})</span>}
        </p>
      )}
      {p.review_reasons?.length > 0 && <ul className="list-disc pl-5 text-xs text-amber-800">{p.review_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <p className="text-xs text-slate-500">{p.disclaimer}</p>
    </div>
  );
}

export function RoutingPanel({ r }: { r: ComplaintDetail["routing"] }) {
  const t = useT();
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <RoutingBadge status={r.routing_status} />
        {r.department && <span className="font-medium">{r.department.name}</span>}
      </div>
      {r.message && <p className="text-slate-700">{t(r.message)}</p>}
      {r.explanation && <p className="text-xs text-slate-500">{r.explanation}</p>}
      {r.jurisdiction && <p className="text-xs text-slate-500">{t("Jurisdiction")}: {r.jurisdiction.name}</p>}
      {r.manually_reviewed && <p className="text-xs text-slate-500">{t("Confirmed by an administrator")}</p>}
    </div>
  );
}

export function ResolutionNotice({ status }: { status: string }) {
  const t = useT();
  if (status === "RESOLVED_AWAITING_VERIFICATION")
    return <Notice tone="warn">{t("The department reports this issue as resolved. It has not yet been verified.")}</Notice>;
  if (status === "VERIFIED_RESOLVED")
    return <Notice tone="success"><CheckCircle2 className="mr-1 inline h-4 w-4" />{t("Resolution verified by an authorized reviewer.")}</Notice>;
  return null;
}
