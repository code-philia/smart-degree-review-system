import { clearReportTranslations } from '../i18n/reportTranslations';
import { applyDefaultLocale } from '../i18n/locale';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  fetchCurrentSession,
  loginWithLocalAccount,
  loginWithTrialAccount,
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
  loginTrial: (payload: LoginRequest) => Promise<AuthenticatedUser>;
  logout: () => Promise<void>;
};

const AuthSessionContext = createContext<AuthSessionContextValue | null>(null);

type AuthSessionProviderProps = {
  children: ReactNode;
};

export function AuthSessionProvider({ children }: AuthSessionProviderProps) {
  const [status, setStatus] = useState<AuthSessionStatus>('loading');
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const identity = useRef<string|null>(null);
  const updateUser = useCallback((nextUser: AuthenticatedUser|null) => {
    if (identity.current !== (nextUser?.id ?? null)) clearReportTranslations();
    identity.current = nextUser?.id ?? null;
    if (nextUser?.id.startsWith('jaccount:')) applyDefaultLocale(nextUser.defaultLocale);
    setUser(nextUser);
  }, []);

  const refreshSession = useCallback(async () => {
    try {
      const session = await fetchCurrentSession();
      updateUser(session.user);
      setStatus('authenticated');
    } catch {
      clearReportTranslations();
      updateUser(null);
      setStatus('anonymous');
    }
  }, [updateUser]);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  const login = useCallback(async (payload: LoginRequest) => {
    const session = await loginWithLocalAccount(payload);
    updateUser(session.user);
    setStatus('authenticated');
    return session.user;
  }, [updateUser]);

  const logout = useCallback(async () => {
    clearReportTranslations();
    await logoutCurrentSession();
    updateUser(null);
    setStatus('anonymous');
  }, [updateUser]);

  const loginTrial = useCallback(async (payload: LoginRequest) => {
    const session = await loginWithTrialAccount(payload);
    updateUser(session.user);
    setStatus('authenticated');
    return session.user;
  }, [updateUser]);

  const value = useMemo(
    () => ({ status, user, refreshSession, login, loginTrial, logout }),
    [status, user, refreshSession, login, loginTrial, logout],
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
