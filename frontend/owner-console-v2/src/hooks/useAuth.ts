import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAuthSession, login as apiLogin, logout as apiLogout, authSessionQueryKey, type LoginRequest } from '../api/authApi';
import { isUnauthorized } from '../api/errors';

export function useAuth() {
  const queryClient = useQueryClient();

  const sessionQuery = useQuery({
    queryKey: authSessionQueryKey,
    queryFn: getAuthSession,
    retry: false,
    staleTime: 30_000,
  });

  const loginMutation = useMutation({
    mutationFn: (credentials: LoginRequest) => apiLogin(credentials),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: authSessionQueryKey });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => apiLogout(),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(authSessionQueryKey, null);
    },
  });

  const isAuthenticated = sessionQuery.isSuccess && sessionQuery.data?.authenticated === true;
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
    logout: logoutMutation.mutateAsync,
    isLoggingOut: logoutMutation.isPending,
    refetchSession: sessionQuery.refetch,
  };
}
