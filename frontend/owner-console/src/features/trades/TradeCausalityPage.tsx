import { useQuery } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import { Maximize2, X } from "lucide-react";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";
import { AppShell } from "../../app/AppShell";
import { DataAge } from "../../components/ui/DataAge";
import { ManualRefreshButton } from "../../components/ui/ManualRefreshButton";
import { formatMoney, formatOwnerReason, formatOwnerStatus } from "../../components/ui/presentation";
import { StatusTag, type StatusTone } from "../../components/ui/StatusTag";
import { UnavailablePanel } from "../../components/ui/UnavailablePanel";
import type { components } from "../../api/schema";
import {
  candlesQueryKey,
  getCandles,
  getTradeCausality,
  tradeCausalityQueryKey,
} from "./api";

const CausalityChart = lazy(() => import("../../components/charts/CausalityChart"));

type Freshness = components["schemas"]["Freshness"];
type Stage = components["schemas"]["LifecycleStageView"];
type Evidence = components["schemas"]["EvidenceRef"];

interface TradeRouteState {
  returnPath?: string;
  ticketIds?: string[];
}

function freshnessPresentation(freshness: Freshness) {
  if (freshness === "stale") return { label: "数据陈旧", tone: "attention" as const };
  if (freshness === "unavailable") return { label: "数据不可用", tone: "danger" as const };
  if (freshness === "contradictory") return { label: "事实矛盾", tone: "danger" as const };
  return { label: "数据正常", tone: "success" as const };
}

function safeReturnPath(value: string | null, stateValue?: string): string {
  const candidate = stateValue ?? value ?? "/trades";
  return candidate === "/trades" || candidate.startsWith("/trades?") ? candidate : "/trades";
}

function formatTimestamp(value: number | null): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date(value));
}

function formatDuration(value: number | null): string {
  if (value === null) return "—";
  if (value < 60_000) return `${Math.round(value / 1000)}s`;
  if (value < 3_600_000) return `${Math.round(value / 60_000)}m`;
  return `${(value / 3_600_000).toFixed(1)}h`;
}

function stageTone(stage: Stage): StatusTone {
  if (stage.status === "current") return "attention";
  if (stage.status === "complete") return "success";
  if (stage.status === "unavailable") return "danger";
  return "neutral";
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) return <p className="m-0 text-[12px] text-[var(--color-text-secondary)]">无证据行</p>;
  return <ul className="m-0 grid list-none gap-1 p-0">{evidence.map((item) => <li className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 text-[11px]" key={`${item.kind}:${item.identity}:${item.occurred_at_ms}`}><span className="uppercase text-[var(--color-text-secondary)]">{item.kind}</span><span className="break-all text-[var(--color-text-primary)]">{item.identity}</span></li>)}</ul>;
}

function StageFacts({ stage }: { stage: Stage }) {
  return (
    <div className="grid content-start gap-3">
      <div className="flex items-center justify-between gap-2"><h2 className="m-0 text-[14px] font-semibold">{stage.label}</h2><StatusTag tone={stageTone(stage)}>{formatOwnerStatus(stage.status)}</StatusTag></div>
      <p className="m-0 break-words text-[12px] leading-5 text-[var(--color-text-primary)]">{stage.summary}</p>
      <dl className="m-0 grid grid-cols-2 gap-2 text-[11px]"><div><dt className="text-[var(--color-text-secondary)]">开始</dt><dd className="m-0 mt-1 tabular-number">{formatTimestamp(stage.started_at_ms)}</dd></div><div><dt className="text-[var(--color-text-secondary)]">完成</dt><dd className="m-0 mt-1 tabular-number">{formatTimestamp(stage.completed_at_ms)}</dd></div><div><dt className="text-[var(--color-text-secondary)]">耗时</dt><dd className="m-0 mt-1 tabular-number">{formatDuration(stage.duration_ms)}</dd></div><div><dt className="text-[var(--color-text-secondary)]">证据数</dt><dd className="m-0 mt-1 tabular-number">{stage.evidence.length}</dd></div></dl>
      <section className="border-t border-[var(--color-divider)] pt-3"><h3 className="mb-2 mt-0 text-[11px] uppercase tracking-[0.04em] text-[var(--color-text-secondary)]">阶段证据</h3><EvidenceList evidence={stage.evidence} /></section>
    </div>
  );
}

function JsonValue({ value }: { value: unknown }) {
  return <pre className="m-0 max-h-28 overflow-auto whitespace-pre-wrap break-all bg-[var(--color-background)] p-2 text-[10px] leading-4 text-[var(--color-text-secondary)]">{JSON.stringify(value, null, 2)}</pre>;
}

export function TradeCausalityPage() {
  const { ticketId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const routeState = (location.state ?? {}) as TradeRouteState;
  const detail = useQuery({ queryKey: tradeCausalityQueryKey(ticketId), queryFn: () => getTradeCausality(ticketId), enabled: ticketId.length > 0 });
  const [selectedStageKey, setSelectedStageKey] = useState<Stage["key"] | null>(null);
  const [chartExpanded, setChartExpanded] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  useEffect(() => {
    setSelectedStageKey(null);
    setChartExpanded(false);
    setChartFullscreen(false);
  }, [ticketId]);
  const envelope = detail.data;
  const closedAtMs = envelope ? envelope.data.trade.terminal_at_ms ?? Date.parse(envelope.generated_at) : 0;
  const candles = useQuery({
    queryKey: candlesQueryKey(ticketId, closedAtMs),
    queryFn: () => getCandles({ exchangeInstrumentId: envelope!.data.trade.exchange_instrument_id, closedAtMs }),
    enabled: chartExpanded && Boolean(envelope) && closedAtMs > 0,
  });
  useEffect(() => {
    if (envelope && selectedStageKey === null) setSelectedStageKey(envelope.data.current_stage);
  }, [envelope, selectedStageKey]);

  const shellStatus = envelope ? freshnessPresentation(envelope.freshness) : { label: detail.isError ? "不可用" : "加载中", tone: "neutral" as StatusTone };
  const returnPath = safeReturnPath(searchParams.get("return"), routeState.returnPath);
  const ticketIds = routeState.ticketIds ?? [];
  const ticketIndex = ticketIds.indexOf(ticketId);
  const previousTicketId = ticketIndex > 0 ? ticketIds[ticketIndex - 1] : null;
  const nextTicketId = ticketIndex >= 0 && ticketIndex < ticketIds.length - 1 ? ticketIds[ticketIndex + 1] : null;
  const detailSearch = searchParams.toString();
  const detailHref = (id: string) => `/trades/${encodeURIComponent(id)}${detailSearch ? `?${detailSearch}` : ""}`;

  const refreshPage = () => {
    void detail.refetch();
    if (chartExpanded) void candles.refetch();
  };

  if (!envelope) {
    return <AppShell dataTime={<DataAge generatedAt={null} />} statusLabel={shellStatus.label} statusTone={shellStatus.tone}><div className="mb-2"><Link className="text-[12px] text-[var(--color-emphasis)] hover:underline" to={returnPath}>返回交易列表</Link></div><UnavailablePanel title={detail.isError ? "Ticket 因果不可用" : "正在读取 Ticket 因果"} detail={detail.isError ? "保留精确 Ticket 路由，不把缺失事实解释为无交易。" : ticketId} /></AppShell>;
  }

  const data = envelope.data;
  const selectedStage = data.stages.find((stage) => stage.key === selectedStageKey) ?? data.stages.find((stage) => stage.key === data.current_stage) ?? data.stages[0];
  const status = freshnessPresentation(envelope.freshness);
  if (!selectedStage) {
    return <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel="事实矛盾" statusTone="danger"><div className="mb-2"><Link className="text-[12px] text-[var(--color-emphasis)] hover:underline" to={returnPath}>返回交易列表</Link></div><UnavailablePanel title="生命周期不可用" detail="精确 Ticket 因果响应没有任何生命周期阶段。" /></AppShell>;
  }

  return (
    <AppShell dataTime={<DataAge generatedAt={envelope.generated_at} />} statusLabel={status.label} statusTone={status.tone}>
      <div className="mb-2 flex min-h-9 items-center justify-between gap-3">
        <nav className="min-w-0 truncate text-[12px] text-[var(--color-text-secondary)]" aria-label="面包屑"><Link className="text-[var(--color-emphasis)] hover:underline" to={returnPath}>交易</Link><span> / {data.trade.exchange_instrument_id} {data.trade.position_side.toUpperCase()} / </span><strong className="text-[var(--color-text-primary)]">{data.trade.ticket_id}</strong></nav>
        <div className="flex flex-none items-center gap-2"><Link className={`owner-button grid h-8 place-items-center no-underline ${previousTicketId ? "" : "pointer-events-none opacity-40"}`} state={routeState} to={previousTicketId ? detailHref(previousTicketId) : "#"} aria-disabled={!previousTicketId}>上一笔</Link><Link className={`owner-button grid h-8 place-items-center no-underline ${nextTicketId ? "" : "pointer-events-none opacity-40"}`} state={routeState} to={nextTicketId ? detailHref(nextTicketId) : "#"} aria-disabled={!nextTicketId}>下一笔</Link><ManualRefreshButton isRefreshing={detail.isFetching || candles.isFetching} onRefresh={refreshPage} /></div>
      </div>

      <section className="mb-2 grid border border-[var(--color-divider)] bg-[var(--color-surface)] lg:grid-cols-12">
        <div className="border-b border-[var(--color-divider)] lg:col-span-3 lg:border-b-0 lg:border-r">
          <div className="flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">生命周期 · 8 阶段</div>
          <div className="grid">{data.stages.map((stage, index) => <button className={`grid min-h-[52px] grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-2 border-b border-[var(--color-divider)] bg-transparent px-2 text-left last:border-b-0 hover:bg-[var(--color-surface-secondary)] ${selectedStage?.key === stage.key ? "bg-[var(--color-surface-secondary)]" : ""}`} data-testid="lifecycle-stage" key={stage.key} type="button" onClick={() => setSelectedStageKey(stage.key)}><span className="grid h-5 w-5 place-items-center border border-[var(--color-divider)] text-[10px] tabular-number">{index + 1}</span><span className="min-w-0"><strong className="block truncate text-[12px] font-medium">{stage.label}</strong><small className="block truncate text-[10px] text-[var(--color-text-secondary)]">{stage.summary}</small></span><StatusTag tone={stageTone(stage)}>{formatOwnerStatus(stage.status)}</StatusTag></button>)}</div>
        </div>

        <div className="min-h-[456px] border-b border-[var(--color-divider)] lg:col-span-6 lg:border-b-0 lg:border-r">
          <div className="flex min-h-[30px] items-center justify-between border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2"><span className="text-[11px] font-medium text-[var(--color-text-secondary)]">价格背景 · 15m · 手动加载</span>{chartExpanded ? <div className="flex items-center gap-3"><button className="inline-flex items-center gap-1 bg-transparent p-0 text-[11px] text-[var(--color-emphasis)] hover:underline" disabled={!candles.data} type="button" aria-label="全屏复盘 K 线" onClick={() => setChartFullscreen(true)}><Maximize2 aria-hidden="true" className="h-3 w-3" />全屏复盘</button><button className="bg-transparent p-0 text-[11px] text-[var(--color-emphasis)] hover:underline" type="button" onClick={() => { setChartExpanded(false); setChartFullscreen(false); }}>收起 K 线</button></div> : null}</div>
          {!chartExpanded ? <div className="grid min-h-[425px] place-content-center gap-3 text-center"><p className="m-0 text-[12px] text-[var(--color-text-secondary)]">生命周期事实已加载，公共 K 线尚未请求</p><button className="owner-button mx-auto h-8" type="button" onClick={() => setChartExpanded(true)}>展开 K 线</button></div> : candles.isError ? <div className="grid min-h-[425px] place-content-center gap-2 text-center"><strong>公共行情不可用</strong><span className="text-[12px] text-[var(--color-text-secondary)]">生命周期、订单与 Review 事实仍可阅读</span></div> : !candles.data ? <div className="grid min-h-[425px] place-content-center text-[12px] text-[var(--color-text-secondary)]">正在读取公共行情</div> : <Suspense fallback={<div className="grid min-h-[425px] place-content-center text-[12px] text-[var(--color-text-secondary)]">正在加载图表组件</div>}><CausalityChart annotations={data.annotations} candles={candles.data.data.candles} /></Suspense>}
        </div>

        <aside className="max-h-[520px] overflow-y-auto p-3 lg:col-span-3" aria-label="当前阶段事实"><StageFacts stage={selectedStage} /></aside>
      </section>

      <Dialog.Root open={chartFullscreen} onOpenChange={setChartFullscreen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/80" />
          <Dialog.Content className="fixed inset-4 z-50 grid max-h-[calc(100vh-32px)] grid-rows-[auto_minmax(0,1fr)] border border-[var(--color-divider)] bg-[var(--color-background)] shadow-2xl outline-none md:inset-8">
            <div className="flex min-h-11 items-center justify-between gap-3 border-b border-[var(--color-divider)] bg-[var(--color-surface)] px-3">
              <div className="min-w-0"><Dialog.Title className="m-0 truncate text-[14px] font-semibold">{data.trade.exchange_instrument_id} {data.trade.position_side.toUpperCase()} · 15m K 线复盘</Dialog.Title><Dialog.Description className="m-0 truncate text-[11px] text-[var(--color-text-secondary)]">只读市场背景，标记对应本 Ticket 的生命周期事实</Dialog.Description></div>
              <Dialog.Close asChild><button className="grid h-8 w-8 place-items-center bg-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]" type="button" aria-label="关闭全屏复盘"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close>
            </div>
            <div className="min-h-0 p-2">{candles.data ? <Suspense fallback={<div className="grid h-full place-content-center text-[12px] text-[var(--color-text-secondary)]">正在加载图表组件</div>}><CausalityChart annotations={data.annotations} candles={candles.data.data.candles} fullscreen /></Suspense> : null}</div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <section className="mb-2 grid border border-[var(--color-divider)] bg-[var(--color-surface)] md:grid-cols-5" aria-label="交易经济事实">
        {[["状态", formatOwnerStatus(data.trade.aggregate_status)], ["退出原因", data.exit_reason?.label ?? (data.trade.exit_reason ? formatOwnerReason(data.trade.exit_reason).label : "—")], ["净盈亏", data.trade.net_pnl.value === null ? "—" : formatMoney(data.trade.net_pnl.value, data.trade.net_pnl.unit, { sign: true })], ["净 R", data.trade.net_r.value === null ? "—" : formatMoney(data.trade.net_r.value, data.trade.net_r.unit, { sign: true })], ["手续费 / 资金费", `${data.trade.fees.value === null ? "—" : formatMoney(data.trade.fees.value, data.trade.fees.unit)} / ${data.trade.funding.value === null ? "—" : formatMoney(data.trade.funding.value, data.trade.funding.unit)}`]].map(([label, value], index) => <div className={`grid min-h-[54px] content-center gap-1 px-2 ${index > 0 ? "border-l border-[var(--color-divider)]" : ""}`} key={label}><span className="text-[10px] text-[var(--color-text-secondary)]">{label}</span><strong className="truncate text-[12px]" title={value}>{value}</strong></div>)}
      </section>

      <div className="grid gap-2 xl:grid-cols-2">
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)]"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">Exchange Commands · {data.raw_commands.length}</h2><div className="grid gap-2 p-2">{data.raw_commands.length === 0 ? <span className="text-[12px] text-[var(--color-text-secondary)]">无 Command</span> : data.raw_commands.map((command) => <article className="grid gap-1 border-b border-[var(--color-divider)] pb-2 last:border-b-0 last:pb-0" key={command.command_id}><div className="flex justify-between gap-2 text-[11px]"><strong>{command.command_kind} · gen {command.generation}</strong><StatusTag tone={command.status.includes("unknown") ? "danger" : "success"}>{command.status}</StatusTag></div><span className="break-all text-[10px] text-[var(--color-text-secondary)]">{command.command_id}</span><JsonValue value={{ request: command.request_payload, result: command.result_payload }} /></article>)}</div></section>
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)]"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">Incidents · {data.raw_incidents.length}</h2><div className="grid gap-2 p-2">{data.raw_incidents.length === 0 ? <span className="text-[12px] text-[var(--color-text-secondary)]">无 Incident</span> : data.raw_incidents.map((incident) => <article className="grid gap-1 border-b border-[var(--color-divider)] pb-2 last:border-b-0" key={incident.incident_id}><div className="flex justify-between gap-2"><strong>{incident.incident_kind}</strong><StatusTag tone={incident.status === "open" ? "danger" : "success"}>{incident.status}</StatusTag></div><span className="break-all text-[11px] text-[var(--color-danger)]">{incident.first_blocker}</span><JsonValue value={incident.details} /></article>)}</div></section>
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)] xl:col-span-2"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">Trade Events · {data.raw_events.length}</h2><div className="overflow-x-auto"><table className="w-full min-w-[760px] border-collapse text-left text-[11px]"><thead className="h-[30px] border-b border-[var(--color-divider)] text-[var(--color-text-secondary)]"><tr><th className="px-2">Seq</th><th className="px-2">Stage</th><th className="px-2">Event</th><th className="px-2">Time</th><th className="px-2">Payload</th></tr></thead><tbody>{data.raw_events.map((event) => <tr className="border-b border-[var(--color-divider)] last:border-b-0" key={event.event_id}><td className="px-2 py-2 tabular-number">{event.sequence}</td><td className="px-2 py-2 uppercase">{event.stage}</td><td className="px-2 py-2 font-medium">{event.event_type}</td><td className="px-2 py-2 tabular-number">{formatTimestamp(event.occurred_at_ms)}</td><td className="max-w-[420px] px-2 py-2"><JsonValue value={event.payload} /></td></tr>)}</tbody></table></div></section>
        <section className="border border-[var(--color-divider)] bg-[var(--color-surface)] xl:col-span-2"><h2 className="m-0 flex min-h-[30px] items-center border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] px-2 text-[11px] font-medium text-[var(--color-text-secondary)]">证据索引 · {data.evidence.length}</h2><div className="grid gap-3 p-2 md:grid-cols-3"><div><h3 className="mb-2 mt-0 text-[10px] uppercase text-[var(--color-text-secondary)]">Signal</h3><EvidenceList evidence={data.signal_evidence} /></div><div><h3 className="mb-2 mt-0 text-[10px] uppercase text-[var(--color-text-secondary)]">Orders / Incidents</h3><EvidenceList evidence={[...data.order_evidence, ...data.incident_evidence]} /></div><div><h3 className="mb-2 mt-0 text-[10px] uppercase text-[var(--color-text-secondary)]">Settlement / Review</h3><EvidenceList evidence={[...data.settlement_evidence, ...data.review_evidence]} /></div></div></section>
      </div>
    </AppShell>
  );
}
