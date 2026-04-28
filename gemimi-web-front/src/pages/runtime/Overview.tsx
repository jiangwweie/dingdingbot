import React, { useEffect, useState } from 'react';
import { getRuntimeOverview } from '@/src/services/api';
import { RuntimeOverview as IRuntimeOverview } from '@/src/types';
import { useRefreshContext } from '@/src/components/layout/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { Badge } from '@/src/components/ui/Badge';
import {
  Loader2, AlertCircle, Shield, Activity, Clock,
  ChevronDown, ChevronUp, TrendingUp, TrendingDown,
} from 'lucide-react';
import {
  DASH, fmtDash, fmtDateTimeFull, fmtTime, fmtMoney, fmtDec,
  runtimeHealthVariant, runtimeHealthLabel,
  freshnessVariant, freshnessLabel,
} from '@/src/lib/console-utils';
import {
  environmentModeLabel, environmentBadgeStyle,
  riskLevel, riskBarColor, riskTextColor,
  pnlColor, formatPercent,
} from '@/src/lib/runtime-format';

// ─── Helpers ──────────────────────────────────────────────────

/** Check whether any health component is not OK. */
function hasHealthAlert(d: IRuntimeOverview): boolean {
  return (
    d.exchange_health !== 'OK' ||
    d.pg_health !== 'OK' ||
    d.webhook_health !== 'OK'
  );
}

/** Check whether operational alerts exist. */
function hasOperationalAlert(d: IRuntimeOverview): boolean {
  return (d.breaker_count ?? 0) > 0 || (d.pending_recovery_tasks ?? 0) > 0;
}

/** Count total alerts for badge. */
function alertCount(d: IRuntimeOverview): number {
  let n = 0;
  if (d.exchange_health !== 'OK') n++;
  if (d.pg_health !== 'OK') n++;
  if (d.webhook_health !== 'OK') n++;
  if ((d.breaker_count ?? 0) > 0) n++;
  if ((d.pending_recovery_tasks ?? 0) > 0) n++;
  return n;
}

/** Describe each alerting item for the banner. */
function alertMessages(d: IRuntimeOverview): string[] {
  const msgs: string[] = [];
  if (d.exchange_health !== 'OK') msgs.push(`交易所 API: ${runtimeHealthLabel(d.exchange_health)}`);
  if (d.pg_health !== 'OK') msgs.push(`数据库: ${runtimeHealthLabel(d.pg_health)}`);
  if (d.webhook_health !== 'OK') msgs.push(`Webhook: ${runtimeHealthLabel(d.webhook_health)}`);
  if ((d.breaker_count ?? 0) > 0) msgs.push(`熔断器触发 ${d.breaker_count} 次`);
  if ((d.pending_recovery_tasks ?? 0) > 0) msgs.push(`${d.pending_recovery_tasks} 项恢复任务待处理`);
  return msgs;
}

// ─── Sub-components ──────────────────────────────────────────

function SummaryCard({
  title,
  value,
  icon,
  accent,
}: {
  title: string;
  value: string | number;
  icon: React.ReactNode;
  accent?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-2.5">
        <div className="flex-shrink-0 w-7 h-7 rounded bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center text-zinc-500">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-[9px] font-bold uppercase tracking-widest text-zinc-400 dark:text-zinc-500 mb-0.5">
            {title}
          </p>
          <p className={`text-sm font-bold font-mono tracking-tight tabular-nums leading-none ${accent ?? 'text-zinc-800 dark:text-zinc-100'}`}>
            {value}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function HealthRow({ label, status }: { label: string; status: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-zinc-100 dark:border-zinc-800/50 last:border-b-0">
      <span className="text-xs text-zinc-600 dark:text-zinc-400">{label}</span>
      <Badge variant={runtimeHealthVariant(status)} className="text-[10px] px-1.5 py-0.5">{runtimeHealthLabel(status)}</Badge>
    </div>
  );
}

function TimeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-zinc-100 dark:border-zinc-800/50 last:border-b-0">
      <span className="text-xs text-zinc-600 dark:text-zinc-400">{label}</span>
      <span className="text-xs font-mono tabular-nums text-zinc-700 dark:text-zinc-300">{value}</span>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────

export default function Overview() {
  const { refreshCount } = useRefreshContext();
  const [data, setData] = useState<IRuntimeOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    getRuntimeOverview().then(res => {
      if (active) {
        setData(res);
        setLoading(false);
      }
    }).catch(() => {
      if (active) {
        setError(true);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, [refreshCount]);

  // ── Loading / Error / Empty ────────────────────────────────

  if (loading && !data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex h-32 items-center justify-center text-rose-400 gap-2">
        <AlertCircle className="w-5 h-5" />
        <span>概览数据加载失败</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <h2 className="text-xl font-bold tracking-tight">交易日概览</h2>
        <Card>
          <CardContent className="py-10 text-center text-zinc-500">暂无概览数据</CardContent>
        </Card>
      </div>
    );
  }

  // ── Derived values ─────────────────────────────────────────

  const envMode = environmentModeLabel(data.mode);
  const envStyle = environmentBadgeStyle(envMode);
  const hasAlert = hasHealthAlert(data) || hasOperationalAlert(data);
  const alerts = alertMessages(data);
  const pnlVal = data.unrealized_pnl;
  const equityVal = data.total_equity;

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Stale data warning */}
      {error && data && (
        <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900/50 text-amber-700 dark:text-amber-400 px-3 py-1.5 rounded-sm text-xs">
          部分数据刷新失败，显示缓存内容
        </div>
      )}

      {/* Alert banner */}
      {hasAlert && (
        <div className="bg-rose-50 dark:bg-rose-950/30 border border-rose-300 dark:border-rose-900/50 rounded-sm px-3 py-2 flex items-start gap-2">
          <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-bold text-rose-700 dark:text-rose-300">
              {alertCount(data)} 项异常需关注
            </p>
            <ul className="mt-0.5 text-[11px] text-rose-600 dark:text-rose-400 space-y-0.5 list-disc list-inside">
              {alerts.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* ── Environment bar ────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 bg-zinc-50 dark:bg-zinc-900/40 p-2.5 rounded-sm border border-zinc-200 dark:border-zinc-800">
        <h2 className="text-sm font-bold uppercase tracking-widest text-zinc-700 dark:text-zinc-300">交易日概览</h2>

        <div className="flex items-center gap-4">
          {/* Environment badge */}
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-[10px] font-bold tracking-wide ${envStyle}`}
          >
            <Shield className="w-3 h-3" />
            {envMode}
          </span>

          {/* Profile name */}
          <span className="text-xs text-zinc-600 dark:text-zinc-400 font-mono">
            {fmtDash(data.profile)}
          </span>

          {/* Frozen status */}
          <Badge variant={data.frozen ? 'info' : 'success'} className="text-[10px] px-1.5 py-0.5">
            {data.frozen ? '已冻结' : '运行中'}
          </Badge>

          {/* Last update */}
          <span className="text-[10px] text-zinc-500 dark:text-zinc-500 font-mono">
            UPDATED: {fmtTime(data.last_runtime_update_at)}
          </span>
        </div>
      </div>

      {/* ── Trading day summary cards ──────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-2">
        <SummaryCard
          title="活跃持仓"
          value={data.active_positions ?? DASH}
          icon={<Activity className="w-4 h-4" />}
        />
        <SummaryCard
          title="活跃信号"
          value={data.active_signals ?? DASH}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <SummaryCard
          title="待执行意图"
          value={data.pending_intents ?? DASH}
          icon={<Clock className="w-4 h-4" />}
        />
        <SummaryCard
          title="恢复任务"
          value={data.pending_recovery_tasks ?? DASH}
          icon={<Shield className="w-4 h-4" />}
          accent={(data.pending_recovery_tasks ?? 0) > 0 ? 'text-amber-500' : undefined}
        />
        <SummaryCard
          title="总权益"
          value={equityVal != null ? `$${fmtMoney(equityVal)}` : DASH}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <SummaryCard
          title="未实现盈亏"
          value={pnlVal != null ? `${pnlVal >= 0 ? '+' : ''}${fmtDec(pnlVal)}` : DASH}
          icon={pnlVal != null && pnlVal >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          accent={pnlColor(pnlVal)}
        />
      </div>

      {/* ── Heartbeat & health ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2">
        {/* Health card */}
        <Card>
          <CardHeader>
            <CardTitle>系统健康</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0 px-3">
            <HealthRow label="交易所 API" status={data.exchange_health} />
            <HealthRow label="PostgreSQL" status={data.pg_health} />
            <HealthRow label="Webhook / 通知" status={data.webhook_health} />
          </CardContent>
        </Card>

        {/* Timing card */}
        <Card>
          <CardHeader>
            <CardTitle>心跳 & 时间</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0 px-3">
            <TimeRow label="服务器时间" value={fmtDateTimeFull(data.server_time)} />
            <TimeRow label="上次心跳" value={fmtTime(data.last_heartbeat_at)} />
            <TimeRow label="最后更新" value={fmtTime(data.last_runtime_update_at)} />
            <div className="flex items-center justify-between py-1.5">
              <span className="text-xs text-zinc-600 dark:text-zinc-400">心跳状态</span>
              <Badge variant={freshnessVariant(data.freshness_status)} className="text-[10px] px-1.5 py-0.5">
                {freshnessLabel(data.freshness_status)}
              </Badge>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Debug info (collapsible) ───────────────────────── */}
      <Card>
        <button
          type="button"
          className="w-full px-4 py-3 flex items-center justify-between text-xs font-bold uppercase tracking-widest text-zinc-600 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors"
          onClick={() => setDebugOpen(prev => !prev)}
        >
          <span>调试信息</span>
          {debugOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>

        {debugOpen && (
          <CardContent className="space-y-3 text-sm border-t border-zinc-200 dark:border-zinc-800">
            <div className="flex justify-between">
              <span className="text-zinc-500">Profile Hash:</span>
              <span className="font-mono text-zinc-600 dark:text-zinc-400 text-xs">{fmtDash(data.hash)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">版本:</span>
              <span className="font-mono text-zinc-600 dark:text-zinc-400">{fmtDash(data.version)}</span>
            </div>
            <div>
              <p className="text-zinc-500 mb-1">后端摘要</p>
              <p className="font-mono text-xs text-blue-700 dark:text-blue-300 break-all">
                {fmtDash(data.backend_summary)}
              </p>
            </div>
            <div>
              <p className="text-zinc-500 mb-1">对账摘要</p>
              <p className="font-mono text-xs text-emerald-700 dark:text-emerald-300 break-all">
                {fmtDash(data.reconciliation_summary)}
              </p>
            </div>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
