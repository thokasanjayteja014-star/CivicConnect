"use client";

import {
  AlertOctagon, Building2, ClipboardList, FileSearch, Globe2, Inbox, LayoutDashboard, Link2, ListChecks, Map,
  Menu, RotateCcw, Route, Settings, ShieldCheck, UserCog, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import type { Role } from "@/types";
import { useRequireRole } from "./AuthProvider";
import { useT } from "./I18nProvider";
import { Spinner, cx } from "./ui";

type Item = { href: string; label: string; icon: ReactNode; exact?: boolean };
type Group = { label?: string; items: Item[] };

const I = (C: typeof Map) => <C className="h-4 w-4 shrink-0" aria-hidden />;

export const ADMIN_NAV: Group[] = [
  { items: [
    { href: "/admin", label: "Overview", icon: I(LayoutDashboard), exact: true },
    { href: "/admin/complaints", label: "Complaints", icon: I(ClipboardList) },
    { href: "/admin/public-issues", label: "Public Issues", icon: I(Globe2) },
  ] },
  { label: "Configuration", items: [
    { href: "/admin/jurisdictions", label: "Jurisdiction Management", icon: I(Map) },
    { href: "/admin/departments", label: "Department Registry", icon: I(Building2) },
    { href: "/admin/mapping", label: "Department–Jurisdiction Mapping", icon: I(Link2) },
    { href: "/admin/responsibilities", label: "Responsibility Management", icon: I(ListChecks) },
    { href: "/admin/users", label: "User & Officer Management", icon: I(Users) },
    { href: "/admin/routing", label: "Routing Configuration", icon: I(Route) },
    { href: "/admin/escalations", label: "Escalation Management", icon: I(AlertOctagon) },
    { href: "/admin/sources", label: "Source References", icon: I(ShieldCheck) },
  ] },
  { label: "Oversight", items: [
    { href: "/admin/audit", label: "Audit Logs", icon: I(FileSearch) },
    { href: "/admin/settings", label: "Settings", icon: I(Settings) },
  ] },
];

const DEPT_ADMIN_NAV: Group[] = [
  { items: [
    { href: "/authority", label: "Overview", icon: I(LayoutDashboard), exact: true },
    { href: "/authority/queue", label: "Unassigned queue", icon: I(Inbox) },
    { href: "/authority/complaints", label: "Complaints", icon: I(ClipboardList) },
    { href: "/authority/escalations", label: "Escalations", icon: I(AlertOctagon) },
    { href: "/authority/officers", label: "Officers & workload", icon: I(UserCog) },
    { href: "/authority/public-issues", label: "Public Issues", icon: I(Globe2) },
    { href: "/authority/reopen", label: "Reopening reviews", icon: I(RotateCcw) },
  ] },
];

const OFFICER_NAV: Group[] = [
  { items: [
    { href: "/authority", label: "Overview", icon: I(LayoutDashboard), exact: true },
    { href: "/authority/complaints", label: "My assignments", icon: I(ClipboardList) },
    { href: "/authority/escalations", label: "Escalations", icon: I(AlertOctagon) },
    { href: "/authority/public-issues", label: "Public Issues", icon: I(Globe2) },
  ] },
];

export function navForRole(role?: Role): Group[] {
  if (role === "SYSTEM_ADMIN") return ADMIN_NAV;
  if (role === "DEPARTMENT_ADMIN") return DEPT_ADMIN_NAV;
  return OFFICER_NAV;
}

/** Sidebar layout for the staff portals (main administrator, department administrator, officer). */
const PORTAL_TITLE: Record<string, string> = {
  SYSTEM_ADMIN: "Main Administration", DEPARTMENT_ADMIN: "Department Administration", OFFICER: "Officer Portal",
};

export function PortalLayout({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, allowed } = useRequireRole(roles);
  const t = useT();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  if (!allowed || !user) return <div className="px-4"><Spinner /></div>;
  // A main administrator browsing a complaint under /authority keeps the admin navigation.
  const groups = navForRole(user.role);
  const title = PORTAL_TITLE[user.role] || "Portal";
  const isActive = (i: Item) => (i.exact ? pathname === i.href : pathname === i.href || pathname.startsWith(i.href + "/"));

  const nav = (
    <nav aria-label={t(title)} className="space-y-4 p-3">
      {groups.map((g, gi) => (
        <div key={gi}>
          {g.label && <div className="px-2 pb-1 text-2xs font-semibold uppercase tracking-wider text-slate-500">{t(g.label)}</div>}
          <ul className="space-y-0.5">
            {g.items.map((i) => (
              <li key={i.href}>
                <Link href={i.href} onClick={() => setOpen(false)}
                  className={cx("flex items-center gap-2 rounded px-2 py-1.5 text-sm", isActive(i) ? "bg-navy-700 font-medium text-white" : "text-slate-700 hover:bg-slate-100")}>
                  {i.icon}<span>{t(i.label)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );

  return (
    <div className="mx-auto flex w-full max-w-[1600px]">
      <aside className="sticky top-[60px] hidden h-[calc(100vh-60px)] w-64 shrink-0 overflow-y-auto border-r border-slate-200 bg-white lg:block">
        <div className="border-b border-slate-200 px-4 py-3">
          <div className="text-2xs font-semibold uppercase tracking-wider text-slate-500">{t(title)}</div>
          {user.department_name && <div className="mt-0.5 text-sm font-medium text-slate-900">{user.department_name}</div>}
          {user.jurisdiction_name && <div className="text-xs text-slate-500">{user.jurisdiction_name}</div>}
        </div>
        {nav}
      </aside>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
          <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="inline-flex items-center gap-2 rounded border border-slate-300 px-2 py-1 text-sm">
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />} {t("Menu")}
          </button>
          <span className="text-sm font-medium text-slate-700">{t(title)}</span>
        </div>
        {open && <div className="border-b border-slate-200 bg-white lg:hidden">{nav}</div>}
        <div className="px-4 py-5 sm:px-6">{children}</div>
      </div>
    </div>
  );
}
