"use client";

import { Bell, FilePlus2, Globe2, LayoutDashboard, LogIn, LogOut, Menu, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/services/api";
import type { Role } from "@/types";
import { homeFor, useAuth } from "./AuthProvider";
import { useI18n } from "./I18nProvider";
import { LANGUAGES, type Lang } from "@/i18n/dictionaries";
import { ROLE_LABEL } from "./labels";
import { Button, Modal, cx } from "./ui";

const DEMO_ROLES: Role[] = ["SYSTEM_ADMIN", "DEPARTMENT_ADMIN", "OFFICER", "CITIZEN"];

/** Persistent strip shown on every page of the demonstration environment. */
function DemoBanner() {
  const { user, demoLogin, exitDemo } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [error, setError] = useState("");

  async function switchTo(role: Role) {
    setBusy(true); setError("");
    try { const me = await demoLogin(role); router.push(homeFor(me.role)); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }

  async function reset() {
    setBusy(true); setError("");
    try {
      await api("/api/demo/reset", { method: "POST" });
      setConfirmReset(false);
      await switchTo(user?.role || "SYSTEM_ADMIN");
    } catch (e) { setError((e as Error).message); setBusy(false); }
  }

  return (
    <div className="border-b border-amber-300 bg-amber-100 text-amber-950">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 text-xs">
        <strong className="tracking-wide">{t("DEMONSTRATION ENVIRONMENT – SAMPLE DATA")}</strong>
        <span className="hidden text-amber-900 md:inline">{t("Separate from the live system. Changes here never affect real records.")}</span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <label htmlFor="demo-role" className="font-medium">{t("View as")}</label>
          <select id="demo-role" disabled={busy} value={user?.role || ""} onChange={(e) => switchTo(e.target.value as Role)}
            className="rounded border border-amber-400 bg-white px-2 py-0.5 text-xs text-slate-900">
            {!user && <option value="">{t("Choose a role")}</option>}
            {DEMO_ROLES.map((r) => <option key={r} value={r}>{t(ROLE_LABEL[r])}</option>)}
          </select>
          <button type="button" onClick={() => setConfirmReset(true)} className="inline-flex items-center gap-1 rounded border border-amber-400 bg-white px-2 py-0.5 hover:bg-amber-50">
            <RotateCcw className="h-3 w-3" aria-hidden /> {t("Reset demo")}
          </button>
          <button type="button" onClick={async () => { await exitDemo(); router.push("/"); }} className="rounded px-2 py-0.5 font-medium underline">
            {t("Exit demo")}
          </button>
        </div>
        {error && <span className="w-full text-red-800">{error}</span>}
      </div>
      <Modal open={confirmReset} title={t("Reset the demonstration data?")} onClose={() => setConfirmReset(false)}
        footer={<><Button variant="secondary" onClick={() => setConfirmReset(false)}>{t("Cancel")}</Button><Button loading={busy} onClick={reset}>{t("Reset demo")}</Button></>}>
        <p>{t("All changes made in the demo are discarded and the sample data is restored. The live system is not affected.")}</p>
      </Modal>
    </div>
  );
}

type NavItem = { href: string; label: string; icon: ReactNode };

function citizenNav(role?: string): NavItem[] {
  const pub: NavItem = { href: "/public", label: "Public issues", icon: <Globe2 className="h-4 w-4" aria-hidden /> };
  if (role === "CITIZEN")
    return [
      { href: "/dashboard", label: "My complaints", icon: <LayoutDashboard className="h-4 w-4" aria-hidden /> },
      { href: "/report", label: "Report an issue", icon: <FilePlus2 className="h-4 w-4" aria-hidden /> },
      pub,
    ];
  return [pub];
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout, env } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const { lang, setLang, t } = useI18n();
  const portal = pathname.startsWith("/admin") || pathname.startsWith("/authority");

  // Adopt the account's saved language on a device that has no choice stored yet.
  useEffect(() => {
    if (!user) return;
    let stored: string | null = null;
    try { stored = localStorage.getItem("cc_lang"); } catch { /* ignore */ }
    if (!stored && user.preferred_language && user.preferred_language !== lang) setLang(user.preferred_language);
  }, [user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  function changeLang(l: Lang) {
    setLang(l);
    if (user) api("/api/auth/me/preferences", { method: "PATCH", body: { preferred_language: l } }).catch(() => undefined);
  }

  useEffect(() => {
    setOpen(false);
    if (!user) return;
    api<{ unread: number }>("/api/notifications?unread_only=true").then((r) => setUnread(r.unread)).catch(() => undefined);
  }, [pathname, user]);

  const nav = portal ? [] : citizenNav(user?.role).map((n) => ({ ...n, label: t(n.label) }));
  const scope = user?.department_name ? `${user.department_name}${user.jurisdiction_name ? ` · ${user.jurisdiction_name}` : ""}` : "";

  return (
    <div className="flex min-h-screen flex-col bg-slate-100">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        {t("Skip to content")}
      </a>
      {env === "demo" && <DemoBanner />}
      <header className="sticky top-0 z-40 border-b border-slate-200 border-t-4 border-t-navy-800 bg-white">
        <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-4 px-4">
          <Link href={user ? homeFor(user.role) : "/"} className="flex items-center gap-2 text-navy-900">
            <span className="grid h-8 w-8 place-items-center rounded bg-navy-800 text-xs font-bold text-white" aria-hidden>CC</span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold">CivicConnect</span>
              <span className="hidden text-2xs text-slate-500 sm:block">{t("Civic grievance redressal")}</span>
            </span>
          </Link>
          <nav className="ml-4 hidden items-center gap-1 md:flex" aria-label={t("Main")}>
            {nav.map((n) => (
              <Link key={n.href} href={n.href}
                className={cx("flex items-center gap-1.5 rounded px-3 py-1.5 text-sm", pathname === n.href || pathname.startsWith(n.href + "/") ? "bg-navy-50 font-medium text-navy-900" : "text-slate-700 hover:bg-slate-100")}>
                {n.icon}{n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1 sm:gap-2">
            <label htmlFor="lang" className="sr-only">{t("Language")}</label>
            <select id="lang" value={lang} onChange={(e) => changeLang(e.target.value as Lang)}
              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-navy-500/30">
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            {user ? (
              <>
                <Link href="/notifications" className="relative rounded p-2 text-slate-600 hover:bg-slate-100" aria-label={`${t("Notifications")}${unread ? `, ${unread}` : ""}`}>
                  <Bell className="h-5 w-5" aria-hidden />
                  {unread > 0 && <span className="absolute right-0.5 top-0.5 rounded bg-red-700 px-1 text-[10px] font-bold text-white">{unread}</span>}
                </Link>
                <div className="hidden border-l border-slate-200 pl-3 text-right text-xs leading-tight sm:block">
                  <div className="font-medium text-slate-900">{user.full_name}</div>
                  <div className="text-slate-500">{t(ROLE_LABEL[user.role])}{scope ? ` · ${scope}` : ""}</div>
                </div>
                <button type="button" onClick={async () => { await logout(); router.push("/"); }} className="rounded p-2 text-slate-600 hover:bg-slate-100" aria-label={t("Log out")} title={t("Log out")}>
                  <LogOut className="h-5 w-5" aria-hidden />
                </button>
              </>
            ) : (
              <Link href="/login" className="flex items-center gap-1 rounded px-3 py-1.5 text-sm text-navy-800 hover:bg-slate-100"><LogIn className="h-4 w-4" aria-hidden /> {t("Log in")}</Link>
            )}
            {nav.length > 0 && (
              <button type="button" className="rounded p-2 text-slate-700 hover:bg-slate-100 md:hidden" onClick={() => setOpen(!open)} aria-label={t("Toggle menu")} aria-expanded={open}>
                {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            )}
          </div>
        </div>
        {open && (
          <nav className="border-t border-slate-200 px-4 py-2 md:hidden" aria-label={t("Mobile")}>
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className="flex items-center gap-2 rounded px-2 py-2 text-sm text-slate-800 hover:bg-slate-100">{n.icon}{n.label}</Link>
            ))}
          </nav>
        )}
      </header>
      <main id="main" className={cx("w-full flex-1", portal ? "" : "mx-auto max-w-6xl px-4 py-6")}>{children}</main>
      {!portal && (
        <footer className="border-t border-slate-200 bg-white py-5 text-center text-xs text-slate-500">
          {t("CivicConnect is an internal grievance workflow. It is not an emergency service — for immediate danger to life, contact local emergency services.")}
        </footer>
      )}
    </div>
  );
}
