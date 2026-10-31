"use client";

import { Building2, Camera, ClipboardCheck, Globe2, MapPin, Search, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { homeFor, useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/components/I18nProvider";
import { Button, LinkButton, inputCls } from "@/components/ui";

const steps = [
  { icon: Camera, title: "Describe the problem", body: "Write or speak in your language, and optionally add photos, a voice note or a short video." },
  { icon: MapPin, title: "Pin the location", body: "Use your phone's GPS or pick the spot on the map. We never guess coordinates for you." },
  { icon: ClipboardCheck, title: "Review and confirm", body: "Check the details (and any AI suggestions, when available) before anything is submitted." },
  { icon: Building2, title: "Routed to a department", body: "Configured jurisdiction and responsibility rules decide where it goes. Unclear cases get human review." },
  { icon: ShieldCheck, title: "Track until verified", body: "Follow every status change, see resolution evidence, and confirm or request reopening." },
];

export default function Landing() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [ref, setRef] = useState("");
  const { t } = useI18n();

  useEffect(() => {
    if (ready && user) router.replace(homeFor(user.role));
  }, [ready, user, router]);

  return (
    <div className="space-y-12">
      <section className="rounded-xl bg-navy-900 px-6 py-12 text-white sm:px-10">
        <p className="text-sm font-medium uppercase tracking-wider text-teal-100">CivicConnect</p>
        <h1 className="mt-2 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">
          {t("Connecting citizens, complaints and responsible departments.")}
        </h1>
        <p className="mt-4 max-w-2xl text-slate-200">
          {t("Report potholes, water leaks, overflowing garbage, blocked drains, broken streetlights and damaged public facilities. Follow your complaint from submission to verified resolution.")}
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <LinkButton href={user ? "/report" : "/register?next=/report"} className="bg-teal-500 text-navy-900 hover:bg-teal-100">{t("Report a civic issue")}</LinkButton>
          <LinkButton href={user ? "/dashboard" : "/login?next=/dashboard"} variant="secondary">{t("Track my complaints")}</LinkButton>
          <LinkButton href="/public" variant="secondary"><Globe2 className="h-4 w-4" /> {t("View public issues")}</LinkButton>
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold text-navy-900">{t("How reporting works")}</h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {steps.map((s, i) => (
            <li key={s.title} className="rounded-lg border border-slate-200 bg-white p-4">
              <s.icon className="h-6 w-6 text-teal-600" aria-hidden />
              <h3 className="mt-3 text-sm font-semibold text-navy-900">{i + 1}. {t(s.title)}</h3>
              <p className="mt-1 text-sm text-slate-600">{t(s.body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-semibold text-navy-900">{t("Look up a public complaint")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("Enter a CivicConnect reference (e.g. CVC-20261031-ABC234). Only privacy-reviewed public information is shown.")}</p>
          <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (ref.trim()) router.push(`/public?reference=${encodeURIComponent(ref.trim())}`); }}>
            <label htmlFor="ref" className="sr-only">{t("Reference ID")}</label>
            <input id="ref" className={inputCls} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="CVC-…" />
            <Button type="submit"><Search className="h-4 w-4" /> {t("Look up")}</Button>
          </form>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-700">
          <h2 className="text-lg font-semibold text-navy-900">{t("What CivicConnect is (and isn't)")}</h2>
          <ul className="mt-3 list-disc space-y-1 pl-5">
            <li>{t("An internal complaint workflow between citizens and configured department teams.")}</li>
            <li>{t("AI output, when enabled, is only a suggestion you review. Priority, routing and status changes follow fixed, auditable rules.")}</li>
            <li>{t("It does not submit complaints to any government portal and is not an emergency service.")}</li>
            <li>{t("Public views never show names, contact details, private photos or internal notes.")}</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
