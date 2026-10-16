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
  const selectedCount = current.latest_selected_count;
  const filteredCount = current.members.length - selectedCount;

  return (
    <div className="rounded border border-border bg-surface shadow-xs">
      {/* Header & Tabs */}
      <div className="flex flex-col gap-3 border-b border-border px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            动态选币与轮动治理 (Selection)
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            各策略独立的 4h 动态打分授权与 Static 基线回退；修改均需 Owner TOTP 签名。
          </p>
        </div>

        {/* Strategy Switcher Tabs */}
        <div className="flex items-center gap-1 rounded border border-border bg-surface-subtle p-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveTab(tab)}
              className={`rounded px-3 py-1 font-mono text-xs font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-surface text-brand font-bold shadow-xs border border-border'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Main Body for Active Strategy: Unified Single-Row Command Bar */}
      <div className="p-3.5">
        <div className="flex flex-col gap-2 rounded border border-border bg-surface-subtle px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
          {/* Left: Mode, Authority, Counts & Freshness */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Mode badge */}
            <span
              className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-semibold ${
                isDynamic
                  ? 'border border-status-blue/30 bg-status-blue-bg text-status-blue'
                  : 'border border-status-amber/30 bg-status-amber-bg text-status-amber'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isDynamic ? 'bg-status-blue' : 'bg-status-amber'
                }`}
              />
              {isDynamic ? `DYNAMIC (${current.cadence_hours}h)` : 'STATIC 基线'}
            </span>

            {/* Authority Status */}
            <div className="flex items-center gap-1 text-xs">
              <ShieldCheck className="h-4 w-4 text-status-green flex-none" />
              <span className="font-semibold text-text-primary">
                {current.authority_status_zh}
              </span>
            </div>

            <span className="text-text-muted opacity-30">·</span>

            {/* Candidates Counts */}
            <div className="flex items-center gap-1 text-xs font-medium text-text-secondary">
              <span className="text-status-green font-semibold">{selectedCount}</span> 入围 /{' '}
              <span className="text-text-muted">{filteredCount}</span> 过滤
            </div>

            <span className="text-text-muted opacity-30">·</span>

            {/* Freshness / Age */}
            <span className="font-mono text-xs text-text-muted">
              年龄: {Math.round(current.latest_successful_completion_age_ms / 3600000)}h 前
            </span>
          </div>

          {/* Right: Actions & Drawer Trigger */}
          <div className="flex items-center gap-2">
            {isDynamic ? (
              <button
                type="button"
                onClick={() => onTriggerFallback(activeTab)}
                className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated hover:text-brand transition-colors shadow-xs"
              >
                <RotateCcw className="h-3.5 w-3.5 text-status-amber" />
                回退 Static
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onTriggerReauthorize(activeTab)}
                className="inline-flex items-center gap-1 rounded border border-status-blue/50 bg-status-blue-bg px-2.5 py-1 text-xs font-semibold text-status-blue hover:bg-status-blue/20 transition-colors shadow-xs"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                授权 Dynamic
              </button>
            )}

            <button
              type="button"
              onClick={() => onRefreshData(activeTab)}
              className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs"
              title="重新读取该策略选币快照"
            >
              <RefreshCw className="h-3.5 w-3.5 text-text-muted" />
              刷新
            </button>

            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-semibold text-brand hover:bg-surface-elevated transition-colors shadow-xs"
            >
              <span>标的明细与诊断</span>
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
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

