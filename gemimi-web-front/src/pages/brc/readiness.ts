import type { BrcActionCard, ReadinessAction, ReadinessResponse } from '@/src/services/api';

export function allActions(readiness: ReadinessResponse | null): ReadinessAction[] {
  return readiness ? [...readiness.available_actions, ...readiness.disabled_actions] : [];
}

export function allActionCards(readiness: ReadinessResponse | null): BrcActionCard[] {
  return readiness ? [...readiness.action_cards, ...readiness.global_cutoff_controls] : [];
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

export function findActionCard(
  readiness: ReadinessResponse | null,
  actionType: BrcActionCard['action_type'],
): BrcActionCard | undefined {
  return allActionCards(readiness).find((action) => action.action_type === actionType);
}

export function isActionCardEnabled(
  readiness: ReadinessResponse | null,
  actionType: BrcActionCard['action_type'],
): boolean {
  return findActionCard(readiness, actionType)?.enabled === true;
}

export function actionCardDisabledReason(
  readiness: ReadinessResponse | null,
  actionType: BrcActionCard['action_type'],
  fallback = '当前 application preflight 尚未确认此动作可用。',
): string {
  const action = findActionCard(readiness, actionType);
  if (!action) return fallback;
  if (action.enabled) return '';
  return action.disabled_reason || fallback;
}

export function whyText(readiness: ReadinessResponse | null): string {
  if (!readiness) return '正在读取操作台状态。';
  return readiness.why.join(' ');
}
