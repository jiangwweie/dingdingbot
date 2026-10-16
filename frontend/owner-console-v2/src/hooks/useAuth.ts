import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAuthSession, login as apiLogin, logout as apiLogout, authSessionQueryKey, type LoginRequest } from '../api/authApi';
import { isUnauthorized } from '../api/errors';

export function useAuth() {
  const queryClient = useQueryClient();
  const [isLoggedOut, setIsLoggedOut] = useState(false);

  const sessionQuery = useQuery({
    queryKey: authSessionQueryKey,
    queryFn: getAuthSession,
    retry: false,
    staleTime: 30_000,
    enabled: !isLoggedOut,
  });

  const loginMutation = useMutation({
    mutationFn: (credentials: LoginRequest) => apiLogin(credentials),
    onSuccess: async () => {
      setIsLoggedOut(false);
      await queryClient.invalidateQueries({ queryKey: authSessionQueryKey });
    },
  });

  const logout = async () => {
    try {
      await apiLogout();
    } catch {
      // Regardless of network or server state, client session must terminate
    } finally {
      setIsLoggedOut(true);
      queryClient.clear();
      queryClient.setQueryData(authSessionQueryKey, null);
    }
  };

  const isAuthenticated = !isLoggedOut && sessionQuery.isSuccess && sessionQuery.data?.authenticated === true;
  const isUnauthorizedError = isUnauthorized(sessionQuery.error);

  return {
    isAuthenticated,
    isLoading: !isLoggedOut && sessionQuery.isPending,
    isCheckingSession: !isLoggedOut && sessionQuery.isPending,
    sessionError: sessionQuery.error,
    isUnauthorized: isUnauthorizedError,
    login: loginMutation.mutateAsync,
    isLoggingIn: loginMutation.isPending,
    loginError: loginMutation.error,
    logout,
    isLoggingOut: false,
    refetchSession: sessionQuery.refetch,
  };
}
