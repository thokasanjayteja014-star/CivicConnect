"use client";

import { useT } from "@/components/I18nProvider";
import { STATUS_LABEL, fmtDate } from "@/components/labels";
import { Badge, Card, KeyValue, PageHeader } from "@/components/ui";
import { Loadable } from "@/features/admin";
import { useApi } from "@/hooks/useApi";

export default function SettingsPage() {
  const t = useT();
  const sys = useApi<any>("/api/admin/system");
  const life = useApi<any>("/api/admin/lifecycle");
  const ok = (v: boolean) => v ? <Badge className="bg-green-50 text-green-800 ring-green-200">{t("Working")}</Badge> : <Badge className="bg-red-50 text-red-800 ring-red-200">{t("Not available")}</Badge>;
  return (
    <div className="space-y-5">
      <PageHeader title={t("Settings")} subtitle={t("System health and fixed workflow rules. Technical details are kept here, away from the operational overview.")} />
      <div className="grid gap-5 xl:grid-cols-2">
        <Card title={t("System status")}>
          <Loadable q={sys}>{(d) => (
            <>
              <KeyValue items={[
                [t("Database"), ok(d.database.ok)],
                [t("Map database (PostGIS)"), d.database.postgis ? d.database.postgis.split(" ")[0] : "—"],
                [t("File storage"), ok(d.storage.ok)],
                [t("AI-assisted reporting"), d.ai.mode === "stub" ? <Badge>{t("Not configured")}</Badge> : <Badge className="bg-green-50 text-green-800 ring-green-200">{t("Configured")}</Badge>],
                [t("Last checked"), fmtDate(d.checked_at)],
              ]} />
              {d.ai.capabilities?.length > 0 && (
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer text-xs font-medium text-navy-700">{t("AI capability details")}</summary>
                  <ul className="mt-2 space-y-1 text-xs text-slate-600">{d.ai.capabilities.map((c: any) => <li key={c.name}>{c.name.replaceAll("_", " ")}: {c.status}{c.model ? ` (${c.model})` : ""}</li>)}</ul>
                </details>
              )}
            </>
          )}</Loadable>
        </Card>
        <Card title={t("Complaint lifecycle")} subtitle={t("Permitted status changes. These are enforced by the server and cannot be weakened from the interface.")}>
          <Loadable q={life}>{(d) => (
            <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
              {Object.entries(d.transitions).map(([from, to]: any) => (
                <tr key={from}><td className="py-1.5 pr-3 font-medium">{t(STATUS_LABEL[from] || from)}</td>
                  <td className="py-1.5 text-xs text-slate-600">→ {to.length ? to.map((x: string) => t(STATUS_LABEL[x] || x)).join(", ") : t("Final")}</td></tr>
              ))}
            </tbody></table>
          )}</Loadable>
        </Card>
      </div>
    </div>
  );
}
