import React, { useState, useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Clock, ShieldCheck, Database, Layers, Info } from 'lucide-react';
import type { SelectionDiagnosticData } from '../types/controls';
import { cleanSymbol } from '../hooks/useOverviewData';
import {
  formatUtcDateTime,
  formatRelativeCountdown,
  formatAgeFromTimestamp,
} from '../utils/time';

interface SelectionDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  data: SelectionDiagnosticData;
}

export const SelectionDrawer: React.FC<SelectionDrawerProps> = ({
  open,
  onOpenChange,
  data,
}) => {
  // Pure local timer for live countdown - never re-triggers API requests
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!open) return;
    const interval = setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => clearInterval(interval);
  }, [open]);

  const isOrb = data.kind === 'orb';

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-xs transition-opacity" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border bg-surface shadow-2xl transition-transform duration-200">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-surface">
            <div>
              <div className="flex items-center gap-2">
                <Dialog.Title className="text-sm font-bold text-text-primary">
                  {data.strategy_group_id} 动态选币底层工程诊断
                </Dialog.Title>
                <span className="rounded bg-surface-subtle px-2 py-0.5 font-mono text-xs text-text-muted border border-border">
                  控制版本: v{data.control_version}
                </span>
              </div>
              <Dialog.Description className="mt-0.5 text-xs text-text-secondary">
                服务于工程排障的底层指标与标的池仲裁证据；日常监控无需常驻。
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded p-1 text-text-muted hover:bg-surface-subtle hover:text-text-primary transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
            {/* Section 1: Authority & State */}
            <div>
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-text-primary">
                <ShieldCheck className="h-4 w-4 text-brand" />
                权威凭证与周期锚点
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2.5 font-mono">
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">实际 Authority Outcome</span>
                  <div className="mt-1 font-bold text-text-primary text-xs">
                    {isOrb ? data.authority_outcome ?? '缺失 / 未生效' : data.current_authority_outcome ?? '缺失 / 未生效'}
                  </div>
                </div>

                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">权威状态 (Authority Health)</span>
                  <div className="mt-1 font-bold text-text-primary text-xs">
                    {data.authority_status_zh}
                  </div>
                </div>

                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Rollback Baseline ID</span>
                  <div className="mt-1 truncate text-text-secondary text-xs" title={data.rollback_baseline_id ?? '无'}>
                    {data.rollback_baseline_id ?? '—'}
                  </div>
                </div>

                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Selection Epoch ID</span>
                  <div className="mt-1 truncate text-text-secondary text-xs" title={data.selection_epoch_id ?? '无'}>
                    {data.selection_epoch_id ?? '—'}
                  </div>
                </div>

                {/* Authority Expiration */}
                <div className="rounded border border-border bg-surface-subtle p-3 col-span-2">
                  <span className="text-xs text-text-muted font-sans">交易权限有效期 (Authority Expiration)</span>
                  <div className="mt-1 font-bold text-text-primary text-xs flex flex-wrap items-center gap-2">
                    {isOrb ? (
                      data.authority_expires_at_ms ? (
                        <>
                          <span>{formatUtcDateTime(data.authority_expires_at_ms)}</span>
                          <span className="text-status-amber font-sans font-medium">
                            ({formatRelativeCountdown(data.authority_expires_at_ms, nowMs)})
                          </span>
                        </>
                      ) : (
                        <span className="text-text-muted font-sans font-normal">权威未生效 / 缺失</span>
                      )
                    ) : (
                      data.membership_valid_until_ms ? (
                        <>
                          <span>{formatUtcDateTime(data.membership_valid_until_ms)}</span>
                          <span className="text-status-amber font-sans font-medium">
                            ({formatRelativeCountdown(data.membership_valid_until_ms, nowMs)})
                          </span>
                        </>
                      ) : (
                        <span className="text-text-muted font-sans font-normal">权威未生效 / 缺失</span>
                      )
                    )}
                  </div>
                </div>

                {/* SOR-1H Snapshot Expiration (distinctly labeled) */}
                {isOrb && (
                  <div className="rounded border border-border bg-surface-subtle p-3 col-span-2">
                    <span className="text-xs text-text-muted font-sans">Snapshot 快照有效期 (独立于交易权限)</span>
                    <div className="mt-1 font-bold text-text-secondary text-xs flex flex-wrap items-center gap-2">
                      {data.snapshot_expires_at_ms ? (
                        <>
                          <span>{formatUtcDateTime(data.snapshot_expires_at_ms)}</span>
                          <span className="text-text-muted font-sans font-normal">
                            ({formatRelativeCountdown(data.snapshot_expires_at_ms, nowMs)})
                          </span>
                        </>
                      ) : (
                        <span className="text-text-muted font-sans font-normal">接口未提供快照有效期</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Section 2: Freshness & Ages */}
            <div>
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-text-primary">
                <Clock className="h-4 w-4 text-status-blue" />
                事实新鲜度与时间戳
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2.5 font-mono">
                {isOrb ? (
                  <>
                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Decision 决策年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.snapshot_decision_at_ms ? (
                          <>
                            {formatAgeFromTimestamp(data.snapshot_decision_at_ms, nowMs).seconds}
                            <span className="ml-1 text-text-muted font-sans">
                              ({formatAgeFromTimestamp(data.snapshot_decision_at_ms, nowMs).labelZh})
                            </span>
                          </>
                        ) : (
                          '未知'
                        )}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Cutoff 截断年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.snapshot_cutoff_at_ms ? (
                          <>
                            {formatAgeFromTimestamp(data.snapshot_cutoff_at_ms, nowMs).seconds}
                            <span className="ml-1 text-text-muted font-sans">
                              ({formatAgeFromTimestamp(data.snapshot_cutoff_at_ms, nowMs).labelZh})
                            </span>
                          </>
                        ) : (
                          '未知'
                        )}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Snapshot 创建年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.snapshot_created_at_ms ? (
                          <>
                            {formatAgeFromTimestamp(data.snapshot_created_at_ms, nowMs).seconds}
                            <span className="ml-1 text-text-muted font-sans">
                              ({formatAgeFromTimestamp(data.snapshot_created_at_ms, nowMs).labelZh})
                            </span>
                          </>
                        ) : (
                          '未知'
                        )}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">首个合格收线 (First Eligible Close)</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.first_eligible_close_time_ms
                          ? formatUtcDateTime(data.first_eligible_close_time_ms)
                          : '—'}
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Snapshot 完成年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.latest_successful_completion_age_ms != null ? (
                          <>
                            {Math.round(data.latest_successful_completion_age_ms / 1000)}s
                            <span className="ml-1 text-text-muted font-sans">
                              ({(data.latest_successful_completion_age_ms / 3600000).toFixed(1)}h 前)
                            </span>
                          </>
                        ) : (
                          '未知'
                        )}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Cutoff 截断年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.latest_successful_cutoff_age_ms != null
                          ? `${Math.round(data.latest_successful_cutoff_age_ms / 1000)}s`
                          : '未知'}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">Membership 来源年龄</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.membership_source_age_ms != null
                          ? `${Math.round(data.membership_source_age_ms / 1000)}s`
                          : '未知'}
                      </div>
                    </div>

                    <div className="rounded border border-border bg-surface-subtle p-3">
                      <span className="text-xs text-text-muted font-sans">连续错过期数</span>
                      <div className="mt-1 text-text-primary text-xs">
                        {data.consecutive_missed_periods ?? 0} 周期
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Section 3: Materialization & Vacuum */}
            <div>
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-text-primary">
                <Layers className="h-4 w-4 text-status-amber" />
                物化与 Vacuum 隔离
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2.5 font-mono">
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">物化状态 (Materialization)</span>
                  <div className="mt-1 font-bold text-text-primary text-xs">
                    {data.materialization_state}
                  </div>
                </div>

                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Vacuum 隔离状态</span>
                  <div className="mt-1 font-bold text-text-primary text-xs">
                    {data.vacuum_state}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 4: Members & Candidate Pool Audit */}
            <div>
              {isOrb ? (
                <>
                  <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-text-primary">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-status-green" />
                      入选标的明细与候选统计 (候选池 {data.candidate_count} 标的)
                    </div>
                    <span className="font-mono text-xs text-text-muted">
                      {data.selected_count} 入选 / {Math.max(0, data.candidate_count - data.selected_count)} 未入选
                    </span>
                  </div>

                  <div className="mt-2.5 divide-y divide-border rounded border border-border bg-surface-subtle font-mono">
                    {data.selected_members.length > 0 ? (
                      data.selected_members.map((symbol) => (
                        <div
                          key={symbol}
                          className="flex items-center justify-between px-3.5 py-2.5 text-xs"
                        >
                          <div className="flex items-center gap-2.5">
                            <span className="h-2 w-2 rounded-full bg-status-green" />
                            <strong className="text-text-primary">{cleanSymbol(symbol)}</strong>
                          </div>
                          <span className="text-status-green font-sans font-semibold">
                            最新快照入选 (Snapshot Selected)
                          </span>
                        </div>
                      ))
                    ) : (
                      <div className="px-3.5 py-4 text-center text-xs text-text-muted font-sans">
                        当前快照暂无入选标的 (空集入选 / VALID_EMPTY)
                      </div>
                    )}

                    {/* Factual disclosure about unselected candidates */}
                    <div className="flex items-start gap-2 px-3.5 py-3 text-xs font-sans text-text-muted bg-surface/60 border-t border-border">
                      <Info className="h-4 w-4 flex-none text-text-secondary mt-0.5" />
                      <div>
                        <p className="font-medium text-text-secondary">
                          候选池统计：共 {data.candidate_count} 个候选标的，当前快照入选 {data.selected_count} 个。
                        </p>
                        <p className="mt-0.5 text-[11px] text-text-muted leading-relaxed">
                          其余 {Math.max(0, data.candidate_count - data.selected_count)} 个标的未入选。后端 API 仅返回入选标的名单，未提供未入选标的的明细名单与过滤归因依据（不伪造未入选归因）。
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-text-primary">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-status-green" />
                      当前策略在役范围成员 ({data.members.length} 个配置标的)
                    </div>
                    <span className="font-mono text-xs text-text-muted">
                      {data.latest_selected_count ?? data.members.length} 入选 /{' '}
                      {Math.max(0, (data.latest_ready_count ?? data.members.length) - (data.latest_selected_count ?? data.members.length))} 未入选
                    </span>
                  </div>

                  <div className="mt-2.5 divide-y divide-border rounded border border-border bg-surface-subtle font-mono">
                    {data.members.map((member) => (
                      <div
                        key={member.facts.exchange_instrument_id}
                        className="flex items-center justify-between px-3.5 py-2.5 text-xs"
                      >
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              member.first_blocker === null ? 'bg-status-green' : 'bg-status-amber'
                            }`}
                          />
                          <strong className="text-text-primary">
                            {member.facts.exchange_instrument_id}
                          </strong>
                        </div>

                        <div className="text-right">
                          {member.first_blocker === null ? (
                            <span className="text-status-green font-sans font-semibold">
                              在役就绪 (Ready)
                            </span>
                          ) : (
                            <span className="text-status-amber font-sans">
                              就绪受阻 · {member.first_blocker}
                            </span>
                          )}
                        </div>
                      </div>
                    ))}

                    {/* Factual disclosure about generic candidate pool */}
                    <div className="flex items-start gap-2 px-3.5 py-3 text-xs font-sans text-text-muted bg-surface/60 border-t border-border">
                      <Info className="h-4 w-4 flex-none text-text-secondary mt-0.5" />
                      <div>
                        <p className="font-medium text-text-secondary">
                          当前列表为本策略组在役范围事实配置成员。
                        </p>
                        <p className="mt-0.5 text-[11px] text-text-muted leading-relaxed">
                          候选全量名单、排名及仲裁归因依据后端接口未提供。
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Footer */}
          <div className="border-t border-border bg-surface px-6 py-3.5 text-right">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded border border-border-strong bg-surface-subtle px-4 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors cursor-pointer"
            >
              关闭诊断抽屉
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
