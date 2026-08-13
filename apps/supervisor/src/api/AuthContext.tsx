import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "@/api/client";
import type { CurrentUser } from "@/api/types";

interface AuthContextValue {
  user: CurrentUser | null;
  /** true пока проверяем сохранённый токен на старте. */
  loading: boolean;
  /** Вход по коду пропуска или UID именного бейджа. */
  login: (passCode: string) => Promise<CurrentUser>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  // Восстановление сессии: токен есть → спрашиваем /auth/me кто мы.
  useEffect(() => {
    let cancelled = false;
    const token = tokenStore.get();
    if (!token) {
      setLoading(false);
      return;
    }
    api.auth
      .me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        tokenStore.clear();
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  // Протух токен в любом запросе → сбрасываем сессию, роутер уведёт на вход.
  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    return () => setUnauthorizedHandler(null);
  }, []);

  const login = useCallback(async (passCode: string) => {
    const { access_token } = await api.auth.login(passCode);
    tokenStore.set(access_token);
    const me = await api.auth.me();
    setUser(me);
    return me;
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
