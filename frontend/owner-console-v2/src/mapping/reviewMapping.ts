import { MoneyDecimal } from './tradeTruth.ts';
import type {
  MoneyMetric,
  ExecutionClassification,
  ReviewItemReviewStatus,
  ReviewStatusQuery,
  ReviewSentence,
} from '../api/reviewApi.ts';

export interface FormattedReviewMoney {
  formatted: string;
  value: string | null;
  isPositive: boolean | null;
  isUnavailable: boolean;
  unavailableReason: string | null;
}

export function formatReviewMoneyMetric(
  metric: MoneyMetric | null | undefined,
  options: { sign?: boolean; defaultUnavailableText?: string; fractionDigits?: number } = {}
): FormattedReviewMoney {
  const { sign = false, defaultUnavailableText = '—', fractionDigits = 2 } = options;

  if (!metric || metric.value === null || metric.value === undefined) {
    const reason = metric?.unavailable_reason ?? null;
    let label = defaultUnavailableText;
    if (reason === 'no_confirmed_natural_review') {
      label = '无已确认自然评审';
    } else if (reason === 'ticket_active') {
      label = '持仓中 · 未结';
    } else if (reason === 'incomplete_review_economics') {
      label = '净额尚未完整核实';
    } else if (reason) {
      label = ({ funding_unavailable: '资金费无法归因', external_exit_unavailable: '退出成交明细缺失', review_missing: '尚无收益核算', no_review_evidence: '暂无已核实数据', no_confirmed_metric: '暂无已核实金额' } as Record<string, string>)[reason] ?? '该项暂不可确认';
    }
    return {
      formatted: label,
      value: null,
      isPositive: null,
      isUnavailable: true,
      unavailableReason: reason,
    };
  }

  let num;
  try {
    num = new MoneyDecimal(metric.value);
  } catch {
    return {
      formatted: defaultUnavailableText,
      value: null,
      isPositive: null,
      isUnavailable: true,
      unavailableReason: 'invalid_number',
    };
  }

  if (!num.isFinite()) {
    return {
      formatted: defaultUnavailableText,
      value: null,
      isPositive: null,
      isUnavailable: true,
      unavailableReason: 'non_finite',
    };
  }

  const isZero = num.isZero();
  const isPos = isZero ? null : num.isPositive();
  const signPrefix = sign && isPos ? '+' : '';
  const unitStr = metric.unit ? ` ${metric.unit}` : '';
  const formatted = `${signPrefix}${num.toFixed(fractionDigits)}${unitStr}`.trim();

  return {
    formatted,
    value: num.toString(),
    isPositive: isPos,
    isUnavailable: false,
    unavailableReason: null,
  };
}

/** Display-only gross fallback. It never becomes a net amount for aggregation. */
export function formatPnlWithGrossFallback(
  net: MoneyMetric | null | undefined,
  gross: MoneyMetric | null | undefined,
): FormattedReviewMoney & { isGrossFallback: boolean } {
  const confirmedNet = formatReviewMoneyMetric(net, { sign: true });
  if (net?.value == null && net?.unavailable_reason === 'funding_unavailable') {
    const knownGross = formatReviewMoneyMetric(gross, { sign: true });
    if (!knownGross.isUnavailable) return {
      ...knownGross,
      formatted: `${knownGross.formatted}（资费不完整）`,
      value: null,
      unavailableReason: net?.unavailable_reason ?? null,
      isGrossFallback: true,
    };
  }
  return { ...confirmedNet, isGrossFallback: false };
}

export function formatExecutionClassification(
  classification: ExecutionClassification
): { label: string; tone: 'success' | 'attention' | 'danger' | 'neutral' } {
  switch (classification) {
    case 'complete':
      return { label: '链路已核实', tone: 'success' };
    case 'recovered_incident':
      return { label: '异常已恢复', tone: 'attention' };
    case 'evidence_incomplete':
      return { label: '存在待核实项', tone: 'attention' };
    case 'waiting_review':
      return { label: '等待复盘', tone: 'neutral' };
    case 'in_progress':
      return { label: '进行中', tone: 'neutral' };
    default:
      return { label: classification, tone: 'neutral' };
  }
}

export function formatReviewStatus(
  status: ReviewItemReviewStatus | ReviewStatusQuery | (string & {})
): { label: string; tone: 'success' | 'attention' | 'danger' | 'neutral' } {
  switch (status as string) {
    case 'complete':
      return { label: '完整', tone: 'success' };
    case 'incomplete_evidence':
      return { label: '存在待核实项', tone: 'attention' };
    case 'waiting_review':
    case 'waiting_for_review':
      return { label: '等待复盘', tone: 'neutral' };
    case 'waiting_for_settlement':
      return { label: '等待结算', tone: 'neutral' };
    case 'in_progress':
      return { label: '进行中', tone: 'neutral' };
    default:
      return { label: status, tone: 'neutral' };
  }
}

export function formatReviewSentenceTemplate(
  templateId: ReviewSentence['template_id']
): { label: string; tone: 'success' | 'attention' | 'danger' | 'neutral' } {
  switch (templateId) {
    case 'execution_complete':
      return { label: '链路已核实', tone: 'success' };
    case 'execution_recovered':
      return { label: '异常已恢复', tone: 'attention' };
    case 'execution_incomplete':
      return { label: '执行证据待核实', tone: 'attention' };
    case 'economics_complete':
      return { label: '经济结算完整', tone: 'success' };
    case 'economics_incomplete':
      return { label: '经济结算不完整', tone: 'danger' };
    case 'review_waiting':
      return { label: '等待复盘', tone: 'neutral' };
    case 'ticket_in_progress':
      return { label: '持仓进行中', tone: 'neutral' };
    default:
      return { label: templateId, tone: 'neutral' };
  }
}

const EXIT_REASON_ZH: Record<string, string> = {
  owner_flatten_all: 'Owner 全部持仓受控平仓',
  pre_tp1_time_stop_hit: 'TP1 前持仓超时退出',
  absolute_time_stop_hit: '持仓达到最长时限退出',
  protection_stop_triggered: '保护止损成交',
  exit_reason_evidence_missing: '退出原因未确认',
  exit_reason_unavailable: '退出原因未确认',
  exit_not_applicable: '不适用（未形成持仓）',
  ticket_active: '持仓未退出',
  stop_loss: '止损触发',
  take_profit: '止盈触发',
  tp1_hit: 'TP1 触发',
  initial_stop_triggered: '初始止损触发',
  'Initial Stop': '初始止损触发',
  take_profit_triggered: '止盈成交触发',
  failed_breakout_reclaimed: '假突破回收退出',
  failed_breakdown_reclaimed: '假跌破回收退出',
  sor_session_expired: '交易时段到期退出',
  exposure_session_expired: '交易时段到期退出',
  time_stop_hit: '持仓时间到期退出',
  strategy_exit: '策略条件退出',
  recover_exit_rejection: '退出恢复处理',
  initial_stop_rejected: '初始止损异常后受控退出',
  initial_stop_absent: '初始止损缺失后受控退出',
  runner_stop: 'Runner 止损退出',
  runner_exit: 'TP1 后 Runner 退出',
  'TP1 + Runner Exit': 'TP1 后 Runner 退出',
  'Controlled Exit': '受控退出',
  'External Flat / Exit Fills Unavailable': '外部平仓已确认，成交明细不可得',
  external_flat_exit_fills_unavailable: '外部平仓已确认，成交明细不可得',
  deployment_drain: '部署前安全退出',
  budget_exhausted: '可用预算不足',
  gross_stop_risk_capacity_exhausted: '总止损风险额度已占用',
  incomplete_review_economics: '经济数据尚不完整',
  hard_safety_stop: '安全保护已阻断',
};

export function formatReviewExitReason(
  raw: string | null | undefined
): { label: string; raw: string | null } {
  if (!raw) return { label: '退出原因未确认', raw: null };
  if (raw.startsWith('owner_flatten_all:')) {
    return { label: 'Owner 全部持仓受控平仓', raw };
  }
  if (raw.startsWith('deployment_drain')) {
    return { label: '部署前安全退出', raw };
  }
  if (raw.startsWith('ticket_incident')) {
    return { label: '交易执行需要核对', raw };
  }
  if (raw.startsWith('exposure_family_cap')) {
    return { label: '同类风险额度已占用', raw };
  }
  if (EXIT_REASON_ZH[raw]) {
    return { label: EXIT_REASON_ZH[raw], raw };
  }
  return { label: '退出原因未识别', raw };
}
