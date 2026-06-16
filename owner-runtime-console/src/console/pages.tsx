import { Activity, AlertTriangle, CheckCircle2, Clock3, FileText, ListChecks, RefreshCw, ShieldCheck, Wallet } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { automationStateLabels, healthLabels } from "../data";
import type { OwnerProductProjection, StrategyGroupProductRow } from "../types";
import { PageShell } from "./chrome";
import { healthTone, isBusinessDataUnavailable, noActionGuaranteeLabels, sourceKindLabels, sourceStatusTone, stateTone, toneClass, toneTextClass, type ConsoleContext, type NavigationKey } from "./model";
import { CascadePanel, ContextRow, CurrentStrategyPanel, FundMiniCard, FundsSafetyPanel, ImportantChanges, MetricTile, SafetyOverviewStrip, StatusBadge, StrategyAvatar, StrategyGroupList, StrategyRunSettings, SystemStateCard } from "./panels";

export function ConsoleContent({
  activeView,
  context,
  onSelect,
  projection,
  selectedStrategy,
}: {
  activeView: NavigationKey;
  context: ConsoleContext;
  onSelect: (id: string) => void;
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
}) {
  if (activeView === "strategies") {
    return <StrategyGroupsPage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
  }
  if (activeView === "funds") {
    return <FundsPage projection={projection} />;
  }
  if (activeView === "orders") {
    return <OrdersPositionsPage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
  }
  if (activeView === "records") {
    return <RecordsPage projection={projection} />;
  }
  if (activeView === "system") {
    return <SystemPage context={context} projection={projection} />;
  }
  return <HomePage onSelect={onSelect} projection={projection} selectedStrategy={selectedStrategy} />;
}

function HomePage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="home">
      <SafetyOverviewStrip summary={projection.productSummary} />
      <RuntimeMetrics summary={projection.productSummary} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="grid min-w-0 gap-4">
          <StrategyGroupList onSelect={onSelect} rows={projection.strategies} selectedId={selectedStrategy?.id ?? null} />
          <FundsSafetyPanel fundPool={projection.fundPool} />
        </div>
        <aside className="grid min-w-0 gap-4">
          <CurrentStrategyPanel strategy={selectedStrategy} />
          <RealOrderReadinessCard projection={projection} />
          <ImportantChanges changes={projection.importantChanges} />
        </aside>
      </div>
    </PageShell>
  );
}

function realOrderTone(projection: OwnerProductProjection) {
  const readiness = projection.realOrderReadiness;
  if (readiness.blockedCount > 0 || projection.sourceHealth.realOrderReadiness.status === "unavailable") return "danger" as const;
  if (readiness.readyForRealOrderAction) return "safe" as const;
  if (readiness.waitingCount > 0) return "waiting" as const;
  return sourceStatusTone[projection.sourceHealth.realOrderReadiness.status];
}

function RealOrderReadinessCard({ projection }: { projection: OwnerProductProjection }) {
  const readiness = projection.realOrderReadiness;
  const tone = realOrderTone(projection);
  const actionText = readiness.readyForRealOrderAction
    ? "路径已就绪，系统自动处理"
    : readiness.blockedCount > 0
      ? "路径未就绪，系统保持关闭"
      : "路径健康，等待市场机会";

  return (
    <Card className="rounded-lg shadow-[var(--shadow-panel)]">
      <CardHeader>
        <CardTitle>实盘边界</CardTitle>
        <CardDescription>系统自动判断是否可以靠近真实订单</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex items-center justify-between gap-3">
          <StatusBadge tone={tone}>{readiness.ownerLabel}</StatusBadge>
          <span className={cn("text-sm font-semibold", toneTextClass(tone))}>{actionText}</span>
        </div>
        <div className="rounded-lg border bg-[color:var(--background-card-raised)] p-4">
          <div className="text-lg font-semibold">
            {readiness.passCount} 项正常 / {readiness.waitingCount} 项等待 / {readiness.blockedCount} 项不可用
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            {readiness.blockedCount > 0 ? "系统会保持关闭，直到状态恢复" : "市场没有机会时，系统继续观察"}
          </div>
        </div>
        <ContextRow label="真实订单" tone={tone} value={readiness.readyForRealOrderAction ? "路径就绪" : "保持关闭"} />
      </CardContent>
    </Card>
  );
}

function RuntimeMetrics({ summary }: { summary: OwnerProductProjection["productSummary"] }) {
  const metrics = [
    { label: "已启用", value: summary.enabledCount, tone: "safe" as const, icon: <CheckCircle2 /> },
    { label: "运行中", value: summary.runningCount, tone: "safe" as const, icon: <Activity /> },
    { label: "等待机会", value: summary.waitingCount, tone: "waiting" as const, icon: <Clock3 /> },
    { label: "处理中", value: summary.processingCount, tone: "processing" as const, icon: <RefreshCw /> },
    { label: "需要介入", value: summary.ownerAttentionCount, tone: "danger" as const, icon: <AlertTriangle /> },
  ];

  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="今日概览">
      {metrics.map((metric) => (
        <MetricTile key={metric.label} {...metric} />
      ))}
    </section>
  );
}

function StrategyGroupsPage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="strategies">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <StrategyGroupList onSelect={onSelect} rows={projection.strategies} selectedId={selectedStrategy?.id ?? null} />
        <aside className="grid gap-4">
          <Card className="rounded-lg shadow-[var(--shadow-panel)]">
            <CardHeader>
              <CardTitle>策略组已接入</CardTitle>
              <CardDescription>当前只显示 Owner 能理解和处理的产品状态</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3">
              <ContextRow label="已启用" tone="safe" value={`${projection.productSummary.enabledCount} 个策略组`} />
              <ContextRow label="运行中" tone="safe" value={`${projection.productSummary.runningCount} 个`} />
              <ContextRow label="等待机会" tone="waiting" value={`${projection.productSummary.waitingCount} 个`} />
              <ContextRow label="处理中" tone="processing" value={`${projection.productSummary.processingCount} 个`} />
              <ContextRow label="需要介入" tone="danger" value={`${projection.productSummary.ownerAttentionCount} 个`} />
            </CardContent>
          </Card>
          <StrategyRunSettings strategy={selectedStrategy} />
          <CurrentStrategyPanel strategy={selectedStrategy} />
        </aside>
      </div>
    </PageShell>
  );
}

function FundsPage({ projection }: { projection: OwnerProductProjection }) {
  const fundPool = projection.fundPool;
  return (
    <PageShell activeView="funds">
      <FundsSafetyPanel fundPool={fundPool} />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>账户只读</CardTitle>
            <CardDescription>本地只读 key 用于读取资金状态，不承担交易动作</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <ContextRow label="账户" tone="safe" value={fundPool.code} />
            <ContextRow label="资金" tone={sourceStatusTone[projection.sourceHealth.accountFunds.status]} value={fundPool.accountLabel} />
            <ContextRow label="保护" tone={healthTone[projection.strategies[0]?.protection ?? "unknown"]} value={fundPool.protectionLabel} />
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)] lg:col-span-2">
          <CardHeader>
            <CardTitle>资金分配</CardTitle>
            <CardDescription>只展示资金池状态，不提供划转、扩额或改仓入口</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <FundMiniCard label="预算" value={fundPool.budget} />
            <FundMiniCard label="已占用" value={fundPool.reserved} tone="processing" />
            <FundMiniCard label="可用" value={fundPool.available} tone="safe" />
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function OrdersPositionsPage({
  projection,
  selectedStrategy,
  onSelect,
}: {
  projection: OwnerProductProjection;
  selectedStrategy: StrategyGroupProductRow | null;
  onSelect: (id: string) => void;
}) {
  return (
    <PageShell activeView="orders">
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>策略组</CardTitle>
            <CardDescription>选择后查看对应订单和持仓级联</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {projection.strategies.length === 0 ? (
              <div className="grid min-h-[140px] place-items-center rounded-lg border border-dashed text-sm text-muted-foreground">
                暂无已启用策略组
              </div>
            ) : (
              projection.strategies.map((strategy) => (
                <button
                  className={cn(
                    "flex cursor-pointer items-center justify-between rounded-lg border bg-[color:var(--background-row)] p-3 text-left transition hover:border-[color:var(--border-strong)]",
                    selectedStrategy?.id === strategy.id && "border-[color:var(--border-strong)] shadow-[inset_4px_0_0_var(--accent-primary)]",
                  )}
                  key={strategy.id}
                  onClick={() => onSelect(strategy.id)}
                  type="button"
                >
                  <span className="flex items-center gap-3">
                    <StrategyAvatar code={strategy.code} />
                    <span>
                      <span className="block font-semibold">{strategy.name}</span>
                      <span className="block text-xs text-muted-foreground">{strategy.description}</span>
                    </span>
                  </span>
                  <StatusBadge tone={stateTone[strategy.automationState]}>
                    {strategy.automationLabel || automationStateLabels[strategy.automationState]}
                  </StatusBadge>
                </button>
              ))
            )}
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>级联视图</CardTitle>
            <CardDescription>持仓、成交单、保护单和对账状态保持同屏可见</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 lg:grid-cols-4">
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.position]}` : "暂无持仓"}
              icon={<Wallet />}
              label="持仓"
              tone={sourceStatusTone[projection.sourceHealth.positions.status]}
              value={projection.fundPool.positionsLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.orders]}` : projection.fundPool.ordersLabel}
              icon={<ListChecks />}
              label="成交单"
              tone={sourceStatusTone[projection.sourceHealth.orders.status]}
              value={projection.fundPool.ordersLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.protection]}` : "暂无保护单"}
              icon={<ShieldCheck />}
              label="保护单"
              tone={healthTone[selectedStrategy?.protection ?? "unknown"]}
              value={projection.fundPool.protectionLabel}
            />
            <CascadePanel
              detail={selectedStrategy ? `${selectedStrategy.name} ${healthLabels[selectedStrategy.reconciliation]}` : "暂无对账"}
              icon={<RefreshCw />}
              label="对账"
              tone={sourceStatusTone[projection.sourceHealth.reconciliation.status]}
              value={projection.fundPool.reconciliationLabel}
            />
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function RecordsPage({ projection }: { projection: OwnerProductProjection }) {
  return (
    <PageShell activeView="records">
      <ImportantChanges changes={projection.importantChanges} />
      <Card className="rounded-lg shadow-[var(--shadow-panel)]">
        <CardHeader>
          <CardTitle>最近记录</CardTitle>
          <CardDescription>Web 只保留重要变化入口，深度复盘交给记录和 AI 解读</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {projection.importantChanges.map((change) => (
            <div className="flex items-center gap-3 rounded-lg border bg-[color:var(--background-row)] p-4" key={change.id}>
              <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl border", toneClass(change.tone))}>
                {change.tone === "processing" ? <RefreshCw /> : change.tone === "danger" ? <AlertTriangle /> : <FileText />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold">{change.title}</div>
                <div className="text-sm text-muted-foreground">{change.detail}</div>
              </div>
              <Badge variant="outline">{sourceKindLabels[change.sourceKind]}</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </PageShell>
  );
}

function SystemPage({ context, projection }: { context: ConsoleContext; projection: OwnerProductProjection }) {
  const connected = context.connectionState === "connected";
  const businessDataUnavailable = isBusinessDataUnavailable(projection.productSummary);
  const dryRunSummary = projection.sourceHealth.runtimeDryRunAudit.summary;
  const dryRunRows = buildDryRunSummaryRows(dryRunSummary);
  const guaranteeRows = Object.entries(projection.noActionGuarantee)
    .filter(([, value]) => value === false)
    .map(([key]) => noActionGuaranteeLabels[key] ?? key);
  const sourceRows = [
    { label: "策略目录", item: projection.sourceHealth.catalog },
    { label: "运行状态", item: projection.sourceHealth.runtime },
    { label: "观察服务", item: projection.sourceHealth.watcher },
    { label: "事实状态", item: projection.sourceHealth.liveFacts },
    { label: "账户资金", item: projection.sourceHealth.accountFunds },
    { label: "订单", item: projection.sourceHealth.orders },
    { label: "持仓", item: projection.sourceHealth.positions },
    { label: "保护", item: projection.sourceHealth.protection },
    { label: "对账", item: projection.sourceHealth.reconciliation },
    { label: "审计记录", item: projection.sourceHealth.operationAudit },
    { label: "审计演练", item: projection.sourceHealth.runtimeDryRunAudit },
    { label: "实盘边界", item: projection.sourceHealth.realOrderReadiness },
  ];

  return (
    <PageShell activeView="system">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>数据状态</CardTitle>
            <CardDescription>后端连接与业务状态分开显示</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            <SystemStateCard label="后端连接" tone={connected ? "safe" : "danger"} value={connected ? "已连接" : "不可用"} />
            <SystemStateCard label="业务数据" tone={businessDataUnavailable ? "danger" : "safe"} value={businessDataUnavailable ? "状态证据待刷新" : "正常"} />
            <SystemStateCard label="刷新时间" tone="neutral" value={context.refreshedAt ? new Date(context.refreshedAt).toLocaleTimeString("zh-CN", { hour12: false }) : "加载中"} />
            {sourceRows.map(({ label, item }) => (
              <SystemStateCard key={label} label={label} tone={sourceStatusTone[item.status]} value={item.label} />
            ))}
          </CardContent>
        </Card>
        <Card className="rounded-lg shadow-[var(--shadow-panel)]">
          <CardHeader>
            <CardTitle>只读保证</CardTitle>
            <CardDescription>当前前端只读取状态，不触发交易动作</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {guaranteeRows.map((label) => (
              <div className="flex items-center gap-2 text-sm text-[color:var(--status-safe)]" key={label}>
                <CheckCircle2 className="size-4" />
                {label}
              </div>
            ))}
            {dryRunRows.length > 0 ? (
              <>
                <Separator className="my-2" />
                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold">审计演练摘要</div>
                      <div className="text-xs text-muted-foreground">共性执行管道已通过只读演练</div>
                    </div>
                    <StatusBadge tone="safe">无需操作</StatusBadge>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                    {dryRunRows.map((row) => (
                      <div className="flex items-center gap-2 text-sm" key={row.label}>
                        <CheckCircle2 className="size-4 text-[color:var(--status-safe)]" />
                        <span className="text-muted-foreground">{row.label}</span>
                        <span className="font-semibold">{row.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : null}
            <Separator className="my-2" />
            <div className="text-xs text-muted-foreground">来源：{context.sourceLabel ?? projection.source}</div>
          </CardContent>
        </Card>
      </div>
    </PageShell>
  );
}

function buildDryRunSummaryRows(summary: Record<string, unknown> | undefined) {
  if (!summary) return [];
  const scenarioCount = typeof summary.scenario_count === "number" ? summary.scenario_count : null;
  const rows = [
    scenarioCount !== null ? { label: "演练场景", value: `${scenarioCount} 项通过` } : null,
    summary.shared_runtime_pipeline_checked === true ? { label: "共性管道", value: "已覆盖" } : null,
    summary.selected_strategygroup_dispatch_guard_checked === true ? { label: "选中范围", value: "已校验" } : null,
    summary.all_selected_strategygroups_reach_finalgate_dispatch_checked === true ? { label: "五组策略", value: "已覆盖" } : null,
    summary.operation_layer_hard_safety_blocker_matrix_checked === true ? { label: "安全矩阵", value: "已覆盖" } : null,
    summary.expanded_watcher_scope_execution_guard_checked === true ? { label: "观察范围", value: "已隔离" } : null,
    summary.operation_layer_authorization_chain_guard_checked === true ? { label: "证据接力", value: "已校验" } : null,
    summary.post_submit_closed_loop_evidence_guard_checked === true ? { label: "闭环证据", value: "已校验" } : null,
    summary.dangerous_effects_absent === true && summary.disabled_smoke_is_real_execution_proof === false
      ? { label: "危险动作", value: "未发生" }
      : null,
  ];
  return rows.filter((row): row is { label: string; value: string } => row !== null);
}
