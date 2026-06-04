import type { Envelope } from '@/types';

export type PageMood = 'ok' | 'attention' | 'blocked' | 'unknown';

export function dataStatusLabel(status?: string): string {
  if (status === 'fresh') return '已同步';
  if (status === 'warning') return '需关注';
  if (status === 'degraded') return '部分同步';
  if (status === 'not_live_connected') return '未同步';
  return '无法确认';
}

export function dataStatusMood(status?: string): PageMood {
  if (status === 'fresh') return 'ok';
  if (status === 'warning') return 'attention';
  if (status === 'degraded') return 'attention';
  return 'unknown';
}

export function pageMoodClasses(mood: PageMood): string {
  const map: Record<PageMood, string> = {
    ok: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-200',
    attention: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-200',
    blocked: 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/50 dark:bg-rose-950/20 dark:text-rose-200',
    unknown: 'border-slate-200 bg-slate-50 text-slate-800 dark:border-slate-800 dark:bg-slate-900/70 dark:text-slate-200',
  };
  return map[mood];
}

export function badgeVariantForMood(mood: PageMood): 'normal' | 'warning' | 'danger' | 'caution' | 'muted' {
  if (mood === 'ok') return 'normal';
  if (mood === 'attention') return 'warning';
  if (mood === 'blocked') return 'danger';
  return 'caution';
}

export function ownerSourceLabel(source?: string): string {
  const map: Record<string, string> = {
    pg: '本地系统',
    exchange: '交易所',
    exchange_normal: '交易所',
    exchange_stop: '交易所条件单',
    read_model: '系统聚合',
    unknown: '无法判断',
    not_available: '暂无数据',
  };
  return map[String(source || 'unknown')] || '无法判断';
}

export function orderClassLabel(value?: string): string {
  const map: Record<string, string> = {
    matched: '已匹配',
    pg_unchecked: '未核验',
    pg_only: '仅本地记录',
    exchange_only: '仅交易所存在',
    mismatch: '状态不一致',
    orphan_protection: '无法归属的保护单',
    unknown: '无法判断',
  };
  return map[String(value || 'unknown')] || '无法判断';
}

export function orderRoleLabel(value?: string): string {
  const normalized = String(value || '').toLowerCase();
  if (normalized.includes('entry')) return '建仓单';
  if (normalized.includes('exit') || normalized.includes('close')) return '平仓单';
  if (normalized.includes('tp') || normalized.includes('take')) return '止盈单';
  if (normalized.includes('sl') || normalized.includes('stop')) return '止损单';
  if (normalized.includes('protect')) return '保护单';
  if (normalized.includes('recover')) return '恢复单';
  return '未知';
}

export function orderStatusLabel(value?: string): string {
  const normalized = String(value || '').toLowerCase();
  const map: Record<string, string> = {
    open: '未完成',
    created: '已创建',
    filled: '已成交',
    partially_filled: '部分成交',
    canceled: '已取消',
    cancelled: '已取消',
    rejected: '已拒绝',
    unknown: '无法确认',
  };
  return map[normalized] || (value ? String(value) : '无法确认');
}

export function sideLabel(value?: string): string {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'long' || normalized === 'buy') return '做多';
  if (normalized === 'short' || normalized === 'sell') return '做空';
  return value ? String(value) : '未知';
}

export function protectionStatusLabel(value?: string): string {
  const map: Record<string, string> = {
    protected: '保护完整',
    partially_protected: '部分保护',
    unprotected: '当前仓位未保护',
    unknown: '无法确认保护状态',
    orphaned: '存在无法归属的保护单',
    not_available: '暂无数据',
  };
  return map[String(value || 'unknown')] || '无法确认保护状态';
}

export function consistencyStatusLabel(value?: string): string {
  const map: Record<string, string> = {
    clean: '已一致',
    matched: '已一致',
    mismatch: '状态不一致',
    degraded: '无法确认',
    not_live_connected: '无法确认',
    unknown: '无法判断',
  };
  return map[String(value || 'unknown')] || '无法判断';
}

export function carrierStatusLabel(value?: string): string {
  const map: Record<string, string> = {
    blocked: '暂不可用',
    read_only_available: '可查看',
    available: '可查看',
    unknown: '无法确认',
  };
  return map[String(value || 'unknown')] || '无法确认';
}

export function authorizationStatusLabel(value?: string): string {
  const map: Record<string, string> = {
    owner_live_authorized_pending_final_preflight: '已授权，等待最终前置检查',
    pending_owner_live_authorization: '等待 Owner 授权',
    consumed: '已消费',
    expired: '已过期',
    cancelled: '已取消',
    unknown: '无法确认',
  };
  return map[String(value || 'unknown')] || '无法确认';
}

export function blockingReasonLabel(value?: string): string {
  const text = String(value || '');
  const normalized = text.toLowerCase();
  if (!text) return '无';
  if (normalized.includes('authorization_permission_flags_false')) return '授权尚未转化为可执行权限';
  if (normalized.includes('authorization_actionable')) return '授权尚未形成可执行动作';
  if (normalized.includes('open_intents')) return '当前没有阻断性的执行意图';
  if (normalized.includes('startup_guard')) return '启动安全检查尚未通过';
  if (normalized.includes('protection')) return '保护状态尚未确认';
  if (normalized.includes('not_live_connected')) return '数据未同步';
  if (normalized.includes('binance') && normalized.includes('timeout')) return '交易所请求超时';
  return '需要人工确认';
}

export function gateCodeLabel(value?: string): string {
  const text = String(value || '');
  if (text.includes('authorization_actionable')) return '授权可执行性';
  if (text.includes('authorization_permission_flags_false')) return '授权权限';
  if (text.includes('protection_health')) return '保护状态';
  if (text.includes('open_intents')) return '执行意图';
  if (text.includes('startup_guard')) return '启动安全检查';
  return text ? '安全检查项' : '未知检查项';
}

export function gateStatusLabel(value?: string): string {
  const text = String(value || '').toLowerCase();
  if (text === 'pass') return '通过';
  if (text === 'warning') return '需关注';
  if (text === 'block' || text === 'blocked') return '阻断';
  if (text === 'read_only_no_execute_endpoint') return '只读展示';
  return value ? String(value) : '未知';
}

export function unavailableOwnerImpact(envelope: Envelope<any> | null): string[] {
  return (envelope?.unavailable || [])
    .map((item) => ownerSourceLabel(item.source));
}

export function pageSummaryFromEnvelope(envelope: Envelope<any> | null, fallback = '暂无待处理事项。') {
  const blockers = envelope?.blockers || [];
  const warnings = envelope?.warnings || [];
  const ownerImpacts = unavailableOwnerImpact(envelope);
  if (blockers.length > 0) {
    return {
      mood: 'blocked' as PageMood,
      title: '存在阻断事项',
      description: blockingReasonLabel(blockers[0]?.message || blockers[0]?.code) || '当前执行链路存在阻断，需要进一步查看。',
    };
  }
  if (ownerImpacts.length > 0 || envelope?.freshness_status === 'degraded') {
    return {
      mood: 'attention' as PageMood,
      title: '部分状态无法确认',
      description: '当前展示已同步的账户、订单和保护信息。',
    };
  }
  if (warnings.length > 0) {
    return {
      mood: 'attention' as PageMood,
      title: '有事项需要关注',
      description: warnings[0]?.message || '存在需要 Owner 关注的风险提示。',
    };
  }
  if (envelope?.freshness_status === 'not_live_connected') {
    return {
      mood: 'unknown' as PageMood,
      title: '无法确认完整状态',
      description: '当前无法确认完整账户状态。',
    };
  }
  return {
    mood: 'ok' as PageMood,
    title: '暂无待处理事项',
    description: fallback,
  };
}

export function formatMoney(value: unknown): string {
  if (value === null || value === undefined || value === '' || value === 'not_available' || value === 'unknown') return '暂无数据';
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 8 });
}

export function shortTime(ms?: number): string {
  if (!ms || !Number.isFinite(ms)) return '未知';
  return new Date(ms).toLocaleString();
}
