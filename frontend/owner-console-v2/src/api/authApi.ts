import { apiClient } from './client';
import { ApiError, apiErrorFromResponse } from './errors';
import type { components } from './schema';

export type LoginRequest = components['schemas']['_LoginRequest'];

export const authSessionQueryKey = ['auth', 'session'] as const;

export async function getAuthProviders() {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/auth/providers');
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data || typeof data.google_login !== 'boolean' || typeof data.google_binding !== 'boolean') {
    throw new ApiError(502, 'invalid_response', 'Invalid authentication provider response');
  }
  return data;
}

export async function startGoogleBinding(totp: string): Promise<string> {
  const { data, error, response } = await apiClient.POST('/api/owner/v1/auth/google/bind/start', { body: { totp_code: totp } });
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Google binding response missing');
  const target = new URL(data.authorization_url);
  if (target.origin !== 'https://accounts.google.com' || target.pathname !== '/o/oauth2/v2/auth') {
    throw new ApiError(502, 'invalid_response', 'Invalid Google authorization destination');
  }
  return target.href;
}

export async function getGoogleBinding() {
  const { data, error, response } = await apiClient.GET('/api/owner/v1/auth/google/binding');
  if (!response.ok) throw apiErrorFromResponse(response, error);
  if (!data) throw new ApiError(502, 'invalid_response', 'Google binding identity missing');
  return data;
}

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
  if (!response.ok && response.status !== 401) {
    throw apiErrorFromResponse(response, error);
  }
}
