import React from 'react';
import type { TradeEpisodeSummary } from '../../types/overview';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  ChevronRight,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Loader2,
  Cpu,
  UserCheck,
} from 'lucide-react';

interface ActiveEpisodesSectionProps {
  episodes: TradeEpisodeSummary[];
  onSelectEpisode: (episode: TradeEpisodeSummary) => void;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string | null;
  unloadedActiveCount?: number;
  onRetry?: () => void;
  highlightedStrategyId?: string | null;
}

const PURE_MANUAL_REDUNDANT_LABELS = new Set([
  '整笔已转人工管理',
  '外部干预触发',
  '整笔已转人工管理 · 外部干预触发',
  '整笔已转人工管理 · 外部干预已触发永久接管',
]);

const PURE_REVIEW_REDUNDANT_LABELS = new Set([
  '接管待核实',
  '自动处置已暂停',
  '自动处置暂停',
  '接管待核实 · 自动处置已暂停',
  '接管待核实 · 自动处置暂停',
]);

/**
 * Deduplicates only exact, purely redundant management-mode labels that carry
 * no supplemental risk facts. Any item containing additional facts (e.g.
 * "整笔已转人工管理；止损已撤销，当前没有保护单" or "接管待核实；存在未核实残留订单")
 * is strictly preserved.
 */
export function deduplicateEpisodeAttentionItems(
  items: string[] | undefined,
  managementMode?: 'AUTO' | 'REVIEW_REQUIRED' | 'MANUAL'
): string[] {
  if (!items || items.length === 0) return [];
  const seen = new Set<string>();
  const result: string[] = [];

  for (const raw of items) {
    const trimmed = raw.trim();
    if (!trimmed) continue;
    if (managementMode === 'MANUAL' && PURE_MANUAL_REDUNDANT_LABELS.has(trimmed)) {
      continue;
    }
    if (managementMode === 'REVIEW_REQUIRED' && PURE_REVIEW_REDUNDANT_LABELS.has(trimmed)) {
      continue;
    }
    if (!seen.has(trimmed)) {
      seen.add(trimmed);
      result.push(trimmed);
    }
  }
  return result;
}

export function translateManualRiskReason(rawReason: string): { shortTag: string; isKnown: boolean; raw: string } {
  const trimmed = rawReason.trim();
  const symbolMatch = /^MANUAL_TAKEOVER_ACTIVE_ON_SYMBOL:\s*(.+)$/i.exec(trimmed);
  if (symbolMatch) {
    const sym = symbolMatch[1].trim();
    return {
      shortTag: `同币种 (${sym}) 新增开仓已锁定`,
      isKnown: true,
      raw: trimmed,
    };
  }
  if (trimmed === 'manual_stop_coverage_incomplete') {
    return {
      shortTag: '止损覆盖待核实 · 新增开仓受限',
      isKnown: true,
      raw: trimmed,
    };
  }
  return { shortTag: '新增开仓受限 · 原因待核实', isKnown: false, raw: trimmed };
}

export const ActiveEpisodesSection: React.FC<ActiveEpisodesSectionProps> = ({
  episodes,
  onSelectEpisode,
  isLoading = false,
  isError = false,
  errorMessage,
  unloadedActiveCount = 0,
  onRetry,
  highlightedStrategyId = null,
}) => {
  return (
    <div id="active-episodes" className="rounded-xl border border-border bg-surface p-5 shadow-xs transition-all">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-baseline justify-between pb-4 border-b border-border/80 gap-1 sm:gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-bold tracking-tight text-text-primary">
            在管交易
          </h2>
          {isLoading ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-surface-subtle px-2 py-0.5 font-mono text-[11px] text-text-muted border border-border">
              <Loader2 className="h-3 w-3 animate-spin text-brand" />
              读取中...
            </span>
          ) : isError ? (
            <span className="inline-flex items-center gap-1 rounded-md bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-rose-600 dark:text-rose-400 border border-rose-500/20">
              <AlertCircle className="h-3 w-3" />
              读取失败
            </span>
          ) : (
            <span className="inline-flex items-center rounded-md bg-brand/10 px-2 py-0.5 font-mono text-xs font-semibold text-brand border border-brand/20">
              {episodes.length} 笔在管
            </span>
          )}
        </div>
        <details className="text-[11px] text-text-muted sm:text-right">
          <summary className="cursor-pointer select-none hover:text-text-secondary focus-visible:outline-2 focus-visible:outline-brand rounded px-1 inline-block">
            账本口径说明
          </summary>
          <div className="mt-1 text-text-muted break-words">
            来自生产 Ticket 账本只读事实 · 严格遵循独立 Netting Domain
          </div>
        </details>
      </div>

      {isLoading ? (
        <div className="py-12 text-center">
          <div className="inline-flex items-center justify-center gap-2 text-xs text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand" />
            <span>正在读取在管持仓事实 (/api/owner/v1/tickets)...</span>
          </div>
        </div>
      ) : isError ? (
        <div className="my-4 flex items-center justify-between rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-xs">
          <div className="flex items-center gap-2.5 text-rose-600 dark:text-rose-400">
            <AlertCircle className="h-4 w-4 flex-none" />
            <div>
              <span className="font-bold">在管持仓事实读取失败: </span>
              <span className="opacity-90">{errorMessage ?? '网络错误或服务端无响应'}</span>
            </div>
          </div>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1 rounded-md border border-rose-500/30 bg-surface px-3 py-1.5 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3 w-3" />
              <span>重试</span>
            </button>
          )}
        </div>
      ) : episodes.length === 0 ? (
        <div className="py-12 text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-surface-subtle text-text-muted mb-2">
            <Shield className="h-5 w-5 opacity-40" />
          </div>
          <p className="text-xs font-semibold text-text-secondary">
            当前无活动持仓
          </p>
          <p className="mt-1 text-[11px] text-text-muted">
            生产策略组在 Observation 持续扫描中，准入前不会占用持仓容量
          </p>
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {episodes.map((ep) => {
            const isLong = ep.side === 'long';
            const management = ep.management_mode ?? 'AUTO';
            const isManual = management === 'MANUAL';
            const isReviewRequired = management === 'REVIEW_REQUIRED';
            const isHighlighted = Boolean(highlightedStrategyId && ep.strategy_id === highlightedStrategyId);
            const reasonInfo = ep.manual_risk_reason ? translateManualRiskReason(ep.manual_risk_reason) : null;
            const deduplicatedAttentionItems = deduplicateEpisodeAttentionItems(ep.attention_items, management);

            return (
              <div
                key={ep.ticket_id}
                data-ticket-id={ep.ticket_id}
                data-strategy-id={ep.strategy_id}
                className={`group relative rounded-lg border bg-surface p-4 hover:border-brand/40 hover:bg-surface-elevated/40 transition-all shadow-2xs ${
                  isHighlighted
                    ? 'border-brand ring-2 ring-brand/40'
                    : isManual || isReviewRequired
                    ? 'border-border border-l-4 border-l-amber-500'
                    : 'border-border'
                }`}
              >
                {/* Tier 1 Row 1: Symbol, Side, Strategy, Stage, PnL, Detail Entry */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                  <div className="flex items-center gap-2.5 min-w-0 flex-wrap">
                    <div
                      className={`flex h-8 w-8 flex-none items-center justify-center rounded-lg ${
                        isLong
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                      }`}
                    >
                      {isLong ? (
                        <ArrowUpRight className="h-4 w-4" />
                      ) : (
                        <ArrowDownRight className="h-4 w-4" />
                      )}
                    </div>

                    <span className="font-mono text-sm font-bold tracking-tight text-text-primary">
                      {ep.symbol}
                    </span>
                    <span
                      className={`font-mono text-[11px] font-bold px-2 py-0.5 rounded uppercase ${
                        isLong
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                      }`}
                    >
                      {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                    </span>

                    <span className="text-xs text-text-muted">
                      <strong className="font-mono font-semibold text-brand">{ep.strategy_id}</strong>
                      {' · '}
                      <span>{ep.strategy_name_zh}</span>
                    </span>

                    <span className="inline-flex items-center gap-1 rounded bg-surface-subtle px-2 py-0.5 text-[11px] text-text-secondary border border-border">
                      <Shield className="h-3 w-3 text-brand" />
                      <span>{ep.lifecycle_stage_zh}</span>
                      <span className="font-mono text-text-muted">
                        ({ep.completed_stage_count}/{ep.total_stage_count})
                      </span>
                    </span>
                  </div>

                  {/* Right: Financial Return + Detail Button */}
                  <div className="flex items-center justify-between sm:justify-end gap-3">
                    {ep.net_r_formatted && ep.net_r_formatted !== '--' && (
                      <span className="font-mono font-bold text-xs text-text-primary">
                        {ep.net_r_formatted}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => onSelectEpisode(ep)}
                      className="inline-flex items-center justify-center gap-1 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-text-primary hover:border-brand hover:text-brand hover:bg-surface-elevated transition-colors shadow-2xs cursor-pointer"
                    >
                      <span>查看交易因果</span>
                      <ChevronRight className="h-3.5 w-3.5 text-text-muted group-hover:text-brand" />
                    </button>
                  </div>
                </div>

                {/* Tier 1 Row 2: Short Status Tags + Expandable Protection/Takeover Disclosure */}
                <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
                  {/* 1. Management Authority Short Tag */}
                  {isManual ? (
                    <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                      <UserCheck className="h-3 w-3" />
                      整笔已转人工管理 · 不再自动处置
                    </span>
                  ) : isReviewRequired ? (
                    <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-700 dark:text-amber-300 border border-amber-500/30">
                      <AlertTriangle className="h-3 w-3" />
                      接管待核实 · 自动处置已暂停
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 rounded bg-surface-subtle px-2 py-0.5 font-mono text-[11px] font-medium text-text-secondary border border-border">
                      <Cpu className="h-3 w-3 text-brand" />
                      程序自动管理
                    </span>
                  )}

                  {/* 2. Short Lock/Restriction Tag if manual_risk_reason is present */}
                  {reasonInfo && (
                    <span className="inline-flex items-center rounded bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-rose-600 dark:text-rose-400 border border-rose-500/20">
                      {reasonInfo.shortTag}
                    </span>
                  )}

                  {/* 3. Non-duplicate independent risk/attention short tags */}
                  {deduplicatedAttentionItems.map((att, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center gap-1 rounded bg-amber-500/10 text-amber-700 dark:text-amber-300 px-2 py-0.5 text-[11px] border border-amber-500/30 font-mono break-words"
                    >
                      <AlertTriangle className="h-3 w-3 flex-none text-amber-500" />
                      <span>{att}</span>
                    </span>
                  ))}

                  {/* 4. Interactive Protection & Fact Disclosure (Tier 2 & Tier 3 on click/tap/keyboard) */}
                  <details className="inline-block text-[11px]">
                    <summary
                      className={`cursor-pointer select-none inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono font-medium border focus-visible:outline-2 focus-visible:outline-brand ${
                        ep.is_protected
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                          : 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30 font-semibold'
                      }`}
                    >
                      {ep.is_protected ? (
                        <ShieldCheck className="h-3.5 w-3.5 flex-none" />
                      ) : (
                        <ShieldAlert className="h-3.5 w-3.5 flex-none" />
                      )}
                      <span>{ep.protection_state ?? (ep.is_protected ? '已确认保护' : '保护待核实')} ›</span>
                    </summary>

                    <div className="mt-2 rounded-md border border-border bg-surface-subtle p-2.5 text-[11px] text-text-secondary space-y-1 break-words">
                      {isManual && (
                        <p className="leading-relaxed text-amber-700 dark:text-amber-300">
                          <strong>整笔已转人工管理 · 外部干预已触发永久接管：</strong>
                          既有挂单是否有效以交易所最新订单事实为准；程序不再自动退出或修改保护。
                        </p>
                      )}
                      {isReviewRequired && (
                        <p className="leading-relaxed text-amber-700 dark:text-amber-300">
                          <strong>接管待核实 · 自动处置已暂停：</strong>
                          订单或持仓事实待核实，程序已暂停该笔自动处置；以交易所最新对账为准。
                        </p>
                      )}
                      {reasonInfo && (
                        <p className="font-mono text-rose-600 dark:text-rose-400 break-all">
                          新增开仓受限原因：{reasonInfo.raw}
                        </p>
                      )}
                      <div className="flex flex-wrap items-center gap-3 font-mono text-text-muted pt-0.5">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          发出时间: {ep.issued_at_formatted}
                        </span>
                        <span>Ticket: #{ep.ticket_id.slice(-8)}</span>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
            );
          })}

          {unloadedActiveCount > 0 && (
            <div className="mt-3 flex items-center justify-between rounded-md border border-border bg-surface-subtle p-3 text-xs text-text-secondary font-sans">
              <span>
                另有 <strong className="font-mono text-text-primary">{unloadedActiveCount}</strong> 笔在管持仓未在首页展示 (受首屏 100 笔限制，遵循分页契约)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
