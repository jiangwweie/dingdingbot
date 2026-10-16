import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getAuthSession,
  login as apiLogin,
  logout as apiLogout,
  authSessionQueryKey,
  type LoginRequest,
} from '../api/authApi';
import { isUnauthorized } from '../api/errors';
import {
  executeAuthLogout,
  evaluateAuthState,
  isSessionBlockedByStorage,
  LOGOUT_UNCONFIRMED_KEY,
} from '../utils/authVerification.ts';

export function useAuth() {
  const queryClient = useQueryClient();

  const [isLogoutUnconfirmed, setIsLogoutUnconfirmed] = useState<boolean>(() => {
    return isSessionBlockedByStorage(typeof window !== 'undefined' ? sessionStorage : null);
  });

  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  const sessionQuery = useQuery({
    queryKey: authSessionQueryKey,
    queryFn: getAuthSession,
    retry: false,
    staleTime: 30_000,
  });

  const loginMutation = useMutation({
    mutationFn: (credentials: LoginRequest) => apiLogin(credentials),
    onSuccess: async () => {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem(LOGOUT_UNCONFIRMED_KEY);
      }
      setIsLogoutUnconfirmed(false);
      setLogoutError(null);
      await queryClient.invalidateQueries({ queryKey: authSessionQueryKey });
    },
  });

  const logout = useCallback(async (): Promise<boolean> => {
    const storage = typeof window !== 'undefined' ? sessionStorage : null;
    return executeAuthLogout({
      apiLogoutFn: apiLogout,
      getSessionFn: getAuthSession,
      queryClient,
      storage,
      sessionQueryKey: authSessionQueryKey,
      onStateChange: (st) => {
        setIsLoggingOut(st.isLoggingOut);
        setIsLogoutUnconfirmed(st.isLogoutUnconfirmed);
        setLogoutError(st.logoutError);
      },
    });
  }, [queryClient]);

  const acknowledgeUnconfirmedSession = useCallback(() => {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem(LOGOUT_UNCONFIRMED_KEY);
    }
    setIsLogoutUnconfirmed(false);
    setLogoutError(null);
    sessionQuery.refetch();
  }, [sessionQuery]);

  const isAuthenticated = evaluateAuthState({
    isLogoutUnconfirmed,
    isLoggingOut,
    sessionSuccess: sessionQuery.isSuccess,
    authenticated: sessionQuery.data?.authenticated,
  });

  const isUnauthorizedError = isUnauthorized(sessionQuery.error);

  return {
    isAuthenticated,
    isLoading: sessionQuery.isPending,
    isCheckingSession: sessionQuery.isPending,
    sessionError: sessionQuery.error,
    isUnauthorized: isUnauthorizedError,
    login: loginMutation.mutateAsync,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    logout,
    isLoggingOut,
    logoutError,
    isLogoutUnconfirmed,
    acknowledgeUnconfirmedSession,
    refetchSession: sessionQuery.refetch,
  };
}
