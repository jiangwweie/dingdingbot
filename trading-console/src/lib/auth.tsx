import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type OperatorSession = {
  authenticated: boolean;
  username?: string | null;
  expires_at_ms?: number | null;
  live_ready?: boolean;
};

type LoginInput = {
  username: string;
  password: string;
  totp_code: string;
};

type AuthState = {
  session: OperatorSession | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

async function parseSessionResponse(response: Response): Promise<OperatorSession> {
  if (!response.ok) {
    throw new Error(`Operator session request returned HTTP ${response.status}`);
  }
  return await response.json();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<OperatorSession | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/auth/session', {
        method: 'GET',
        credentials: 'include',
      });
      const payload = await parseSessionResponse(response);
      setSession(payload.authenticated ? payload : null);
    } catch (error) {
      console.error('Operator session check failed', error);
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    });
    const payload = await parseSessionResponse(response);
    setSession(payload.authenticated ? payload : null);
  }, []);

  const logout = useCallback(async () => {
    try {
      const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) throw new Error(`Operator logout returned HTTP ${response.status}`);
    } catch (error) {
      console.error('Operator logout failed', error);
    } finally {
      setSession(null);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onUnauthorized = () => setSession(null);
    window.addEventListener('trading-console:unauthorized', onUnauthorized);
    return () => window.removeEventListener('trading-console:unauthorized', onUnauthorized);
  }, []);

  const value = useMemo(() => ({ session, loading, login, logout, refresh }), [session, loading, login, logout, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
