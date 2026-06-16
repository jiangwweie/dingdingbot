import { AlertTriangle, CheckCircle2, ChevronRight, Clock3, RefreshCw, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { automationStateLabels, healthLabels } from "../data";
import type { FundPoolSummary, OwnerHealthState, OwnerImportantChange, OwnerProductSummary, StrategyGroupProductRow } from "../types";
import { attentionTone, healthTone, observationModeLabel, percentOf, sourceKindLabels, stateTone, strategyRiskLabel, toneClass, toneDotClass, toneTextClass, type Tone } from "./model";

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <Badge className={cn("h-6 rounded-lg border px-2 font-semibold leading-none", toneClass(tone))} variant="outline">
      {children}
    </Badge>
  );
}

export function HealthChip({ label, state }: { label: string; state: OwnerHealthState }) {
  const text = state === "normal" ? `${label}正常` : state === "processing" ? `${label}处理中` : `${label}${healthLabels[state]}`;
  return <StatusBadge tone={healthTone[state]}>{text}</StatusBadge>;
}

function primaryHealthFor(strategy: StrategyGroupProductRow): { label: string; state: OwnerHealthState } {
  const items = [
    { label: "资金", state: strategy.funds },
    { label: "订单", state: strategy.orders },
    { label: "持仓", state: strategy.position },
    { label: "保护", state: strategy.protection },
  ];
  return items.find((item) => item.state === "abnormal")
    ?? items.find((item) => item.state === "processing")
    ?? items.find((item) => item.state === "unknown")
    ?? { label: "运行", state: "normal" };
}

export function MetricTile({ icon, label, value, tone }: { icon: ReactNode; label: string; value: number; tone: Tone }) {
  return (
    <Card className="rounded-2xl bg-[color:var(--background-card-raised)] py-0 shadow-[var(--shadow-card)]">
      <CardContent className="flex min-h-[102px] flex-col justify-between p-4">
        <div className="flex items-center gap-3">
          <span className={cn("grid size-7 place-items-center rounded-full border", toneClass(tone))}>{icon}</span>
          <span className="text-sm font-semibold text-muted-foreground">{label}</span>
        </div>
        <div>
          <div className="text-3xl font-semibold tracking-normal">{value}</div>
          <div className="text-xs text-muted-foreground">个策略组</div>
        </div>
      </CardContent>
    </Card>
  );
}

export function SafetyOverviewStrip({ summary }: { summary: OwnerProductSummary }) {
  const overallTone = summary.overallStatus === "safe" ? "safe" : "danger";
  const businessDataUnavailable = !summary.dataFreshnessLabel.startsWith("数据新鲜");
  const headline =
    summary.overallStatus === "safe"
      ? "系统安全运行"
      : businessDataUnavailable
        ? "状态证据待刷新"
        : summary.systemLabel;
  const description =
    summary.overallStatus === "safe"
      ? "自动化正常运行，当前无需操作"
      : businessDataUnavailable
        ? "后端已连接，等待业务状态证据刷新"
        : (summary.reason ?? "状态需要确认");

  return (
    <Card className="rounded-2xl bg-[color:var(--background-panel-strong)] shadow-[var(--shadow-panel)]">
      <CardContent className="flex flex-col gap-4 p-4 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-4">
          <div className={cn("grid size-14 place-items-center rounded-2xl border", toneClass(overallTone))}>
            {overallTone === "safe" ? <ShieldCheck /> : <AlertTriangle />}
          </div>
          <div>
            <div className="text-[1.45rem] font-semibold leading-tight tracking-normal">{headline}</div>
            <div className="mt-1 text-sm text-muted-foreground">{description}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CompactCount label="需处理" tone="danger" value={summary.ownerAttentionCount} />
          <CompactCount label="处理中" tone="processing" value={summary.processingCount} />
          <CompactCount label="暂不可用" tone="danger" value={summary.unavailableCount} />
          <CompactCount label="运行中" tone="safe" value={summary.runningCount} />
        </div>
      </CardContent>
    </Card>
  );
}

export function CompactCount({ label, value, tone }: { label: string; value: number; tone: Tone }) {
  return (
    <div className="min-w-[112px] rounded-xl border bg-card/70 px-4 py-2.5">
      <div className={cn("text-xl font-semibold", toneTextClass(tone))}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export function StrategyAvatar({ code }: { code: StrategyGroupProductRow["code"] }) {
  return (
    <div className={cn("grid size-11 shrink-0 place-items-center rounded-full text-sm font-semibold text-white", `strategy-avatar-${code.toLowerCase()}`)}>
      {code}
    </div>
  );
}

export function StrategyGroupList({
  rows,
  selectedId,
  onSelect,
}: {
  rows: StrategyGroupProductRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
        <CardHeader>
          <CardTitle>策略组状态</CardTitle>
          <CardDescription>暂无已启用策略组</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid min-h-[260px] place-items-center rounded-xl border border-dashed text-sm text-muted-foreground">
            暂无已启用策略组
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-lg shadow-[var(--shadow-panel)]">
      <CardHeader className="pb-3">
        <CardTitle>策略组状态</CardTitle>
        <CardDescription>只显示可用状态、系统处理和需要 Owner 处理的事项</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {rows.map((strategy) => {
          const selected = strategy.id === selectedId;
          const stateLabel = strategy.automationLabel || automationStateLabels[strategy.automationState];
          const state = stateTone[strategy.automationState];
          const ownerAttention = attentionTone[strategy.ownerAttention];
          const primaryHealth = primaryHealthFor(strategy);
          return (
            <button
              className={cn(
                "grid min-h-[64px] cursor-pointer grid-cols-1 gap-3 rounded-lg border bg-[color:var(--background-row)] p-3 text-left transition hover:border-[color:var(--border-strong)] xl:grid-cols-[minmax(150px,1fr)_96px_minmax(0,1.45fr)_88px]",
                selected && "border-[color:var(--border-strong)] shadow-[inset_4px_0_0_var(--accent-primary)]",
              )}
              key={strategy.id}
              onClick={() => onSelect(strategy.id)}
              type="button"
            >
              <div className="flex min-w-0 items-center gap-3">
                <StrategyAvatar code={strategy.code} />
                <div className="min-w-0">
                  <div className="font-semibold">{strategy.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{strategy.description}</div>
                </div>
              </div>
              <div className="flex items-center">
                <StatusBadge tone={state}>{stateLabel}</StatusBadge>
              </div>
              <div className="flex min-w-0 items-center gap-2">
                <HealthChip label={primaryHealth.label} state={primaryHealth.state} />
                <span className="min-w-0 truncate text-xs text-muted-foreground">
                  {strategy.automationState === "waiting_for_opportunity" ? "观察中，等待机会" : strategy.availabilityReason || "边界内状态正常"}
                </span>
              </div>
              <div className={cn("flex min-w-0 items-center justify-start text-sm font-semibold xl:justify-end", toneTextClass(ownerAttention))}>
                {strategy.ownerAttentionLabel}
              </div>
            </button>
          );
        })}
      </CardContent>
    </Card>
  );
}

export function MiniTrendChart({ tone = "safe" }: { tone?: Tone }) {
  const color = tone === "danger" ? "var(--status-danger)" : tone === "processing" ? "var(--status-processing)" : "var(--status-safe)";
  return (
    <div className="relative h-28 overflow-hidden rounded-2xl border bg-[color:var(--background-chart)]">
      <svg aria-hidden="true" className="absolute inset-0 size-full" preserveAspectRatio="none" viewBox="0 0 280 120">
        <defs>
          <linearGradient id="trendFill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.42" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d="M0,98 C24,92 28,70 48,76 C68,82 70,52 92,60 C114,68 115,40 138,48 C160,56 165,32 190,38 C214,44 218,24 240,32 C258,38 266,22 280,26 L280,120 L0,120 Z" fill="url(#trendFill)" />
        <path d="M0,98 C24,92 28,70 48,76 C68,82 70,52 92,60 C114,68 115,40 138,48 C160,56 165,32 190,38 C214,44 218,24 240,32 C258,38 266,22 280,26" fill="none" stroke={color} strokeLinecap="round" strokeWidth="4" />
      </svg>
    </div>
  );
}

export function CurrentStrategyPanel({ strategy }: { strategy: StrategyGroupProductRow | null }) {
  if (!strategy) {
    return (
      <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
        <CardHeader>
          <CardTitle>当前策略组</CardTitle>
          <CardDescription>暂无已启用策略组</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const state = stateTone[strategy.automationState];
  const ownerAttention = attentionTone[strategy.ownerAttention];

  return (
    <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
      <CardHeader>
        <CardTitle>当前策略组</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <StrategyAvatar code={strategy.code} />
          <div>
            <div className="text-lg font-semibold">{strategy.name}</div>
            <div className="text-sm text-muted-foreground">{strategy.description}</div>
          </div>
        </div>
        <MiniTrendChart tone={state} />
        <div className="flex flex-col gap-3">
          <ContextRow label="状态" tone={state} value={strategy.automationLabel || automationStateLabels[strategy.automationState]} />
          <ContextRow label="资金" tone={healthTone[strategy.funds]} value={healthLabels[strategy.funds]} />
          <ContextRow label="订单" tone={healthTone[strategy.orders]} value={healthLabels[strategy.orders]} />
          <ContextRow label="持仓" tone={healthTone[strategy.position]} value={healthLabels[strategy.position]} />
          <ContextRow label="保护" tone={healthTone[strategy.protection]} value={healthLabels[strategy.protection]} />
          <ContextRow label="处理" tone={ownerAttention} value={strategy.ownerAttentionLabel} />
        </div>
        {strategy.availabilityReason && (
          <Alert className="border-[color:var(--status-danger-border)] bg-[color:var(--status-danger-bg)] text-[color:var(--status-danger)]">
            <AlertTriangle />
            <AlertTitle>提示</AlertTitle>
            <AlertDescription className="text-[color:var(--status-danger)]">{strategy.availabilityReason}</AlertDescription>
          </Alert>
        )}
        <Button className="w-full justify-between" variant="outline">
          查看记录
          <ChevronRight />
        </Button>
      </CardContent>
    </Card>
  );
}

export function ContextRow({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b pb-3 last:border-b-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={cn("flex items-center gap-2 text-sm font-semibold", toneTextClass(tone))}>
        <span className={cn("size-2 rounded-full", toneDotClass(tone))} />
        {value}
      </span>
    </div>
  );
}

export function FundsSafetyPanel({ fundPool }: { fundPool: FundPoolSummary }) {
  const reservedPercent = percentOf(fundPool.reserved, fundPool.budget);
  const availablePercent = percentOf(fundPool.available, fundPool.budget);
  const items = [
    { label: "预算", value: fundPool.budget, detail: "100%" },
    { label: "已占用", value: fundPool.reserved, detail: `${reservedPercent}%` },
    { label: "可用", value: fundPool.available, detail: `${availablePercent}%` },
    { label: "订单", value: fundPool.ordersLabel, detail: fundPool.openOrders > 0 ? `${fundPool.openOrders} 个` : "只读确认" },
    { label: "持仓", value: fundPool.positionsLabel, detail: fundPool.activePositions > 0 ? `${fundPool.activePositions} 个` : "只读确认" },
  ];

  return (
    <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck />
          安全资金池
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 xl:grid-cols-[190px_1fr_160px] xl:items-center">
        <div className="flex items-center gap-4 rounded-2xl border bg-[color:var(--background-card-raised)] p-3">
          <div className="grid size-14 place-items-center rounded-2xl border bg-[color:var(--brand-surface)] text-[color:var(--status-safe)]">
            <ShieldCheck />
          </div>
          <div>
            <div className="text-xs text-muted-foreground">{fundPool.label}</div>
            <div className="font-semibold">{fundPool.code}</div>
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {items.map((item) => (
            <div className="min-w-0 border-l pl-4 first:border-l-0 first:pl-0" key={item.label}>
              <div className="text-xs text-muted-foreground">{item.label}</div>
              <div className="mt-1 text-lg font-semibold">{item.value}</div>
              <div className="text-xs text-muted-foreground">{item.detail}</div>
              {(item.label === "已占用" || item.label === "可用") && (
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", item.label === "已占用" ? "bg-[color:var(--status-processing)]" : "bg-[color:var(--status-safe)]")}
                    style={{ width: item.label === "已占用" ? `${reservedPercent}%` : `${availablePercent}%` }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3 rounded-2xl border bg-[color:var(--background-card-raised)] p-3 text-[color:var(--status-safe)]">
          <ShieldCheck />
          <div>
            <div className="text-lg font-semibold">{fundPool.protectionLabel}</div>
            <div className="text-xs text-muted-foreground">{fundPool.reconciliationLabel}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function ImportantChanges({ changes }: { changes: OwnerImportantChange[] }) {
  if (changes.length === 0) return null;

  return (
    <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
      <CardHeader>
        <CardTitle>重要变化</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        {changes.slice(0, 3).map((change) => (
          <div className="flex gap-3 rounded-2xl border bg-[color:var(--background-row)] p-4" key={change.id}>
            <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl border", toneClass(change.tone))}>
              {change.tone === "processing" ? <Clock3 /> : change.tone === "danger" ? <AlertTriangle /> : <ShieldCheck />}
            </span>
            <div className="min-w-0">
              <div className="text-xs text-muted-foreground">{sourceKindLabels[change.sourceKind]}</div>
              <div className="truncate font-semibold">{change.title}</div>
              <div className="truncate text-xs text-muted-foreground">{change.detail}</div>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function FundMiniCard({ label, value, tone = "neutral" }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="rounded-2xl border bg-[color:var(--background-card-raised)] p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold", toneTextClass(tone))}>{value}</div>
    </div>
  );
}

export function StrategyRunSettings({ strategy }: { strategy: StrategyGroupProductRow | null }) {
  const mode = observationModeLabel(strategy);
  const modeTone: Tone = !strategy
    ? "paused"
    : strategy.automationState === "temporarily_unavailable"
      ? "danger"
      : strategy.automationState === "paused" || strategy.automationState === "not_enabled"
        ? "paused"
        : "safe";

  return (
    <Card className="rounded-2xl shadow-[var(--shadow-panel)]">
      <CardHeader>
        <CardTitle>运行设置</CardTitle>
        <CardDescription>只读展示，不修改风险参数</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <ContextRow label="策略组" tone={strategy ? stateTone[strategy.automationState] : "paused"} value={strategy?.name ?? "未选择"} />
        <ContextRow label="风险档" tone={strategyRiskLabel(strategy) === "观察" ? "paused" : "safe"} value={strategyRiskLabel(strategy)} />
        <ContextRow label="观察模式" tone={modeTone} value={mode} />
      </CardContent>
    </Card>
  );
}

export function CascadePanel({ detail, icon, label, tone, value }: { detail: string; icon: ReactNode; label: string; tone: Tone; value: string }) {
  return (
    <div className="rounded-2xl border bg-[color:var(--background-card-raised)] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className={cn("grid size-10 place-items-center rounded-xl border", toneClass(tone))}>{icon}</span>
        <StatusBadge tone={tone}>{value}</StatusBadge>
      </div>
      <div className="mt-5 text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold">{detail}</div>
    </div>
  );
}

export function SystemStateCard({ label, value, tone }: { label: string; value: string; tone: Tone }) {
  return (
    <div className="rounded-2xl border bg-[color:var(--background-card-raised)] p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={cn("mt-2 flex items-center gap-2 text-lg font-semibold", toneTextClass(tone))}>
        <span className={cn("size-2 rounded-full", toneDotClass(tone))} />
        {value}
      </div>
    </div>
  );
}
