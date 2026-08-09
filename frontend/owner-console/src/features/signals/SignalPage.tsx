import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ChangeEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../../app/AppShell";
import { CursorPagination } from "../../components/tables/CursorPagination";
import { DenseTable, type DenseTableColumnDef } from "../../components/tables/DenseTable";
import { InlineDetailRow } from "../../components/tables/InlineDetailRow";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { PageHeader } from "../../components/ui/PageHeader";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import type { components } from "../../api/schema";
import {
  getSignalDetail,
  getSignals,
  signalDetailQueryKey,
  signalsQueryKey,
} from "./api";
import {
  parseSignalSearchParams,
  signalSearchParamsToString,
  type SignalSearchParams,
} from "./searchParams";

type SignalItem = components["schemas"]["SignalListItem"];
type SignalDetail = components["schemas"]["SignalAdmissionDetail"];
type Freshness = components["schemas"]["Freshness"];

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function formatTimestamp(value: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function shadowLabel(signal: SignalItem): string {
  return signal.shadow_summary ? signal.shadow_summary.status : "—";
}

function compactBlockerLabel(blocker: string): string {
  return blocker.length > 28 ? `${blocker.slice(0, 28)}…` : blocker;
}

function DetailContent({ signalEventId, refreshVersion }: { signalEventId: string; refreshVersion: number }) {
  const detail = useQuery({
    queryKey: signalDetailQueryKey(signalEventId, refreshVersion),
    queryFn: () => getSignalDetail(signalEventId),
  });

  if (!detail.data) {
    return (
      <div className="min-h-[76px] py-2 text-[12px] text-[var(--color-text-secondary)]" role="status">
        {detail.isError ? "Signal 因果详情不可用" : "正在读取持久化因果详情"}
      </div>
    );
  }

  return <CausalityDetail detail={detail.data.data} />;
}

function CausalityDetail({ detail }: { detail: SignalDetail }) {
  const shadow = detail.shadow_summary;
  return (
    <div className="grid gap-2 text-[12px]">
      <section className="grid gap-1">
        <h3 className="m-0 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--color-text-secondary)]">发生了什么</h3>
        <p className="m-0 break-words text-[var(--color-text-primary)]">{detail.what_happened}</p>
      </section>
      <section className="grid gap-1 border-t border-[var(--color-divider)] pt-2">
        <h3 className="m-0 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--color-text-secondary)]">为什么没有 Ticket</h3>
        <p className="m-0 break-words text-[var(--color-text-primary)]">{detail.why_no_ticket ?? "此 Signal 已准入并创建精确 Ticket。"}</p>
      </section>
      <section className="grid gap-1 border-t border-[var(--color-divider)] pt-2">
        <h3 className="m-0 text-[11px] font-semibold uppercase tracking-[0.04em] text-[var(--color-text-secondary)]">Shadow Outcome</h3>
        {shadow ? (
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[var(--color-text-primary)] sm:grid-cols-4">
            <span>状态 <strong className="tabular-number">{shadow.status}</strong></span>
            <span>MFE R <strong className="tabular-number">{shadow.mfe_r ?? "—"}</strong></span>
            <span>MAE R <strong className="tabular-number">{shadow.mae_r ?? "—"}</strong></span>
            <span className="break-words">{shadow.completion_reason ?? "正在观察"}</span>
          </div>
        ) : (
          <p className="m-0 text-[var(--color-text-secondary)]">没有 Shadow Outcome。</p>
        )}
      </section>
    </div>
  );
}

function SignalFilters({ filters, onChange }: { filters: SignalSearchParams; onChange: (filters: SignalSearchParams) => void }) {
  const setTextFilter = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    const next = { ...filters, [name]: value.trim() || undefined, cursor: undefined } as SignalSearchParams;
    onChange(next);
  };
  const setSelectFilter = (event: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = event.target;
    const next = { ...filters, [name]: value || undefined, cursor: undefined } as SignalSearchParams;
    onChange(next);
  };

  return (
    <form className="mb-2 grid grid-cols-2 gap-2 border border-[var(--color-divider)] bg-[var(--color-surface)] p-2 md:grid-cols-6" aria-label="Signal 筛选条件">
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        StrategyGroup
        <input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="strategy_group_id" value={filters.strategy_group_id ?? ""} onChange={setTextFilter} />
      </label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        Instrument
        <input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="exchange_instrument_id" value={filters.exchange_instrument_id ?? ""} onChange={setTextFilter} />
      </label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        Side
        <select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="position_side" value={filters.position_side ?? ""} onChange={setSelectFilter}>
          <option value="">全部</option><option value="long">Long</option><option value="short">Short</option>
        </select>
      </label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        Decision
        <select className="h-[30px] border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" name="decision_status" value={filters.decision_status ?? ""} onChange={setSelectFilter}>
          <option value="">全部</option><option value="admitted">Admitted</option><option value="rejected">Rejected</option>
        </select>
      </label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        From (ms)
        <input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" inputMode="numeric" name="from_ms" value={filters.from_ms ?? ""} onChange={setTextFilter} />
      </label>
      <label className="grid gap-1 text-[11px] text-[var(--color-text-secondary)]">
        To (ms)
        <input className="h-[30px] min-w-0 border border-[var(--color-divider)] bg-[var(--color-background)] px-2 text-[12px] text-[var(--color-text-primary)] outline-none focus:border-[var(--color-emphasis)]" inputMode="numeric" name="to_ms" value={filters.to_ms ?? ""} onChange={setTextFilter} />
      </label>
    </form>
  );
}

export function SignalPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseSignalSearchParams(searchParams), [searchParams]);
  const [expandedSignalId, setExpandedSignalId] = useState<string | null>(null);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const signals = useQuery({ queryKey: signalsQueryKey(filters), queryFn: () => getSignals(filters) });
  const envelope = signals.data;
  const shellStatus = envelope
    ? freshnessPresentation(envelope.freshness)
    : { label: signals.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };

  const updateFilters = (nextFilters: SignalSearchParams) => {
    setExpandedSignalId(null);
    setSearchParams(signalSearchParamsToString(nextFilters));
  };
  const refreshPage = () => {
    setRefreshVersion((version) => version + 1);
    void signals.refetch();
  };

  const pageHeader = (
    <PageHeader
      title="信号"
      description="持久化 Signal 的准入漏斗与逐条因果事实"
      actions={<ManualRefreshButton isRefreshing={signals.isFetching} onRefresh={refreshPage} />}
    />
  );

  if (!envelope) {
    return (
      <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}>
        {pageHeader}
        <UnavailablePanel title={signals.isError ? "信号不可用" : "正在读取 Signal"} detail={signals.isError ? "保留页面，不把缺失数据解释为无机会。" : "仅读取一次页面快照。"} />
      </AppShell>
    );
  }

  const items = envelope.data.items;
  const admittedCount = items.filter((item) => item.decision_status === "admitted").length;
  const rejectedCount = items.length - admittedCount;
  const status = freshnessPresentation(envelope.freshness);
  const columns: DenseTableColumnDef<SignalItem>[] = [
    {
      id: "signal",
      header: "Signal",
      cell: ({ row }) => {
        const isExpanded = expandedSignalId === row.original.signal_event_id;
        return <button className="min-w-0 max-w-full truncate bg-transparent p-0 text-left text-[var(--color-emphasis)] underline-offset-2 hover:underline" type="button" aria-expanded={isExpanded} aria-label={`${isExpanded ? "收起" : "展开"} ${row.original.strategy_group_id}`} title={row.original.signal_event_id} onClick={() => setExpandedSignalId(isExpanded ? null : row.original.signal_event_id)}>{row.original.signal_event_id}</button>;
      },
    },
    { accessorKey: "strategy_group_id", header: "StrategyGroup", cell: ({ getValue }) => <span className="block truncate">{String(getValue())}</span> },
    { accessorKey: "exchange_instrument_id", header: "Instrument", cell: ({ getValue }) => <span className="block truncate tabular-number">{String(getValue())}</span> },
    { accessorKey: "position_side", header: "Side", cell: ({ getValue }) => <span className="uppercase">{String(getValue())}</span> },
    { accessorKey: "occurred_at_ms", header: "时间", cell: ({ getValue }) => <span className="tabular-number whitespace-nowrap">{formatTimestamp(Number(getValue()))}</span> },
    { accessorKey: "decision_status", header: "Decision", cell: ({ getValue }) => <StatusTag tone={getValue() === "admitted" ? "success" : "attention"}>{getValue() === "admitted" ? "Admitted" : "Rejected"}</StatusTag> },
    { accessorKey: "first_blocker", header: "First blocker", cell: ({ row }) => row.original.first_blocker ? <span className="block truncate text-[var(--color-text-primary)]" title={row.original.first_blocker}>{compactBlockerLabel(row.original.first_blocker)}</span> : row.original.ticket_id ? <Link className="text-[var(--color-emphasis)] hover:underline" to={`/trades/${encodeURIComponent(row.original.ticket_id)}`}>查看 Ticket</Link> : "—" },
    { id: "shadow", header: "Shadow", cell: ({ row }) => <span className="tabular-number text-[var(--color-text-secondary)]">{shadowLabel(row.original)}</span> },
  ];

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      {pageHeader}
      {signals.isRefetchError ? <div className="refresh-error" role="status">刷新失败 · {new Date(signals.errorUpdatedAt).toLocaleTimeString("zh-CN", { hour12: false })}<span>继续显示上一次成功快照</span></div> : null}
      <SignalFilters filters={filters} onChange={updateFilters} />
      <section className="mb-2 grid grid-cols-3 border border-[var(--color-divider)] bg-[var(--color-surface)]" aria-label="准入漏斗">
        <div className="grid min-h-[48px] content-center gap-1 px-2"><span className="text-[11px] text-[var(--color-text-secondary)]">本页 Signals</span><strong className="tabular-number text-[16px]">{items.length}</strong></div>
        <div className="grid min-h-[48px] content-center gap-1 border-l border-[var(--color-divider)] px-2"><span className="text-[11px] text-[var(--color-text-secondary)]">Admitted</span><strong className="tabular-number text-[16px] text-[var(--color-success)]">{admittedCount}</strong></div>
        <div className="grid min-h-[48px] content-center gap-1 border-l border-[var(--color-divider)] px-2"><span className="text-[11px] text-[var(--color-text-secondary)]">Rejected</span><strong className="tabular-number text-[16px]">{rejectedCount}</strong></div>
      </section>
      {items.length === 0 ? <div className="panel compact-empty px-2">当前筛选范围内没有持久化 Signal</div> : <DenseTable ariaLabel="Signal 准入决策" columns={columns} data={items} getRowId={(item) => item.signal_event_id} expandedRowId={expandedSignalId} renderExpandedRow={(item, columnCount) => <InlineDetailRow colSpan={columnCount}><DetailContent signalEventId={item.signal_event_id} refreshVersion={refreshVersion} /></InlineDetailRow>} />}
      <CursorPagination hasNextPage={envelope.data.next_cursor !== null} onNextPage={() => updateFilters({ ...filters, cursor: envelope.data.next_cursor ?? undefined })} />
    </AppShell>
  );
}
