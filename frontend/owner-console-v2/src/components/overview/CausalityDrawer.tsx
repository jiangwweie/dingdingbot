import React, { useState } from 'react';
import type { TradeEpisodeSummary } from '../../types/overview';
import { X, ShieldCheck, CheckCircle2, CircleDot, ChevronDown, ChevronUp, Copy, Check } from 'lucide-react';

interface CausalityDrawerProps {
  episode: TradeEpisodeSummary | null;
  onClose: () => void;
}

export const CausalityDrawer: React.FC<CausalityDrawerProps> = ({
  episode,
  onClose,
}) => {
  const [showRawEvidence, setShowRawEvidence] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!episode) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(JSON.stringify(episode, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isLong = episode.side === 'long';

  return (
    <div
      className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      aria-labelledby="slide-over-title"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div className="absolute inset-y-0 right-0 flex max-w-full pl-10">
        <div
          className="w-screen max-w-xl bg-surface border-l border-border shadow-2xl flex flex-col h-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
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

            <div className="mt-2.5 flex items-baseline justify-between text-xs">
              <span className="text-text-secondary">
                {episode.strategy_name_zh} · 当前浮盈{' '}
                <strong
                  className={`font-mono ${
                    episode.pnl_r >= 0
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {episode.pnl_r >= 0 ? `+${episode.pnl_r.toFixed(2)}` : episode.pnl_r.toFixed(2)} R
                </strong>
              </span>
              <span className="font-mono text-text-muted">
                持仓时长: {episode.duration_formatted}
              </span>
            </div>

            {/* Quick fact badges */}
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="inline-flex items-center gap-1 rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-medium text-emerald-600 dark:text-emerald-400">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>{episode.protection_label} ({episode.stop_price})</span>
              </span>
              <span className="rounded border border-border bg-surface px-2 py-0.5 font-mono text-text-muted">
                入场: {episode.entry_price}
              </span>
              <span className="rounded border border-border bg-surface px-2 py-0.5 font-mono text-text-muted">
                现价: {episode.current_price}
              </span>
            </div>
          </div>

          {/* Timeline Content */}
          <div className="flex-1 overflow-y-auto p-5 space-y-6">
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted">
                全链路 8 阶段因果演进 (8-Stage Causal Chain)
              </h3>
              <p className="mt-0.5 text-xs text-text-secondary">
                从 Observation 市场特征到持久化生命周期追踪，每一步均有不可变证据
              </p>
            </div>

            <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
              {episode.causality_stages?.map((st) => {
                const isPassed = st.status === 'passed';
                const isActive = st.status === 'active';

                return (
                  <div key={st.stage_number} className="relative group">
                    {/* Node Dot */}
                    <div
                      className={`absolute -left-6 top-0.5 flex h-5 w-5 items-center justify-center rounded-full border bg-surface transition-all ${
                        isActive
                          ? 'border-brand text-brand ring-4 ring-brand/10'
                          : isPassed
                          ? 'border-emerald-500 text-emerald-500'
                          : 'border-border text-text-muted'
                      }`}
                    >
                      {isActive ? (
                        <CircleDot className="h-3 w-3 animate-pulse" />
                      ) : (
                        <CheckCircle2 className="h-3 w-3" />
                      )}
                    </div>

                    {/* Step Content */}
                    <div className="rounded border border-border/80 bg-surface-subtle p-3 hover:border-border-strong transition-all">
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-text-primary">
                          {st.stage_title}
                        </span>
                        <span className="font-mono text-[11px] text-text-muted">
                          {st.timestamp_utc}
                        </span>
                      </div>

                      <p className="mt-1 text-xs text-text-secondary leading-relaxed">
                        {st.summary_zh}
                      </p>

                      {st.evidence_json && (
                        <div className="mt-2 rounded bg-surface p-2 font-mono text-[10px] text-text-muted border border-border/40">
                          {Object.entries(st.evidence_json).map(([k, v]) => (
                            <div key={k} className="flex items-center justify-between py-0.5">
                              <span className="text-text-secondary">{k}:</span>
                              <span className="text-text-primary font-medium">{String(v)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Collapsible raw evidence */}
            <div className="pt-4 border-t border-border">
              <button
                type="button"
                onClick={() => setShowRawEvidence(!showRawEvidence)}
                className="flex w-full items-center justify-between text-xs font-semibold text-text-muted hover:text-text-primary transition-colors"
              >
                <span>底层工程事实与命令哈希 (L4 Audit Evidence)</span>
                {showRawEvidence ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

              {showRawEvidence && (
                <div className="mt-3 relative">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="absolute top-2 right-2 flex items-center gap-1 rounded bg-surface-elevated border border-border px-2 py-1 text-[11px] text-text-secondary hover:text-text-primary transition-colors"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3 text-emerald-500" />
                        <span>已复制</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        <span>复制 JSON</span>
                      </>
                    )}
                  </button>
                  <pre className="max-h-56 overflow-auto rounded border border-border bg-surface-elevated p-3 font-mono text-[10px] text-text-secondary leading-relaxed">
                    {JSON.stringify(
                      {
                        ticket_id: episode.ticket_id,
                        strategy_id: episode.strategy_id,
                        side: episode.side,
                        netting_domain: `binance:perp:${episode.symbol}:${episode.side}`,
                        stop_price: episode.stop_price,
                        tp1_status: episode.tp1_status,
                        causality_stages_count: episode.causality_stages?.length,
                      },
                      null,
                      2
                    )}
                  </pre>
                </div>
              )}
            </div>
          </div>

          {/* Footer actions */}
          <div className="border-t border-border bg-surface-subtle p-4 flex items-center justify-between">
            <span className="text-[11px] text-text-muted">
              Ticket ID: <span className="font-mono">{episode.ticket_id.slice(0, 18)}...</span>
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
