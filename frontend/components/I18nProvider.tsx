"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { DICTIONARIES, LANGUAGES, type Lang } from "@/i18n/dictionaries";

const KEY = "cc_lang";

type I18nCtx = { lang: Lang; setLang: (l: Lang) => void; t: (s: string, vars?: Record<string, string | number>) => string };

const Ctx = createContext<I18nCtx | null>(null);

/** BCP-47 locale for speech recognition and date formatting. */
export const SPEECH_LOCALE: Record<Lang, string> = { en: "en-IN", hi: "hi-IN", kn: "kn-IN", te: "te-IN" };

function interpolate(s: string, vars?: Record<string, string | number>) {
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`)) : s;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY) as Lang | null;
      if (saved && LANGUAGES.some((l) => l.code === saved)) setLangState(saved);
    } catch { /* storage unavailable */ }
  }, []);

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
  }, []);

  // English strings are the keys; a missing translation falls back to English.
  const t = useCallback((s: string, vars?: Record<string, string | number>) => interpolate(DICTIONARIES[lang]?.[s] ?? s, vars), [lang]);

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export function useI18n() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useI18n outside I18nProvider");
  return c;
}

export function useT() {
  return useI18n().t;
}
