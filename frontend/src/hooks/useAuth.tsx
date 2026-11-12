import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "../services/api";
import type { User } from "../types";

interface AuthState {
  user: User | null;
  loading: boolean;
  needsSetup: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  setup: (email: string, name: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(signOut);
    (async () => {
      try {
        const status = await api.get<{ needs_setup: boolean }>("/api/auth/status");
        setNeedsSetup(status.needs_setup);
        if (tokenStore.get()) setUser(await api.get<User>("/api/auth/me"));
      } catch {
        tokenStore.clear();
      } finally {
        setLoading(false);
      }
    })();
  }, [signOut]);

  const finish = (res: { token: string; user: User }) => {
    tokenStore.set(res.token);
    setUser(res.user);
    setNeedsSetup(false);
  };
  const signIn = async (email: string, password: string) =>
    finish(await api.post("/api/auth/login", { email, password }));
  const setup = async (email: string, name: string, password: string) =>
    finish(await api.post("/api/auth/setup", { email, name, password }));

  return (
    <AuthContext.Provider value={{ user, loading, needsSetup, signIn, setup, signOut }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
