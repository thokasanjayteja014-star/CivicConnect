"use client";

import { Bell, Building2, ClipboardList, FilePlus2, Globe2, LayoutDashboard, LogIn, LogOut, Menu, RotateCcw, Settings, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/services/api";
import { homeFor, useAuth } from "./AuthProvider";
import { useI18n } from "./I18nProvider";
import { LANGUAGES, type Lang } from "@/i18n/dictionaries";
import { ROLE_LABEL } from "./labels";
import { cx } from "./ui";

type NavItem = { href: string; label: string; icon: ReactNode };

function navFor(role?: string): NavItem[] {
  const pub: NavItem = { href: "/public", label: "Public issues", icon: <Globe2 className="h-4 w-4" aria-hidden /> };
  if (role === "CITIZEN")
    return [
      { href: "/dashboard", label: "My complaints", icon: <LayoutDashboard className="h-4 w-4" aria-hidden /> },
      { href: "/report", label: "Report an issue", icon: <FilePlus2 className="h-4 w-4" aria-hidden /> },
      pub,
    ];
  if (role === "OFFICER" || role === "DEPARTMENT_ADMIN")
    return [
      { href: "/authority", label: "Department dashboard", icon: <ClipboardList className="h-4 w-4" aria-hidden /> },
      { href: "/authority/reopen", label: "Reopening reviews", icon: <RotateCcw className="h-4 w-4" aria-hidden /> },
      pub,
    ];
  if (role === "SYSTEM_ADMIN")
    return [
      { href: "/admin", label: "Administration", icon: <Settings className="h-4 w-4" aria-hidden /> },
      { href: "/authority", label: "All routed complaints", icon: <Building2 className="h-4 w-4" aria-hidden /> },
      { href: "/authority/reopen", label: "Reopening reviews", icon: <RotateCcw className="h-4 w-4" aria-hidden /> },
      pub,
    ];
  return [pub];
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const { lang, setLang, t } = useI18n();

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

  const nav = navFor(user?.role).map((n) => ({ ...n, label: t(n.label) }));

  return (
    <div className="min-h-screen bg-slate-50">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2">
        {t("Skip to content")}
      </a>
      <header className="sticky top-0 z-40 border-b border-navy-800 bg-navy-900 text-white">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4">
          <Link href={user ? homeFor(user.role) : "/"} className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="grid h-7 w-7 place-items-center rounded bg-teal-500 text-sm font-bold text-navy-900">CC</span>
            CivicConnect
          </Link>
          <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="Main">
            {nav.map((n) => (
              <Link key={n.href} href={n.href}
                className={cx("flex items-center gap-1.5 rounded px-3 py-1.5 text-sm", pathname === n.href || (n.href !== "/" && pathname.startsWith(n.href + "/")) ? "bg-navy-700" : "text-slate-200 hover:bg-navy-800")}>
                {n.icon}{n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <label htmlFor="lang" className="sr-only">{t("Language")}</label>
            <select id="lang" value={lang} onChange={(e) => changeLang(e.target.value as Lang)}
              className="rounded border border-navy-700 bg-navy-800 px-2 py-1 text-xs text-white focus:outline-none focus:ring-2 focus:ring-teal-500">
              {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
            {user ? (
              <>
                <Link href="/notifications" className="relative rounded p-2 hover:bg-navy-800" aria-label={`${t("Notifications")}${unread ? `, ${unread}` : ""}`}>
                  <Bell className="h-5 w-5" aria-hidden />
                  {unread > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-teal-500 px-1.5 text-[10px] font-bold text-navy-900">{unread}</span>}
                </Link>
                <div className="hidden text-right text-xs leading-tight sm:block">
                  <div className="font-medium">{user.full_name}</div>
                  <div className="text-slate-300">{t(ROLE_LABEL[user.role])}{user.department_name ? ` · ${user.department_name}` : ""}</div>
                </div>
                <button onClick={async () => { await logout(); router.push("/"); }} className="rounded p-2 hover:bg-navy-800" aria-label={t("Log out")}>
                  <LogOut className="h-5 w-5" aria-hidden />
                </button>
              </>
            ) : (
              <Link href="/login" className="flex items-center gap-1 rounded px-3 py-1.5 text-sm hover:bg-navy-800"><LogIn className="h-4 w-4" aria-hidden /> {t("Log in")}</Link>
            )}
            <button className="rounded p-2 hover:bg-navy-800 md:hidden" onClick={() => setOpen(!open)} aria-label={t("Toggle menu")} aria-expanded={open}>
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        {open && (
          <nav className="border-t border-navy-800 px-4 py-2 md:hidden" aria-label="Mobile">
            {nav.map((n) => (
              <Link key={n.href} href={n.href} className="flex items-center gap-2 rounded px-2 py-2 text-sm hover:bg-navy-800">{n.icon}{n.label}</Link>
            ))}
          </nav>
        )}
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500">
        {t("CivicConnect is an internal grievance workflow. It is not an emergency service — for immediate danger to life, contact local emergency services.")}
      </footer>
    </div>
  );
}
