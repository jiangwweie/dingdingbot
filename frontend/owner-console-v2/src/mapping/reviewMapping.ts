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
      label = '经济数据不完整';
    } else if (reason) {
      label = reason;
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

export function formatExecutionClassification(
  classification: ExecutionClassification
): { label: string; tone: 'success' | 'attention' | 'danger' | 'neutral' } {
  switch (classification) {
    case 'complete':
      return { label: '执行完整', tone: 'success' };
    case 'recovered_incident':
      return { label: '异常已恢复', tone: 'attention' };
    case 'evidence_incomplete':
      return { label: '证据不完整', tone: 'danger' };
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
      return { label: '证据不完整', tone: 'danger' };
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
      return { label: '执行完整', tone: 'success' };
    case 'execution_recovered':
      return { label: '异常已恢复', tone: 'attention' };
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
  if (!raw) return { label: '—', raw: null };
  if (raw.startsWith('owner_flatten_all')) {
    return { label: 'Owner 受控平仓', raw };
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
  return { label: raw, raw };
}
