import { priceFacts } from '../../mapping/tradeTruth';
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchTicketCausality, causalityQueryKey } from '../../api/ticketsApi';
import type { TradeEpisodeSummary } from '../../types/overview';
import type { TradeEpisode } from '../../types/trades';
import {
  X,
  CheckCircle2,
  CircleDot,
  Copy,
  Check,
  AlertTriangle,
  Code,
  Terminal,
  FileText,
} from 'lucide-react';


interface CausalityDrawerProps {
  episode: TradeEpisodeSummary | TradeEpisode | null;
  onClose: () => void;
}

const STAGE_LABELS_ZH: Record<string, string> = {
  signal: '信号 (Signal)',
  admission: '准入评估 (Admission)',
  entry: '入场下单 (Entry)',
  protection: '保护安装 (Protection)',
  tp_runner: '止盈 / Runner (TP/Runner)',
  exit: '退出执行 (Exit)',
  reconciliation: '账本对账 (Reconciliation)',
  review: '事后复盘 (Review)',
};


export const CausalityDrawer: React.FC<CausalityDrawerProps> = ({ episode, onClose }) => {
  const [activeTab, setActiveTab] = useState<'timeline' | 'commands' | 'events' | 'incidents' | 'evidence'>('timeline');
  const [copied, setCopied] = useState(false);

  const ticketId = episode?.ticket_id ?? '';

  const { data, isLoading, isError, error } = useQuery({
    queryKey: causalityQueryKey(ticketId),
    queryFn: () => fetchTicketCausality(ticketId),
    enabled: Boolean(ticketId),
    staleTime: 10_000,
  });

  if (!episode) return null;

  const causality = data?.data;
  const isLong = episode.side === 'long';

  const handleCopyJson = () => {
    if (!causality) return;
    navigator.clipboard.writeText(JSON.stringify(causality, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      data-testid="causality-drawer"
      className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      aria-labelledby="slide-over-title"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="absolute inset-y-0 right-0 flex max-w-full pl-10">
        <div
          className="w-screen max-w-2xl bg-surface border-l border-border shadow-2xl flex flex-col h-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* 1. Header */}
          <div className="border-b border-border bg-surface-subtle p-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded bg-brand/10 px-2 py-0.5 font-mono text-xs font-bold text-brand">
                  {episode.strategy_id}
                </span>
                <span className="font-mono text-sm font-bold text-text-primary">
                  {episode.symbol}
                </span>
                <span
                  className={`font-mono text-[11px] font-semibold px-2 py-0.5 rounded uppercase ${
                    isLong
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {isLong ? '做多 (LONG)' : '做空 (SHORT)'}
                </span>
                <span className="font-mono text-xs text-text-muted">
                  #{episode.ticket_id.slice(-8)}
                </span>
              </div>

              <button
                type="button"
                onClick={onClose}
                className="rounded p-1 text-text-muted hover:bg-surface-elevated hover:text-text-primary transition-colors"
                aria-label="关闭抽屉"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Subheader facts */}
            <div className="mt-2.5 flex flex-wrap items-baseline justify-between text-xs gap-2">
              <div className="flex flex-wrap items-center gap-2 text-text-secondary">
                <span>{episode.strategy_name_zh}</span>
                <span>·</span>
                <span>
                  当前阶段:{' '}
                  <strong data-testid="causality-current-stage" className="text-brand font-semibold">
                    {causality?.current_stage
                      ? STAGE_LABELS_ZH[causality.current_stage] ?? causality.current_stage
                      : episode.lifecycle_stage_zh}
                  </strong>
                </span>
                {causality?.exit_reason && (
                  <span className="inline-flex items-center rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-text-muted">
                    退出原因: {causality.exit_reason.label || causality.exit_reason.code}
                  </span>
                )}
                {episode.net_r_formatted &&
                  episode.net_r_formatted !== '—' &&
                  episode.net_r_formatted !== '持仓中 · 未结' && (
                    <span className="font-mono font-bold text-text-primary">
                      {episode.net_r_formatted} ({episode.net_pnl_formatted})
                    </span>
                  )}
              </div>
              <span className="font-mono text-text-muted text-[11px]" title={episode.ticket_id} data-ticket-id={episode.ticket_id}>
                Ticket ID: {episode.ticket_id} · 发出时间: {episode.issued_at_formatted}
              </span>
            </div>

            {/* Price Plan Quick Bar (if available from real causality) */}
            {causality?.price_plan && (
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
                <div data-testid="causality-entry-price" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">实际入场执行价</div>
                  <div data-testid="plan-value" className="font-bold text-text-primary mt-0.5">
                    {priceFacts(causality.price_plan).actual}
                  </div>
                </div>
                <div className="rounded border border-border bg-surface p-2">
                  <div className="text-text-muted">计划参考入场价</div>
                  <div data-testid="causality-reference-price">{priceFacts(causality.price_plan).reference}</div>
                </div>
                <div data-testid="causality-initial-stop" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">初始止损价</div>
                  <div data-testid="plan-value" className="font-bold text-rose-600 dark:text-rose-400 mt-0.5">
                    {priceFacts(causality.price_plan).initialStop}
                  </div>
                </div>
                <div data-testid="causality-active-stop" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">当前活动止损</div>
                  <div data-testid="plan-value" className="font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                    {priceFacts(causality.price_plan).activeStop}
                  </div>
                </div>
                <div data-testid="causality-quantity" className="rounded border border-border bg-surface p-2">
                  <div className="text-[10px] text-text-muted uppercase">头寸数量</div>
                  <div data-testid="plan-value" className="font-bold text-text-primary mt-0.5">
                    {causality.price_plan.ticket_quantity ?? '未取得'}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 2. Navigation Tabs */}
          <div className="flex border-b border-border bg-surface px-5 text-xs">
            <button
              type="button"
              onClick={() => setActiveTab('timeline')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors ${
                activeTab === 'timeline'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              8 阶段时间线
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('commands')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === 'commands'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Terminal className="h-3.5 w-3.5" />
              <span>底层命令 ({causality?.raw_commands?.length ?? 0})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('events')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === 'events'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>事件证据 ({causality?.raw_events?.length ?? 0})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('evidence')}
              className={`py-2.5 px-3 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === 'evidence'
                  ? 'border-brand text-brand font-semibold'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <Code className="h-3.5 w-3.5" />
              <span>审计证据</span>
            </button>
          </div>

          {/* 3. Main Body */}
          <div className="flex-1 overflow-y-auto p-5">
            {isLoading ? (
              <div className="py-20 text-center">
                <div className="inline-block h-6 w-6 border-2 border-brand/30 border-t-brand rounded-full animate-spin mb-3" />
                <p className="text-xs text-text-secondary font-medium">
                  正在读取 /tickets/{ticketId}/causality 真实因果链...
                </p>
              </div>
            ) : isError ? (
              <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 text-xs text-danger">
                <div className="flex items-center gap-2 font-bold mb-1">
                  <AlertTriangle className="h-4 w-4" />
                  <span>因果事实读取失败</span>
                </div>
                <p>{error instanceof Error ? error.message : '无法获取该 Ticket 的 causality 快照'}</p>
              </div>
            ) : causality ? (
              <>
                {/* TAB 1: 8 Stages Timeline */}
                {activeTab === 'timeline' && (
                  <div className="space-y-4">
                    <div className="relative pl-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                      {causality.stages.map((st, idx) => {
                        const isComplete = st.status === 'complete';
                        const isCurrent = st.status === 'current';
                        const isSkipped = st.status === 'skipped';


                        return (
                          <div key={st.key} className="relative mb-5 last:mb-0 group">
                            {/* Circle Node Icon */}
                            <div
                              className={`absolute -left-6 top-0 flex h-4 w-4 items-center justify-center rounded-full bg-surface border-2 ${
                                isComplete
                                  ? 'border-emerald-500 text-emerald-500'
                                  : isCurrent
                                  ? 'border-brand text-brand ring-4 ring-brand/10'
                                  : isSkipped
                                  ? 'border-text-muted text-text-muted'
                                  : 'border-border text-border'
                              }`}
                            >
                              {isComplete ? (
                                <CheckCircle2 className="h-3 w-3 fill-emerald-500 text-surface" />
                              ) : isCurrent ? (
                                <CircleDot className="h-3 w-3 fill-brand text-surface animate-pulse" />
                              ) : (
                                <span className="h-1.5 w-1.5 rounded-full bg-border" />
                              )}
                            </div>

                            {/* Stage Content */}
                            <div className="rounded border border-border bg-surface-subtle p-3 hover:border-brand/40 transition-colors">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono text-[11px] font-bold text-text-primary">
                                    Stage {idx + 1}: {STAGE_LABELS_ZH[st.key] ?? st.label}
                                  </span>
                                  <span
                                    className={`font-mono text-[10px] font-semibold px-1.5 py-0.2 rounded uppercase ${
                                      isComplete
                                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                        : isCurrent
                                        ? 'bg-brand/10 text-brand'
                                        : 'bg-surface text-text-muted border border-border'
                                    }`}
                                  >
                                    {st.status}
                                  </span>
                                </div>
                                {st.duration_ms !== null && (
                                  <span className="font-mono text-[10px] text-text-muted">
                                    耗时: {st.duration_ms}ms
                                  </span>
                                )}
                              </div>

                              <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                                {st.summary}
                              </p>

                              {st.started_at_ms && (
                                <div className="mt-2 flex items-center gap-3 text-[10px] text-text-muted font-mono">
                                  <span>
                                    触发: {new Date(st.started_at_ms).toLocaleTimeString('zh-CN', { hour12: false })}
                                  </span>
                                  {st.completed_at_ms && (
                                    <span>
                                      完成: {new Date(st.completed_at_ms).toLocaleTimeString('zh-CN', { hour12: false })}
                                    </span>
                                  )}
                                  {st.evidence?.length > 0 && (
                                    <span>{st.evidence.length} 项证据锚点</span>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* TAB 2: Raw Commands */}
                {activeTab === 'commands' && (
                  <div className="space-y-2 font-mono text-xs">
                    {causality.raw_commands.length === 0 ? (
                      <div className="py-10 text-center text-text-muted font-sans">
                        暂无底层交易所命令生成
                      </div>
                    ) : (
                      causality.raw_commands.map((cmd) => (
                        <div key={cmd.command_id} className="rounded border border-border bg-surface-subtle p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-text-primary">{cmd.command_kind}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface border border-border text-brand font-semibold">
                              {cmd.status}
                            </span>
                          </div>
                          <div className="text-[11px] text-text-secondary space-y-0.5">
                            <div>Command ID: {cmd.command_id} · Gen: {cmd.generation}</div>
                            <div className="text-text-muted">
                              时间: {cmd.created_at_ms ? new Date(cmd.created_at_ms).toLocaleTimeString() : '--'}
                            </div>
                            {cmd.request_payload && (
                              <pre className="mt-1 p-1.5 rounded bg-surface border border-border text-[10px] overflow-x-auto text-text-muted">
                                {JSON.stringify(cmd.request_payload, null, 2)}
                              </pre>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* TAB 3: Raw Events */}
                {activeTab === 'events' && (
                  <div className="space-y-2 font-mono text-xs">
                    {causality.raw_events.length === 0 ? (
                      <div className="py-10 text-center text-text-muted font-sans">
                        暂无生命周期事件记录
                      </div>
                    ) : (
                      causality.raw_events.map((evt) => (
                        <div key={evt.event_id} className="rounded border border-border bg-surface-subtle p-3">
                          <div className="flex items-center justify-between mb-1">
                            <span className="font-bold text-text-primary">
                              {evt.event_type} <span className="text-text-muted text-[10px]">({evt.stage})</span>
                            </span>
                            <span className="text-[10px] text-text-muted">
                              {evt.occurred_at_ms ? new Date(evt.occurred_at_ms).toLocaleTimeString() : '--'}
                            </span>
                          </div>
                          {evt.payload && (
                            <pre className="mt-1 p-1.5 rounded bg-surface border border-border text-[10px] overflow-x-auto text-text-muted">
                              {JSON.stringify(evt.payload, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                )}


                {/* TAB 4: Evidence Refs & Raw JSON */}
                {activeTab === 'evidence' && (
                  <div className="space-y-3 font-mono text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-sans text-xs font-bold text-text-primary">
                        完整审计证据引用与 JSON 快照
                      </span>
                      <button
                        type="button"
                        onClick={handleCopyJson}
                        className="inline-flex items-center gap-1.5 rounded border border-border bg-surface px-2.5 py-1 text-xs text-text-secondary hover:text-text-primary transition-colors"
                      >
                        {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{copied ? '已复制' : '复制 JSON'}</span>
                      </button>
                    </div>

                    <pre className="max-h-96 overflow-auto rounded border border-border bg-surface-subtle p-3 text-[11px] text-text-secondary">
                      {JSON.stringify(causality, null, 2)}
                    </pre>
                  </div>
                )}
              </>
            ) : null}
          </div>

          {/* 4. Footer */}
          <div className="border-t border-border bg-surface-subtle p-4 flex items-center justify-between text-xs">
            <span className="text-[11px] text-text-muted">
              遵循 L1 → L2 → L3 → L4 渐进披露 · 真实不可变因果链
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-border bg-surface px-4 py-1.5 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors"
            >
              关闭
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
