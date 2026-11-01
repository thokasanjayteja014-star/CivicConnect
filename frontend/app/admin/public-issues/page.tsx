"use client";

import { Suspense } from "react";
import { Spinner } from "@/components/ui";
import { PublicIssuesManager } from "@/features/public-issues";

export default function Page() {
  return <Suspense fallback={<Spinner />}><PublicIssuesManager /></Suspense>;
}
