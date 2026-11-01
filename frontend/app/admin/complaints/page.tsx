"use client";

import { Suspense } from "react";
import { useT } from "@/components/I18nProvider";
import { PageHeader, Spinner } from "@/components/ui";
import { ComplaintsBrowser } from "@/features/complaints-browser";

export default function AdminComplaints() {
  const t = useT();
  return (
    <div>
      <PageHeader title={t("Complaints")} subtitle={t("All routed complaints across departments and jurisdictions. Complaints awaiting routing are under Routing Configuration.")} />
      <Suspense fallback={<Spinner />}><ComplaintsBrowser defaults={{ sort: "newest" }} /></Suspense>
    </div>
  );
}
