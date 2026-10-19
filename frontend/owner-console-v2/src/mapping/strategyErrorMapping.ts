import { ApiError } from '../api/errors.ts';

export interface StrategyErrorDiagnostic {
  title: string;
  isConflict409: boolean;
  httpStatus: number | null;
  code: string;
  message: string;
  explanation: string;
  canReturnToCurrent: boolean;
}

export function parseStrategyError(error: unknown, view: 'current' | 'all'): StrategyErrorDiagnostic {
  if (error instanceof ApiError) {
    const status = error.status;
    const code = error.code;
    const message = error.message;

    if (status === 409 || code === 'contradictory_facts') {
      return {
        title:
          view === 'all'
            ? '无法汇总全部版本 (HTTP 409 Contradictory Facts)'
            : '版本事实冲突 (HTTP 409 Contradictory Facts)',
        isConflict409: true,
        httpStatus: 409,
        code: code || 'contradictory_facts',
        message,
        explanation:
          '服务端存在相互矛盾的策略版本事实，禁止跨版本合并聚合（后端返回 contradictory_facts: Current facts are contradictory）。此为服务端事实一致性保护，前端禁止伪造或自动合并数据。',
        canReturnToCurrent: view === 'all',
      };
    }

    if (status === 401) {
      return {
        title: '访问未授权 (HTTP 401 Unauthorized)',
        isConflict409: false,
        httpStatus: 401,
        code: code || 'unauthorized',
        message,
        explanation: '登录凭证缺失或已失效，请重新登录认证。',
        canReturnToCurrent: false,
      };
    }

    if (status === 403) {
      return {
        title: '无权访问 (HTTP 403 Forbidden)',
        isConflict409: false,
        httpStatus: 403,
        code: code || 'forbidden',
        message,
        explanation: '当前凭证无权读取策略评估事实。',
        canReturnToCurrent: false,
      };
    }

    if (status === 422) {
      return {
        title: '请求参数校验失败 (HTTP 422 Unprocessable Entity)',
        isConflict409: false,
        httpStatus: 422,
        code: code || 'validation_error',
        message,
        explanation: message || '请求参数不符合服务端契约要求。',
        canReturnToCurrent: view === 'all',
      };
    }

    if (status >= 500) {
      return {
        title: `服务端异常 (HTTP ${status} ${code})`,
        isConflict409: false,
        httpStatus: status,
        code: code || 'server_error',
        message,
        explanation: '服务端或数据库处理失败，未返回有效策略评估数据。',
        canReturnToCurrent: view === 'all',
      };
    }

    return {
      title: `请求失败 (HTTP ${status} ${code})`,
      isConflict409: false,
      httpStatus: status,
      code,
      message,
      explanation: message || '未能成功获取策略评估数据。',
      canReturnToCurrent: view === 'all',
    };
  }

  // Network / client error
  const message = error instanceof Error ? error.message : '网络或服务异常，未能获取策略评估数据';
  return {
    title: '网络连接异常 (Network Error)',
    isConflict409: false,
    httpStatus: null,
    code: 'network_error',
    message,
    explanation: message,
    canReturnToCurrent: view === 'all',
  };
}
