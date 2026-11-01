"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useT } from "@/components/I18nProvider";
import { CATEGORY_LABEL, ISSUE_PROGRESS_LABEL, fmtDate } from "@/components/labels";
import { PointMap } from "@/components/map";
import { Badge, Card, ErrorBox, KeyValue, Spinner } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

export default function PublicIssuePage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const q = useApi<any>(`/api/public/issues/${id}`);
  const i = q.data;
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link href="/public" className="inline-flex items-center gap-1 text-sm text-navy-700 underline"><ArrowLeft className="h-4 w-4" /> {t("All public issues")}</Link>
      <ErrorBox error={q.error} onRetry={q.reload} />
      {!i ? (!q.error && <Spinner />) : (
        <>
          <div className="border-b border-slate-200 pb-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={i.progress === "RESOLVED" ? "bg-green-50 text-green-800 ring-green-200" : "bg-slate-50 text-slate-700 ring-slate-300"}>{t(ISSUE_PROGRESS_LABEL[i.progress])}</Badge>
              {i.verification && <Badge className={i.verification === "Verified by the department" ? "bg-navy-50 text-navy-800 ring-navy-200" : "bg-amber-50 text-amber-900 ring-amber-200"}>{t(i.verification)}</Badge>}
              {i.auto_generated && <Badge className="bg-amber-50 text-amber-900 ring-amber-200">{t("Reported by several residents")}</Badge>}
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900">{i.title}</h1>
            <p className="mt-1 text-sm text-slate-600">{[i.general_location, i.area].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <Card title={t("About this issue")}>
                <p className="whitespace-pre-wrap text-slate-800">{i.description}</p>
                {i.published_automatically && <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">{t("CivicConnect published this issue automatically because the department did not review it within 7 days of several residents reporting it.")}</p>}
                {i.resolution_info && <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900"><strong>{t("Resolution")}:</strong> {i.resolution_info}</div>}
              </Card>
              <Card title={t("Progress updates")}>
                {i.updates.length === 0 ? <p className="text-sm text-slate-500">{t("No updates yet.")}</p> : (
                  <ol className="space-y-3">{i.updates.map((u: any, n: number) => (
                    <li key={n} className="border-l-2 border-navy-200 pl-3">
                      <p className="text-xs text-slate-500">{fmtDate(u.created_at)}{u.progress ? ` · ${t(ISSUE_PROGRESS_LABEL[u.progress])}` : ""}</p>
                      <p className="text-sm">{u.automatic ? t(u.message) : u.message}</p>
                    </li>
                  ))}</ol>
                )}
              </Card>
            </div>
            <div className="space-y-5">
              <Card title={t("Details")}>
                <KeyValue items={[
                  [t("Department"), i.department], [t("Category"), i.category ? t(CATEGORY_LABEL[i.category]) : "—"],
                  [t("Related complaints"), i.related_complaints], [t("Impact"), i.impact_level ? t(i.impact_level) : "—"],
                  [t("Published"), fmtDate(i.published_at, false)], [t("Last update"), fmtDate(i.last_update, false)],
                  ...(i.resolved_at ? [[t("Resolved"), fmtDate(i.resolved_at, false)] as [string, string]] : []),
                ]} />
              </Card>
              {i.latitude != null && i.longitude != null && <Card title={t("Approximate location")}><PointMap lat={i.latitude} lng={i.longitude} /></Card>}
            </div>
          </div>
          <p className="text-xs text-slate-500">{t("Personal details of the citizens who reported this issue are never published.")}</p>
        </>
      )}
    </div>
  );
}
