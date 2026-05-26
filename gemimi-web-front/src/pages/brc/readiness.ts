import type { ReadinessAction, ReadinessResponse } from '@/src/services/api';

export function allActions(readiness: ReadinessResponse | null): ReadinessAction[] {
  return readiness ? [...readiness.available_actions, ...readiness.disabled_actions] : [];
}

export function findAction(
  readiness: ReadinessResponse | null,
  actionId: string,
): ReadinessAction | undefined {
  return allActions(readiness).find((action) => action.action_id === actionId);
}

export function isActionEnabled(readiness: ReadinessResponse | null, actionId: string): boolean {
  return findAction(readiness, actionId)?.enabled === true;
}

export function actionDisabledReason(
  readiness: ReadinessResponse | null,
  actionId: string,
  fallback = '当前 readiness 尚未确认此动作可用。',
): string {
  const action = findAction(readiness, actionId);
  if (!action) return fallback;
  if (action.enabled) return '';
  return action.disabled_reason || fallback;
}

export function whyText(readiness: ReadinessResponse | null): string {
  if (!readiness) return '正在读取操作台状态。';
  return readiness.why.join(' ');
}
