import React, { useState } from 'react';
import type { SelectionDiagnosticData } from '../types/controls';
import { SelectionDrawer } from './SelectionDrawer';
import { RefreshCw, RotateCcw, ShieldCheck, ExternalLink, ShieldAlert } from 'lucide-react';

interface SelectionSectionProps {
  selectionMap: Record<string, SelectionDiagnosticData>;
  onTriggerFallback: (groupId: string) => void;
  onTriggerReauthorize: (groupId: string) => void;
  onRefreshData: (groupId: string) => void;
}

const TABS = ['CPM-RO-001', 'BRF2-001', 'MI-001', 'MPG-001', 'SOR-1H-001'];

export const SelectionSection: React.FC<SelectionSectionProps> = ({
  selectionMap,
  onTriggerFallback,
  onTriggerReauthorize,
  onRefreshData,
}) => {
  const [activeTab, setActiveTab] = useState('CPM-RO-001');
  const [drawerOpen, setDrawerOpen] = useState(false);

  const current = selectionMap[activeTab];
  if (!current) return null;

  const isDynamic = current.selection_mode === 'dynamic_selection';
  const selectedMembers = current.members.filter((m) => m.selected);
  const filteredMembers = current.members.filter((m) => !m.selected);

  return (
    <div className="rounded border border-border-base bg-surface-1 shadow-sm">
      {/* Header & Tabs */}
      <div className="flex flex-col gap-3 border-b border-border-base px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
            动态选币与轮动治理 (Selection)
          </h2>
          <p className="mt-0.5 text-[11px] text-slate-400">
            各策略独立的 4h 动态打分授权与 Static 基线回退；修改均需 Owner TOTP 签名。
          </p>
        </div>

        {/* Strategy Switcher Tabs */}
        <div className="flex items-center gap-1 rounded border border-border-base bg-surface-2 p-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded px-2.5 py-1 font-mono text-[11px] font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-surface-3 text-brand font-bold shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Main Body for Active Strategy */}
      <div className="p-4 space-y-4">
        {/* Top Ribbon: Mode, Authority & Direct Actions */}
        <div className="flex flex-col gap-3 rounded border border-border-base bg-surface-2/60 p-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            {/* Mode badge */}
            <span
              className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-semibold ${
                isDynamic
                  ? 'border border-status-blue/30 bg-status-blue-bg text-status-blue'
                  : 'border border-status-amber/30 bg-status-amber-bg text-status-amber'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isDynamic ? 'bg-status-blue' : 'bg-status-amber'
                }`}
              />
              {isDynamic ? `DYNAMIC (${current.cadence_hours}h 轮动)` : 'STATIC 基线模式'}
            </span>

            {/* Authority Status */}
            <div className="flex items-center gap-1.5 text-xs">
              <ShieldCheck className="h-3.5 w-3.5 text-status-green flex-none" />
              <span className="font-medium text-slate-200">
                {current.authority_status_zh}
              </span>
            </div>

            <span className="hidden sm:inline text-slate-700">·</span>

            <span className="font-mono text-[11px] text-slate-400">
              数据年龄: {Math.round(current.latest_successful_completion_age_ms / 3600000)}h 前
            </span>
          </div>

          {/* Action Buttons (CLEAR & EXPLICIT) */}
          <div className="flex flex-wrap items-center gap-2">
            {isDynamic ? (
              <button
                type="button"
                onClick={() => onTriggerFallback(activeTab)}
                className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface-2 px-2.5 py-1 text-xs font-medium text-slate-200 hover:bg-surface-3 hover:text-brand transition-colors"
              >
                <RotateCcw className="h-3 w-3 text-status-amber" />
                回退至 Static 基线
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onTriggerReauthorize(activeTab)}
                className="inline-flex items-center gap-1.5 rounded border border-status-blue/50 bg-status-blue-bg px-2.5 py-1 text-xs font-medium text-status-blue hover:bg-status-blue/20 transition-colors"
              >
                <ShieldAlert className="h-3 w-3" />
                重新授权 Dynamic 轮动
              </button>
            )}

            <button
              type="button"
              onClick={() => onRefreshData(activeTab)}
              className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface-2 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-surface-3 transition-colors"
              title="重新读取该策略选币快照"
            >
              <RefreshCw className="h-3 w-3 text-slate-400" />
              刷新
            </button>

            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface-2 px-2.5 py-1 text-xs font-medium text-slate-300 hover:bg-surface-3 transition-colors"
            >
              <ExternalLink className="h-3 w-3 text-slate-400" />
              底层工程诊断 (Drawer)
            </button>
          </div>
        </div>

        {/* Member Filtering Overview (Replaces the 24 noisy badges) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* Left: Selected Qualified Members */}
          <div className="rounded border border-border-base bg-surface-2/30 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">
                本轮已选入候选池 ({selectedMembers.length} 标的)
              </span>
              <span className="text-[10px] text-status-green font-medium">准入正常</span>
            </div>
            <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
              {selectedMembers.map((m) => (
                <span
                  key={m.exchange_instrument_id}
                  className="rounded border border-border-base bg-surface-2 px-2 py-0.5 text-slate-200"
                >
                  {m.exchange_instrument_id.replace('USDT', '')}
                </span>
              ))}
            </div>
          </div>

          {/* Right: Filtered / Blocked Members with human reasons */}
          <div className="rounded border border-border-base bg-surface-2/30 p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                门禁过滤 / 未入围 ({filteredMembers.length} 标的)
              </span>
              <span className="text-[10px] text-slate-500">规则拦截</span>
            </div>
            <div className="flex flex-wrap gap-1.5 text-[11px]">
              {filteredMembers.map((m) => (
                <span
                  key={m.exchange_instrument_id}
                  className="inline-flex items-center gap-1 rounded border border-border-base bg-surface-1 px-1.5 py-0.5 text-slate-400"
                  title={m.first_blocker ?? '未入选'}
                >
                  <strong className="font-mono text-slate-300">
                    {m.exchange_instrument_id.replace('USDT', '')}
                  </strong>
                  <span className="text-[10px] text-slate-500">
                    ({m.first_blocker?.slice(0, 4) ?? '未入围'})
                  </span>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Drawer */}
      <SelectionDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        data={current}
      />
    </div>
  );
};
