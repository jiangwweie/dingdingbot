import React, { useState } from 'react';
import type { ReviewCenterItem } from '../../types/review.ts';
import {
  formatReviewMoneyMetric,
  formatExecutionClassification,
  formatReviewStatus,
  formatReviewExitReason,
  formatReviewSentenceTemplate,
} from '../../mapping/reviewMapping.ts';
import { cleanSymbol } from '../../utils/symbol.ts';
import {
  ChevronRight,
  ChevronDown,
  ArrowUpRight,
  ArrowDownRight,
  ExternalLink,
  AlertTriangle,
  FileText,
  Clock,
} from 'lucide-react';

interface ReviewTableProps {
  items: ReviewCenterItem[];
  onSelectTicket: (ticketId: string) => void;
  isLoading?: boolean;
}

export const ReviewTable: React.FC<ReviewTableProps> = ({
  items,
  onSelectTicket,
  isLoading = false,
}) => {
  const [expandedTicketIds, setExpandedTicketIds] = useState<Set<string>>(new Set());

  const toggleExpand = (ticketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedTicketIds((prev) => {
      const next = new Set(prev);
      if (next.has(ticketId)) {
        next.delete(ticketId);
      } else {
        next.add(ticketId);
      }
      return next;
    });
  };

  if (!isLoading && items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-surface p-8 text-center text-xs text-text-muted">
        <Clock className="mx-auto h-8 w-8 text-text-muted/50 mb-2" />
        <p className="font-semibold text-text-secondary">当前筛选范围内没有完成 Ticket 复盘记录</p>
        <p className="mt-1 text-[11px]">请调整时间范围、策略组或复盘状态后重新查询。</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs">
      <div className="overflow-x-auto">
        <table data-testid="review-table" className="w-full text-left text-xs font-sans">
          <thead>
            <tr className="border-b border-border bg-surface-subtle font-mono text-[11px] uppercase tracking-wider text-text-muted">
              <th scope="col" className="px-3 py-3 font-semibold">
                标的 / 方向
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                策略组
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                执行质量
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                退出原因
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                净盈亏 (Net PnL)
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                净回报 (Net R)
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-right">
                费用 / 资金费
              </th>
              <th scope="col" className="px-3 py-3 font-semibold">
                证据状态
              </th>
              <th scope="col" className="px-3 py-3 font-semibold text-center">
                关注项
              </th>
              <th scope="col" className="px-4 py-3 font-semibold text-right">
                因果追溯
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border font-sans">
            {items.map((item) => {
              const expanded = expandedTicketIds.has(item.ticket_id);
              const isLong = item.position_side === 'long';
              const symbol = cleanSymbol(item.exchange_instrument_id);
              const execClass = formatExecutionClassification(item.review.execution_classification);
              const reviewStatus = formatReviewStatus(item.review.review_status);
              const exitReason = formatReviewExitReason(item.review.exit_reason);
              const pnl = formatReviewMoneyMetric(item.review.economic_summary.net_pnl, { sign: true });
              const r = formatReviewMoneyMetric(item.review.economic_summary.net_r, { sign: true, fractionDigits: 4 });
              const fees = formatReviewMoneyMetric(item.review.economic_summary.fees);
              const funding = formatReviewMoneyMetric(item.review.economic_summary.funding);
              const attentionCount = item.review.attention_items?.length || 0;

              return (
                <React.Fragment key={item.ticket_id}>
                  <tr
                    data-ticket-id={item.ticket_id}
                    className={`group transition-colors cursor-pointer ${
                      expanded ? 'bg-surface-elevated/60' : 'hover:bg-surface-elevated'
                    }`}
                    onClick={(e) => toggleExpand(item.ticket_id, e)}
                  >
                    {/* 1. Symbol & Side & Expand */}
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          aria-expanded={expanded}
                          aria-label={`${expanded ? '收起' : '展开'} ${symbol} ${item.position_side.toUpperCase()} 复盘`}
                          onClick={(e) => toggleExpand(item.ticket_id, e)}
                          className="grid h-5 w-5 flex-none place-items-center rounded bg-transparent p-0 text-text-muted hover:bg-surface-subtle hover:text-text-primary transition-colors cursor-pointer"
                        >
                          {expanded ? (
                            <ChevronDown className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5" />
                          )}
                        </button>
                        <div className="flex flex-col min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="font-mono font-bold text-text-primary truncate">
                              {symbol}
                            </span>
                            <span
                              className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.2 font-mono text-[10px] font-bold uppercase ${
                                isLong
                                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                                  : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                              }`}
                            >
                              {isLong ? (
                                <ArrowUpRight className="h-3 w-3" />
                              ) : (
                                <ArrowDownRight className="h-3 w-3" />
                              )}
                              <span>{item.position_side}</span>
                            </span>
                          </div>
                          <span className="font-mono text-[10px] text-text-muted truncate mt-0.5" title={item.ticket_id}>
                            {item.ticket_id}
                          </span>
                        </div>
                      </div>
                    </td>

                    {/* 2. Strategy Group */}
                    <td className="px-3 py-3 whitespace-nowrap">
                      <span className="rounded bg-brand/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-brand border border-brand/20">
                        {item.strategy_group_id}
                      </span>
                    </td>

                    {/* 3. Execution Classification */}
                    <td className="px-3 py-3 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium border ${
                          execClass.tone === 'success'
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                            : execClass.tone === 'attention'
                            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                            : execClass.tone === 'danger'
                            ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                            : 'bg-surface-subtle text-text-secondary border-border'
                        }`}
                        title={item.review.execution_classification}
                      >
                        {execClass.label}
                      </span>
                    </td>

                    {/* 4. Exit Reason */}
                    <td className="px-3 py-3">
                      <span
                        className="block max-w-[150px] truncate text-[11px] text-text-secondary"
                        title={exitReason.raw ?? '—'}
                      >
                        {exitReason.label}
                      </span>
                    </td>

                    {/* 5. Net PnL */}
                    <td className="px-3 py-3 text-right whitespace-nowrap">
                      <span
                        className={`font-mono font-bold tabular-number ${
                          pnl.isUnavailable
                            ? 'text-text-muted'
                            : pnl.isPositive
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-rose-600 dark:text-rose-400'
                        }`}
                        title={pnl.formatted}
                      >
                        {pnl.formatted}
                      </span>
                    </td>

                    {/* 6. Net R */}
                    <td className="px-3 py-3 text-right whitespace-nowrap">
                      <span
                        className={`font-mono font-semibold tabular-number ${
                          r.isUnavailable
                            ? 'text-text-muted'
                            : r.isPositive
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-rose-600 dark:text-rose-400'
                        }`}
                        title={r.formatted}
                      >
                        {r.formatted}
                      </span>
                    </td>

                    {/* 7. Fees / Funding */}
                    <td className="px-3 py-3 text-right whitespace-nowrap font-mono text-[11px] text-text-muted">
                      <div>{fees.formatted}</div>
                      <div className="text-[10px]">{funding.formatted}</div>
                    </td>

                    {/* 8. Evidence Status */}
                    <td className="px-3 py-3 whitespace-nowrap">
                      <div className="flex flex-col gap-0.5">
                        <span
                          className={`inline-flex items-center rounded px-1.5 py-0.2 text-[10px] font-semibold border ${
                            reviewStatus.tone === 'success'
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                              : reviewStatus.tone === 'danger'
                              ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                              : 'bg-surface-subtle text-text-secondary border-border'
                          }`}
                        >
                          {reviewStatus.label}
                        </span>
                        <span className="text-[10px] text-text-muted">
                          {item.review.evidence.length} 项证据
                        </span>
                      </div>
                    </td>

                    {/* 9. Attention Items */}
                    <td className="px-3 py-3 text-center whitespace-nowrap">
                      {attentionCount > 0 ? (
                        <span className="inline-flex items-center gap-1 rounded bg-rose-500/10 px-2 py-0.5 font-mono text-[11px] font-bold text-rose-600 dark:text-rose-400 border border-rose-500/20">
                          <AlertTriangle className="h-3 w-3" />
                          <span>{attentionCount}</span>
                        </span>
                      ) : (
                        <span className="text-text-muted">—</span>
                      )}
                    </td>

                    {/* 10. Causality Actions */}
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectTicket(item.ticket_id);
                        }}
                        className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-[11px] font-medium text-brand hover:bg-brand/10 hover:border-brand/30 transition-colors shadow-2xs cursor-pointer"
                      >
                        <span>因果与 K 线</span>
                        <ExternalLink className="h-3 w-3" />
                      </button>
                    </td>
                  </tr>

                  {/* Expanded Detail Row */}
                  {expanded && (
                    <tr className="bg-surface-subtle/50">
                      <td colSpan={10} className="px-6 py-4">
                        <div className="space-y-3 rounded-lg border border-border bg-surface p-4 shadow-2xs">
                          {/* Title & Ticket Identity */}
                          <div className="flex items-center justify-between border-b border-border pb-2.5">
                            <div className="flex items-center gap-2">
                              <FileText className="h-4 w-4 text-brand" />
                              <h4 className="text-xs font-bold text-text-primary">
                                复盘因果评估陈述与可追溯证据
                              </h4>
                            </div>
                            <button
                              type="button"
                              onClick={() => onSelectTicket(item.ticket_id)}
                              className="inline-flex items-center gap-1 text-[11px] font-medium text-brand hover:underline"
                            >
                              <span>在因果抽屉中查看完整链路</span>
                              <ExternalLink className="h-3 w-3" />
                            </button>
                          </div>

                          {/* Review Sentences */}
                          <div className="space-y-2">
                            {item.review.sentences.map((sent, sIdx) => {
                              const tmpl = formatReviewSentenceTemplate(sent.template_id);
                              return (
                                <div
                                  key={sIdx}
                                  className="rounded border border-border bg-surface-subtle/80 p-3 space-y-1.5"
                                >
                                  <div className="flex items-center gap-2">
                                    <span
                                      className={`rounded px-1.5 py-0.2 font-mono text-[10px] font-semibold border ${
                                        tmpl.tone === 'success'
                                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                                          : tmpl.tone === 'danger'
                                          ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
                                          : tmpl.tone === 'attention'
                                          ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                                          : 'bg-surface text-text-secondary border-border'
                                      }`}
                                    >
                                      {tmpl.label}
                                    </span>
                                  </div>
                                  <p className="text-xs text-text-primary leading-relaxed">
                                    {sent.text}
                                  </p>

                                  {/* Sentence Evidence Refs */}
                                  {sent.evidence.length > 0 && (
                                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                                      <span className="text-[10px] text-text-muted">证据项:</span>
                                      {sent.evidence.map((ref, rIdx) => (
                                        <button
                                          key={`${ref.kind}:${ref.identity}:${rIdx}`}
                                          type="button"
                                          onClick={() => onSelectTicket(item.ticket_id)}
                                          className="inline-flex items-center gap-1 rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-text-secondary border border-border hover:border-brand/40 hover:text-brand transition-colors cursor-pointer"
                                          title={`查看证据 ${ref.identity} (${ref.kind})`}
                                        >
                                          <span className="text-text-muted uppercase text-[9px]">{ref.kind}:</span>
                                          <span className="font-semibold">{ref.identity}</span>
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>

                          {/* Attention Banner if present */}
                          {attentionCount > 0 && (
                            <div className="rounded border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-700 dark:text-rose-300 space-y-1">
                              <div className="flex items-center gap-1.5 font-bold">
                                <AlertTriangle className="h-4 w-4 text-rose-500" />
                                <span>关注项提示 ({attentionCount})</span>
                              </div>
                              <ul className="list-disc list-inside space-y-0.5 text-[11px] font-mono pl-1">
                                {item.review.attention_items.map((att, aIdx) => (
                                  <li key={aIdx}>{att}</li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {/* Final Conclusion if present */}
                          {item.review.final_conclusion && (
                            <div className="rounded border border-border bg-surface-subtle p-2.5 text-xs text-text-secondary">
                              <strong className="text-text-primary">结论摘要: </strong>
                              <span>{item.review.final_conclusion}</span>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
