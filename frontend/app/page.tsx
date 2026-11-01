"use client";

import { ArrowRight, Building2, ClipboardCheck, FlaskConical, Globe2, LogIn, MapPin, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { homeFor, useAuth } from "@/components/AuthProvider";
import { useT } from "@/components/I18nProvider";
import { ISSUE_PROGRESS_LABEL, fmtDate } from "@/components/labels";
import { Button, LinkButton, inputCls } from "@/components/ui";
import { useApi } from "@/hooks/useApi";

const steps = [
  { icon: MapPin, title: "Report with location", body: "Describe the problem in your language, add photos, and pin the exact spot." },
  { icon: Building2, title: "Sent to the right office", body: "The location decides the jurisdiction, and configured rules decide the responsible department and officer." },
  { icon: ClipboardCheck, title: "Worked within a deadline", body: "Each complaint has a service deadline. Overdue complaints are escalated automatically." },
  { icon: ShieldCheck, title: "Verified before closing", body: "Resolution evidence is reviewed, and you can confirm the fix or ask for it to be reopened." },
];

export default function Landing() {
  const t = useT();
  const { user, ready } = useAuth();
  const router = useRouter();
  const [ref, setRef] = useState("");
  const issues = useApi<{ total: number; items: any[] }>("/api/public/issues?limit=3");

  useEffect(() => { if (ready && user) router.replace(homeFor(user.role)); }, [ready, user, router]);

  return (
    <div className="space-y-10">
      <section className="border-b border-slate-200 pb-8">
        <p className="text-sm font-semibold text-navy-700">{t("CivicConnect public grievance system")}</p>
        <h1 className="mt-2 max-w-3xl text-3xl font-semibold leading-tight text-slate-900 sm:text-4xl">{t("Report civic problems. Track them to a verified resolution.")}</h1>
        <p className="mt-3 max-w-2xl text-slate-700">{t("Potholes, water leaks, garbage, blocked drains, broken streetlights and damaged public facilities, handled by the department responsible for your area.")}</p>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col rounded-md border border-slate-300 bg-white p-6">
          <LogIn className="h-6 w-6 text-navy-700" aria-hidden />
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{t("Login / Register")}</h2>
          <p className="mt-1 flex-1 text-sm text-slate-600">{t("Citizens report and track complaints. Officers and administrators sign in to their work portal.")}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <LinkButton href="/login">{t("Sign in")}</LinkButton>
            <LinkButton href="/register" variant="secondary">{t("Create citizen account")}</LinkButton>
          </div>
        </div>
        <div className="flex flex-col rounded-md border border-amber-300 bg-amber-50 p-6">
          <FlaskConical className="h-6 w-6 text-amber-800" aria-hidden />
          <h2 className="mt-3 text-lg font-semibold text-slate-900">{t("Explore Demo")}</h2>
          <p className="mt-1 flex-1 text-sm text-slate-700">{t("Try every role with sample data in a separate demonstration environment. Nothing you do there affects real complaints.")}</p>
          <div className="mt-4"><LinkButton href="/demo" variant="secondary">{t("Open the demonstration")} <ArrowRight className="h-4 w-4" /></LinkButton></div>
        </div>
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-lg font-semibold text-slate-900">{t("Public issues")}</h2>
          <Link href="/public" className="text-sm font-medium text-navy-700 underline">{t("View all public issues")}</Link>
        </div>
        <p className="text-sm text-slate-600">{t("Issues verified and published by departments, with progress updates.")}</p>
        {issues.data && issues.data.items.length > 0 ? (
          <ul className="mt-3 grid gap-3 md:grid-cols-3">{issues.data.items.map((i) => (
            <li key={i.id} className="rounded-md border border-slate-200 bg-white p-4">
              <Link href={`/public/issues/${i.id}`} className="font-medium text-navy-800 underline">{i.title}</Link>
              <p className="mt-1 text-xs text-slate-500">{i.general_location || i.area} · {i.department}</p>
              <p className="mt-2 text-sm"><span className="font-medium">{t(ISSUE_PROGRESS_LABEL[i.progress])}</span> · <span className="text-slate-500">{t("updated {date}", { date: fmtDate(i.last_update, false) })}</span></p>
            </li>
          ))}</ul>
        ) : <p className="mt-3 rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-500">{t("No public issues have been published yet.")}</p>}
      </section>

      <section>
        <h2 className="text-lg font-semibold text-slate-900">{t("How it works")}</h2>
        <ol className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s, i) => (
            <li key={s.title} className="rounded-md border border-slate-200 bg-white p-4">
              <s.icon className="h-5 w-5 text-navy-700" aria-hidden />
              <h3 className="mt-2 text-sm font-semibold text-slate-900">{i + 1}. {t(s.title)}</h3>
              <p className="mt-1 text-sm text-slate-600">{t(s.body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-md border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-900">{t("Look up a published complaint")}</h2>
          <p className="mt-1 text-sm text-slate-600">{t("Enter a CivicConnect reference number. Only information approved for public display is shown.")}</p>
          <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); if (ref.trim()) router.push(`/public?tab=complaints&reference=${encodeURIComponent(ref.trim())}`); }}>
            <label htmlFor="ref" className="sr-only">{t("Reference number")}</label>
            <input id="ref" className={inputCls} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="CVC-…" />
            <Button type="submit"><Search className="h-4 w-4" /> {t("Look up")}</Button>
          </form>
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-5 text-sm text-slate-700">
          <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Globe2 className="h-4 w-4" /> {t("Important")}</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>{t("This is not an emergency service. For emergencies call 112.")}</li>
            <li>{t("Public pages never show names, contact details, private photos or internal notes.")}</li>
            <li>{t("Available in English, Hindi, Kannada and Telugu.")}</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
