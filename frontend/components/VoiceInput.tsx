"use client";

import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { SPEECH_LOCALE, useI18n } from "./I18nProvider";
import { Button } from "./ui";

/** Live dictation with the browser's speech recognition (Chrome/Edge; free, no server).
 *  Appends the recognised text in the selected language. Hidden when unsupported. */
export function DictateButton({ onText }: { onText: (text: string) => void }) {
  const { lang, t } = useI18n();
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState("");
  const rec = useRef<any>(null);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));
    return () => rec.current?.abort?.();
  }, []);

  function start() {
    setError("");
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const r = new SR();
    r.lang = SPEECH_LOCALE[lang];
    r.continuous = true;
    r.interimResults = false;
    r.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) onText(e.results[i][0].transcript.trim());
      }
    };
    r.onerror = (e: any) => {
      setError(e.error === "not-allowed" ? t("Microphone permission was denied.") : t("Voice typing stopped. Please try again."));
      setListening(false);
    };
    r.onend = () => setListening(false);
    rec.current = r;
    r.start();
    setListening(true);
  }

  if (!supported) return null;
  return (
    <span className="inline-flex items-center gap-2">
      {listening ? (
        <Button type="button" variant="secondary" onClick={() => rec.current?.stop()}>
          <Square className="h-4 w-4 text-red-600" /> {t("Stop voice typing")}
        </Button>
      ) : (
        <Button type="button" variant="secondary" onClick={start}><Mic className="h-4 w-4" /> {t("Speak instead of typing")}</Button>
      )}
      {listening && <span className="text-xs text-red-700" aria-live="polite">{t("Listening…")}</span>}
      {error && <span className="text-xs text-red-700">{error}</span>}
    </span>
  );
}

/** Record a voice note as 16 kHz mono WAV (supported by the backend validator and speech models). */
export function VoiceRecorder({ onRecorded, maxSeconds = 120, disabled }: { onRecorded: (file: File) => void; maxSeconds?: number; disabled?: boolean }) {
  const { t } = useI18n();
  const [recording, setRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const state = useRef<{ ctx?: AudioContext; stream?: MediaStream; node?: ScriptProcessorNode; chunks: Float32Array[]; timer?: any; rate: number }>({ chunks: [], rate: 48000 });

  useEffect(() => () => stop(true), []); // eslint-disable-line react-hooks/exhaustive-deps

  async function start() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      const ctx = new AudioContext();
      const src = ctx.createMediaStreamSource(stream);
      const node = ctx.createScriptProcessor(4096, 1, 1);
      state.current = { ctx, stream, node, chunks: [], rate: ctx.sampleRate };
      node.onaudioprocess = (e) => state.current.chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
      src.connect(node);
      node.connect(ctx.destination);
      setSeconds(0);
      setRecording(true);
      const began = Date.now();
      state.current.timer = setInterval(() => {
        const s = Math.floor((Date.now() - began) / 1000);
        setSeconds(s);
        if (s >= maxSeconds) stop();
      }, 250);
    } catch {
      setError(t("Microphone permission was denied."));
    }
  }

  function stop(discard = false) {
    const st = state.current;
    clearInterval(st.timer);
    st.node?.disconnect();
    st.stream?.getTracks().forEach((tr) => tr.stop());
    st.ctx?.close().catch(() => undefined);
    setRecording(false);
    if (discard || !st.chunks.length) return;
    const wav = encodeWav(st.chunks, st.rate, 16000);
    st.chunks = [];
    onRecorded(new File([wav], `voice-note-${Date.now()}.wav`, { type: "audio/wav" }));
  }

  return (
    <span className="inline-flex items-center gap-2">
      {recording ? (
        <Button type="button" variant="secondary" onClick={() => stop()}>
          <Square className="h-4 w-4 text-red-600" /> {t("Stop recording")} ({seconds}s / {maxSeconds}s)
        </Button>
      ) : (
        <Button type="button" variant="secondary" onClick={start} disabled={disabled}><Mic className="h-4 w-4" /> {t("Record a voice note")}</Button>
      )}
      {error && <span className="text-xs text-red-700">{error}</span>}
    </span>
  );
}

function encodeWav(chunks: Float32Array[], inRate: number, outRate: number): Blob {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const input = new Float32Array(total);
  let o = 0;
  for (const c of chunks) { input.set(c, o); o += c.length; }
  const ratio = inRate / outRate;
  const outLen = Math.floor(total / ratio);
  const buf = new ArrayBuffer(44 + outLen * 2);
  const v = new DataView(buf);
  const w = (p: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(p + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + outLen * 2, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, outRate, true); v.setUint32(28, outRate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, outLen * 2, true);
  for (let i = 0; i < outLen; i++) {
    // simple averaging downsample
    const start = Math.floor(i * ratio), end = Math.min(total, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let k = start; k < end; k++) sum += input[k];
    const s = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}
