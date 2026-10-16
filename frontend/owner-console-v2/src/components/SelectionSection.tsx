import React, { useState } from 'react';
import { useSelectionPreview } from '../hooks/useControlsData';
import { SelectionDrawer } from './SelectionDrawer';
import { formatAgeFromTimestamp } from '../utils/time';
import { RefreshCw, RotateCcw, ShieldCheck, ExternalLink, ShieldAlert, Loader2 } from 'lucide-react';
import { mapPreviewToDiagnostic } from '../mapping/selectionMapping';

export { mapPreviewToDiagnostic };

interface SelectionSectionProps {
  onTriggerFallback?: (groupId: string) => void;
  onTriggerReauthorize?: (groupId: string) => void;
  onRefreshData?: (groupId: string) => void;
}

export const TABS = ['CPM-RO-001', 'BRF2-001', 'MI-001', 'MPG-001', 'SOR-1H-001'] as const;

export const SelectionSection: React.FC<SelectionSectionProps> = () => {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('CPM-RO-001');
  const [drawerOpen, setDrawerOpen] = useState(false);

  const { data: rawPreview, isLoading, isError, refetch } = useSelectionPreview(activeTab);
  const current = mapPreviewToDiagnostic(activeTab, rawPreview);

  const isDynamic = current ? current.selection_mode === 'dynamic_selection' : true;

  // Selected & Unselected count labels adhering to facts
  const counts = (() => {
    if (!current) return { selected: 0, unselected: 0, total: 0, label: '0 入选' };
    if (current.kind === 'orb') {
      const total = current.candidate_count;
      const selected = current.selected_count;
      const unselected = Math.max(0, total - selected);
      return {
        selected,
        unselected,
        total,
        label: `${selected} 入选 / ${unselected} 未入选 (候选总数 ${total})`,
      };
    } else {
      const selected = current.latest_selected_count ?? current.members.filter((m) => m.first_blocker === null).length;
      const total = current.latest_ready_count ?? current.members.length;
      const unselected = Math.max(0, total - selected);
      return {
        selected,
        unselected,
        total,
        label: `${selected} 入选 / ${unselected} 未入选 (配置在役 ${current.members.length})`,
      };
    }
  })();

  const ageLabel = (() => {
    if (!current) return '—';
    if (current.kind === 'orb') {
      const ts = current.snapshot_decision_at_ms ?? current.snapshot_created_at_ms;
      return ts ? formatAgeFromTimestamp(ts).labelZh : '未知';
    } else {
      if (current.latest_successful_completion_age_ms != null) {
        const h = Math.round(current.latest_successful_completion_age_ms / 3600000);
        return h > 0 ? `${h}h 前` : '近期生成';
      }
      return '未知';
    }
  })();

  return (
    <div id="selection-section" className="rounded border border-border bg-surface shadow-xs">
      {/* Header & Tabs */}
      <div className="flex flex-col gap-3 border-b border-border px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-primary">
            动态选币与轮动治理 (Selection)
          </h2>
          <p className="mt-0.5 text-xs text-text-secondary">
            各策略独立的 4h / 24h 动态打分授权与 Static 基线回退；修改均需 Owner TOTP 签名。
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

      {/* Main Body for Active Strategy */}
      <div className="p-3.5">
        {isLoading ? (
          <div className="flex items-center justify-center py-6 gap-2 text-xs text-text-muted">
            <Loader2 className="h-4 w-4 animate-spin text-brand" />
            <span>正在读取 {activeTab} 选币真实快照...</span>
          </div>
        ) : isError || !current ? (
          <div className="flex items-center justify-between rounded border border-border bg-surface-subtle px-4 py-3 text-xs text-text-muted">
            <span>该策略当前暂无可用的选币事实或尚未安装。</span>
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex items-center gap-1 rounded border border-border px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        ) : (
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
                {isDynamic
                  ? current.cadence_hours === 24
                    ? 'DYNAMIC (24h 日周期)'
                    : `DYNAMIC (${current.cadence_hours}h)`
                  : 'STATIC 基线'}
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
                <span className="text-status-green font-semibold">{counts.selected}</span> 入选 /{' '}
                <span className="text-text-muted">{counts.unselected}</span> 未入选
                <span className="text-text-muted text-[11px]">
                  ({current.kind === 'orb' ? `候选总数 ${counts.total}` : `配置在役 ${current.members.length}`})
                </span>
              </div>

              <span className="text-text-muted opacity-30">·</span>

              {/* Freshness / Age */}
              <span className="font-mono text-xs text-text-muted">
                年龄: {ageLabel}
              </span>
            </div>

            {/* Right: Actions & Drawer Trigger */}
            <div className="flex items-center gap-2">
              {isDynamic ? (
                <button
                  type="button"
                  disabled
                  title="Phase 1 · 只读模式 (选币模式切换写操作未开放)"
                  className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed shadow-none"
                >
                  <RotateCcw className="h-3.5 w-3.5 text-text-muted" />
                  回退 Static (只读)
                </button>
              ) : (
                <button
                  type="button"
                  disabled
                  title="Phase 1 · 只读模式 (选币模式切换写操作未开放)"
                  className="inline-flex items-center gap-1 rounded border border-border bg-surface px-2.5 py-1 text-xs font-medium text-text-muted opacity-60 cursor-not-allowed shadow-none"
                >
                  <ShieldAlert className="h-3.5 w-3.5 text-text-muted" />
                  授权 Dynamic (只读)
                </button>
              )}

              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-medium text-text-primary hover:bg-surface-elevated transition-colors shadow-xs cursor-pointer"
                title="重新读取该策略选币快照"
              >
                <RefreshCw className="h-3.5 w-3.5 text-text-muted" />
                刷新
              </button>

              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                className="inline-flex items-center gap-1 rounded border border-border-strong bg-surface px-2.5 py-1 text-xs font-semibold text-brand hover:bg-surface-elevated transition-colors shadow-xs cursor-pointer"
              >
                <span>标的明细与诊断</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Drawer */}
      {current && (
        <SelectionDrawer
          open={drawerOpen}
          onOpenChange={setDrawerOpen}
          data={current}
        />
      )}
    </div>
  );
};
