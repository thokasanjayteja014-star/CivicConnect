"use client";

import Link from "next/link";
import { useRequireRole } from "@/components/AuthProvider";
import { useI18n } from "@/components/I18nProvider";
import { NotificationSettings } from "@/components/NotificationSettings";
import { fmtDate } from "@/components/labels";
import { Button, EmptyState, ErrorBox, PageHeader, Spinner, cx } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

export default function Notifications() {
  const { user, allowed } = useRequireRole(["CITIZEN", "OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"]);
  const { t } = useI18n();
  const { data, error, loading, reload } = useApi<any>(allowed ? "/api/notifications" : null);
  if (!allowed) return <Spinner />;
  const base = user?.role === "CITIZEN" ? "/complaints" : "/authority/complaints";
  return (
    <div className="space-y-6">
      <PageHeader title={t("Notifications")} subtitle={t("Updates about your complaints and assignments.")}
        actions={data?.unread > 0 && <Button variant="secondary" onClick={async () => { await api("/api/notifications/read-all", { method: "POST" }); reload(); }}>{t("Mark all as read")}</Button>} />
      <NotificationSettings />
      <ErrorBox error={error} onRetry={reload} />
      {loading && !data ? <Spinner /> : data?.items.length === 0 ? <EmptyState title={t("No notifications yet")} /> : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
          {data?.items.map((n: any) => (
            <li key={n.id} className={cx("flex items-start gap-3 px-4 py-3 text-sm", !n.read_at && "bg-teal-50/50")}>
              <span className={cx("mt-1.5 h-2 w-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : "bg-teal-500")} aria-hidden />
              <div className="flex-1">
                <p>{n.message}</p>
                <p className="text-xs text-slate-500">{fmtDate(n.created_at)}
                  {n.external_deliveries?.map((d: any) => <span key={d.channel} className={cx("ml-2 rounded px-1.5 py-0.5 text-[10px]", d.status === "SENT" ? "bg-green-50 text-green-800" : "bg-red-50 text-red-800")}>{t(d.channel === "EMAIL" ? "Email" : d.channel === "SMS" ? "SMS" : "Browser")} {d.status === "SENT" ? t("sent") : t("failed")}</span>)}
                </p>
              </div>
              {n.complaint_id && <Link href={`${base}/${n.complaint_id}`} onClick={() => api(`/api/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined)} className="text-xs font-medium text-teal-700 underline">{t("Open")}</Link>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
