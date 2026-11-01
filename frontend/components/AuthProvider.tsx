"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api, clearSession, getEnv, getSession, setEnv, setSession, type AppEnv } from "@/services/api";
import type { Me, Role } from "@/types";

type AuthCtx = {
  user: Me | null;
  ready: boolean;
  env: AppEnv;
  /** Enter the isolated demo environment signed in as the sample user of a role. */
  demoLogin: (role: Role) => Promise<Me>;
  /** Leave the demo environment (production session, if any, is untouched). */
  exitDemo: () => Promise<void>;
  login: (email: string, password: string) => Promise<Me>;
  register: (full_name: string, email: string, password: string, phone?: string) => Promise<Me>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export function homeFor(role: Role): string {
  if (role === "CITIZEN") return "/dashboard";
  if (role === "SYSTEM_ADMIN") return "/admin";
  return "/authority";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [env, setEnvState] = useState<AppEnv>("production");

  const refresh = useCallback(async () => {
    if (!getSession()) {
      setUser(null);
      setReady(true);
      return;
    }
    try {
      setUser(await api<Me>("/api/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    setEnvState(getEnv());
    refresh();
    const onUnauth = () => setUser(null);
    const onEnv = () => { setEnvState(getEnv()); refresh(); };
    window.addEventListener("cc:unauthenticated", onUnauth);
    window.addEventListener("cc:env", onEnv);
    return () => { window.removeEventListener("cc:unauthenticated", onUnauth); window.removeEventListener("cc:env", onEnv); };
  }, [refresh]);

  const demoLogin = async (role: Role) => {
    if (getEnv() !== "demo") setEnv("demo");
    const r = await api<{ access_token: string; expires_at: string }>("/api/demo/login", { body: { role } });
    setSession(r.access_token, r.expires_at);
    const me = await api<Me>("/api/auth/me");
    setEnvState("demo");
    setUser(me);
    return me;
  };

  const exitDemo = async () => {
    if (getEnv() === "demo") {
      try { await api("/api/auth/logout", { method: "POST" }); } catch { /* ignore */ }
      clearSession();
      setEnv("production");
    }
  };

  const login = async (email: string, password: string) => {
    const r = await api<{ access_token: string; expires_at: string; user: Me }>("/api/auth/login", { body: { email, password } });
    setSession(r.access_token, r.expires_at);
    setUser(r.user);
    return r.user;
  };

  const register = async (full_name: string, email: string, password: string, phone?: string) => {
    const r = await api<{ access_token: string; expires_at: string; user: Me }>("/api/auth/register", {
      body: { full_name, email, password, phone: phone || null },
    });
    setSession(r.access_token, r.expires_at);
    setUser(r.user);
    return r.user;
  };

  const logout = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      /* session may already be expired */
    }
    clearSession();
    setUser(null);
  };

  return <Ctx.Provider value={{ user, ready, env, demoLogin, exitDemo, login, register, logout, refresh }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

/** Client-side guard for UX only; every protected operation is enforced by the backend. */
export function useRequireRole(roles: Role[]) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const allowed = !!user && roles.includes(user.role);
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
    else if (!roles.includes(user.role)) router.replace(homeFor(user.role));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user]);
  return { user, ready, allowed };
}
