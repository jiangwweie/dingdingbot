import { isUnauthorized } from '../api/errors.ts';

export const LOGOUT_UNCONFIRMED_KEY = 'brc_owner_logout_unconfirmed';

export interface LogoutVerificationResult {
  success: boolean;
  unconfirmed: boolean;
  errorDetail: string | null;
}

export interface AuthStateContext {
  isLogoutUnconfirmed: boolean;
  isLoggingOut: boolean;
  sessionSuccess: boolean;
  authenticated: boolean | undefined;
}

/**
 * Evaluates whether sensitive console views and interactions should be accessible.
 * 
 * Access is strictly revoked if:
 * 1. Logout is in progress (isLoggingOut = true)
 * 2. An unconfirmed logout was recorded (isLogoutUnconfirmed = true)
 * 3. Session query failed or reported authenticated = false
 */
export function evaluateAuthState(ctx: AuthStateContext): boolean {
  return (
    !ctx.isLogoutUnconfirmed &&
    !ctx.isLoggingOut &&
    ctx.sessionSuccess &&
    ctx.authenticated === true
  );
}

/**
 * Checks if the persistent storage holds an unconfirmed logout guard flag.
 */
export function isSessionBlockedByStorage(storage?: Storage | null): boolean {
  if (!storage) return false;
  return storage.getItem(LOGOUT_UNCONFIRMED_KEY) === 'true';
}

export async function performLogoutVerification(
  apiLogoutFn: () => Promise<void>,
  getSessionFn: () => Promise<unknown>,
  storage?: Storage | null
): Promise<LogoutVerificationResult> {
  let postSucceeded = false;
  let postErrorDetail = '';

  try {
    await apiLogoutFn();
    postSucceeded = true;
  } catch (err) {
    postErrorDetail = err instanceof Error ? err.message : '网络或服务异常';
  }

  // Explicitly verify server session invalidation via GET /api/owner/v1/auth/session
  let serverSessionInvalidated = false;
  try {
    await getSessionFn();
    // If getSessionFn succeeded without throwing 401, the session is still active on server!
    serverSessionInvalidated = false;
  } catch (err) {
    if (isUnauthorized(err)) {
      serverSessionInvalidated = true;
    }
  }

  if (postSucceeded && serverSessionInvalidated) {
    storage?.removeItem(LOGOUT_UNCONFIRMED_KEY);
    return {
      success: true,
      unconfirmed: false,
      errorDetail: null,
    };
  } else {
    storage?.setItem(LOGOUT_UNCONFIRMED_KEY, 'true');
    const detail = !postSucceeded
      ? `注销接口请求失败 (${postErrorDetail})`
      : '服务端 Session 校验未返回 401，未能确认销毁';
    return {
      success: false,
      unconfirmed: true,
      errorDetail: `服务端退出未确认：${detail}`,
    };
  }
}

export interface AuthLogoutExecutionParams {
  apiLogoutFn: () => Promise<void>;
  getSessionFn: () => Promise<unknown>;
  queryClient: {
    clear: () => void;
    setQueryData: (key: any, data: any) => void;
  };
  storage?: Storage | null;
  sessionQueryKey?: unknown;
  onStateChange?: (state: {
    isLoggingOut: boolean;
    isLogoutUnconfirmed: boolean;
    logoutError: string | null;
  }) => void;
}

/**
 * Executes the complete real authentication logout workflow:
 * 1. Sets isLoggingOut = true (which immediately closes sensitive views via evaluateAuthState)
 * 2. Invokes network API logout and verifies server session invalidation
 * 3. On success: clears cache and session query data, sets isLogoutUnconfirmed = false
 * 4. On failure: flags isLogoutUnconfirmed = true, records error, and still purges queryClient cache to protect user data
 */
export async function executeAuthLogout(
  params: AuthLogoutExecutionParams
): Promise<boolean> {
  params.onStateChange?.({
    isLoggingOut: true,
    isLogoutUnconfirmed: false,
    logoutError: null,
  });

  const res = await performLogoutVerification(
    params.apiLogoutFn,
    params.getSessionFn,
    params.storage
  );

  if (res.success) {
    params.onStateChange?.({
      isLoggingOut: false,
      isLogoutUnconfirmed: false,
      logoutError: null,
    });
    params.queryClient.clear();
    if (params.sessionQueryKey) {
      params.queryClient.setQueryData(params.sessionQueryKey, null);
    }
    return true;
  } else {
    params.onStateChange?.({
      isLoggingOut: false,
      isLogoutUnconfirmed: true,
      logoutError: res.errorDetail,
    });
    // Critical privacy requirement: purge all query caches even when server logout failed or unconfirmed
    params.queryClient.clear();
    return false;
  }
}
