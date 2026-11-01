"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/components/I18nProvider";
import { Button, ErrorBox, Field, inputCls } from "@/components/ui";

function RegisterForm() {
  const { register } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const { t } = useI18n();
  const [error, setError] = useState<unknown>(null);
  const mismatch = form.confirm.length > 0 && form.password !== form.confirm;
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold text-navy-900">{t("Create a citizen account")}</h1>
      <p className="mt-1 text-sm text-slate-600">{t("Your name and contact details are private and never shown publicly.")}</p>
      <form
        className="mt-6 space-y-4 rounded-md border border-slate-200 bg-white p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          if (mismatch) return;
          setBusy(true);
          setError(null);
          try {
            await register(form.full_name, form.email, form.password, form.phone);
            router.replace(next && next.startsWith("/") ? next : "/dashboard");
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ErrorBox error={error} />
        <Field label={t("Full name")} htmlFor="full_name" required>
          <input id="full_name" required minLength={2} maxLength={120} autoComplete="name" className={inputCls} value={form.full_name} onChange={set("full_name")} />
        </Field>
        <Field label={t("Email")} htmlFor="email" required>
          <input id="email" type="email" required autoComplete="email" className={inputCls} value={form.email} onChange={set("email")} />
        </Field>
        <Field label={t("Phone (optional)")} htmlFor="phone" hint={t("Use international format, e.g. +919876543210, if you want SMS updates. Leave blank if you prefer.")}>
          <input id="phone" type="tel" autoComplete="tel" className={inputCls} value={form.phone} onChange={set("phone")} />
        </Field>
        <Field label={t("Password")} htmlFor="password" required hint={t("At least 8 characters.")}>
          <input id="password" type="password" required minLength={8} autoComplete="new-password" className={inputCls} value={form.password} onChange={set("password")} />
        </Field>
        <Field label={t("Confirm password")} htmlFor="confirm" required error={mismatch ? t("Passwords do not match.") : undefined}>
          <input id="confirm" type="password" required autoComplete="new-password" className={inputCls} value={form.confirm} onChange={set("confirm")} />
        </Field>
        <Button type="submit" loading={busy} disabled={mismatch} className="w-full">{t("Create account")}</Button>
        <p className="text-center text-sm text-slate-600">{t("Already registered?")} <Link href="/login" className="font-medium text-navy-700 underline">{t("Log in")}</Link></p>
      </form>
    </div>
  );
}

export default function RegisterPage() {
  return <Suspense><RegisterForm /></Suspense>;
}
