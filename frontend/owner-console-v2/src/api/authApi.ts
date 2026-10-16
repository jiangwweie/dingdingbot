import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type LoginRequest = components['schemas']['_LoginRequest'];

export const authSessionQueryKey = ['auth', 'session'] as const;

export interface AuthSession {
  authenticated: true;
}

export async function getAuthSession(): Promise<AuthSession> {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/auth/session');
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (data?.authenticated !== true) {
    throw new ApiError(502, 'invalid_response', 'Invalid authentication response');
  }
  return { authenticated: true };
}

export async function login(credentials: LoginRequest): Promise<void> {
  const { error, response } = await apiClient.POST('/api/owner/v1/auth/login', {
    body: credentials,
  });
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
}

export async function logout(): Promise<void> {
  const { error, response } = await apiClient.POST('/api/owner/v1/auth/logout');
  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
}
