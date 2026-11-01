"use client";

// CivicConnect design system. Flat surfaces, 6px radius, one brand colour (navy), status
// colours only where they carry meaning. Every visible string goes through t().
import { AlertTriangle, ChevronDown, Inbox, Loader2, RefreshCw, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useT } from "./I18nProvider";
import { CATEGORY_LABEL, PRIORITY_STYLE, ROUTING_LABEL, STATUS_LABEL, STATUS_STYLE } from "./labels";

export function cx(...c: Array<string | false | null | undefined>) {
  return c.filter(Boolean).join(" ");
}

// ---------------- buttons ----------------
type Variant = "primary" | "secondary" | "danger" | "ghost";
const BTN_BASE = "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-navy-500 disabled:cursor-not-allowed";
const BTN: Record<Variant, string> = {
  primary: "bg-navy-700 text-white hover:bg-navy-800 disabled:bg-navy-200",
  secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-700 text-white hover:bg-red-800 disabled:bg-red-300",
  ghost: "text-navy-700 hover:bg-navy-50 disabled:text-slate-400",
};

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean; size?: "sm" | "md" };
export function Button({ variant = "primary", loading, size = "md", className, children, disabled, type = "button", ...rest }: BtnProps) {
  return (
    <button type={type} className={cx(BTN_BASE, BTN[variant], size === "sm" && "px-2.5 py-1 text-xs", className)} disabled={disabled || loading} {...rest}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({ href, children, variant = "primary", className }: { href: string; children: ReactNode; variant?: Variant; className?: string }) {
  return <Link href={href} className={cx(BTN_BASE, BTN[variant], className)}>{children}</Link>;
}

export function IconButton({ label, onClick, children, tone = "default", disabled }: { label: string; onClick: () => void; children: ReactNode; tone?: "default" | "danger"; disabled?: boolean }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} disabled={disabled}
      className={cx("rounded p-1.5 disabled:opacity-40", tone === "danger" ? "text-slate-500 hover:bg-red-50 hover:text-red-700" : "text-slate-500 hover:bg-slate-100 hover:text-navy-800")}>
      {children}
    </button>
  );
}

// ---------------- surfaces ----------------
export function Card({ title, subtitle, actions, children, className, padded = true }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={cx("rounded-md border border-slate-200 bg-white", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-slate-900">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone, href }: { label: string; value: ReactNode; hint?: string; tone?: "warn" | "danger" | "ok"; href?: string }) {
  const accent = tone === "danger" ? "border-l-red-600" : tone === "warn" ? "border-l-amber-500" : tone === "ok" ? "border-l-green-600" : "border-l-navy-600";
  const body = (
    <div className={cx("h-full rounded-md border border-l-4 border-slate-200 bg-white px-4 py-3", accent, href && "hover:bg-slate-50")}>
      <div className="text-xs font-medium text-slate-600">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

export function KeyValue({ items }: { items: Array<[ReactNode, ReactNode]> }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
      {items.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-slate-500">{k}</dt>
          <dd className="text-slate-900">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------- badges ----------------
export function Badge({ children, className, title }: { children: ReactNode; className?: string; title?: string }) {
  return <span title={title} className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", className || "bg-slate-100 text-slate-700 ring-slate-300")}>{children}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const t = useT();
  return <Badge className={STATUS_STYLE[status] || "bg-slate-100 ring-slate-300"}>{t(STATUS_LABEL[status] || status)}</Badge>;
}

export function PriorityBadge({ level, status, score }: { level: string | null; status?: string; score?: number | null }) {
  const t = useT();
  if (!level) {
    return <Badge className="bg-white text-slate-600 ring-slate-300" title={t("Score withheld until all factors are assessed")}>
      {status === "UNAVAILABLE" ? t("Priority unavailable") : t("Priority provisional")}
    </Badge>;
  }
  return <Badge className={PRIORITY_STYLE[level]}>{t(level)}{score != null ? ` · ${score.toFixed(1)}` : ""}</Badge>;
}

export function RoutingBadge({ status }: { status: string }) {
  const t = useT();
  const style = status === "ROUTED" ? "bg-green-50 text-green-800 ring-green-200" : status === "PENDING_REVIEW" ? "bg-amber-50 text-amber-800 ring-amber-200" : "bg-slate-100 text-slate-700 ring-slate-300";
  return <Badge className={style}>{t(ROUTING_LABEL[status] || status)}</Badge>;
}

const VERIFICATION: Record<string, { label: string; cls: string; tip: string }> = {
  VERIFIED: { label: "Verified", cls: "bg-green-50 text-green-800 ring-green-200", tip: "A source reference has been recorded." },
  PENDING_VERIFICATION: { label: "Pending verification", cls: "bg-amber-50 text-amber-800 ring-amber-200", tip: "No source reference recorded yet." },
  PROTOTYPE: { label: "Prototype", cls: "bg-slate-100 text-slate-700 ring-slate-300", tip: "Sample configuration, not official data." },
};
/** Compact, consistent verification indicator; the explanation lives in the tooltip. */
export function VerificationBadge({ status }: { status?: string | null }) {
  const t = useT();
  const v = VERIFICATION[status || ""];
  if (!v) return null;
  return <Badge className={v.cls} title={t(v.tip)}>{t(v.label)}</Badge>;
}

export function ActiveBadge({ active }: { active: boolean }) {
  const t = useT();
  return active ? <Badge className="bg-white text-green-800 ring-green-300">{t("Active")}</Badge> : <Badge className="bg-slate-100 text-slate-500 ring-slate-300">{t("Inactive")}</Badge>;
}

export function CategoryLabel({ category }: { category: string }) {
  const t = useT();
  return <span>{t(CATEGORY_LABEL[category] || category)}</span>;
}

// ---------------- states ----------------
export function Spinner({ label }: { label?: string }) {
  const t = useT();
  return (
    <div role="status" className="flex items-center gap-2 py-8 text-sm text-slate-600">
      <Loader2 className="h-5 w-5 animate-spin text-navy-600" aria-hidden /> {label ?? t("Loading…")}
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-md border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <Inbox className="h-7 w-7 text-slate-400" aria-hidden />
      <h3 className="mt-2 text-sm font-semibold text-slate-900">{title}</h3>
      {body && <p className="mt-1 max-w-md text-sm text-slate-600">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const t = useT();
  if (!error) return null;
  const e = error as { message?: string; requestId?: string; code?: string };
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p>{e.message ? t(e.message) : t("Something went wrong.")}</p>
        {e.requestId && <p className="mt-1 text-xs text-red-600">{t("Reference")}: {e.requestId}</p>}
      </div>
      {onRetry && (
        <button type="button" onClick={onRetry} className="inline-flex items-center gap-1 text-xs font-medium underline">
          <RefreshCw className="h-3 w-3" aria-hidden /> {t("Retry")}
        </button>
      )}
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "success"; children: ReactNode }) {
  const style = { info: "border-navy-100 bg-navy-50 text-navy-900", warn: "border-amber-200 bg-amber-50 text-amber-900", success: "border-green-200 bg-green-50 text-green-900" }[tone];
  return <div className={cx("rounded-md border p-3 text-sm", style)}>{children}</div>;
}

// ---------------- forms ----------------
export function Field({ label, htmlFor, hint, error, children, required }: { label: string; htmlFor: string; hint?: ReactNode; error?: string; children: ReactNode; required?: boolean }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-800">
        {label} {required && <span className="text-red-700" aria-hidden>*</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      {error && <p className="text-xs text-red-700" role="alert">{error}</p>}
    </div>
  );
}

export const inputCls = "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm placeholder:text-slate-400 focus:border-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-500/20 disabled:bg-slate-50";

export function Checkbox({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex items-start gap-2 text-sm text-slate-800">
      <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-navy-700 focus:ring-navy-500" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}{hint && <span className="block text-xs text-slate-500">{hint}</span>}</span>
    </label>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3 border-b border-slate-200 pb-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

// ---------------- tables ----------------
export const tableCls = "min-w-full divide-y divide-slate-200 text-sm";
export const thCls = "bg-slate-50 px-3 py-2 text-left text-xs font-semibold text-slate-600";
export const tdCls = "px-3 py-2 align-top";

export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">{children}</div>;
}

// ---------------- tabs ----------------
export function Tabs<T extends string>({ tabs, value, onChange, counts }: { tabs: { id: T; label: string }[]; value: T; onChange: (v: T) => void; counts?: Partial<Record<T, number>> }) {
  return (
    <div className="flex flex-wrap gap-1 border-b border-slate-200" role="tablist">
      {tabs.map((tab) => (
        <button key={tab.id} type="button" role="tab" aria-selected={value === tab.id} onClick={() => onChange(tab.id)}
          className={cx("-mb-px border-b-2 px-3 py-2 text-sm", value === tab.id ? "border-navy-700 font-medium text-navy-900" : "border-transparent text-slate-600 hover:text-slate-900")}>
          {tab.label}{counts?.[tab.id] != null && <span className="ml-1.5 rounded bg-slate-100 px-1.5 text-xs text-slate-600">{counts[tab.id]}</span>}
        </button>
      ))}
    </div>
  );
}

// ---------------- modal ----------------
export function Modal({ open, title, onClose, children, footer, width = "max-w-lg" }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: string }) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className={cx("w-full rounded-md border border-slate-200 bg-white outline-none", width)}>
        <header className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
          <IconButton label={t("Close")} onClick={onClose}><X className="h-4 w-4" /></IconButton>
        </header>
        <div className="space-y-3 p-4 text-sm">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-4 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

// ---------------- filter bar ----------------
export type FilterDef = {
  key: string;
  label: string;
  type: "search" | "select" | "date" | "toggle";
  options?: { value: string; label: string }[];
  advanced?: boolean;
  placeholder?: string;
};

/** Essential filters always visible; the rest live in a collapsible Advanced panel with
 *  Apply / Clear all, active-filter chips and a result count. Values are plain strings. */
export function FilterBar({ defs, value, onChange, total }: { defs: FilterDef[]; value: Record<string, string>; onChange: (v: Record<string, string>) => void; total?: number | null }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>(value);
  const [q, setQ] = useState(value.q || "");
  useEffect(() => { setDraft(value); setQ(value.q || ""); }, [value]);
  useEffect(() => {
    const h = setTimeout(() => { if ((value.q || "") !== q) onChange({ ...value, q }); }, 350);
    return () => clearTimeout(h);
  }, [q]); // eslint-disable-line react-hooks/exhaustive-deps

  const essentials = defs.filter((d) => !d.advanced);
  const advanced = defs.filter((d) => d.advanced);
  const active = defs.filter((d) => value[d.key]);
  const advCount = advanced.filter((d) => value[d.key]).length;
  const labelOf = (d: FilterDef, v: string) => d.type === "toggle" ? d.label : `${d.label}: ${d.options?.find((o) => o.value === v)?.label ?? v}`;

  const control = (d: FilterDef, vals: Record<string, string>, set: (k: string, v: string) => void) => {
    if (d.type === "search") return <input aria-label={d.label} className={inputCls} placeholder={d.placeholder || t("Search")} value={q} onChange={(e) => setQ(e.target.value)} />;
    if (d.type === "select") return (
      <select aria-label={d.label} className={inputCls} value={vals[d.key] || ""} onChange={(e) => set(d.key, e.target.value)}>
        <option value="">{d.label}: {t("All")}</option>
        {d.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
    if (d.type === "date") return <input aria-label={d.label} type="date" className={inputCls} value={vals[d.key] || ""} onChange={(e) => set(d.key, e.target.value)} />;
    return <Checkbox label={d.label} checked={vals[d.key] === "true"} onChange={(c) => set(d.key, c ? "true" : "")} />;
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {essentials.map((d) => (
          <div key={d.key} className={d.type === "search" ? "min-w-[14rem] flex-1" : "w-full sm:w-48"}>
            {control(d, value, (k, v) => onChange({ ...value, [k]: v }))}
          </div>
        ))}
        {advanced.length > 0 && (
          <Button variant="secondary" onClick={() => setOpen(!open)} aria-expanded={open}>
            <SlidersHorizontal className="h-4 w-4" aria-hidden /> {t("Advanced filters")}
            {advCount > 0 && <span className="rounded bg-navy-700 px-1.5 text-xs text-white">{advCount}</span>}
            <ChevronDown className={cx("h-4 w-4 transition-transform", open && "rotate-180")} aria-hidden />
          </Button>
        )}
      </div>
      {open && advanced.length > 0 && (
        <div className="rounded-md border border-slate-200 bg-white p-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {advanced.map((d) => (
              <div key={d.key} className="space-y-1">
                {d.type !== "toggle" && <span className="block text-xs font-medium text-slate-600">{d.label}</span>}
                {control(d, draft, (k, v) => setDraft({ ...draft, [k]: v }))}
              </div>
            ))}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => { const cleared = { ...draft }; advanced.forEach((d) => delete cleared[d.key]); setDraft(cleared); }}>{t("Reset")}</Button>
            <Button onClick={() => { onChange({ ...draft, q }); setOpen(false); }}>{t("Apply")}</Button>
          </div>
        </div>
      )}
      {(active.length > 0 || total != null) && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
          {total != null && <span className="font-medium text-slate-700">{t("{n} result(s)", { n: total })}</span>}
          {active.map((d) => (
            <span key={d.key} className="inline-flex items-center gap-1 rounded border border-slate-300 bg-white px-2 py-0.5">
              {d.type === "search" ? `“${value[d.key]}”` : labelOf(d, value[d.key])}
              <button type="button" aria-label={t("Remove filter")} onClick={() => { const n = { ...value }; delete n[d.key]; if (d.key === "q") setQ(""); onChange(n); }}><X className="h-3 w-3" /></button>
            </span>
          ))}
          {active.length > 0 && <button type="button" className="font-medium text-navy-700 underline" onClick={() => { setQ(""); onChange({}); }}>{t("Clear all")}</button>}
        </div>
      )}
    </div>
  );
}

/** Builds a query string from filter values; date filters become ISO day bounds. */
export function filterQuery(v: Record<string, string>, map: Record<string, string> = {}) {
  const p = new URLSearchParams();
  Object.entries(v).forEach(([k, val]) => {
    if (!val) return;
    const key = map[k] || k;
    if (k === "date_from") p.set(key, new Date(val + "T00:00:00").toISOString());
    else if (k === "date_to") p.set(key, new Date(val + "T23:59:59").toISOString());
    else p.set(key, val);
  });
  return p.toString();
}
