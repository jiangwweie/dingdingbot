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
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border-base bg-surface-1 shadow-2xl transition-transform duration-200">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border-base px-6 py-4">
            <div>
              <div className="flex items-center gap-2">
                <Dialog.Title className="text-sm font-bold text-slate-100">
                  {data.strategy_group_id} 动态选币底层工程诊断
                </Dialog.Title>
                <span className="rounded bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-slate-400">
                  v{data.control_version}
                </span>
              </div>
              <Dialog.Description className="mt-0.5 text-xs text-slate-400">
                服务于工程排障的底层指标与全量标的池仲裁证据；日常监控无需常驻。
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded p-1 text-slate-400 hover:bg-surface-2 hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6 text-xs">
            {/* Section 1: Authority & State */}
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
                <ShieldCheck className="h-4 w-4 text-brand" />
                权威凭证与周期锚点
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2 font-mono">
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">实际 Authority Outcome</span>
                  <div className="mt-1 font-bold text-slate-100">
                    {data.current_authority_outcome}
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">连续错过期数 (Missed Periods)</span>
                  <div className="mt-1 font-bold text-slate-100">
                    {data.consecutive_missed_periods} 周期
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Rollback Baseline ID</span>
                  <div className="mt-1 truncate text-slate-300" title={data.rollback_baseline_id ?? '无'}>
                    {data.rollback_baseline_id ?? '—'}
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Selection Epoch ID</span>
                  <div className="mt-1 truncate text-slate-300" title={data.selection_epoch_id ?? '无'}>
                    {data.selection_epoch_id ?? '—'}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 2: Freshness & Ages */}
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
                <Clock className="h-4 w-4 text-status-blue" />
                事实新鲜度与时间戳
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2 font-mono">
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Snapshot 完成年龄</span>
                  <div className="mt-1 text-slate-100">
                    {Math.round(data.latest_successful_completion_age_ms / 1000)}s
                    <span className="ml-1 text-slate-400">
                      ({(data.latest_successful_completion_age_ms / 3600000).toFixed(1)}h 前)
                    </span>
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Cutoff 截断年龄</span>
                  <div className="mt-1 text-slate-100">
                    {Math.round(data.latest_successful_cutoff_age_ms / 1000)}s
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Membership 来源年龄</span>
                  <div className="mt-1 text-slate-100">
                    {Math.round(data.membership_source_age_ms / 1000)}s
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">有效期截止 (Stale Deadline)</span>
                  <div className="mt-1 text-slate-100">
                    {new Date(data.membership_valid_until_ms).toLocaleTimeString('zh-CN')}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 3: Materialization & Vacuum */}
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-300">
                <Layers className="h-4 w-4 text-status-amber" />
                物化与 Vacuum 隔离
              </div>
              <div className="mt-2.5 grid grid-cols-2 gap-2 font-mono">
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">物化状态 (Materialization)</span>
                  <div className="mt-1 font-bold text-slate-100">
                    {data.materialization_state}
                  </div>
                </div>
                <div className="rounded border border-border-base bg-surface-2 p-3">
                  <span className="text-[10px] text-slate-400">Vacuum 隔离状态</span>
                  <div className="mt-1 font-bold text-slate-100">
                    {data.vacuum_state}
                  </div>
                </div>
              </div>
            </div>

            {/* Section 4: All 24 Universe Members Full Audit */}
            <div>
              <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-slate-300">
                <div className="flex items-center gap-2">
                  <Database className="h-4 w-4 text-status-green" />
                  标的池全量仲裁明细 ({data.members.length} 标的)
                </div>
                <span className="font-mono text-[11px] text-slate-400">
                  {data.latest_selected_count} 入围 / {data.members.length - data.latest_selected_count} 过滤
                </span>
              </div>

              <div className="mt-2.5 divide-y divide-border-base rounded border border-border-base bg-surface-2 font-mono">
                {data.members.map((member) => (
                  <div
                    key={member.exchange_instrument_id}
                    className="flex items-center justify-between px-3 py-2 text-[11px]"
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          member.selected ? 'bg-status-green' : 'bg-slate-500'
                        }`}
                      />
                      <strong className="text-slate-200">{member.exchange_instrument_id}</strong>
                    </div>

                    <div className="text-right">
                      {member.selected ? (
                        <span className="text-status-green font-sans font-medium">
                          合格已入围 (Selected)
                        </span>
                      ) : (
                        <span className="text-status-amber font-sans">
                          {member.first_blocker ?? '未达入围排名'}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-t border-border-base bg-surface-2/40 px-6 py-3 text-right">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded border border-border-strong bg-surface-2 px-4 py-1.5 text-xs font-medium text-slate-300 hover:bg-surface-3 hover:text-white"
            >
              关闭诊断抽屉
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
