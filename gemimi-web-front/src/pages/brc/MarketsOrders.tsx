import { useEffect, useState } from 'react';
import { ListOrdered, ShieldCheck } from 'lucide-react';
import { brcApi, AccountFactsResponse, ReadinessResponse } from '@/src/services/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/src/components/ui/Card';
import { DeveloperDetails, EmptyState, ErrorState, JsonDetails, OwnerSummary, StageStrip, StatusBadge } from './ConsolePrimitives';

export default function MarketsOrders() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [data, setData] = useState<AccountFactsResponse | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([brcApi.readiness(), brcApi.accountFacts()])
      .then(([ready, payload]) => {
        setReadiness(ready);
        setData(payload);
      })
      .catch(setError);
  }, []);

  if (error) return <ErrorState error={error} />;
  if (!data) return <div className="text-xs text-zinc-500">Loading Markets & Orders...</div>;

  const account = data.account_summary || {};
  const reconciliationStatus = String(data.reconciliation_status?.status || 'unknown');
  const localSummaryOnly = data.source === 'local_pg' && data.truth_level === 'summary';
  const attention = data.blockers.length > 0
    || data.positions.length > 0
    || data.open_orders.length > 0
    || data.unknown_or_unmanaged_orders.length > 0
    || data.unknown_or_unmanaged_positions.length > 0;

  return (
    <div className="space-y-4">
      <StageStrip
        current="Account Facts"
        next="Inspect the BRC-scoped account fact source, truth level, and reconciliation status before any operation."
        global="This is a bounded Owner Console account facts view. It is not a general exchange terminal."
      />
      <OwnerSummary
        conclusion={localSummaryOnly ? 'Current view is local BRC summary, not complete exchange account truth.' : `Account facts source is ${data.source}.`}
        why={`source=${data.source}; truth_level=${data.truth_level}; reconciliation=${reconciliationStatus}.`}
        canDo="Review source, truth level, local BRC positions, local open orders, exposure summary, limitations, and reconciliation structure."
        cannotDo="Cannot place orders, cancel orders, close positions, flatten, withdraw, transfer, enable live, or display fake full fills/history."
        accountImpact="Read-only account facts query. No runtime or exchange mutation is performed."
        next="Emergency flatten/stop planning blocks on unavailable facts, reconciliation mismatch, or unknown/unmanaged exchange exposure."
        tone={attention ? 'warning' : 'info'}
      />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <FactCard title="Source" rows={[
          ['source', data.source],
          ['truth_level', data.truth_level],
          ['reconciliation', reconciliationStatus],
          ['generated', new Date(data.generated_at_ms).toLocaleString()],
        ]} />
        <FactCard title="Account Summary" rows={[
          ['active positions', String(account.active_position_count ?? 0)],
          ['open orders', String(account.open_order_count ?? 0)],
          ['local flat', String(account.all_local_flat ?? false)],
          ['complete truth', String(account.complete_exchange_account_truth ?? false)],
        ]} />
        <FactCard title="Connection Health" rows={[
          ['local_pg', String(recordAt(data.connection_health, 'local_pg').available ?? false)],
          ['exchange_testnet', String(recordAt(data.connection_health, 'exchange_testnet_read').available ?? false)],
          ['exchange_live', String(recordAt(data.connection_health, 'exchange_live_read').available ?? false)],
          ['mutation', String(data.connection_health?.mutation_enabled ?? false)],
        ]} />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <SummaryCard title="Positions" items={data.positions} empty="No local active positions returned." />
        <SummaryCard title="Local Open Orders" items={data.open_orders} empty="No local open orders returned." />
      </div>

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        <SummaryCard title="Recent Orders" items={data.recent_orders} empty="Recent orders are unavailable; they are not mocked." />
        <SummaryCard title="Recent Fills" items={data.recent_fills} empty="Recent fills are unavailable; they are not mocked." />
        <SummaryCard title="Unknown / Unmanaged Orders" items={data.unknown_or_unmanaged_orders} empty="Unknown orders are not inferred without exchange reconciliation." />
        <SummaryCard title="Unknown / Unmanaged Positions" items={data.unknown_or_unmanaged_positions} empty="Unknown positions are not inferred without exchange reconciliation." />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
            Exposure By Symbol
          </CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-2 text-xs leading-5 text-zinc-700 dark:text-zinc-300 md:grid-cols-2">
          {Object.entries(data.exposure_by_symbol).map(([symbol, payload]) => (
            <Metric key={symbol} label={symbol} value={<JsonDetails data={payload} label="Exposure summary" />} />
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Limitations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-xs leading-5">
          <div className="rounded-sm border border-amber-500/30 bg-amber-500/[0.05] p-3 text-amber-800 dark:text-amber-200">
            Unknown or unmanaged exchange exposure blocks emergency execution. Stop Runtime does not flatten or cancel orders by itself;
            flatten planning does not execute flatten unless a backend executor is available.
          </div>
          <List title="Limitations" items={data.limitations} />
          <List title="Warnings" items={data.warnings} />
          <List title="Blockers" items={data.blockers} />
          <JsonDetails data={data.reconciliation_status} label="Reconciliation details" />
        </CardContent>
      </Card>

      <DeveloperDetails data={{ account_facts: data, readiness }} />
    </div>
  );
}

function SummaryCard({
  title,
  items,
  empty,
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  empty: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListOrdered className="h-3.5 w-3.5 text-blue-500" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <EmptyState
            title={empty}
            body="This is not a full exchange account or historical order source."
          />
        ) : (
          <div className="space-y-2">
            {items.map((item, index) => (
              <div key={String(item.order_id || item.position_id || item.symbol || item.display_symbol || index)} className="rounded-sm border border-zinc-200 p-3 text-xs leading-5 dark:border-zinc-800">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-zinc-800 dark:text-zinc-200">
                    {String(item.display_symbol || item.symbol || item.order_id || item.position_id || `record-${index}`)}
                  </span>
                  <StatusBadge state={item.status || item.status_label || item.state || 'record'} />
                </div>
                <JsonDetails data={item} label="Details" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FactCard({ title, rows }: { title: string; rows: Array<[string, React.ReactNode]> }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-xs leading-5">
        {rows.map(([label, value]) => (
          <Metric key={label} label={label} value={value} />
        ))}
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-500">{label}</p>
      <div className="mt-1 font-medium">{value}</div>
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return <EmptyState title={`No ${title.toLowerCase()}`} body="No records returned for this section." />;
  }
  return (
    <div className="rounded-sm border border-zinc-200 p-3 dark:border-zinc-800">
      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">{title}</p>
      <ul className="list-disc space-y-1 pl-5 text-zinc-700 dark:text-zinc-300">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function recordAt(source: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = source[key];
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
