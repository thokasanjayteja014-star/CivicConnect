"use client";

import { Building2, Shield, User, Wrench } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { homeFor, useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { Button, ErrorBox, Notice } from "@/components/ui";
import type { Role } from "@/types";

const ROLES: { role: Role; icon: typeof User; title: string; who: string; body: string }[] = [
  { role: "SYSTEM_ADMIN", icon: Shield, title: "Main administrator", who: "State administration",
    body: "Configure jurisdictions, departments, unit mapping, responsibilities, staff, escalation rules and public issues. See the governance overview." },
  { role: "DEPARTMENT_ADMIN", icon: Building2, title: "Department administrator", who: "Roads department, Hubballi-Dharwad",
    body: "Manage your unit's queue, assign and reassign officers, handle escalations, verify resolutions and publish public issues." },
  { role: "OFFICER", icon: Wrench, title: "Officer", who: "Ravi Patil, Wards 1 and 2",
    body: "Accept assigned complaints, update progress, upload resolution evidence and escalate when needed." },
  { role: "CITIZEN", icon: User, title: "Citizen", who: "Sample resident",
    body: "Report a problem with location and photos, track it, and confirm or dispute the resolution." },
];

export default function DemoEntry() {
  const t = useT();
  const { demoLogin } = useAuth();
  const router = useRouter();
  const [busy, setBusy] = useState<Role | null>(null);
  const [error, setError] = useState<unknown>(null);
  const enter = async (role: Role) => {
    setBusy(role); setError(null);
    try { const me = await demoLogin(role); router.push(homeFor(me.role)); } catch (e) { setError(e); setBusy(null); }
  };
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("Explore the demonstration")}</h1>
        <p className="mt-1 text-slate-700">{t("Choose a role to sign in with sample data. You can switch roles at any time from the banner at the top.")}</p>
      </div>
      <Notice tone="warn">{t("The demonstration uses a separate database with sample data. No emails or messages are sent, and nothing here affects real complaints. Any visitor can reset it.")}</Notice>
      <ErrorBox error={error} />
      <ul className="grid gap-4 sm:grid-cols-2">{ROLES.map((r) => (
        <li key={r.role} className="flex flex-col rounded-md border border-slate-300 bg-white p-5">
          <div className="flex items-center gap-3"><r.icon className="h-6 w-6 text-navy-700" aria-hidden />
            <div><h2 className="font-semibold text-slate-900">{t(r.title)}</h2><p className="text-xs text-slate-500">{t(r.who)}</p></div></div>
          <p className="mt-3 flex-1 text-sm text-slate-600">{t(r.body)}</p>
          <Button className="mt-4 self-start" loading={busy === r.role} disabled={!!busy} onClick={() => enter(r.role)}>{t("Enter as {role}", { role: t(r.title) })}</Button>
        </li>
      ))}</ul>
    </div>
  );
}
