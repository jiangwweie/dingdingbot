import React, { useState } from 'react';
import type { ReviewCenterSummary } from '../../types/review.ts';
import {
  formatExecutionClassification,
  formatReviewExitReason,
} from '../../mapping/reviewMapping.ts';
import type { ExecutionClassification, EvidenceRef } from '../../api/reviewApi.ts';
import { Layers, ShieldCheck, DoorOpen, FileSearch, ChevronDown, ChevronUp } from 'lucide-react';

interface BreakdownEvidenceTrayProps {
  evidence?: EvidenceRef[];
  onSelectTicket?: (ticketId: string) => void;
  maxInitial?: number;
}

const BreakdownEvidenceTray: React.FC<BreakdownEvidenceTrayProps> = ({
  evidence,
  onSelectTicket,
  maxInitial = 4,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!evidence || evidence.length === 0) {
    return (
      <div className="text-[10px] text-text-muted italic pt-0.5" data-testid="evidence-empty-note">
        无直接关联证据项
      </div>
    );
  }

  const visibleEvidence = isExpanded ? evidence : evidence.slice(0, maxInitial);
  const remainingCount = evidence.length - maxInitial;

  return (
    <div className="flex flex-wrap items-center gap-1 pt-1" data-testid="evidence-tray">
      {visibleEvidence.map((ref, idx) => {
        const isTicket = ref.kind === 'ticket';
        const key = `${ref.kind}:${ref.identity}:${ref.occurred_at_ms || idx}`;
        if (isTicket) {
          return (
            <button
              key={key}
              type="button"
              onClick={() => onSelectTicket?.(ref.identity)}
              className="inline-flex items-center gap-1 rounded bg-brand/10 hover:bg-brand/20 text-brand px-1.5 py-0.5 font-mono text-[10px] font-medium border border-brand/20 transition-colors cursor-pointer"
              title={`查看 Ticket 因果复盘: ${ref.identity}`}
              data-testid={`evidence-ticket-${ref.identity}`}
            >
              <FileSearch className="h-2.5 w-2.5 flex-none" />
              <span className="truncate max-w-[120px]">{ref.identity}</span>
            </button>
          );
        }
        return (
          <span
            key={key}
            className="inline-flex items-center gap-1 rounded bg-surface-subtle text-text-muted px-1.5 py-0.5 font-mono text-[10px] border border-border"
            title={`${ref.kind}: ${ref.identity}`}
            data-testid={`evidence-chip-${ref.kind}-${ref.identity}`}
          >
            <span className="opacity-70">{ref.kind}:</span>
            <span className="truncate max-w-[100px]">{ref.identity}</span>
          </span>
        );
      })}

      {remainingCount > 0 && (
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-mono text-[10px] text-brand hover:underline cursor-pointer"
          data-testid="evidence-expand-toggle"
        >
          {isExpanded ? (
            <>
              <ChevronUp className="h-2.5 w-2.5" />
              <span>收起</span>
            </>
          ) : (
            <>
              <ChevronDown className="h-2.5 w-2.5" />
              <span>+{remainingCount} 更多</span>
            </>
          )}
        </button>
      )}
    </div>
  );
};

interface ReviewBreakdownSectionsProps {
  summary: ReviewCenterSummary | null;
  onSelectTicket?: (ticketId: string) => void;
}

export const ReviewBreakdownSections: React.FC<ReviewBreakdownSectionsProps> = ({
  summary,
  onSelectTicket,
}) => {
  if (!summary) return null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* 1. StrategyGroup Evidence */}
      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs flex flex-col">
        <div className="flex items-center justify-between border-b border-border bg-surface-subtle px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-brand" />
            <h3 className="text-xs font-bold text-text-primary">StrategyGroup Evidence</h3>
          </div>
          <span className="font-mono text-[10px] text-text-muted">
            {summary.strategy_group_samples.length} 策略组
          </span>
        </div>

        <div className="divide-y divide-border text-xs flex-1">
          {summary.strategy_group_samples.length === 0 ? (
            <div className="p-4 text-center text-text-muted text-[11px]">无策略组样本记录</div>
          ) : (
            summary.strategy_group_samples.map((item) => (
              <div
                key={item.strategy_group_id}
                className="flex flex-col gap-1 px-4 py-2.5 hover:bg-surface-elevated transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono font-semibold text-text-primary truncate">
                      {item.strategy_group_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono tabular-number text-[11px] text-text-muted">
                      {item.sample_count} 笔
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.2 font-mono text-[10px] font-semibold border ${
                        item.evidence_state === 'observe_only'
                          ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20'
                          : 'bg-surface-subtle text-text-muted border-border'
                      }`}
                    >
                      {item.evidence_state === 'observe_only' ? 'Observe Only' : 'No Evidence'}
                    </span>
                  </div>
                </div>

                {/* Evidence tray */}
                <BreakdownEvidenceTray
                  evidence={item.evidence}
                  onSelectTicket={onSelectTicket}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* 2. Execution Classification Breakdown */}
      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs flex flex-col">
        <div className="flex items-center justify-between border-b border-border bg-surface-subtle px-4 py-2.5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-brand" />
            <h3 className="text-xs font-bold text-text-primary">Execution Classification</h3>
          </div>
          <span className="font-mono text-[10px] text-text-muted">
            {summary.execution_quality_breakdown.length} 分类
          </span>
        </div>

        <div className="divide-y divide-border text-xs flex-1">
          {summary.execution_quality_breakdown.length === 0 ? (
            <div className="p-4 text-center text-text-muted text-[11px]">无执行质量记录</div>
          ) : (
            summary.execution_quality_breakdown.map((item) => {
              const execClass = formatExecutionClassification(item.label as ExecutionClassification);
              return (
                <div
                  key={item.label}
                  className="flex flex-col gap-1 px-4 py-2.5 hover:bg-surface-elevated transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
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
                      >
                        {execClass.label}
                      </span>
                      <span className="font-mono text-[10px] text-text-muted truncate">
                        ({item.label})
                      </span>
                    </div>
                    <strong className="font-mono font-bold text-text-primary tabular-number">
                      {item.ticket_count}
                    </strong>
                  </div>

                  {/* Evidence tray */}
                  <BreakdownEvidenceTray
                    evidence={item.evidence}
                    onSelectTicket={onSelectTicket}
                  />
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 3. Exit Reason Breakdown */}
      <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-xs flex flex-col">
        <div className="flex items-center justify-between border-b border-border bg-surface-subtle px-4 py-2.5">
          <div className="flex items-center gap-2">
            <DoorOpen className="h-4 w-4 text-brand" />
            <h3 className="text-xs font-bold text-text-primary">Exit Reason</h3>
          </div>
          <span className="font-mono text-[10px] text-text-muted">
            {summary.exit_reason_breakdown.length} 原因项
          </span>
        </div>

        <div className="divide-y divide-border text-xs flex-1">
          {summary.exit_reason_breakdown.length === 0 ? (
            <div className="p-4 text-center text-text-muted text-[11px]">无退出原因记录</div>
          ) : (
            summary.exit_reason_breakdown.map((item) => {
              const formattedReason = formatReviewExitReason(item.label);
              return (
                <div
                  key={item.label}
                  className="flex flex-col gap-1 px-4 py-2.5 hover:bg-surface-elevated transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <span
                      className="truncate text-[12px] text-text-secondary max-w-[200px]"
                      title={item.label}
                    >
                      {formattedReason.label}
                    </span>
                    <strong className="font-mono font-bold text-text-primary tabular-number">
                      {item.ticket_count}
                    </strong>
                  </div>

                  {/* Evidence tray */}
                  <BreakdownEvidenceTray
                    evidence={item.evidence}
                    onSelectTicket={onSelectTicket}
                  />
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
