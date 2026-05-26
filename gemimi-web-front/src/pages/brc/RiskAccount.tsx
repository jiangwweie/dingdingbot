import { useEffect, useState } from 'react';
import { CircleDollarSign, ShieldAlert } from 'lucide-react';
import { brcApi, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, EmptyState, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';
import { whyText } from './readiness';

export default function RiskAccount() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    brcApi.readiness().then(setReadiness).catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!readiness) return <div className="text-xs text-zinc-500">正在读取风险与账户状态...</div>;

  const summary = readiness.risk_account_summary || {};
  const accountState = recordAt(summary, 'account_state');
  const exposure = recordAt(summary, 'exposure_orders');
  const flatness = recordAt(exposure, 'flatness_proof');
  const envelope = recordAt(summary, 'risk_envelope');
  const symbols = arrayOfRecords(exposure, 'symbols');
  const positions = arrayOfRecords(exposure, 'active_positions');
  const orders = arrayOfRecords(exposure, 'open_orders');

  return (
    <div className="space-y-4">
      <StageStrip
        current="Risk & Account 风险与账户"
        next="先看系统给出的 risk 判断，再看是否有持仓、挂单或未知风险。"
        global="这是只读风险桌面，不是交易终端，也不是参数编辑页。"
      />
      <OwnerSummary
        conclusion={`系统风险判断：${readiness.risk_decision}`}
        why={whyText(readiness)}
        canDo="查看账户边界、持仓/挂单、本地空仓证明和风险包络。"
        cannotDo="不能在这里下单、平仓、改杠杆、改数量或改策略参数。"
        accountImpact="只读展示，不影响真实账户。"
        next="如果出现 unknown exposure 或 attention_required，先停止推进 testnet，回到 Runtime Control 看安全按钮。"
        tone={readiness.risk_decision === 'ALLOW_MONITOR' ? 'success' : readiness.risk_decision === 'ALLOW_READ' ? 'info' : 'warning'}
      />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
              风险判断
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="Risk" value={<StatusBadge state={readiness.risk_decision} />} />
            <Row label="Runtime" value={<StatusBadge state={readiness.runtime_state} />} />
            <Row label="未知风险" value={<StatusBadge state={valueAt(exposure, 'unknown_exposure', 'unknown')} />} />
            <Row label="急停可用" value={<StatusBadge state={valueAt(summary, 'cutoff_available', 'unknown')} />} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>账户边界</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="环境" value={stringAt(accountState, 'environment', 'simulation')} />
            <Row label="交易所模式" value={stringAt(accountState, 'exchange_mode', 'unknown')} />
            <Row label="真实账户影响" value={stringAt(accountState, 'real_account_impact', 'none')} />
            <Row label="钱包余额可见" value={<StatusBadge state={valueAt(accountState, 'wallet_equity_available', false)} />} />
            <Row label="保证金可见" value={<StatusBadge state={valueAt(accountState, 'available_margin_available', false)} />} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>空仓证明</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300">
            <Row label="是否空仓" value={<StatusBadge state={valueAt(flatness, 'all_local_flat', 'unknown')} />} />
            <Row label="来源" value={stringAt(flatness, 'source', stringAt(exposure, 'order_source', 'unknown'))} />
            <Row label="时间" value={String(valueAt(flatness, 'timestamp_ms', 'unknown'))} />
            <Row label="订单来源" value={stringAt(exposure, 'order_source', 'unknown')} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CircleDollarSign className="h-3.5 w-3.5 text-emerald-500" />
            持仓与挂单
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 xl:grid-cols-3">
          <RecordPanel title="交易对" items={symbols} empty="当前没有交易对明细。" />
          <RecordPanel title="持仓" items={positions} empty="当前没有本地 active position。" />
          <RecordPanel title="挂单" items={orders} empty="当前没有本地 open order。" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Risk Envelope 风险边界</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300 md:grid-cols-2 xl:grid-cols-4">
          {Object.entries(envelope).map(([key, value]) => (
            <div key={key} className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
              <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{key}</p>
              <p className="mt-1">{String(value)}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <DeveloperDetails data={summary} label="展开风险与账户技术数据" />
    </div>
  );
}

function RecordPanel({ title, items, empty }: { title: string; items: Array<Record<string, unknown>>; empty: string }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-widest text-zinc-500">{title}</p>
      {items.length === 0 ? (
        <EmptyState title={empty} body="这只是本地事实源的读数，不代表真实账户被查询或修改。" />
      ) : (
        <div className="space-y-2">
          {items.map((item, index) => (
            <div key={String(item.order_id || item.position_id || item.symbol_key || index)} className="rounded-sm border border-zinc-200 p-2 text-xs leading-5 dark:border-zinc-800">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-zinc-700 dark:text-zinc-300">{String(item.symbol || item.display_symbol || item.order_id || item.position_id || `record-${index}`)}</span>
                <StatusBadge state={item.status || item.state || item.status_label || 'record'} />
              </div>
              <JsonDetails data={item} label="展开明细" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-2 last:border-0 last:pb-0 dark:border-zinc-800">
      <span className="text-zinc-500">{label}</span>
      <span className="max-w-[65%] text-right font-medium">{value}</span>
    </div>
  );
}

function recordAt(source: Record<string, unknown> | undefined | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayOfRecords(source: Record<string, unknown> | undefined | null, key: string): Array<Record<string, unknown>> {
  const value = source?.[key];
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null && !Array.isArray(item)) : [];
}

function valueAt(source: Record<string, unknown> | undefined | null, key: string, fallback: unknown): unknown {
  return source && key in source ? source[key] : fallback;
}

function stringAt(source: Record<string, unknown> | undefined | null, key: string, fallback: string): string {
  const value = valueAt(source, key, fallback);
  return typeof value === 'string' ? value : String(value);
}
