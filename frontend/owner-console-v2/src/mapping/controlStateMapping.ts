export interface ControlOperationStateMeta {
  label: string;
  tone: 'success' | 'danger' | 'attention' | 'brand';
  isUnknown: boolean;
  raw: string;
}

const KNOWN_OPERATION_STATES: Record<
  string,
  { label: string; tone: 'success' | 'danger' | 'attention' | 'brand' }
> = {
  validating: { label: '校验中', tone: 'brand' },
  pending: { label: '待执行', tone: 'brand' },
  claimed: { label: '已认领', tone: 'brand' },
  exits_requested: { label: '已发出平仓指令', tone: 'brand' },
  exit_in_progress: { label: '平仓执行中', tone: 'brand' },
  reconciliation_pending: { label: '待对账确认', tone: 'brand' },
  settlement_pending: { label: '待结算确认', tone: 'brand' },
  review_pending: { label: '待复盘确认', tone: 'brand' },
  completed: { label: '已完成', tone: 'success' },
  blocked: { label: '已阻断', tone: 'danger' },
  needs_intervention: { label: '需人工介入', tone: 'danger' },
};

export function formatControlOperationState(
  state: string,
  blocker?: string | null
): ControlOperationStateMeta {
  if (state === 'completed') {
    return {
      label: blocker ? '曾需关注 · 已完成' : '已完成',
      tone: 'success',
      isUnknown: false,
      raw: state,
    };
  }
  const known = KNOWN_OPERATION_STATES[state];
  if (known) {
    return {
      ...known,
      isUnknown: false,
      raw: state,
    };
  }
  return {
    label: '状态待核实',
    tone: 'attention',
    isUnknown: true,
    raw: state,
  };
}

export function isManualTakeoverBlocker(blocker?: string | null): boolean {
  if (!blocker) return false;
  return (
    blocker.startsWith('manual_') ||
    blocker.includes(':manual_') ||
    blocker.endsWith(':manual_open')
  );
}
