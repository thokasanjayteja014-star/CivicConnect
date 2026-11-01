"use client";

import { BellRing, Mail, MessageSquare, Send } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/services/api";
import type { Me } from "@/types";
import { useAuth } from "./AuthProvider";
import { useI18n } from "./I18nProvider";
import { Button, Card, ErrorBox, Notice, inputCls } from "./ui";

type Channels = { in_app: boolean; email: boolean; sms: boolean; push: boolean; vapid_public_key: string | null };

function urlBase64ToUint8Array(b64: string) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export function NotificationSettings() {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  const [channels, setChannels] = useState<Channels | null>(null);
  const [phone, setPhone] = useState(user?.phone || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [msg, setMsg] = useState("");
  const [pushState, setPushState] = useState<"unsupported" | "denied" | "on" | "off">("off");

  useEffect(() => {
    api<Channels>("/api/notifications/channels").then(setChannels).catch(() => setChannels(null));
    if (typeof window === "undefined" || !("serviceWorker" in navigator) || !("PushManager" in window)) { setPushState("unsupported"); return; }
    if (Notification.permission === "denied") { setPushState("denied"); return; }
    navigator.serviceWorker.getRegistration("/sw.js").then(async (reg) => {
      const sub = await reg?.pushManager.getSubscription();
      setPushState(sub ? "on" : "off");
    });
  }, []);

  if (!user) return null;

  async function save(body: Partial<Me> & { phone?: string }) {
    setSaving(true); setError(null); setMsg("");
    try {
      await api("/api/auth/me/preferences", { method: "PATCH", body });
      await refresh();
      setMsg(t("Saved."));
    } catch (e) {
      setError(e);
    } finally {
      setSaving(false);
    }
  }

  async function enablePush() {
    setError(null); setMsg("");
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setPushState(perm === "denied" ? "denied" : "off"); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(channels!.vapid_public_key!) });
      const json = sub.toJSON() as any;
      await api("/api/notifications/push-subscriptions", { body: { endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth } });
      if (!user!.notify_push) await save({ notify_push: true });
      setPushState("on");
      setMsg(t("Browser notifications are on for this device."));
    } catch (e) {
      setError(e);
    }
  }

  async function disablePush() {
    const reg = await navigator.serviceWorker.getRegistration("/sw.js");
    const sub = await reg?.pushManager.getSubscription();
    if (sub) {
      await api(`/api/notifications/push-subscriptions?endpoint=${encodeURIComponent(sub.endpoint)}`, { method: "DELETE" }).catch(() => undefined);
      await sub.unsubscribe();
    }
    setPushState("off");
  }

  const row = "flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 py-3 first:border-t-0";
  const notSetUp = <span className="text-xs text-slate-500">{t("Not set up on this server yet")}</span>;

  return (
    <Card title={t("How should we notify you?")}>
      <p className="mb-2 text-sm text-slate-600">{t("You always get updates here in the app. You can also get them by email, SMS or browser notification.")}</p>
      <ErrorBox error={error} />
      {msg && <Notice tone="success">{msg}</Notice>}
      <div className="text-sm">
        <div className={row}>
          <span className="flex items-center gap-2"><Mail className="h-4 w-4 text-navy-700" /> {t("Email")} <span className="text-xs text-slate-500">({user.email})</span></span>
          {channels?.email ? (
            <label className="flex items-center gap-2"><input type="checkbox" checked={user.notify_email} disabled={saving}
              onChange={(e) => save({ notify_email: e.target.checked })} /> {t("Send me emails")}</label>
          ) : notSetUp}
        </div>
        <div className={row}>
          <span className="flex items-center gap-2"><MessageSquare className="h-4 w-4 text-navy-700" /> {t("SMS")}</span>
          {channels?.sms ? (
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="sms-phone" className="sr-only">{t("Mobile number")}</label>
              <input id="sms-phone" className={inputCls + " w-44"} placeholder="+919876543210" value={phone} onChange={(e) => setPhone(e.target.value.trim())} />
              <label className="flex items-center gap-2"><input type="checkbox" checked={user.notify_sms} disabled={saving}
                onChange={(e) => save({ notify_sms: e.target.checked, phone })} /> {t("Send me SMS")}</label>
            </div>
          ) : notSetUp}
        </div>
        <div className={row}>
          <span className="flex items-center gap-2"><BellRing className="h-4 w-4 text-navy-700" /> {t("Browser notifications")}</span>
          {!channels?.push ? notSetUp : pushState === "unsupported" ? <span className="text-xs text-slate-500">{t("This browser does not support notifications.")}</span>
            : pushState === "denied" ? <span className="text-xs text-amber-700">{t("Blocked in your browser settings. Allow notifications for this site to turn them on.")}</span>
            : pushState === "on" ? <Button variant="secondary" onClick={disablePush}>{t("Turn off on this device")}</Button>
            : <Button variant="secondary" onClick={enablePush}>{t("Turn on for this device")}</Button>}
        </div>
      </div>
      <div className="mt-3 border-t border-slate-100 pt-3">
        <Button variant="secondary" onClick={async () => { await api("/api/notifications/test", { method: "POST" }); setMsg(t("Test notification sent. Check your email, phone or browser.")); }}>
          <Send className="h-4 w-4" /> {t("Send me a test notification")}
        </Button>
      </div>
    </Card>
  );
}
