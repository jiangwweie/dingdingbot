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
import { performLogoutVerification, LOGOUT_UNCONFIRMED_KEY } from '../utils/authVerification.ts';

export function useAuth() {
  const queryClient = useQueryClient();

  const [isLogoutUnconfirmed, setIsLogoutUnconfirmed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem(LOGOUT_UNCONFIRMED_KEY) === 'true';
    }
    return false;
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
    setIsLoggingOut(true);
    setLogoutError(null);

    const storage = typeof window !== 'undefined' ? sessionStorage : null;
    const res = await performLogoutVerification(apiLogout, getAuthSession, storage);

    setIsLoggingOut(false);

    if (res.success) {
      setIsLogoutUnconfirmed(false);
      setLogoutError(null);
      queryClient.clear();
      queryClient.setQueryData(authSessionQueryKey, null);
      return true;
    } else {
      setIsLogoutUnconfirmed(true);
      setLogoutError(res.errorDetail);
      // For privacy, clear sensitive cached query data
      queryClient.clear();
      return false;
    }
  }, [queryClient]);

  const acknowledgeUnconfirmedSession = useCallback(() => {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem(LOGOUT_UNCONFIRMED_KEY);
    }
    setIsLogoutUnconfirmed(false);
    setLogoutError(null);
    sessionQuery.refetch();
  }, [sessionQuery]);

  const isAuthenticated =
    !isLogoutUnconfirmed &&
    sessionQuery.isSuccess &&
    sessionQuery.data?.authenticated === true;

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
