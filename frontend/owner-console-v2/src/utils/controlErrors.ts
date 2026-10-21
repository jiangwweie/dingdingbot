import { ApiError } from '../api/errors';

/**
 * Translate backend control-plane errors into accurate, non-misleading Chinese messages.
 */
export function formatControlError(error: unknown): string {
  if (error instanceof ApiError) {
    // 1. Conflict (409)
    if (error.status === 409 || error.code === 'control_conflict') {
      if (error.message.includes('flatten_snapshot_conflict')) {
        return '持仓状态快照冲突（服务端持仓在确认期间已发生变化）。请重新读取最新快照。';
      }
      if (error.message.includes('version_conflict') || error.message.includes('strategy_control_version_conflict')) {
        return '策略控制版本冲突（服务端版本已发生变化）。已自动重新读取最新状态，请核对后再试。';
      }
      return `状态版本冲突：${error.message}`;
    }

    // 2. Forbidden / Step-Up (403)
    if (error.status === 403) {
      if (error.code === 'step_up_invalid') {
        return 'Google Authenticator 动态口令无效或已过期，请重新输入 6 位数字。';
      }
      if (error.code === 'forbidden_request') {
        return '请求来源或访问域名未通过安全校验，请刷新页面核对访问地址。';
      }
      return `权限不足或认证失效 (${error.code})：${error.message}`;
    }

    // 3. Blocked / Validation (422)
    if (error.status === 422) {
      if (error.message.includes('strategy_retired')) {
        return '该策略已永久退役，禁止恢复新准入。';
      }
      if (error.message.includes('strategy_group_not_active')) {
        return '策略组在系统中非活跃状态，无法变更控制状态。';
      }
      if (error.message.includes('strategy_control_missing')) {
        return '策略控制配置记录缺失，请联系系统管理员。';
      }
      if (error.code === 'invalid_request') {
        return '请求参数校验失败，请检查输入格式。';
      }
      return `业务规则拒绝：${error.message}`;
    }

    // 4. Unauthorized (401)
    if (error.status === 401) {
      return '登录会话已失效，请重新登录后再操作。';
    }

    // 5. Server or Gateway errors (5xx)
    if (error.status >= 500) {
      return `服务端暂时不可用 (${error.status})：${error.message}。当前未作成功假设。`;
    }

    return `操作未执行成功 (${error.status})：${error.message}`;
  }

  if (error instanceof Error) {
    if (
      error.name === 'AbortError' ||
      error.message.includes('timeout') ||
      error.message.includes('Failed to fetch') ||
      error.message.includes('NetworkError')
    ) {
      return '网络请求超时或连接失败，当前结果未知且未作成功假设。请刷新页面核对最新状态。';
    }
    return error.message;
  }

  return '发生未知错误，当前未作成功假设。请重新读取最新状态。';
}
