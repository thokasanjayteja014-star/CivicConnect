"use client";

import { Bot, CheckCircle2, Crosshair, FileUp, Languages, MapPin, RotateCw, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { AddressSearch, reverseGeocode } from "@/components/AddressSearch";
import { useRequireRole } from "@/components/AuthProvider";
import { useI18n } from "@/components/I18nProvider";
import { DictateButton, VoiceRecorder } from "@/components/VoiceInput";
import { CATEGORY_LABEL, fmtBytes } from "@/components/labels";
import { LocationPicker } from "@/components/map";
import { Badge, Button, Card, ErrorBox, Field, Notice, PageHeader, Spinner, cx, inputCls } from "@/components/ui";
import { ApiError, api, newIdempotencyKey, uploadWithProgress } from "@/services/api";
import { CATEGORIES } from "@/types";

type Upload = { localId: string; file: File; preview?: string; progress: number; mediaId?: string; error?: string; type: string };
type Loc = { lat: number; lng: number; accuracy: number | null; source: "GPS" | "MAP_SELECTION" | "MANUAL_ENTRY" } | null;

const DRAFT_KEY = "cc_report_draft";
const SEVERITY = [["MINOR", "Minor / localized"], ["MODERATE", "Moderate damage or disruption"], ["SUBSTANTIAL", "Substantial damage"], ["SEVERE", "Severe / major failure"]];
const SAFETY = [["NONE", "No safety concern"], ["LOW", "Low risk"], ["MODERATE", "Moderate risk"], ["SIGNIFICANT", "Significant risk to people"], ["IMMEDIATE", "Potentially immediate danger"]];
const EXPOSURE = [["INDIVIDUAL", "Just me / one household"], ["FEW_HOUSEHOLDS", "A few households"], ["STREET", "The whole street"], ["NEIGHBOURHOOD", "The neighbourhood"], ["WIDE_AREA", "A wide area / main road"]];
const ACCEPT = "image/jpeg,image/png,image/webp,audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/x-m4a,audio/ogg,video/mp4";

function kindOf(f: File) {
  return f.type.startsWith("image/") ? "IMAGE" : f.type.startsWith("audio/") ? "AUDIO" : f.type.startsWith("video/") ? "VIDEO" : "OTHER";
}

export default function ReportPage() {
  const { allowed } = useRequireRole(["CITIZEN"]);
  const { t, lang } = useI18n();
  const [transcribing, setTranscribing] = useState<string | null>(null);
  const [transcribeMsg, setTranscribeMsg] = useState("");
  const [step, setStep] = useState(1);
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [loc, setLoc] = useState<Loc>(null);
  const [landmark, setLandmark] = useState("");
  const [address, setAddress] = useState("");
  const [gpsBusy, setGpsBusy] = useState(false);
  const [gpsError, setGpsError] = useState("");
  const [occurred, setOccurred] = useState("");
  const [details, setDetails] = useState("");
  const [severity, setSeverity] = useState("");
  const [safety, setSafety] = useState("");
  const [exposure, setExposure] = useState("");
  const [allowPublic, setAllowPublic] = useState(true);
  const [title, setTitle] = useState("");
  const [confirmedDesc, setConfirmedDesc] = useState("");
  const [analysis, setAnalysis] = useState<any>(null);
  const [aiError, setAiError] = useState<ApiError | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [nearby, setNearby] = useState<any>(null);
  const [confirm, setConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [result, setResult] = useState<any>(null);
  const idemKey = useRef<string>(newIdempotencyKey());
  const fileInput = useRef<HTMLInputElement>(null);

  // Draft recovery (text fields only) so a failed submit never loses work.
  useEffect(() => {
    try {
      const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
      if (d) {
        setDescription(d.description || ""); setCategory(d.category || ""); setLandmark(d.landmark || ""); setAddress(d.address || "");
        setOccurred(d.occurred || ""); setDetails(d.details || ""); setTitle(d.title || ""); setLoc(d.loc || null);
        setSeverity(d.severity || ""); setSafety(d.safety || ""); setExposure(d.exposure || "");
        if (d.idem) idemKey.current = d.idem;
      }
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    if (result) return;
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ description, category, landmark, address, occurred, details, title, loc, severity, safety, exposure, idem: idemKey.current }));
  }, [description, category, landmark, address, occurred, details, title, loc, severity, safety, exposure, result]);

  const descLen = description.trim().length;
  const descError = descLen > 3000 ? t("Your description exceeds the 3000-character limit.") : descLen > 0 && descLen < 10 ? t("Please provide a more detailed description of the issue.") : "";
  const readyMedia = uploads.filter((u) => u.mediaId);
  const uploading = uploads.some((u) => !u.mediaId && !u.error);
  const canStep1 = !descError && (descLen >= 10 || readyMedia.length > 0) && !uploading;
  const imageCount = uploads.filter((u) => u.type === "IMAGE" && !u.error).length;

  async function startUpload(u: Upload) {
    setUploads((prev) => prev.map((x) => (x.localId === u.localId ? { ...x, error: undefined, progress: 0 } : x)));
    try {
      const r = await uploadWithProgress<{ media_id: string }>("/api/media/upload", u.file, (p) =>
        setUploads((prev) => prev.map((x) => (x.localId === u.localId ? { ...x, progress: p } : x))));
      setUploads((prev) => prev.map((x) => (x.localId === u.localId ? { ...x, mediaId: r.media_id, progress: 100 } : x)));
    } catch (e) {
      setUploads((prev) => prev.map((x) => (x.localId === u.localId ? { ...x, error: (e as Error).message } : x)));
    }
  }

  function addFiles(files: FileList | File[]) {
    const list = Array.from(files).map((file) => ({
      localId: newIdempotencyKey(), file, progress: 0, type: kindOf(file),
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
    }));
    const valid: Upload[] = [];
    for (const u of list) {
      const counts = { IMAGE: 5, AUDIO: 1, VIDEO: 1 } as Record<string, number>;
      const existing = [...uploads, ...valid].filter((x) => x.type === u.type && !x.error).length;
      if (u.type === "OTHER") valid.push({ ...u, error: t("This file format is not supported. Please upload a supported image, audio or video file.") });
      else if (existing >= counts[u.type]) valid.push({ ...u, error: u.type === "IMAGE" ? t("You can upload a maximum of 5 images per complaint.") : t("Only one audio and one video file per complaint.") });
      else valid.push(u);
    }
    setUploads((prev) => [...prev, ...valid]);
    valid.filter((u) => !u.error).forEach(startUpload);
  }

  async function transcribe(u: Upload) {
    if (!u.mediaId) return;
    setTranscribing(u.localId); setTranscribeMsg("");
    try {
      const r = await api<{ transcription: string }>("/api/complaints/transcribe", { body: { media_id: u.mediaId } });
      if (r.transcription?.trim()) setDescription((d) => (d.trim() ? `${d.trim()}\n${r.transcription.trim()}` : r.transcription.trim()));
      setTranscribeMsg(t("Transcription added to the description. Please check and correct it."));
    } catch (e) {
      const code = (e as ApiError).code;
      setTranscribeMsg(code === "AI_NOT_CONFIGURED" || code === "AI_NOT_IMPLEMENTED"
        ? t("Automatic transcription is not configured. Your voice note is still attached for the department.")
        : t("We could not transcribe the audio. Please retry or provide a written description."));
    } finally {
      setTranscribing(null);
    }
  }

  // Fill the address from the map point when the citizen has not typed one.
  async function fillAddress(lat: number, lng: number) {
    if (address.trim()) return;
    const name = await reverseGeocode(lat, lng, lang);
    if (name) setAddress((a) => a.trim() ? a : name.slice(0, 300));
  }

  function useGps() {
    setGpsError("");
    if (!navigator.geolocation) { setGpsError(t("We could not access your location. Please select the issue location on the map.")); return; }
    setGpsBusy(true);
    navigator.geolocation.getCurrentPosition(
      (p) => { setLoc({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: Math.round(p.coords.accuracy), source: "GPS" }); setGpsBusy(false); fillAddress(p.coords.latitude, p.coords.longitude); },
      () => { setGpsError(t("We could not access your location. Please select the issue location on the map.")); setGpsBusy(false); },
      { enableHighAccuracy: true, timeout: 15000 },
    );
  }

  async function runAnalysis() {
    setAnalyzing(true); setAiError(null); setAnalysis(null);
    try {
      const r = await api("/api/complaints/analyze", {
        body: {
          description: description.trim() || null, media_ids: readyMedia.map((u) => u.mediaId), category: category || null, language_hint: lang,
          location: loc ? { latitude: loc.lat, longitude: loc.lng, accuracy_meters: loc.accuracy, landmark: landmark || null, address_text: address || null, location_source: loc.source } : null,
        },
      });
      setAnalysis(r);
    } catch (e) {
      setAiError(e as ApiError);
    } finally {
      setAnalyzing(false);
    }
  }

  useEffect(() => {
    if (step !== 4) return;
    if (!confirmedDesc) setConfirmedDesc(description.trim());
    if (loc) api(`/api/complaints/nearby?latitude=${loc.lat}&longitude=${loc.lng}${category ? `&category=${category}` : ""}`).then(setNearby).catch(() => setNearby(null));
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps

  async function submit() {
    setSubmitting(true); setSubmitError(null);
    try {
      const r = await api("/api/complaints", {
        headers: { "Idempotency-Key": idemKey.current },
        body: {
          title: title.trim(), original_description: description.trim() || null, description: confirmedDesc.trim(), category,
          location: { latitude: loc!.lat, longitude: loc!.lng, accuracy_meters: loc!.accuracy, landmark: landmark || null, address_text: address || null, location_source: loc!.source },
          occurred_at: occurred ? new Date(occurred).toISOString() : null, additional_details: details || null,
          media_ids: readyMedia.map((u) => u.mediaId), analysis_id: analysis?.analysis_id || null,
          observed_severity: severity || null, safety_risk: safety || null, public_exposure: exposure || null,
          allow_public_display: allowPublic, confirmed: confirm,
        },
      });
      setResult(r);
      localStorage.removeItem(DRAFT_KEY);
    } catch (e) {
      setSubmitError(e);
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit = title.trim().length >= 5 && !!category && confirmedDesc.trim().length >= 10 && confirmedDesc.trim().length <= 3000 && !!loc && confirm;
  const stepNames = [t("Describe"), t("Location"), t("Details"), t("Review & confirm")];
  const todayMax = useMemo(() => new Date().toISOString().slice(0, 10), []);

  if (!allowed) return <Spinner />;

  if (result) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <Card>
          <div className="flex items-start gap-3">
            <CheckCircle2 className="h-8 w-8 text-green-600" aria-hidden />
            <div className="space-y-2">
              <h1 className="text-xl font-semibold text-navy-900">{t("Complaint submitted")}</h1>
              <p className="text-sm text-slate-700">{t("Your CivicConnect reference ID is")}</p>
              <p className="font-mono text-2xl font-semibold text-navy-800">{result.reference_id}</p>
              <p className="text-xs text-slate-500">{t("This is an internal CivicConnect reference, not a government complaint number.")}</p>
              <div className="flex flex-wrap gap-2 pt-2 text-sm">
                <Badge className="bg-slate-100 ring-slate-300">{t("Status: Submitted")}</Badge>
                <Badge className="bg-slate-100 ring-slate-300">{result.department ? `${t("Routed to")} ${result.department.name}` : result.routing_status === "PENDING_REVIEW" ? t("Routing: administrative review") : t("Routing: no eligible department configured")}</Badge>
                <Badge className="bg-slate-100 ring-slate-300">{t("Priority")}: {result.priority_level ?? result.priority_assessment_status.toLowerCase()}</Badge>
              </div>
              <p className="text-sm text-slate-600">{result.routing_message}</p>
              <div className="flex gap-3 pt-3">
                <Link href={`/complaints/${result.complaint_id}`} className="font-medium text-navy-700 underline">{t("Track this complaint")}</Link>
                <Link href="/dashboard" className="text-slate-600 underline">{t("Back to dashboard")}</Link>
              </div>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title={t("Report a civic issue")} subtitle={t("Nothing is submitted until you review and confirm on the last step.")} />
      <ol className="flex flex-wrap gap-2 text-sm" aria-label={t("Progress")}>
        {stepNames.map((n, i) => (
          <li key={n} aria-current={step === i + 1 ? "step" : undefined}
            className={cx("rounded px-3 py-1", step === i + 1 ? "bg-navy-700 text-white" : step > i + 1 ? "bg-navy-100 text-navy-800" : "bg-slate-200 text-slate-600")}>
            {i + 1}. {n}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <Card title={t("What is the problem?")}>
          <div className="space-y-5">
            <p className="flex items-center gap-2 rounded-md bg-navy-50 px-3 py-2 text-xs text-navy-900">
              <Languages className="h-4 w-4 shrink-0" aria-hidden />
              {t("You can write or speak in English, Hindi, Kannada or any language you are comfortable with.")}
            </p>
            <Field label={t("Description")} htmlFor="desc" error={descError || undefined}
              hint={t("Describe what you see, how it affects people, and where exactly it is (nearby shop, junction, landmark).")}>
              <textarea id="desc" rows={6} maxLength={3500} className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} />
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
                <DictateButton onText={(txt) => setDescription((d) => (d.trim() ? `${d.trim()} ${txt}` : txt))} />
                <div className={cx("ml-auto text-xs", descLen > 3000 ? "text-red-700" : "text-slate-500")}>{descLen} / 3000</div>
              </div>
            </Field>
            <Field label={t("Category (if you know it)")} htmlFor="cat">
              <select id="cat" className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">{t("Not sure yet")}</option>
                {CATEGORIES.map((c) => <option key={c} value={c}>{t(CATEGORY_LABEL[c])}</option>)}
              </select>
            </Field>
            <div>
              <span className="block text-sm font-medium text-slate-800">{t("Photos, voice note or video (optional)")}</span>
              <div
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files); }}
                className="mt-1 flex flex-col items-center rounded-md border-2 border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
                <FileUp className="h-6 w-6 text-slate-400" aria-hidden />
                <p className="mt-2">{t("Drag files here or")} <button type="button" className="font-medium text-navy-700 underline" onClick={() => fileInput.current?.click()}>{t("choose files")}</button></p>
                <p className="mt-1 text-xs">{t("Up to 5 images (JPEG/PNG/WEBP, 10 MB each) · 1 audio (MP3/WAV/M4A, 15 MB, 2 min) · 1 video (MP4, 50 MB, 1 min)")}</p>
                <div className="mt-3"><VoiceRecorder onRecorded={(f) => addFiles([f])} disabled={uploads.some((u) => u.type === "AUDIO" && !u.error)} /></div>
                <input ref={fileInput} type="file" multiple accept={ACCEPT} className="sr-only" onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
              </div>
              <p className="mt-1 text-xs text-slate-500">{imageCount}/5 {t("images")}</p>
              {transcribeMsg && <p className="mt-1 text-xs text-navy-800" aria-live="polite">{transcribeMsg}</p>}
              {uploads.length > 0 && (
                <ul className="mt-3 space-y-2">
                  {uploads.map((u) => (
                    <li key={u.localId} className="flex items-center gap-3 rounded border border-slate-200 bg-white p-2 text-sm">
                      {u.preview ? <img src={u.preview} alt="" className="h-12 w-12 rounded object-cover" /> : <div className="grid h-12 w-12 place-items-center rounded bg-slate-100 text-xs">{u.type}</div>}
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-medium">{u.file.name}</div>
                        <div className="text-xs text-slate-500">{fmtBytes(u.file.size)}</div>
                        {u.error ? <div className="text-xs text-red-700">{u.error}</div> : !u.mediaId ? (
                          <div className="mt-1 h-1.5 w-full rounded bg-slate-200"><div className="h-1.5 rounded bg-navy-600" style={{ width: `${u.progress}%` }} /></div>
                        ) : <div className="text-xs text-green-700">{t("Uploaded and validated")}</div>}
                      </div>
                      {u.type === "AUDIO" && u.mediaId && (
                        <Button variant="secondary" onClick={() => transcribe(u)} loading={transcribing === u.localId}>{t("Convert speech to text")}</Button>
                      )}
                      {u.error && u.type !== "OTHER" && <Button variant="ghost" onClick={() => startUpload(u)} aria-label={t("Retry upload")}><RotateCw className="h-4 w-4" /></Button>}
                      <Button variant="ghost" onClick={() => setUploads((p) => p.filter((x) => x.localId !== u.localId))} aria-label={`${t("Remove")} ${u.file.name}`}><Trash2 className="h-4 w-4" /></Button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {!canStep1 && descLen === 0 && readyMedia.length === 0 && <p className="text-xs text-slate-500">{t("Please provide a complaint description or supported media before continuing.")}</p>}
            <div className="flex justify-end"><Button disabled={!canStep1} onClick={() => setStep(2)}>{t("Continue")}</Button></div>
          </div>
        </Card>
      )}

      {step === 2 && (
        <Card title={t("Where is it?")}>
          <div className="space-y-4">
            <AddressSearch onPick={(p) => { setLoc({ lat: p.latitude, lng: p.longitude, accuracy: null, source: "MAP_SELECTION" }); setAddress(p.display_name.slice(0, 300)); }} />
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="secondary" onClick={useGps} loading={gpsBusy}><Crosshair className="h-4 w-4" /> {t("Use my current location")}</Button>
              <span className="text-sm text-slate-600">{t("or click the map to place the pin")}</span>
            </div>
            {gpsError && <Notice tone="warn">{gpsError}</Notice>}
            <LocationPicker value={loc ? { lat: loc.lat, lng: loc.lng } : null} onChange={(lat, lng) => { setLoc({ lat, lng, accuracy: null, source: "MAP_SELECTION" }); fillAddress(lat, lng); }} />
            {loc ? (
              <p className="flex items-center gap-2 text-sm text-slate-700">
                <MapPin className="h-4 w-4 text-navy-600" /> {loc.lat.toFixed(6)}, {loc.lng.toFixed(6)}
                <Badge className="bg-slate-100 ring-slate-300">{loc.source === "GPS" ? `GPS · ±${loc.accuracy ?? "?"} m` : t("Selected on map")}</Badge>
              </p>
            ) : <p className="text-sm text-slate-500">{t("No location selected yet. We never guess a location for you.")}</p>}
            <p className="text-xs text-slate-500">{t("Check the pin is on the exact spot. You can click the map to adjust it.")}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("Landmark (optional)")} htmlFor="landmark"><input id="landmark" maxLength={200} className={inputCls} value={landmark} onChange={(e) => setLandmark(e.target.value)} /></Field>
              <Field label={t("Address (optional)")} htmlFor="address"><input id="address" maxLength={300} className={inputCls} value={address} onChange={(e) => setAddress(e.target.value)} /></Field>
            </div>
            <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(1)}>{t("Back")}</Button><Button disabled={!loc} onClick={() => setStep(3)}>{t("Continue")}</Button></div>
          </div>
        </Card>
      )}

      {step === 3 && (
        <Card title={t("A few more details (optional)")}>
          <div className="space-y-4">
            <p className="text-sm text-slate-600">{t("These help the department prioritize. Leave anything you are unsure about blank — we never fill in values for you.")}</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("When did you first notice it?")} htmlFor="occ"><input id="occ" type="date" max={todayMax} className={inputCls} value={occurred} onChange={(e) => setOccurred(e.target.value)} /></Field>
              <Field label={t("How severe is the damage?")} htmlFor="sev">
                <select id="sev" className={inputCls} value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="">{t("Not sure")}</option>{SEVERITY.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select>
              </Field>
              <Field label={t("Is anyone at risk of harm?")} htmlFor="saf" hint={t("If someone is in immediate danger, contact emergency services first.")}>
                <select id="saf" className={inputCls} value={safety} onChange={(e) => setSafety(e.target.value)}><option value="">{t("Not sure")}</option>{SAFETY.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select>
              </Field>
              <Field label={t("Who is affected?")} htmlFor="exp">
                <select id="exp" className={inputCls} value={exposure} onChange={(e) => setExposure(e.target.value)}><option value="">{t("Not sure")}</option>{EXPOSURE.map(([v, l]) => <option key={v} value={v}>{t(l)}</option>)}</select>
              </Field>
            </div>
            {safety === "IMMEDIATE" && <Notice tone="warn">{t("CivicConnect is not an emergency service. If there is an immediate threat to life or safety, contact local emergency services now. Your report will also be flagged for prompt human review.")}</Notice>}
            <Field label={t("Anything else the department should know?")} htmlFor="det">
              <textarea id="det" rows={3} maxLength={2000} className={inputCls} value={details} onChange={(e) => setDetails(e.target.value)} />
            </Field>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" className="mt-1" checked={allowPublic} onChange={(e) => setAllowPublic(e.target.checked)} />
              {t("Allow a privacy-reviewed summary and approximate location to appear on the public issues map (your name, contact details and photos are never shown).")}
            </label>
            <div className="flex justify-between"><Button variant="secondary" onClick={() => setStep(2)}>{t("Back")}</Button><Button onClick={() => setStep(4)}>{t("Continue to review")}</Button></div>
          </div>
        </Card>
      )}

      {step === 4 && (
        <div className="space-y-4">
          <Card title={<span className="flex items-center gap-2"><Bot className="h-4 w-4" /> {t("AI analysis (optional)")}</span>}>
            {!analysis && !aiError && (
              <div className="space-y-2 text-sm text-slate-700">
                <p>{t("AI can suggest a title, category and summary from your description, photos, video and voice note. You can skip this and fill in the details yourself.")}</p>
                <Button variant="secondary" onClick={runAnalysis} loading={analyzing}><Sparkles className="h-4 w-4" /> {analyzing ? t("Analyzing your report…") : t("Analyze my report")}</Button>
              </div>
            )}
            {aiError && (
              <div className="space-y-2">
                <Notice tone="warn">
                  <strong>{aiError.code === "AI_NOT_CONFIGURED" || aiError.code === "AI_NOT_IMPLEMENTED" ? t("AI analysis is not configured on this deployment.") : t("AI analysis is unavailable right now.")}</strong>{" "}
                  {aiError.message} {t("No AI suggestions were generated.")}
                </Notice>
                {!["AI_NOT_CONFIGURED", "AI_NOT_IMPLEMENTED"].includes(aiError.code) && <Button variant="secondary" onClick={runAnalysis} loading={analyzing}>{t("Retry analysis")}</Button>}
              </div>
            )}
            {analysis && <AnalysisPreview a={analysis} onUse={(t, c, s) => { setTitle(t); setCategory(c); if (s) setConfirmedDesc(s); }} />}
          </Card>

          {nearby?.items?.length > 0 && (
            <Card title={t("Potentially related public reports nearby")}>
              <p className="mb-3 text-sm text-slate-700">{nearby.message} {t("You can still submit if your issue is separate — your report is always kept as its own record.")}</p>
              <ul className="space-y-2 text-sm">{nearby.items.map((n: any) => (
                <li key={n.public_reference} className="rounded border border-slate-200 p-2"><span className="font-mono text-xs">{n.public_reference}</span> · {CATEGORY_LABEL[n.category]} · {n.public_status}<div className="text-slate-600">{n.public_summary}</div></li>
              ))}</ul>
            </Card>
          )}

          <Card title={t("Review and confirm")}>
            <div className="space-y-4">
              <Field label={t("Title")} htmlFor="title" required hint={t("A short name for the issue, e.g. “Deep pothole outside Ward 4 school gate”.")}>
                <input id="title" maxLength={150} className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />
              </Field>
              <Field label={t("Category")} htmlFor="cat2" required>
                <select id="cat2" className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="">{t("Choose a category")}</option>
                  {CATEGORIES.map((c) => <option key={c} value={c}>{t(CATEGORY_LABEL[c])}</option>)}
                </select>
              </Field>
              <Field label={t("Description to submit")} htmlFor="cdesc" required hint={t("Your original text is kept unchanged as well. Edit this version if needed.")}>
                <textarea id="cdesc" rows={5} maxLength={3000} className={inputCls} value={confirmedDesc} onChange={(e) => setConfirmedDesc(e.target.value)} />
              </Field>
              <dl className="grid gap-2 rounded-md bg-slate-50 p-3 text-sm sm:grid-cols-2">
                <div><dt className="text-xs text-slate-500">{t("Location")}</dt><dd>{loc ? `${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)} (${loc.source === "GPS" ? "GPS" : t("map")})` : "—"}</dd></div>
                <div><dt className="text-xs text-slate-500">{t("Landmark / address")}</dt><dd>{[landmark, address].filter(Boolean).join(" · ") || "—"}</dd></div>
                <div><dt className="text-xs text-slate-500">{t("Media")}</dt><dd>{readyMedia.length} {t("file(s)")}</dd></div>
                <div><dt className="text-xs text-slate-500">{t("First noticed")}</dt><dd>{occurred || t("Unknown")}</dd></div>
              </dl>
              <label className="flex items-start gap-2 text-sm text-slate-800">
                <input type="checkbox" className="mt-1" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
                {t("I have reviewed these details and confirm they are accurate to the best of my knowledge.")}
              </label>
              <ErrorBox error={submitError} />
              {(submitError as ApiError)?.code === "NETWORK_ERROR" && <p className="text-xs text-slate-600">{t("If your connection dropped after submitting, retrying is safe: the same submission will not be created twice.")}</p>}
              <div className="flex justify-between">
                <Button variant="secondary" onClick={() => setStep(3)}>{t("Back")}</Button>
                <Button onClick={submit} disabled={!canSubmit} loading={submitting}>{submitting ? t("Submitting…") : t("Submit complaint")}</Button>
              </div>
              {!canSubmit && <p className="text-right text-xs text-slate-500">{t("Title (5+ chars), category, description (10+ chars), location and confirmation are required.")}</p>}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function AnalysisPreview({ a, onUse }: { a: any; onUse: (title: string, category: string, summary?: string) => void }) {
  const { t } = useI18n();
  const band = a.confidence_band as string;
  return (
    <div className="space-y-3 text-sm">
      <Notice tone="info">{t("These are AI suggestions, not decisions. Please verify everything before using it.")}</Notice>
      {a.requires_human_review && (
        <Notice tone="warn"><strong>{t("Review recommended.")}</strong> {a.review_reasons?.join(" ")}</Notice>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <div><span className="text-xs text-slate-500">{t("Suggested title")}</span><p className="font-medium">{a.suggested_title}</p></div>
        <div><span className="text-xs text-slate-500">{t("Suggested category")}</span><p className="font-medium">{t(CATEGORY_LABEL[a.suggested_category])}</p></div>
      </div>
      <div><span className="text-xs text-slate-500">{t("Summary")}</span><p>{a.suggested_summary}</p></div>
      {a.media_analysis?.length > 0 && <div><span className="text-xs text-slate-500">{t("What the AI saw in your media")}</span><ul className="list-disc pl-5">{a.media_analysis.map((m: any) => <li key={m.media_id}><span className="text-xs font-medium">{m.media_type === "VIDEO" ? t("Video") : m.media_type === "AUDIO" ? t("Voice note") : t("Photo")}:</span> {m.extracted_description}</li>)}</ul></div>}
      {a.visible_evidence?.length > 0 && <div><span className="text-xs text-slate-500">{t("Visible evidence")}</span><ul className="list-disc pl-5">{a.visible_evidence.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
      {a.potential_safety_concerns?.length > 0 && <div><span className="text-xs text-slate-500">{t("Potential safety concerns")}</span><ul className="list-disc pl-5 text-amber-800">{a.potential_safety_concerns.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
      {a.transcription && <div><span className="text-xs text-slate-500">{t("Audio transcription")}</span><p className="italic">{a.transcription}</p></div>}
      {a.missing_information?.length > 0 && <div><span className="text-xs text-slate-500">{t("Missing information")}</span><ul className="list-disc pl-5">{a.missing_information.map((x: string) => <li key={x}>{x}</li>)}</ul></div>}
      <p className="text-xs text-slate-600">
        {t("Confidence")}: <strong>{band}</strong>{a.classification_confidence != null ? ` (${a.classification_confidence})` : ""} — {a.confidence_method}
      </p>
      <Button variant="secondary" onClick={() => onUse(a.suggested_title, a.suggested_category, a.suggested_summary)}>{t("Use suggested title, category and English summary (you can still edit)")}</Button>
    </div>
  );
}
