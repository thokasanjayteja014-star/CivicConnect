"use client";

import { AlertTriangle, CheckCircle2, CircleDot, MessageSquare } from "lucide-react";
import Link from "next/link";
import { CATEGORY_LABEL, FACTOR_LABEL, STATUS_LABEL, fmtDate } from "@/components/labels";
import { Badge, Notice, PriorityBadge, RoutingBadge, StatusBadge } from "@/components/ui";
import type { ComplaintDetail, ComplaintListItem } from "@/types";

export function ComplaintTable({ items, hrefBase, staff = false }: { items: ComplaintListItem[]; hrefBase: string; staff?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-4 py-3">Reference</th>
            <th className="px-4 py-3">Title</th>
            <th className="px-4 py-3">Category</th>
            {staff && <th className="px-4 py-3">Location</th>}
            <th className="px-4 py-3">Priority</th>
            <th className="px-4 py-3">Submitted</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">{staff ? "Assigned officer" : "Department"}</th>
            <th className="px-4 py-3"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((c) => (
            <tr key={c.complaint_id} className="hover:bg-slate-50">
              <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-navy-800">{c.reference_id}</td>
              <td className="px-4 py-3">
                <div className="font-medium text-slate-900">{c.title}</div>
                {c.needs_prompt_review && <span className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-red-700"><AlertTriangle className="h-3 w-3" /> Safety review</span>}
              </td>
              <td className="whitespace-nowrap px-4 py-3">{CATEGORY_LABEL[c.category]}</td>
              {staff && <td className="px-4 py-3 text-xs text-slate-600">{c.location.landmark || c.location.address_text || `${c.location.latitude.toFixed(4)}, ${c.location.longitude.toFixed(4)}`}</td>}
              <td className="px-4 py-3"><PriorityBadge level={c.priority_level} status={c.priority_assessment_status} score={c.priority_score} /></td>
              <td className="whitespace-nowrap px-4 py-3 text-slate-600">{fmtDate(c.created_at, false)}</td>
              <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
              <td className="px-4 py-3 text-slate-700">
                {staff ? (c.assigned_officer ? `${c.assigned_officer.full_name ?? ""} (${c.assigned_officer.designation})` : "—")
                  : c.department ? c.department.name : <RoutingBadge status={c.routing_status} />}
              </td>
              <td className="px-4 py-3 text-right">
                <Link href={`${hrefBase}/${c.complaint_id}`} className="text-sm font-medium text-teal-700 hover:underline">Open</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Timeline({ entries }: { entries: ComplaintDetail["timeline"] }) {
  return (
    <ol className="relative space-y-4 border-l border-slate-200 pl-6">
      {entries.map((e, i) => (
        <li key={i} className="relative">
          <span className="absolute -left-[31px] top-0.5 grid h-5 w-5 place-items-center rounded-full bg-white ring-1 ring-slate-300">
            {e.type === "STATUS" ? <CircleDot className="h-3 w-3 text-navy-600" /> : <MessageSquare className="h-3 w-3 text-teal-600" />}
          </span>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {e.type === "STATUS" ? (
              <span className="font-medium text-slate-900">{e.previous_status ? `${STATUS_LABEL[e.previous_status]} → ` : ""}{STATUS_LABEL[e.new_status!]}</span>
            ) : (
              <span className="font-medium text-slate-900">
                {e.type === "CLARIFICATION_REQUEST" ? "Clarification requested" : e.type === "CITIZEN_REPLY" ? "Citizen reply" : "Remark"}
                {e.visibility === "INTERNAL" && <Badge className="ml-2 bg-slate-800 text-white ring-slate-800">Internal</Badge>}
              </span>
            )}
            <span className="text-xs text-slate-500">{e.author_name ? `${e.author_name} · ` : ""}{e.actor_role} · {fmtDate(e.created_at)}</span>
          </div>
          {e.remarks && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{e.remarks}</p>}
        </li>
      ))}
    </ol>
  );
}

export function PriorityPanel({ p }: { p: ComplaintDetail["priority"] }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <PriorityBadge level={p.priority_level} status={p.priority_assessment_status} score={p.priority_score} />
        <Badge className="bg-white text-slate-600 ring-slate-300">Assessment: {p.priority_assessment_status}</Badge>
        {p.needs_prompt_review && <Badge className="bg-red-50 text-red-800 ring-red-200">Prompt safety review</Badge>}
      </div>
      {p.factors && (
        <table className="w-full text-sm">
          <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="py-1">Factor</th><th>Value</th><th>Weight</th><th>Evidence</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {Object.entries(p.factors).map(([k, f]) => (
              <tr key={k}>
                <td className="py-1.5 pr-2 font-medium text-slate-800">{FACTOR_LABEL[k] || k}</td>
                <td className="pr-2">{f.value == null ? <span className="text-slate-400">unknown</span> : f.value}</td>
                <td className="pr-2 text-slate-500">{p.weights?.[k] != null ? p.weights[k].toFixed(2) : ""}</td>
                <td className="text-xs text-slate-600">{f.explanation} <span className="text-slate-400">({f.source.replaceAll("_", " ").toLowerCase()})</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {p.review_reasons?.length > 0 && <ul className="list-disc pl-5 text-xs text-amber-800">{p.review_reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <p className="text-xs text-slate-500">{p.disclaimer}</p>
    </div>
  );
}

export function RoutingPanel({ r }: { r: ComplaintDetail["routing"] }) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <RoutingBadge status={r.routing_status} />
        {r.department && <span className="font-medium">{r.department.name}{r.department.is_prototype && <span className="ml-1 text-xs text-slate-500">(prototype configuration)</span>}</span>}
      </div>
      {r.message && <p className="text-slate-700">{r.message}</p>}
      {r.explanation && <p className="text-xs text-slate-500">{r.explanation}</p>}
      {r.jurisdiction && <p className="text-xs text-slate-500">Jurisdiction: {r.jurisdiction.name}{r.jurisdiction.is_prototype ? " (prototype configuration)" : ""}</p>}
      {r.rule_version && <p className="text-xs text-slate-400">Rule version {r.rule_version}{r.manually_reviewed ? " · confirmed by administrator" : ""}</p>}
    </div>
  );
}

export function ResolutionNotice({ status }: { status: string }) {
  if (status === "RESOLVED_AWAITING_VERIFICATION")
    return <Notice tone="warn">The department reports this issue as resolved. It has <strong>not yet been independently verified</strong>.</Notice>;
  if (status === "VERIFIED_RESOLVED")
    return <Notice tone="success"><CheckCircle2 className="mr-1 inline h-4 w-4" />Resolution verified by an authorized reviewer.</Notice>;
  return null;
}
