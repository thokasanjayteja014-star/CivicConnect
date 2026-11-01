"use client";

import { Suspense } from "react";
import { useT } from "@/components/I18nProvider";
import { PageHeader, Spinner } from "@/components/ui";
import { ComplaintsBrowser } from "@/features/complaints-browser";

export default function UnassignedQueue() {
  const t = useT();
  return (
    <div>
      <PageHeader title={t("Unassigned queue")}
        subtitle={t("Complaints routed to your unit that have no officer yet, usually because no active officer covers the location. Open a complaint to assign it.")} />
      <Suspense fallback={<Spinner />}>
        <ComplaintsBrowser fixed={{ assignment: "unassigned" }} defaults={{ sort: "oldest" }}
          emptyTitle={t("No complaints are waiting for assignment")} />
      </Suspense>
    </div>
  );
}
