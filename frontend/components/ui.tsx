"use client";

import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { CATEGORY_LABEL, PRIORITY_STYLE, ROUTING_LABEL, STATUS_LABEL, STATUS_STYLE } from "./labels";

export function cx(...c: Array<string | false | null | undefined>) {
  return c.filter(Boolean).join(" ");
}

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; loading?: boolean };
export function Button({ variant = "primary", loading, className, children, disabled, ...rest }: BtnProps) {
  const styles = {
    primary: "bg-navy-700 text-white hover:bg-navy-800 disabled:bg-navy-600/50",
    secondary: "bg-white text-navy-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
    danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
    ghost: "text-navy-700 hover:bg-navy-50",
  }[variant];
  return (
    <button
      className={cx("inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500 disabled:cursor-not-allowed", styles, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({ href, children, variant = "primary", className }: { href: string; children: ReactNode; variant?: "primary" | "secondary"; className?: string }) {
  const styles = variant === "primary" ? "bg-navy-700 text-white hover:bg-navy-800" : "bg-white text-navy-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50";
  return (
    <Link href={href} className={cx("inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-500", styles, className)}>
      {children}
    </Link>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-slate-200 bg-white shadow-sm", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
          {title && <h2 className="text-base font-semibold text-navy-900">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-navy-900">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function Badge({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return <span title={title} className={cx("inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", className)}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge className={STATUS_STYLE[status] || "bg-slate-100 ring-slate-300"}>{STATUS_LABEL[status] || status}</Badge>;
}

export function PriorityBadge({ level, status, score }: { level: string | null; status?: string; score?: number | null }) {
  if (!level) {
    return <Badge className="bg-white text-slate-600 ring-slate-300" title="Score withheld until all factors are assessed">
      {status === "UNAVAILABLE" ? "Priority unavailable" : "Priority provisional"}
    </Badge>;
  }
  return <Badge className={PRIORITY_STYLE[level]}>{level}{score != null ? ` · ${score.toFixed(2)}` : ""}</Badge>;
}

export function RoutingBadge({ status }: { status: string }) {
  const style = status === "ROUTED" ? "bg-teal-50 text-teal-800 ring-teal-200" : status === "PENDING_REVIEW" ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-slate-100 text-slate-700 ring-slate-300";
  return <Badge className={style}>{ROUTING_LABEL[status] || status}</Badge>;
}

export function CategoryLabel({ category }: { category: string }) {
  return <span>{CATEGORY_LABEL[category] || category}</span>;
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-8 text-sm text-slate-600">
      <Loader2 className="h-5 w-5 animate-spin text-navy-600" aria-hidden /> {label}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-slate-300 bg-slate-50/60 px-6 py-10 text-center">
      <Inbox className="h-8 w-8 text-slate-400" aria-hidden />
      <h3 className="mt-3 text-sm font-semibold text-navy-900">{title}</h3>
      {body && <p className="mt-1 max-w-md text-sm text-slate-600">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (!error) return null;
  const e = error as { message?: string; requestId?: string; code?: string };
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p>{e.message || "Something went wrong."}</p>
        {e.requestId && <p className="mt-1 text-xs text-red-600">Reference: {e.requestId}</p>}
      </div>
      {onRetry && (
        <button onClick={onRetry} className="inline-flex items-center gap-1 text-xs font-medium underline">
          <RefreshCw className="h-3 w-3" aria-hidden /> Retry
        </button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "success"; children: ReactNode }) {
  const style = { info: "border-blue-200 bg-blue-50 text-blue-900", warn: "border-amber-200 bg-amber-50 text-amber-900", success: "border-green-200 bg-green-50 text-green-900" }[tone];
  return <div className={cx("rounded-md border p-3 text-sm", style)}>{children}</div>;
}

export function Field({ label, htmlFor, hint, error, children, required }: { label: string; htmlFor: string; hint?: ReactNode; error?: string; children: ReactNode; required?: boolean }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-800">
        {label} {required && <span className="text-red-600" aria-hidden>*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      {error && <p className="text-xs text-red-700" role="alert">{error}</p>}
    </div>
  );
}

export const inputCls = "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/30 disabled:bg-slate-50";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-navy-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}
