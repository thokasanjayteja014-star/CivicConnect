"use client";

import Link from "next/link";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { STATUS_LABEL, fmtDate } from "@/components/labels";
import { Card, PageHeader, Stat, StatusBadge, TableWrap, cx, tableCls, tdCls, thCls } from "@/components/ui";
import { Loadable } from "@/features/admin";
import { useApi } from "@/hooks/useApi";

// Validated categorical pair (light surface): submitted / resolved.
const SERIES = [
  { key: "submitted", label: "Submitted", color: "#2f5fae" },
  { key: "resolved", label: "Verified resolved", color: "#c2410c" },
] as const;

function hours(h: number | null) {
  if (h == null) return "—";
  return h >= 48 ? `${(h / 24).toFixed(1)} d` : `${h.toFixed(0)} h`;
}

function TrendChart({ data }: { data: { week_start: string; submitted: number; resolved: number }[] }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const W = 640, H = 200, padL = 28, padB = 24, padT = 8;
  const max = Math.max(1, ...data.flatMap((d) => [d.submitted, d.resolved]));
  const ticks = Array.from(new Set([0, Math.ceil(max / 2), max]));
  const band = (W - padL) / data.length;
  const bw = Math.max(3, Math.min(14, band / 2 - 4));
  const y = (v: number) => padT + (H - padT - padB) * (1 - v / max);
  const label = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4 text-xs text-slate-600">
        {SERIES.map((s) => <span key={s.key} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />{t(s.label)}</span>)}
        <button type="button" className="ml-auto font-medium text-navy-700 underline" onClick={() => setTable(!table)}>{table ? t("Show chart") : t("Show as table")}</button>
      </div>
      {table ? (
        <TableWrap><table className={tableCls}><thead><tr><th className={thCls}>{t("Week starting")}</th><th className={thCls}>{t("Submitted")}</th><th className={thCls}>{t("Verified resolved")}</th></tr></thead>
          <tbody className="divide-y divide-slate-100">{data.map((d) => <tr key={d.week_start}><td className={tdCls}>{label(d.week_start)}</td><td className={tdCls}>{d.submitted}</td><td className={tdCls}>{d.resolved}</td></tr>)}</tbody></table></TableWrap>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-52 w-full" role="img" aria-label={t("Complaints submitted and resolved per week, last 12 weeks")}>
            {ticks.map((v) => (
              <g key={v}>
                <line x1={padL} x2={W} y1={y(v)} y2={y(v)} stroke="#e2e8f0" strokeWidth={1} />
                <text x={padL - 6} y={y(v) + 3} textAnchor="end" fontSize={10} fill="#64748b">{v}</text>
              </g>
            ))}
            {data.map((d, i) => {
              const cx0 = padL + band * i + band / 2;
              return (
                <g key={d.week_start} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={padL + band * i} y={padT} width={band} height={H - padT - padB} fill={hover === i ? "#f1f5f9" : "transparent"} />
                  {SERIES.map((s, si) => {
                    const v = d[s.key];
                    const x = cx0 + (si === 0 ? -bw - 1 : 1);
                    const h = Math.max(0, H - padB - y(v));
                    return v > 0 ? <path key={s.key} fill={s.color}
                      d={`M${x},${H - padB} v${-(h - Math.min(4, h))} q0,-${Math.min(4, h)} ${Math.min(4, bw / 2)},-${Math.min(4, h)} h${bw - 2 * Math.min(4, bw / 2)} q${Math.min(4, bw / 2)},0 ${Math.min(4, bw / 2)},${Math.min(4, h)} v${h - Math.min(4, h)} z`} /> : null;
                  })}
                  {i % 2 === 0 && <text x={cx0} y={H - 8} textAnchor="middle" fontSize={10} fill="#64748b">{label(d.week_start)}</text>}
                </g>
              );
            })}
          </svg>
          {hover != null && (
            <div className="pointer-events-none absolute top-0 rounded border border-slate-200 bg-white px-2 py-1 text-xs"
              style={{ left: `${Math.min(80, ((padL + band * hover) / W) * 100)}%` }}>
              <div className="font-medium text-slate-900">{t("Week of {d}", { d: label(data[hover].week_start) })}</div>
              {SERIES.map((s) => <div key={s.key} className="flex items-center gap-1.5 text-slate-700"><span className="h-2 w-2 rounded-sm" style={{ background: s.color }} />{t(s.label)}: {data[hover][s.key]}</div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminOverview() {
  const t = useT();
  const q = useApi<any>("/api/admin/overview");
  return (
    <div className="space-y-5">
      <PageHeader title={t("Overview")} subtitle={t("Live figures from complaint records across all departments and jurisdictions.")} />
      <Loadable q={q}>{(d) => {
        const tot = d.totals;
        const att = d.attention;
        const pv = att.pending_verification;
        return (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
              <Stat label={t("Total complaints")} value={tot.total} href="/admin/complaints" />
              <Stat label={t("New")} value={tot.new} hint={t("Submitted, not yet reviewed")} href="/admin/complaints?status=SUBMITTED" />
              <Stat label={t("Pending")} value={tot.pending} hint={t("All open complaints")} href="/admin/complaints?status_group=open" />
              <Stat label={t("Awaiting assignment")} value={tot.awaiting_assignment} tone={tot.awaiting_assignment ? "warn" : undefined} href="/admin/complaints?assignment=unassigned" />
              <Stat label={t("Under investigation")} value={tot.under_investigation} hint={t("Assigned, in progress or on hold")} />
              <Stat label={t("Resolved")} value={tot.resolved} tone="ok" hint={t("{n} verified", { n: tot.verified_resolved })} />
              <Stat label={t("Overdue")} value={tot.overdue} tone={tot.overdue ? "danger" : undefined} href="/admin/complaints?overdue=true" />
              <Stat label={t("Escalated")} value={tot.escalated} tone={tot.escalated ? "warn" : undefined} href="/admin/escalations" />
              <Stat label={t("Average resolution time")} value={hours(tot.avg_resolution_hours)} hint={tot.resolved_sample ? t("Across {n} verified resolutions", { n: tot.resolved_sample }) : t("No verified resolutions yet")} />
              <Stat label={t("Rejected")} value={tot.rejected} />
            </div>

            <div className="grid gap-5 xl:grid-cols-3">
              <Card title={t("Complaint trend")} subtitle={t("Last 12 weeks")} className="xl:col-span-2"><TrendChart data={d.trend_weekly} /></Card>
              <Card title={t("Needs attention")}>
                <ul className="space-y-3 text-sm">
                  <li className="flex items-center justify-between gap-2"><Link className="text-navy-700 underline" href="/admin/routing">{t("Complaints awaiting routing review")}</Link><strong>{att.routing_review}</strong></li>
                  <li className="flex items-center justify-between gap-2"><Link className="text-navy-700 underline" href="/admin/public-issues">{t("Public issues awaiting publication")}</Link><strong>{att.public_issues_awaiting_publication}</strong></li>
                  <li>
                    <div className="flex items-center justify-between gap-2"><Link className="text-navy-700 underline" href="/admin/users">{t("Department units without officers")}</Link><strong>{att.units_without_officers.length}</strong></div>
                    {att.units_without_officers.length > 0 && <ul className="mt-1 space-y-0.5 pl-3 text-xs text-slate-600">{att.units_without_officers.slice(0, 5).map((u: any) => <li key={u.unit_id}>{u.label}</li>)}</ul>}
                  </li>
                  <li className="flex items-center justify-between gap-2"><Link className="text-navy-700 underline" href="/admin/sources">{t("Records pending verification")}</Link><strong>{pv.departments + pv.jurisdictions + pv.responsibilities}</strong></li>
                </ul>
              </Card>
            </div>

            <div className="grid gap-5 xl:grid-cols-2">
              <Card title={t("Department performance")} padded={false}>
                {d.department_performance.length === 0 ? <p className="p-4 text-sm text-slate-500">{t("No departments configured yet.")}</p> : (
                  <div className="overflow-x-auto"><table className={tableCls}>
                    <thead><tr>{["Department", "Total", "Open", "Resolved", "Overdue", "Escalated", "Resolution rate", "Avg. time"].map((h) => <th key={h} className={thCls}>{t(h)}</th>)}</tr></thead>
                    <tbody className="divide-y divide-slate-100">{d.department_performance.map((p: any) => (
                      <tr key={p.department_id}>
                        <td className={tdCls + " font-medium"}>{p.department}{!p.active && <span className="ml-1 text-xs text-slate-500">({t("inactive")})</span>}</td>
                        <td className={tdCls}>{p.total}</td><td className={tdCls}>{p.open}</td><td className={tdCls}>{p.resolved}</td>
                        <td className={cx(tdCls, p.overdue && "font-semibold text-red-700")}>{p.overdue}</td>
                        <td className={tdCls}>{p.escalated}</td>
                        <td className={tdCls}>{p.resolution_rate == null ? "—" : `${p.resolution_rate}%`}</td>
                        <td className={tdCls}>{hours(p.avg_resolution_hours)}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>
                )}
              </Card>
              <Card title={t("Complaints by jurisdiction")} padded={false}>
                {d.by_jurisdiction.length === 0 ? <p className="p-4 text-sm text-slate-500">{t("No located complaints yet.")}</p> : (
                  <div className="overflow-x-auto"><table className={tableCls}>
                    <thead><tr><th className={thCls}>{t("Jurisdiction")}</th><th className={thCls}>{t("Total")}</th><th className={thCls}>{t("Open")}</th></tr></thead>
                    <tbody className="divide-y divide-slate-100">{d.by_jurisdiction.map((j: any) => (
                      <tr key={j.jurisdiction_id}><td className={tdCls}>{j.name}</td><td className={tdCls}>{j.count}</td><td className={tdCls}>{j.open}</td></tr>
                    ))}</tbody>
                  </table></div>
                )}
              </Card>
            </div>

            <div className="grid gap-5 xl:grid-cols-3">
              <Card title={t("Recent activity")} className="xl:col-span-2" padded={false}>
                {d.recent_activity.length === 0 ? <p className="p-4 text-sm text-slate-500">{t("No activity yet.")}</p> : (
                  <ul className="divide-y divide-slate-100 text-sm">{d.recent_activity.map((a: any, i: number) => (
                    <li key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2">
                      <span className="w-36 shrink-0 text-xs text-slate-500">{fmtDate(a.at)}</span>
                      <Link href={`/authority/complaints/${a.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{a.reference_id}</Link>
                      <span className="min-w-0 flex-1 truncate">{a.title}</span>
                      <StatusBadge status={a.status} />
                      <span className="text-xs text-slate-500">{a.by}</span>
                    </li>
                  ))}</ul>
                )}
              </Card>
              <Card title={t("Configuration")}>
                <ul className="space-y-2 text-sm">
                  {[["Active departments", d.configuration.departments, "/admin/departments"], ["Active jurisdictions", d.configuration.jurisdictions, "/admin/jurisdictions"],
                    ["Department units", d.configuration.units, "/admin/mapping"], ["Department administrators", d.configuration.department_admins, "/admin/users"],
                    ["Officers", d.configuration.officers, "/admin/users"]].map(([l, v, h]) => (
                    <li key={l as string} className="flex justify-between"><Link href={h as string} className="text-navy-700 underline">{t(l as string)}</Link><strong>{v as number}</strong></li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-slate-500">{t("By status")}: {Object.entries(d.by_status).map(([k, v]) => `${t(STATUS_LABEL[k] || k)} ${v}`).join(" · ") || "—"}</p>
              </Card>
            </div>
          </>
        );
      }}</Loadable>
    </div>
  );
}
