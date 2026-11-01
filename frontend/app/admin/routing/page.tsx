"use client";

import Link from "next/link";
import { useState } from "react";
import { useT } from "@/components/I18nProvider";
import { AddressSearch } from "@/components/AddressSearch";
import { CATEGORY_LABEL, REASON_LABEL, fmtDate } from "@/components/labels";
import { PolygonDrawer } from "@/components/map";
import { ActiveBadge, Badge, Button, Card, Checkbox, Field, Notice, PageHeader, Tabs, inputCls } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { Feedback, Loadable, useSubmit } from "@/features/admin";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";

type Tab = "queue" | "how" | "sensitive" | "priority" | "duplicates" | "safety";

export default function RoutingPage() {
  const t = useT();
  const [tab, setTab] = useState<Tab>("queue");
  return (
    <div className="space-y-4">
      <PageHeader title={t("Routing Configuration")} subtitle={t("Review complaints that could not be routed automatically, and maintain the data routing and prioritisation depend on.")} />
      <Tabs value={tab} onChange={setTab} tabs={[
        { id: "queue", label: t("Review queue") }, { id: "how", label: t("How routing works") }, { id: "sensitive", label: t("Sensitive locations") },
        { id: "priority", label: t("Priority rules") }, { id: "duplicates", label: t("Possible duplicates") }, { id: "safety", label: t("Safety review") },
      ]} />
      {tab === "queue" && <RoutingQueue />}
      {tab === "how" && <HowRouting />}
      {tab === "sensitive" && <SensitiveLocations />}
      {tab === "priority" && <PriorityConfig />}
      {tab === "duplicates" && <Duplicates />}
      {tab === "safety" && <SafetyReview />}
    </div>
  );
}

function HowRouting() {
  const t = useT();
  const steps = [
    "The complaint location is matched to the deepest active jurisdiction whose boundary contains it (for example a ward).",
    "Departments with an active responsibility for the complaint category are found.",
    "For each such department, the nearest active unit is taken by walking up from the ward to its parents (ward → municipality → district → state).",
    "If exactly one unit qualifies, the complaint is routed to it. Otherwise it waits here for an administrator.",
    "Within the unit, an active officer whose operational area covers the location is chosen; ties go to the officer with the fewest active assignments.",
    "If no officer is available, the complaint waits in the unit's unassigned queue and the department administrator is notified.",
  ];
  return (
    <Card title={t("Routing sequence")}>
      <ol className="list-decimal space-y-2 pl-5 text-sm text-slate-700">{steps.map((s) => <li key={s}>{t(s)}</li>)}</ol>
      <p className="mt-3 text-sm text-slate-600">{t("Configure the inputs under")} <Link className="text-navy-700 underline" href="/admin/jurisdictions">{t("Jurisdiction Management")}</Link>, <Link className="text-navy-700 underline" href="/admin/mapping">{t("Department–Jurisdiction Mapping")}</Link>, <Link className="text-navy-700 underline" href="/admin/responsibilities">{t("Responsibility Management")}</Link> {t("and")} <Link className="text-navy-700 underline" href="/admin/users">{t("User & Officer Management")}</Link>.</p>
    </Card>
  );
}

function RoutingQueue() {
  const t = useT();
  const q = useApi<any[]>("/api/admin/routing-queue?status=PENDING_REVIEW");
  const depts = useApi<any[]>("/api/admin/departments");
  return (
    <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No complaints awaiting routing review")} emptyBody={t("Complaints that cannot be routed automatically appear here. Nothing is ever discarded.")}>
      {(rows) => <ul className="space-y-3">{rows.map((c) => <RoutingItem key={c.complaint_id} c={c} depts={depts.data || []} onDone={q.reload} />)}</ul>}
    </Loadable>
  );
}

function RoutingItem({ c, depts, onDone }: { c: any; depts: any[]; onDone: () => void }) {
  const t = useT();
  const [dept, setDept] = useState("");
  const [unit, setUnit] = useState("");
  const [reason, setReason] = useState("");
  const s = useSubmit();
  const candidateUnits = (c.candidates?.units || []) as { id: string; department: string; jurisdiction: string }[];
  const d = depts.find((x) => x.id === dept);
  return (
    <li className="rounded-md border border-slate-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/authority/complaints/${c.complaint_id}`} className="font-mono text-xs text-navy-700 underline">{c.reference_id}</Link>
        <span className="font-medium text-slate-900">{c.title}</span>
        <Badge>{t(CATEGORY_LABEL[c.category])}</Badge>
        <Badge className="bg-amber-50 text-amber-800 ring-amber-200">{t(REASON_LABEL[c.reason_code] || c.reason_code)}</Badge>
        <span className="ml-auto text-xs text-slate-500">{fmtDate(c.created_at)}</span>
      </div>
      <p className="mt-1 text-slate-700">{c.explanation}</p>
      {c.candidates?.actionable?.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{c.candidates.actionable.map((a: string) => <li key={a}>{a}</li>)}</ul>}
      <p className="text-xs text-slate-500">{c.jurisdiction?.name ? `${c.jurisdiction.name} · ` : ""}{c.location.landmark || `${c.location.latitude.toFixed(5)}, ${c.location.longitude.toFixed(5)}`}</p>
      <div className="mt-2"><Feedback s={s} /></div>
      <div className="mt-2 grid gap-2 lg:grid-cols-[1fr_1fr_2fr_auto_auto]">
        <select aria-label={t("Department")} className={inputCls} value={dept} onChange={(e) => { setDept(e.target.value); setUnit(""); }}>
          <option value="">{t("Choose department…")}</option>
          {depts.filter((x) => x.active).map((x) => <option key={x.id} value={x.id}>{x.name}{candidateUnits.some((u) => u.department === x.name) ? ` (${t("candidate")})` : ""}</option>)}
        </select>
        <select aria-label={t("Department unit")} className={inputCls} value={unit} onChange={(e) => setUnit(e.target.value)} disabled={!d}>
          <option value="">{t("Nearest unit (automatic)")}</option>
          {d?.units?.filter((u: any) => u.active).map((u: any) => <option key={u.id} value={u.id}>{u.jurisdiction_name}</option>)}
        </select>
        <input aria-label={t("Reason")} className={inputCls} placeholder={t("Reason (required)")} value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button disabled={!dept || reason.trim().length < 3} loading={s.busy} onClick={() => s.run(async () => {
          await api(`/api/admin/complaints/${c.complaint_id}/routing`, { body: { department_id: dept, unit_id: unit || null, reason } }); onDone();
        }, "Complaint routed.")}>{t("Route")}</Button>
        <Button variant="secondary" onClick={() => s.run(async () => {
          const r = await api(`/api/complaints/${c.complaint_id}/route`, { method: "POST" }); onDone();
          if (r.routing_status !== "ROUTED") throw { message: `${t("Still not routable")}: ${r.explanation}` };
        }, "Re-run routed it.")}>{t("Re-run routing")}</Button>
      </div>
    </li>
  );
}

function SensitiveLocations() {
  const t = useT();
  const q = useApi<any[]>("/api/admin/sensitive-locations");
  const [pt, setPt] = useState<[number, number] | null>(null);
  const [form, setForm] = useState({ label: "", location_type: "SCHOOL", radius_m: "100", sensitivity_score: "80", source_reference: "", is_prototype: false });
  const s = useSubmit();
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Card title={t("Add sensitive location")} subtitle={t("Schools, hospitals and critical facilities raise the location-sensitivity factor of nearby complaints.")}>
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
          await api("/api/admin/sensitive-locations", { body: { ...form, latitude: pt![0], longitude: pt![1], radius_m: Number(form.radius_m), sensitivity_score: Number(form.sensitivity_score) } });
          setPt(null); setForm({ ...form, label: "" }); q.reload();
        }); }}>
          <Feedback s={s} />
          <AddressSearch onPick={(p) => { setPt([p.latitude, p.longitude]); if (!form.label.trim()) setForm({ ...form, label: p.display_name.split(",")[0].slice(0, 120) }); }} />
          <PolygonDrawer vertices={pt ? [pt] : []} onAdd={(lat, lng) => setPt([lat, lng])} height={260} focus={pt} />
          <p className="text-xs text-slate-500">{pt ? `${pt[0].toFixed(5)}, ${pt[1].toFixed(5)} · ${t("click the map to adjust")}` : t("Search for the place above, or click the map to place the point.")}</p>
          <div className="grid grid-cols-2 gap-2">
            <Field label={t("Label")} htmlFor="sl" required><input id="sl" className={inputCls} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></Field>
            <Field label={t("Type")} htmlFor="st"><select id="st" className={inputCls} value={form.location_type} onChange={(e) => setForm({ ...form, location_type: e.target.value })}>
              {[["SCHOOL", "School"], ["HOSPITAL", "Hospital"], ["CRITICAL_FACILITY", "Critical facility"], ["HIGH_USE", "High-use public area"], ["OTHER", "Other"]].map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select></Field>
            <Field label={t("Radius (m)")} htmlFor="sr"><input id="sr" type="number" min={1} max={5000} className={inputCls} value={form.radius_m} onChange={(e) => setForm({ ...form, radius_m: e.target.value })} /></Field>
            <Field label={t("Sensitivity (0–100)")} htmlFor="ss"><input id="ss" type="number" min={0} max={100} className={inputCls} value={form.sensitivity_score} onChange={(e) => setForm({ ...form, sensitivity_score: e.target.value })} /></Field>
          </div>
          <Field label={t("Source reference")} htmlFor="ssr"><input id="ssr" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
          <Checkbox label={t("Prototype record")} hint={t("Tick only for sample or test data.")} checked={form.is_prototype} onChange={(v) => setForm({ ...form, is_prototype: v })} />
          <Button type="submit" loading={s.busy} disabled={!pt || form.label.trim().length < 2}>{t("Save")}</Button>
        </form>
      </Card>
      <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No sensitive locations")}>{(rows) => (
        <ul className="space-y-2">{rows.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white p-3 text-sm">
            <span className="font-medium">{l.label}</span><Badge>{l.location_type}</Badge><ActiveBadge active={l.active} />
            <span className="text-xs text-slate-500">{t("score")} {l.sensitivity_score} · {l.radius_m} m</span>
            <Button variant="ghost" size="sm" className="ml-auto" onClick={async () => { await api(`/api/admin/sensitive-locations/${l.id}`, { method: "PATCH", body: { active: !l.active } }); q.reload(); }}>{l.active ? t("Deactivate") : t("Activate")}</Button>
          </li>
        ))}</ul>
      )}</Loadable>
    </div>
  );
}

function PriorityConfig() {
  const t = useT();
  const q = useApi<any>("/api/admin/priority-config");
  const [text, setText] = useState<string | null>(null);
  const s = useSubmit();
  return (
    <Loadable q={q}>{(d) => (
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title={`${t("Active priority rules")} (v${d.active_version})`} className="xl:col-span-2">
          <Feedback s={s} />
          <p className="mb-2 text-xs text-slate-600">{t("Weights must add up to 1.0, and thresholds must satisfy CRITICAL > HIGH > MEDIUM. Every change creates a new audited version.")}</p>
          <textarea aria-label={t("Priority configuration")} rows={20} className={inputCls + " font-mono text-xs"} value={text ?? JSON.stringify(d.config, null, 2)} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <Button loading={s.busy} disabled={text === null} onClick={() => s.run(async () => {
              let cfg; try { cfg = JSON.parse(text!); } catch { throw { message: t("The configuration is not valid JSON.") }; }
              await api("/api/admin/priority-config", { body: { config: cfg } }); setText(null); q.reload();
            }, "New version saved.")}>{t("Save new version")}</Button>
            <Button variant="secondary" onClick={() => setText(JSON.stringify(d.default, null, 2))}>{t("Load built-in default")}</Button>
          </div>
        </Card>
        <Card title={t("Version history")}>
          {d.history.length === 0 ? <p className="text-sm text-slate-500">{t("Using the built-in default.")}</p> : (
            <ul className="space-y-1 text-sm">{d.history.map((h: any) => <li key={h.version}>v{h.version} {h.active && <Badge className="bg-green-50 text-green-800 ring-green-200">{t("Active")}</Badge>} · {fmtDate(h.created_at)}</li>)}</ul>
          )}
        </Card>
      </div>
    )}</Loadable>
  );
}

function Duplicates() {
  const t = useT();
  const q = useApi<any[]>("/api/admin/relationships?status=SUGGESTED");
  return (
    <Loadable q={q} empty={(d) => d.length === 0} emptyTitle={t("No suggested duplicates")}>{(rows) => (
      <ul className="space-y-2">{rows.map((r) => (
        <li key={r.relationship_id} className="rounded-md border border-slate-200 bg-white p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Link className="font-mono text-xs text-navy-700 underline" href={`/authority/complaints/${r.source.complaint_id}`}>{r.source.reference_id}</Link> ↔
            <Link className="font-mono text-xs text-navy-700 underline" href={`/authority/complaints/${r.related.complaint_id}`}>{r.related.reference_id}</Link>
            <span className="text-xs text-slate-500">{r.distance_m} m</span>
          </div>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{r.match_reasons.map((m: string) => <li key={m}>{m}</li>)}</ul>
          <div className="mt-2 flex gap-2">
            {[["CONFIRMED_RELATED", "Related"], ["NOT_RELATED", "Not related"]].map(([v, l]) => <Button key={v} variant="secondary" size="sm" onClick={async () => {
              await api(`/api/complaints/${r.source.complaint_id}/relationships`, { body: { related_complaint_id: r.related.complaint_id, relationship_status: v } }); q.reload();
            }}>{t(l)}</Button>)}
          </div>
        </li>
      ))}</ul>
    )}</Loadable>
  );
}

function SafetyReview() {
  const t = useT();
  const q = useApi<any>("/api/admin/ai-review-queue");
  return (
    <Loadable q={q}>{(d) => (
      <div className="space-y-4">
        <Notice>{t("Complaints that describe a possible immediate danger are flagged for prompt human review.")}</Notice>
        <Card title={`${t("Prompt safety reviews")} (${d.prompt_safety_reviews.length})`} padded={false}>
          {d.prompt_safety_reviews.length ? <ComplaintTable items={d.prompt_safety_reviews} hrefBase="/authority/complaints" staff /> : <p className="p-4 text-sm text-slate-500">{t("None.")}</p>}
        </Card>
        <Card title={`${t("Analyses needing a second look")} (${d.low_confidence_or_flagged.length})`}>
          {d.low_confidence_or_flagged.length === 0 ? <p className="text-sm text-slate-500">{t("None.")}</p> : (
            <ul className="space-y-2 text-sm">{d.low_confidence_or_flagged.map((c: any) => (
              <li key={c.complaint_id} className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
                <Link className="font-mono text-xs text-navy-700 underline" href={`/authority/complaints/${c.complaint_id}`}>{c.reference_id}</Link>{c.title}
                <Button variant="secondary" size="sm" className="ml-auto" onClick={async () => { await api(`/api/admin/ai-review/${c.complaint_id}/ack`, { method: "POST" }); q.reload(); }}>{t("Mark reviewed")}</Button>
              </li>
            ))}</ul>
          )}
        </Card>
      </div>
    )}</Loadable>
  );
}
