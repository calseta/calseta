import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { hasApiKey, setApiKey, clearApiKey } from "./api-client";

interface AuthContextValue {
  isAuthenticated: boolean;
  login: (key: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authed, setAuthed] = useState(hasApiKey);

  const login = useCallback((key: string) => {
    setApiKey(key);
    setAuthed(true);
  }, []);

  const logout = useCallback(() => {
    clearApiKey();
    setAuthed(false);
  }, []);

  const value = useMemo(
    () => ({ isAuthenticated: authed, login, logout }),
    [authed, login, logout],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
