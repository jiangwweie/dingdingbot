import { describe, it, expect } from 'vitest';
import { formatControlError } from './controlErrors';
import { ApiError } from '../api/errors';

describe('formatControlError', () => {
  it('translates 409 version conflict accurately', () => {
    const error = new ApiError(409, 'control_conflict', 'strategy_control_version_conflict');
    const msg = formatControlError(error);
    expect(msg).toContain('策略控制版本冲突');
  });

  it('translates 403 step_up_invalid accurately', () => {
    const error = new ApiError(403, 'step_up_invalid', 'Invalid TOTP');
    const msg = formatControlError(error);
    expect(msg).toContain('Google Authenticator 动态口令无效');
  });

  it('translates 422 strategy_retired accurately', () => {
    const error = new ApiError(422, 'control_blocked', 'strategy_retired');
    const msg = formatControlError(error);
    expect(msg).toContain('该策略已永久退役，禁止恢复新准入');
  });

  it('translates network timeout without assuming success', () => {
    const error = new Error('Network timeout occurred');
    const msg = formatControlError(error);
    expect(msg).toContain('网络请求超时或连接失败');
    expect(msg).toContain('未作成功假设');
  });
});
