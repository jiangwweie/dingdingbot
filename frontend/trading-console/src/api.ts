import type { SessionResponse, TradingConsoleEnvelope } from "./types";

const defaultSession: SessionResponse = {
  authenticated: false,
  username: null,
  expires_at_ms: null,
  current_stage: "BRC operator console",
  next_recommended_step: "Login required.",
  global_planning_stage: "Trading console frontend.",
  live_ready: false,
};

type RequestOptions = RequestInit & { allowUnauthenticated?: boolean };

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (response.status === 401 && !options.allowUnauthenticated) {
    throw new Error("UNAUTHENTICATED");
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getSession(): Promise<SessionResponse> {
  try {
    return await request<SessionResponse>("/api/auth/session", {
      allowUnauthenticated: true,
    });
  } catch {
    return defaultSession;
  }
}

export async function login(username: string, password: string, totpCode: string): Promise<SessionResponse> {
  return request<SessionResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({
      username,
      password,
      totp_code: totpCode,
    }),
    allowUnauthenticated: true,
  });
}

export async function logout(): Promise<SessionResponse> {
  return request<SessionResponse>("/api/auth/logout", {
    method: "POST",
    allowUnauthenticated: true,
  });
}

export async function readModel<T = Record<string, unknown>>(
  path: string,
): Promise<TradingConsoleEnvelope<T>> {
  return request<TradingConsoleEnvelope<T>>(path);
}

