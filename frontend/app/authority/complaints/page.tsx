"use client";

import { Suspense } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { PageHeader, Spinner } from "@/components/ui";
import { ComplaintsBrowser } from "@/features/complaints-browser";

export default function AuthorityComplaints() {
  const t = useT();
  const { user } = useAuth();
  const officer = user?.role === "OFFICER";
  return (
    <div>
      <PageHeader title={officer ? t("My assignments") : t("Complaints")}
        subtitle={officer ? t("Complaints assigned to you and complaints in your operational areas.") : t("All complaints handled by your department unit.")} />
      <Suspense fallback={<Spinner />}>
        <ComplaintsBrowser defaults={officer ? { assignment: "mine", status_group: "open", sort: "due" } : { status_group: "open", sort: "priority" }}
          emptyTitle={officer ? t("Nothing assigned to you right now") : undefined} />
      </Suspense>
    </div>
  );
}
