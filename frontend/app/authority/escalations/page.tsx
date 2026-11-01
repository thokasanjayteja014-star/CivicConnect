"use client";

import { useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { PageHeader } from "@/components/ui";
import { EscalationList } from "@/features/escalations";

export default function AuthorityEscalations() {
  const t = useT();
  const { user } = useAuth();
  return (
    <div>
      <PageHeader title={t("Escalations")} subtitle={user?.role === "OFFICER"
        ? t("Escalations on complaints you handle. To escalate a complaint, open it and choose Escalate.")
        : t("Overdue and manually escalated complaints in your unit. Close an escalation once you have acted on it.")} />
      <EscalationList />
    </div>
  );
}
