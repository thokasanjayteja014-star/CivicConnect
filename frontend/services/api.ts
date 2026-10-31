// Thin client for the CivicConnect backend. No secrets live in the frontend:
// the only credential is the user's own short-lived session token.

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "cc_session";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  requestId?: string;
  constructor(status: number, code: string, message: string, details?: unknown, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

type Session = { token: string; expiresAt: string };

export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const s = JSON.parse(raw) as Session;
    if (new Date(s.expiresAt).getTime() <= Date.now()) {
      window.localStorage.removeItem(TOKEN_KEY);
      return null;
    }
    return s;
  } catch {
    return null;
  }
}

export function setSession(token: string, expiresAt: string) {
  window.localStorage.setItem(TOKEN_KEY, JSON.stringify({ token, expiresAt }));
}

export function clearSession() {
  if (typeof window !== "undefined") window.localStorage.removeItem(TOKEN_KEY);
}

type Opts = { method?: string; body?: unknown; form?: FormData; headers?: Record<string, string>; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  const s = getSession();
  if (s) headers["Authorization"] = `Bearer ${s.token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "NETWORK_ERROR", "Your connection was interrupted. Please check your internet connection and retry.");
  }
  if (res.status === 204) return undefined as T;
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    /* non-JSON */
  }
  if (!res.ok) {
    if (res.status === 401) {
      clearSession();
      if (typeof window !== "undefined") window.dispatchEvent(new Event("cc:unauthenticated"));
    }
    throw new ApiError(res.status, data?.error_code || "ERROR", data?.message || "Something went wrong. Please try again.",
      data?.details, data?.request_id);
  }
  return data as T;
}

/** Upload with progress (XHR, since fetch has no upload progress). */
export function uploadWithProgress<T = any>(path: string, file: File, onProgress: (pct: number) => void, extra?: Record<string, string>): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`);
    const s = getSession();
    if (s) xhr.setRequestHeader("Authorization", `Bearer ${s.token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      let data: any = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else reject(new ApiError(xhr.status, data?.error_code || "ERROR", data?.message || "Upload failed.", data?.details, data?.request_id));
    };
    xhr.onerror = () => reject(new ApiError(0, "NETWORK_ERROR", "Your connection was interrupted. Please retry the upload."));
    const fd = new FormData();
    fd.append("file", file);
    Object.entries(extra || {}).forEach(([k, v]) => fd.append(k, v));
    xhr.send(fd);
  });
}

export async function mediaUrl(mediaId: string): Promise<string> {
  const r = await api<{ url: string }>(`/api/media/${mediaId}/link`);
  return r.url;
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
