import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  fetchCurrentSession,
  loginWithLocalAccount,
  logoutCurrentSession,
  type AuthenticatedUser,
  type LoginRequest,
} from '../api/authSession';

type AuthSessionStatus = 'loading' | 'authenticated' | 'anonymous';

type AuthSessionContextValue = {
  status: AuthSessionStatus;
  user: AuthenticatedUser | null;
  refreshSession: () => Promise<void>;
  login: (payload: LoginRequest) => Promise<AuthenticatedUser>;
  logout: () => Promise<void>;
};

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

type AuthSessionProviderProps = {
  children: ReactNode;
};

export function AuthSessionProvider({ children }: AuthSessionProviderProps) {
  const [status, setStatus] = useState<AuthSessionStatus>('loading');
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  const refreshSession = useCallback(async () => {
    try {
      const session = await fetchCurrentSession();
      setUser(session.user);
      setStatus('authenticated');
    } catch {
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(async (payload: LoginRequest) => {
    const session = await loginWithLocalAccount(payload);
    setUser(session.user);
    setStatus('authenticated');
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    await logoutCurrentSession();
    setUser(null);
    setStatus('anonymous');
  }, []);

  const value = useMemo(
    () => ({ status, user, refreshSession, login, logout }),
    [status, user, refreshSession, login, logout],
  );

  return <AuthSessionContext.Provider value={value}>{children}</AuthSessionContext.Provider>;
}

export function useAuthSession() {
  const context = useContext(AuthSessionContext);
  if (!context) {
    throw new Error('useAuthSession must be used within AuthSessionProvider');
  }
  return context;
}
