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

const LOGOUT_UNCONFIRMED_KEY = 'brc_owner_logout_unconfirmed';

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

    let postSucceeded = false;
    let postErrorDetail = '';

    try {
      await apiLogout();
      postSucceeded = true;
    } catch (err) {
      postErrorDetail = err instanceof Error ? err.message : '网络或服务异常';
    }

    // Explicitly verify server session invalidation via GET /api/owner/v1/auth/session
    let serverSessionInvalidated = false;
    try {
      await getAuthSession();
      // If getAuthSession succeeded without throwing 401, the session is still active on server!
      serverSessionInvalidated = false;
    } catch (err) {
      if (isUnauthorized(err)) {
        serverSessionInvalidated = true;
      }
    }

    setIsLoggingOut(false);

    if (postSucceeded && serverSessionInvalidated) {
      // Confirmed genuine server logout
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem(LOGOUT_UNCONFIRMED_KEY);
      }
      setIsLogoutUnconfirmed(false);
      setLogoutError(null);
      queryClient.clear();
      queryClient.setQueryData(authSessionQueryKey, null);
      return true;
    } else {
      // Server logout unconfirmed
      if (typeof window !== 'undefined') {
        sessionStorage.setItem(LOGOUT_UNCONFIRMED_KEY, 'true');
      }
      setIsLogoutUnconfirmed(true);
      const detail = !postSucceeded
        ? `注销接口请求失败 (${postErrorDetail})`
        : '服务端 Session 校验未返回 401，未能确认销毁';
      const errMsg = `服务端退出未确认：${detail}`;
      setLogoutError(errMsg);
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
