"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useRequireRole } from "@/components/AuthProvider";
import { CATEGORY_LABEL, ROLE_LABEL, fmtDate } from "@/components/labels";
import { PolygonDrawer } from "@/components/map";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Notice, PageHeader, Spinner, Stat, cx, inputCls } from "@/components/ui";
import { ComplaintTable } from "@/features/complaints";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import { CATEGORIES } from "@/types";

const TABS = ["Overview", "Routing queue", "AI & safety review", "Duplicates", "Departments", "Jurisdictions", "Responsibilities",
  "Sensitive locations", "Users & officers", "Priority config", "Lifecycle", "Audit log"] as const;
type Tab = (typeof TABS)[number];

export default function AdminPage() {
  const { allowed } = useRequireRole(["SYSTEM_ADMIN"]);
  const [tab, setTab] = useState<Tab>("Overview");
  if (!allowed) return <Spinner />;
  return (
    <div className="space-y-6">
      <PageHeader title="Administration" subtitle="Configuration entered here is administrator-maintained prototype configuration unless marked with a verified source." />
      <div className="flex flex-wrap gap-1 border-b border-slate-200" role="tablist">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={cx("rounded-t px-3 py-2 text-sm", tab === t ? "border border-b-white border-slate-200 bg-white font-medium text-navy-900" : "text-slate-600 hover:text-navy-800")}>{t}</button>
        ))}
      </div>
      {tab === "Overview" && <Overview />}
      {tab === "Routing queue" && <RoutingQueue />}
      {tab === "AI & safety review" && <AIReview />}
      {tab === "Duplicates" && <Duplicates />}
      {tab === "Departments" && <Departments />}
      {tab === "Jurisdictions" && <Jurisdictions />}
      {tab === "Responsibilities" && <Responsibilities />}
      {tab === "Sensitive locations" && <SensitiveLocations />}
      {tab === "Users & officers" && <Users />}
      {tab === "Priority config" && <PriorityConfig />}
      {tab === "Lifecycle" && <Lifecycle />}
      {tab === "Audit log" && <AuditLog />}
    </div>
  );
}

function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ok, setOk] = useState("");
  const run = async (fn: () => Promise<void>, success = "Saved.") => {
    setBusy(true); setError(null); setOk("");
    try { await fn(); setOk(success); } catch (e) { setError(e); } finally { setBusy(false); }
  };
  return { busy, error, ok, run };
}

function Feedback({ s }: { s: ReturnType<typeof useSubmit> }) {
  return <>{s.ok && <Notice tone="success">{s.ok}</Notice>}<ErrorBox error={s.error} /></>;
}

function Loadable<T>({ q, children, empty }: { q: { data: T | null; error: unknown; loading: boolean; reload: () => void }; children: (d: T) => ReactNode; empty?: (d: T) => boolean }) {
  if (q.loading && !q.data) return <Spinner />;
  if (q.error) return <ErrorBox error={q.error} onRetry={q.reload} />;
  if (!q.data) return null;
  if (empty?.(q.data)) return <EmptyState title="Nothing here yet" />;
  return <>{children(q.data)}</>;
}

function Overview() {
  const q = useApi<any>("/api/admin/system");
  return (
    <Loadable q={q}>{(d) => (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
          <Stat label="Database" value={d.database.ok ? "OK" : "DOWN"} hint={d.database.postgis ? `PostGIS ${d.database.postgis.split(" ")[0]}` : undefined} />
          <Stat label="Media storage" value={d.storage.ok ? "OK" : "DOWN"} hint={d.storage.kind} />
          <Stat label="AI mode" value={d.ai.mode === "stub" ? "Not configured" : "Configured"} hint={d.ai.provider || "no provider"} />
          <Stat label="Complaints" value={d.counts.complaints} />
          <Stat label="Routing review" value={d.counts.routing_pending_review} />
          <Stat label="Unrouted" value={d.counts.unrouted} />
        </div>
        <Card title="AI capabilities">
          <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
            {d.ai.capabilities.map((c: any) => (
              <tr key={c.name}><td className="py-1.5 font-medium">{c.name.replaceAll("_", " ")}</td>
                <td><Badge className={c.configured ? "bg-green-50 text-green-800 ring-green-200" : "bg-slate-100 text-slate-700 ring-slate-300"}>{c.status}</Badge></td>
                <td className="text-xs text-slate-500">{c.model || ""} {c.note || ""}</td></tr>
            ))}
          </tbody></table>
          {d.ai.mode === "stub" && <p className="mt-2 text-xs text-slate-500">AI is in explicit stub mode: analysis requests return AI_NOT_CONFIGURED and citizens report manually. See README → AI integration.</p>}
        </Card>
        <p className="text-xs text-slate-500">Checked {fmtDate(d.checked_at)} · users {d.counts.users} · departments {d.counts.departments} · jurisdictions {d.counts.jurisdictions}</p>
      </div>
    )}</Loadable>
  );
}

function RoutingQueue() {
  const [status, setStatus] = useState("PENDING_REVIEW");
  const q = useApi<any[]>(`/api/admin/routing-queue?status=${status}`, [status]);
  const depts = useApi<any[]>("/api/admin/departments");
  return (
    <div className="space-y-3">
      <div className="flex gap-2 text-sm">
        {["PENDING_REVIEW", "UNROUTED"].map((s) => <Button key={s} variant={status === s ? "primary" : "secondary"} onClick={() => setStatus(s)}>{s === "PENDING_REVIEW" ? "Needs review" : "Unrouted (monitoring)"}</Button>)}
      </div>
      {status === "UNROUTED" && <Notice>Unrouted complaints have no eligible department under the current configuration and no specific review action. Adding a jurisdiction or responsibility rule and re-running routing may resolve them.</Notice>}
      <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
        <ul className="space-y-3">{rows.map((c) => <RoutingItem key={c.complaint_id} c={c} depts={depts.data || []} onDone={q.reload} />)}</ul>
      )}</Loadable>
    </div>
  );
}

function RoutingItem({ c, depts, onDone }: { c: any; depts: any[]; onDone: () => void }) {
  const [dept, setDept] = useState("");
  const [reason, setReason] = useState("");
  const s = useSubmit();
  const candidates = c.candidates?.eligible_departments?.map((d: any) => d.id) || [];
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs">{c.reference_id}</span><span className="font-medium">{c.title}</span>
        <Badge className="bg-slate-100 ring-slate-300">{CATEGORY_LABEL[c.category]}</Badge><Badge className="bg-amber-50 text-amber-800 ring-amber-200">{c.reason_code}</Badge></div>
      <p className="mt-1 text-slate-700">{c.explanation}</p>
      <p className="text-xs text-slate-500">{c.location.latitude.toFixed(5)}, {c.location.longitude.toFixed(5)} {c.location.landmark ? `· ${c.location.landmark}` : ""}</p>
      <Feedback s={s} />
      <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_2fr_auto_auto]">
        <select aria-label="Department" className={inputCls} value={dept} onChange={(e) => setDept(e.target.value)}>
          <option value="">Confirm department…</option>
          {depts.filter((d) => d.active).map((d) => <option key={d.id} value={d.id}>{d.name}{candidates.includes(d.id) ? " (candidate)" : ""}</option>)}
        </select>
        <input aria-label="Reason" className={inputCls} placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button disabled={!dept || reason.trim().length < 3} loading={s.busy} onClick={() => s.run(async () => { await api(`/api/admin/complaints/${c.complaint_id}/routing`, { body: { department_id: dept, reason } }); onDone(); }, "Routed.")}>Route</Button>
        <Button variant="secondary" onClick={() => s.run(async () => { const r = await api(`/api/complaints/${c.complaint_id}/route`, { method: "POST" }); onDone(); if (r.routing_status !== "ROUTED") throw { message: `Re-run result: ${r.routing_status} — ${r.explanation}` }; }, "Re-run routed it.")}>Re-run rules</Button>
      </div>
    </li>
  );
}

function AIReview() {
  const q = useApi<any>("/api/admin/ai-review-queue");
  return (
    <Loadable q={q}>{(d) => (
      <div className="space-y-4">
        <Card title={`Prompt safety reviews (${d.prompt_safety_reviews.length})`}>
          {d.prompt_safety_reviews.length ? <ComplaintTable items={d.prompt_safety_reviews} hrefBase="/authority/complaints" staff /> : <p className="text-sm text-slate-500">None.</p>}
        </Card>
        <Card title={`Low-confidence / flagged AI analyses (${d.low_confidence_or_flagged.length})`}>
          {d.low_confidence_or_flagged.length === 0 ? <p className="text-sm text-slate-500">None.</p> : (
            <ul className="space-y-2 text-sm">{d.low_confidence_or_flagged.map((c: any) => (
              <li key={c.complaint_id} className="flex flex-wrap items-center gap-2 rounded border border-slate-200 p-2">
                <span className="font-mono text-xs">{c.reference_id}</span>{c.title}
                <span className="text-xs text-slate-500">{c.analysis?.confidence_band} · {(c.analysis?.review_reasons || []).join(" ")}</span>
                <Button variant="secondary" className="ml-auto" onClick={async () => { await api(`/api/admin/ai-review/${c.complaint_id}/ack`, { method: "POST" }); q.reload(); }}>Mark reviewed</Button>
              </li>
            ))}</ul>
          )}
        </Card>
        <Card title="Recent AI failures">
          {d.recent_ai_failures.length === 0 ? <p className="text-sm text-slate-500">None recorded.</p> : (
            <ul className="text-sm">{d.recent_ai_failures.map((f: any, i: number) => <li key={i}>{fmtDate(f.created_at)} · {f.code}</li>)}</ul>
          )}
        </Card>
      </div>
    )}</Loadable>
  );
}

function Duplicates() {
  const q = useApi<any[]>("/api/admin/relationships?status=SUGGESTED");
  return (
    <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
      <ul className="space-y-2">{rows.map((r) => (
        <li key={r.relationship_id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Link className="font-mono text-xs text-teal-700 underline" href={`/authority/complaints/${r.source.complaint_id}`}>{r.source.reference_id}</Link> ↔
            <Link className="font-mono text-xs text-teal-700 underline" href={`/authority/complaints/${r.related.complaint_id}`}>{r.related.reference_id}</Link>
            <span className="text-xs text-slate-500">score {r.similarity_score.toFixed(2)} · {r.distance_m} m · {r.text_similarity_method} {r.text_similarity?.toFixed(2)}</span>
          </div>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-600">{r.match_reasons.map((m: string) => <li key={m}>{m}</li>)}</ul>
          <div className="mt-2 flex gap-2">
            {["CONFIRMED_RELATED", "NOT_RELATED"].map((s) => <Button key={s} variant="secondary" onClick={async () => {
              await api(`/api/complaints/${r.source.complaint_id}/relationships`, { body: { related_complaint_id: r.related.complaint_id, relationship_status: s } }); q.reload();
            }}>{s === "CONFIRMED_RELATED" ? "Related" : "Not related"}</Button>)}
          </div>
        </li>
      ))}</ul>
    )}</Loadable>
  );
}

function Departments() {
  const q = useApi<any[]>("/api/admin/departments");
  const [form, setForm] = useState({ name: "", description: "", source_reference: "", is_prototype: true });
  const s = useSubmit();
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Add department" className="lg:col-span-1">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); s.run(async () => { await api("/api/admin/departments", { body: form }); setForm({ name: "", description: "", source_reference: "", is_prototype: true }); q.reload(); }, "Department created."); }}>
          <Feedback s={s} />
          <Field label="Name" htmlFor="dn" required><input id="dn" className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Description" htmlFor="dd"><textarea id="dd" className={inputCls} rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <Field label="Source reference" htmlFor="ds" hint="Official source for this department's mandate, if any."><input id="ds" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_prototype} onChange={(e) => setForm({ ...form, is_prototype: e.target.checked })} /> Prototype configuration (not verified official data)</label>
          <Button type="submit" loading={s.busy} disabled={form.name.trim().length < 2}>Create</Button>
        </form>
      </Card>
      <div className="lg:col-span-2">
        <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
          <ul className="space-y-2">{rows.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <span className="font-medium">{d.name}</span>
              {d.is_prototype && <Badge className="bg-amber-50 text-amber-800 ring-amber-200">prototype</Badge>}
              {!d.active && <Badge className="bg-slate-200 ring-slate-300">inactive</Badge>}
              <span className="text-xs text-slate-500">{d.supported_categories.map((c: string) => CATEGORY_LABEL[c]).join(", ") || "no verified responsibilities"}</span>
              <Button variant="ghost" className="ml-auto" onClick={async () => { await api(`/api/admin/departments/${d.id}`, { method: "PATCH", body: { active: !d.active } }); q.reload(); }}>{d.active ? "Deactivate" : "Activate"}</Button>
            </li>
          ))}</ul>
        )}</Loadable>
      </div>
    </div>
  );
}

function Jurisdictions() {
  const q = useApi<any[]>("/api/admin/jurisdictions");
  const depts = useApi<any[]>("/api/admin/departments");
  const [vertices, setVertices] = useState<[number, number][]>([]);
  const [geojson, setGeojson] = useState("");
  const [form, setForm] = useState({ name: "", source_reference: "", is_prototype: true, department_ids: [] as string[], last_verified_at: "" });
  const s = useSubmit();

  const boundary = () => {
    if (geojson.trim()) {
      const g = JSON.parse(geojson);
      return g.type === "Feature" ? g.geometry : g.type === "FeatureCollection" ? g.features[0].geometry : g;
    }
    const ring = vertices.map(([lat, lng]) => [lng, lat]);
    return { type: "Polygon", coordinates: [[...ring, ring[0]]] };
  };
  const existing = (q.data || []).filter((j) => j.boundary).map((j) => ({
    name: j.name,
    rings: (j.boundary.type === "Polygon" ? [j.boundary.coordinates] : j.boundary.coordinates).map((poly: number[][][]) => poly[0].map(([lng, lat]) => [lat, lng] as [number, number])),
  }));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Add jurisdiction">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
          let b; try { b = boundary(); } catch { throw { message: "GeoJSON could not be parsed." }; }
          await api("/api/admin/jurisdictions", { body: { ...form, boundary: b, last_verified_at: form.last_verified_at ? new Date(form.last_verified_at).toISOString() : null } });
          setVertices([]); setGeojson(""); setForm({ ...form, name: "", department_ids: [] }); q.reload();
        }, "Jurisdiction saved."); }}>
          <Feedback s={s} />
          <Field label="Name" htmlFor="jn" required><input id="jn" className={inputCls} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div>
            <p className="mb-1 text-sm font-medium text-slate-800">Boundary — click the map to add vertices ({vertices.length}) <button type="button" className="ml-2 text-xs text-teal-700 underline" onClick={() => setVertices([])}>clear</button></p>
            <PolygonDrawer vertices={vertices} onAdd={(lat, lng) => setVertices((v) => [...v, [lat, lng]])} existing={existing} />
          </div>
          <Field label="…or paste GeoJSON (Polygon / MultiPolygon / Feature)" htmlFor="gj" hint="Prefer verified, appropriately licensed boundary data.">
            <textarea id="gj" rows={3} className={inputCls + " font-mono text-xs"} value={geojson} onChange={(e) => setGeojson(e.target.value)} />
          </Field>
          <fieldset><legend className="text-sm font-medium text-slate-800">Departments operating here</legend>
            <div className="mt-1 grid grid-cols-2 gap-1 text-sm">{(depts.data || []).map((d) => (
              <label key={d.id} className="flex items-center gap-1"><input type="checkbox" checked={form.department_ids.includes(d.id)}
                onChange={(e) => setForm({ ...form, department_ids: e.target.checked ? [...form.department_ids, d.id] : form.department_ids.filter((x) => x !== d.id) })} />{d.name}</label>
            ))}</div>
          </fieldset>
          <Field label="Source reference" htmlFor="jsr"><input id="jsr" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
          <Field label="Last verified" htmlFor="jlv"><input id="jlv" type="date" className={inputCls} value={form.last_verified_at} onChange={(e) => setForm({ ...form, last_verified_at: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_prototype} onChange={(e) => setForm({ ...form, is_prototype: e.target.checked })} /> Prototype configuration (not verified official boundary)</label>
          <Button type="submit" loading={s.busy} disabled={form.name.trim().length < 2 || (vertices.length < 3 && !geojson.trim())}>Save jurisdiction</Button>
        </form>
      </Card>
      <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
        <ul className="space-y-2">{rows.map((j) => (
          <li key={j.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{j.name}</span>
              {j.is_prototype && <Badge className="bg-amber-50 text-amber-800 ring-amber-200">prototype</Badge>}
              {!j.active && <Badge className="bg-slate-200 ring-slate-300">inactive</Badge>}</div>
            <p className="text-xs text-slate-600">Departments: {j.departments.map((d: any) => d.name).join(", ") || "none"}</p>
            <p className="text-xs text-slate-500">Source: {j.source_reference || "—"} · verified {j.last_verified_at ? fmtDate(j.last_verified_at, false) : "never"}</p>
          </li>
        ))}</ul>
      )}</Loadable>
    </div>
  );
}

function Responsibilities() {
  const q = useApi<any[]>("/api/admin/responsibilities");
  const depts = useApi<any[]>("/api/admin/departments");
  const [form, setForm] = useState({ department_id: "", category: "", verified: false, active: true, source_reference: "" });
  const s = useSubmit();
  const save = (body: any) => s.run(async () => { await api("/api/admin/responsibilities", { body }); q.reload(); depts.reload(); });
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Add / update mapping">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save(form); }}>
          <Feedback s={s} />
          <Field label="Department" htmlFor="rd" required><select id="rd" className={inputCls} value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}><option value="">Choose…</option>{(depts.data || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
          <Field label="Category" htmlFor="rc" required><select id="rc" className={inputCls} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}><option value="">Choose…</option>{CATEGORIES.map((c) => <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>)}</select></Field>
          <Field label="Source reference" htmlFor="rs"><input id="rs" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.verified} onChange={(e) => setForm({ ...form, verified: e.target.checked })} /> I have verified this responsibility</label>
          <p className="text-xs text-slate-500">Only active, verified mappings are used for automatic routing. Unverified mappings send matching complaints to administrative review.</p>
          <Button type="submit" loading={s.busy} disabled={!form.department_id || !form.category}>Save mapping</Button>
        </form>
      </Card>
      <div className="lg:col-span-2">
        <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
          <table className="w-full rounded-lg border border-slate-200 bg-white text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500"><tr><th className="p-2">Category</th><th>Department</th><th>Verified</th><th>Active</th><th></th></tr></thead>
            <tbody className="divide-y divide-slate-100">{rows.map((r) => (
              <tr key={r.id}><td className="p-2">{CATEGORY_LABEL[r.category]}</td><td>{r.department_name}</td>
                <td>{r.verified ? `Yes (${fmtDate(r.verified_at, false)})` : "No"}</td><td>{r.active ? "Yes" : "No"}</td>
                <td className="space-x-2 text-right">
                  <Button variant="ghost" onClick={() => save({ department_id: r.department_id, category: r.category, verified: !r.verified, active: r.active, source_reference: r.source_reference })}>{r.verified ? "Unverify" : "Verify"}</Button>
                  <Button variant="ghost" onClick={() => save({ department_id: r.department_id, category: r.category, verified: r.verified, active: !r.active, source_reference: r.source_reference })}>{r.active ? "Deactivate" : "Activate"}</Button>
                </td></tr>
            ))}</tbody>
          </table>
        )}</Loadable>
      </div>
    </div>
  );
}

function SensitiveLocations() {
  const q = useApi<any[]>("/api/admin/sensitive-locations");
  const [vertices, setVertices] = useState<[number, number][]>([]);
  const [form, setForm] = useState({ label: "", location_type: "SCHOOL", radius_m: "100", sensitivity_score: "80", source_reference: "", is_prototype: true });
  const s = useSubmit();
  const pt = vertices[vertices.length - 1];
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Add sensitive location">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
          await api("/api/admin/sensitive-locations", { body: { ...form, latitude: pt[0], longitude: pt[1], radius_m: Number(form.radius_m), sensitivity_score: Number(form.sensitivity_score) } });
          setVertices([]); setForm({ ...form, label: "" }); q.reload();
        }, "Saved."); }}>
          <Feedback s={s} />
          <p className="text-xs text-slate-600">Used for the location-sensitivity (L) factor. Rubric: 76–100 verified sensitive location (school entrance, hospital access, critical facility); 51–75 high-use / vulnerable users.</p>
          <PolygonDrawer vertices={pt ? [pt] : []} onAdd={(lat, lng) => setVertices([[lat, lng]])} height={260} />
          <p className="text-xs text-slate-500">{pt ? `${pt[0].toFixed(5)}, ${pt[1].toFixed(5)}` : "Click the map to place the point."}</p>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Label" htmlFor="sl" required><input id="sl" className={inputCls} value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} /></Field>
            <Field label="Type" htmlFor="st"><select id="st" className={inputCls} value={form.location_type} onChange={(e) => setForm({ ...form, location_type: e.target.value })}>{["SCHOOL", "HOSPITAL", "CRITICAL_FACILITY", "TRANSIT_HUB", "MARKET", "OTHER"].map((t) => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Radius (m)" htmlFor="sr"><input id="sr" type="number" min={1} max={5000} className={inputCls} value={form.radius_m} onChange={(e) => setForm({ ...form, radius_m: e.target.value })} /></Field>
            <Field label="Sensitivity (0–100)" htmlFor="ss"><input id="ss" type="number" min={0} max={100} className={inputCls} value={form.sensitivity_score} onChange={(e) => setForm({ ...form, sensitivity_score: e.target.value })} /></Field>
          </div>
          <Field label="Source reference" htmlFor="ssr"><input id="ssr" className={inputCls} value={form.source_reference} onChange={(e) => setForm({ ...form, source_reference: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.is_prototype} onChange={(e) => setForm({ ...form, is_prototype: e.target.checked })} /> Prototype configuration</label>
          <Button type="submit" loading={s.busy} disabled={!pt || form.label.trim().length < 2}>Save</Button>
        </form>
      </Card>
      <Loadable q={q} empty={(d) => d.length === 0}>{(rows) => (
        <ul className="space-y-2">{rows.map((l) => (
          <li key={l.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
            <span className="font-medium">{l.label}</span><Badge className="bg-slate-100 ring-slate-300">{l.location_type}</Badge>
            <span className="text-xs text-slate-500">score {l.sensitivity_score} · {l.radius_m} m{l.is_prototype ? " · prototype" : ""}</span>
            <Button variant="ghost" className="ml-auto" onClick={async () => { await api(`/api/admin/sensitive-locations/${l.id}`, { method: "PATCH", body: { active: !l.active } }); q.reload(); }}>{l.active ? "Deactivate" : "Activate"}</Button>
          </li>
        ))}</ul>
      )}</Loadable>
    </div>
  );
}

function Users() {
  const [role, setRole] = useState("");
  const q = useApi<any>(`/api/admin/users${role ? `?role=${role}` : ""}`, [role]);
  const depts = useApi<any[]>("/api/admin/departments");
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "OFFICER", department_id: "", designation: "" });
  const s = useSubmit();
  const patch = (id: string, body: any) => s.run(async () => { await api(`/api/admin/users/${id}`, { method: "PATCH", body }); q.reload(); }, "User updated.");
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Create staff account">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); s.run(async () => {
          await api("/api/admin/users", { body: { ...form, department_id: form.department_id || null, designation: form.designation || null } });
          setForm({ ...form, full_name: "", email: "", password: "", designation: "" }); q.reload();
        }, "Account created. Share the initial password securely and ask the user to keep it private."); }}>
          <Feedback s={s} />
          <Field label="Full name" htmlFor="uf" required><input id="uf" className={inputCls} value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
          <Field label="Email" htmlFor="ue" required><input id="ue" type="email" className={inputCls} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Initial password" htmlFor="up" required hint="At least 8 characters."><input id="up" type="password" autoComplete="new-password" className={inputCls} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          <Field label="Role" htmlFor="ur"><select id="ur" className={inputCls} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>{["OFFICER", "DEPARTMENT_ADMIN", "SYSTEM_ADMIN"].map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></Field>
          {form.role !== "SYSTEM_ADMIN" && <>
            <Field label="Department" htmlFor="ud" required><select id="ud" className={inputCls} value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}><option value="">Choose…</option>{(depts.data || []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
            <Field label="Designation" htmlFor="udes"><input id="udes" className={inputCls} value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} placeholder="e.g. Assistant Engineer" /></Field>
          </>}
          <Button type="submit" loading={s.busy}>Create account</Button>
        </form>
      </Card>
      <div className="space-y-3 lg:col-span-2">
        <select aria-label="Filter by role" className={inputCls + " w-56"} value={role} onChange={(e) => setRole(e.target.value)}><option value="">All roles</option>{Object.keys(ROLE_LABEL).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
        <Loadable q={q} empty={(d) => d.items.length === 0}>{(d) => (
          <ul className="space-y-2">{d.items.map((u: any) => (
            <li key={u.id} className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2"><span className="font-medium">{u.full_name}</span><span className="text-xs text-slate-500">{u.email}</span>
                <Badge className="bg-slate-100 ring-slate-300">{ROLE_LABEL[u.role]}</Badge>
                {u.account_status !== "ACTIVE" && <Badge className="bg-red-50 text-red-800 ring-red-200">{u.account_status}</Badge>}
                {u.permissions.map((p: string) => <Badge key={p} className="bg-teal-50 text-teal-800 ring-teal-200">{p}</Badge>)}</div>
              {u.officer && <p className="text-xs text-slate-600">{u.officer.department_name} · {u.officer.designation}{u.officer.active ? "" : " · officer inactive"}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="ghost" onClick={() => patch(u.id, { account_status: u.account_status === "ACTIVE" ? "DISABLED" : "ACTIVE" })}>{u.account_status === "ACTIVE" ? "Disable" : "Enable"}</Button>
                {u.role === "OFFICER" && <Button variant="ghost" onClick={() => patch(u.id, u.permissions.includes("VERIFY_RESOLUTION") ? { revoke_permissions: ["VERIFY_RESOLUTION"] } : { grant_permissions: ["VERIFY_RESOLUTION"] })}>{u.permissions.includes("VERIFY_RESOLUTION") ? "Revoke verify permission" : "Grant verify permission"}</Button>}
                {u.officer && <Button variant="ghost" onClick={() => patch(u.id, { officer_active: !u.officer.active })}>{u.officer.active ? "Deactivate officer" : "Activate officer"}</Button>}
              </div>
            </li>
          ))}</ul>
        )}</Loadable>
      </div>
    </div>
  );
}

function PriorityConfig() {
  const q = useApi<any>("/api/admin/priority-config");
  const [text, setText] = useState<string | null>(null);
  const s = useSubmit();
  return (
    <Loadable q={q}>{(d) => (
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={`Active configuration (${d.active_version})`} className="lg:col-span-2">
          <Feedback s={s} />
          <p className="mb-2 text-xs text-slate-600">{d.disclaimer} Weights must sum to 1.0; thresholds must satisfy CRITICAL &gt; HIGH &gt; MEDIUM. Every change creates a new audited version.</p>
          <textarea aria-label="Priority configuration JSON" rows={22} className={inputCls + " font-mono text-xs"} value={text ?? JSON.stringify(d.config, null, 2)} onChange={(e) => setText(e.target.value)} />
          <div className="mt-2 flex gap-2">
            <Button loading={s.busy} disabled={text === null} onClick={() => s.run(async () => {
              let cfg; try { cfg = JSON.parse(text!); } catch { throw { message: "Configuration is not valid JSON." }; }
              await api("/api/admin/priority-config", { body: { config: cfg } }); setText(null); q.reload();
            }, "New configuration version saved.")}>Save new version</Button>
            <Button variant="secondary" onClick={() => setText(JSON.stringify(d.default, null, 2))}>Load built-in default</Button>
          </div>
        </Card>
        <Card title="Version history">
          {d.history.length === 0 ? <p className="text-sm text-slate-500">Using the built-in default (v0).</p> : (
            <ul className="text-sm">{d.history.map((h: any) => <li key={h.version}>v{h.version} {h.active && <Badge className="bg-teal-50 text-teal-800 ring-teal-200">active</Badge>} · {fmtDate(h.created_at)}</li>)}</ul>
          )}
        </Card>
      </div>
    )}</Loadable>
  );
}

function Lifecycle() {
  const q = useApi<any>("/api/admin/lifecycle");
  return (
    <Loadable q={q}>{(d) => (
      <Card title="Permitted status transitions (enforced in backend code)">
        <table className="w-full text-sm"><tbody className="divide-y divide-slate-100">
          {Object.entries(d.transitions).map(([from, to]: any) => <tr key={from}><td className="py-1.5 font-mono text-xs">{from}</td><td className="text-xs">→ {to.join(", ") || "(terminal)"}</td></tr>)}
        </tbody></table>
        <p className="mt-3 text-xs text-slate-600">Reason required: {d.reason_required.join(", ")}. Workflow-only targets: {Object.entries(d.workflow_only).map(([k, v]) => `${k} (${v})`).join(", ")}.</p>
        <p className="mt-1 text-xs text-slate-500">Transitions are deliberately not editable at runtime so they cannot be weakened; change them in code with tests.</p>
      </Card>
    )}</Loadable>
  );
}

function AuditLog() {
  const [action, setAction] = useState("");
  const q = useApi<any>(`/api/admin/audit-logs?limit=200${action ? `&action=${action}` : ""}`, [action]);
  return (
    <div className="space-y-3">
      <input aria-label="Filter by action" className={inputCls + " w-72"} placeholder="Filter by action, e.g. STATUS_CHANGED" value={action} onChange={(e) => setAction(e.target.value.toUpperCase())} />
      <Loadable q={q} empty={(d) => d.items.length === 0}>{(d) => (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-left uppercase text-slate-500"><tr><th className="p-2">Time</th><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{d.items.map((l: any) => (
              <tr key={l.id} className="align-top"><td className="whitespace-nowrap p-2">{fmtDate(l.created_at)}</td><td className="font-mono">{l.actor_label}</td>
                <td className="font-medium">{l.action}</td><td className="font-mono">{l.entity_type}:{l.entity_id?.slice(0, 8)}</td>
                <td className="max-w-md truncate font-mono text-slate-500" title={JSON.stringify(l.details)}>{JSON.stringify(l.details)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}</Loadable>
    </div>
  );
}
