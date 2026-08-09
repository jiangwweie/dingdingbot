import { apiClient } from "../../api/client";
import { ApiError, apiErrorFromResponse } from "../../api/errors";
import type { LoginCredentials } from "./schema";

export const authSessionQueryKey = ["auth", "session"] as const;

export async function login(credentials: LoginCredentials): Promise<void> {
  const { error, response } = await apiClient.POST("/api/owner/v1/auth/login", {
    body: credentials,
  });

  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
}

export interface AuthSession {
  authenticated: true;
}

export async function getAuthSession(): Promise<AuthSession> {
  const { data, error, response } = await apiClient.GET("/api/owner/v1/auth/session");

  if (!response.ok) {
    throw apiErrorFromResponse(response, error);
  }
  if (data?.authenticated !== true) {
    throw new ApiError(502, "invalid_response", "Invalid authentication response");
  }

  return { authenticated: true };
}
