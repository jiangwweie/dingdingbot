import { isUnauthorized } from '../api/errors.ts';

export const LOGOUT_UNCONFIRMED_KEY = 'brc_owner_logout_unconfirmed';

export interface LogoutVerificationResult {
  success: boolean;
  unconfirmed: boolean;
  errorDetail: string | null;
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
