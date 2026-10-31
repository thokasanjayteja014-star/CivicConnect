"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { homeFor, useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/components/I18nProvider";
import { Button, ErrorBox, Field, inputCls } from "@/components/ui";

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const next = useSearchParams().get("next");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const { t } = useI18n();
  const [error, setError] = useState<unknown>(null);

  return (
    <div className="mx-auto max-w-md">
      <h1 className="text-2xl font-semibold text-navy-900">{t("Log in")}</h1>
      <p className="mt-1 text-sm text-slate-600">{t("Citizens, department officers and administrators all sign in here.")}</p>
      <form
        className="mt-6 space-y-4 rounded-lg border border-slate-200 bg-white p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            const u = await login(email, password);
            router.replace(next && next.startsWith("/") ? next : homeFor(u.role));
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ErrorBox error={error} />
        <Field label={t("Email")} htmlFor="email" required>
          <input id="email" type="email" autoComplete="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t("Password")} htmlFor="password" required>
          <input id="password" type="password" autoComplete="current-password" required className={inputCls} value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" loading={busy} className="w-full">{t("Log in")}</Button>
        <p className="text-center text-sm text-slate-600">
          {t("New here?")} <Link href={`/register${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-teal-700 underline">{t("Create a citizen account")}</Link>
        </p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
