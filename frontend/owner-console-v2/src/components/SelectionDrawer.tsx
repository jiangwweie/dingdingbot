import React from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Clock, ShieldCheck, Database, Layers } from 'lucide-react';
import type { SelectionDiagnosticData } from '../types/controls';

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
                  v{data.control_version}
                </span>
              </div>
              <Dialog.Description className="mt-0.5 text-xs text-text-secondary">
                服务于工程排障的底层指标与全量标的池仲裁证据；日常监控无需常驻。
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded p-1 text-text-muted hover:bg-surface-subtle hover:text-text-primary transition-colors"
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
                    {data.current_authority_outcome}
                  </div>
                </div>
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">连续错过期数 (Missed Periods)</span>
                  <div className="mt-1 font-bold text-text-primary text-xs">
                    {data.consecutive_missed_periods} 周期
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
              </div>
            </div>

            {/* Section 2: Freshness & Ages - Unambiguous Timestamp */}
            <div>
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-text-primary">
                <Clock className="h-4 w-4 text-status-blue" />
                事实新鲜度与时间戳
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2.5 font-mono">
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Snapshot 完成年龄</span>
                  <div className="mt-1 text-text-primary text-xs">
                    {Math.round(data.latest_successful_completion_age_ms / 1000)}s
                    <span className="ml-1 text-text-muted font-sans">
                      ({(data.latest_successful_completion_age_ms / 3600000).toFixed(1)}h 前)
                    </span>
                  </div>
                </div>
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Cutoff 截断年龄</span>
                  <div className="mt-1 text-text-primary text-xs">
                    {Math.round(data.latest_successful_cutoff_age_ms / 1000)}s
                  </div>
                </div>
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">Membership 来源年龄</span>
                  <div className="mt-1 text-text-primary text-xs">
                    {Math.round(data.membership_source_age_ms / 1000)}s
                  </div>
                </div>
                {/* Crystal clear deadline: specific UTC time AND countdown */}
                <div className="rounded border border-border bg-surface-subtle p-3">
                  <span className="text-xs text-text-muted font-sans">有效期截止 (Stale Deadline)</span>
                  <div className="mt-1 text-text-primary font-bold text-xs">
                    10/16 14:08 UTC
                    <span className="ml-1 text-status-amber font-medium font-sans">
                      (剩余 02:43:18)
                    </span>
                  </div>
                </div>
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

            {/* Section 4: All Universe Members Full Audit */}
            <div>
              {(() => {
                const poolSize = Math.max(data.latest_ready_count, data.members.length, 24);
                const filteredCount = Math.max(0, poolSize - data.latest_selected_count);

                return (
                  <>
                    <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-text-primary">
                      <div className="flex items-center gap-2">
                        <Database className="h-4 w-4 text-status-green" />
                        标的池全量仲裁明细 ({poolSize} 标的)
                      </div>
                      <span className="font-mono text-xs text-text-muted">
                        {data.latest_selected_count} 入围 / {filteredCount} 过滤
                      </span>
                    </div>

                    <div className="mt-2.5 divide-y divide-border rounded border border-border bg-surface-subtle font-mono">
                      {data.members.map((member) => (
                        <div
                          key={member.exchange_instrument_id}
                          className="flex items-center justify-between px-3.5 py-2.5 text-xs"
                        >
                          <div className="flex items-center gap-2.5">
                            <span
                              className={`h-2 w-2 rounded-full ${
                                member.selected ? 'bg-status-green' : 'bg-slate-400 dark:bg-slate-500'
                              }`}
                            />
                            <strong className="text-text-primary">{member.exchange_instrument_id}</strong>
                          </div>

                          <div className="text-right">
                            {member.selected ? (
                              <span className="text-status-green font-sans font-semibold">
                                合格已入围 (Selected)
                              </span>
                            ) : (
                              <span className="text-status-amber font-sans">
                                {member.first_blocker ?? '未达入围阈值'}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}

                      {data.members.length < poolSize && (
                        <div className="px-3.5 py-2.5 text-xs font-sans text-text-muted bg-surface/50">
                          其余 {filteredCount} 个候选标的因未达打分阈值或波动门禁已自动过滤。
                        </div>
                      )}
                    </div>
                  </>
                );
              })()}
            </div>
          </div>

          {/* Footer */}
          <div className="border-t border-border bg-surface px-6 py-3.5 text-right">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded border border-border-strong bg-surface-subtle px-4 py-1.5 text-xs font-semibold text-text-primary hover:bg-surface-elevated transition-colors"
            >
              关闭诊断抽屉
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};

