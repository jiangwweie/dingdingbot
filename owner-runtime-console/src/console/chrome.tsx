import { Activity, AlertTriangle, Bell, CheckCircle2, ChevronRight, Home, ListChecks, Lock, Moon, RefreshCw, ShieldCheck, SlidersHorizontal, Sun, User, Wallet, FileText } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { OwnerProductSummary } from "../types";
import { isBusinessDataUnavailable, navigationDescriptions, navigationTitles, toneClass, type BackendConnectionState, type NavigationKey, type ThemeMode, type Tone } from "./model";

const navigation = [
  { key: "home", label: "首页", icon: Home },
  { key: "strategies", label: "策略组", icon: SlidersHorizontal },
  { key: "funds", label: "资金", icon: Wallet },
  { key: "orders", label: "订单与持仓", icon: ListChecks },
  { key: "records", label: "记录", icon: FileText },
  { key: "system", label: "系统", icon: RefreshCw },
] satisfies Array<{ key: NavigationKey; label: string; icon: LucideIcon }>;

export function useThemeMode() {
  const [theme, setTheme] = useState<ThemeMode>(() => {
    if (typeof window === "undefined") return "dark";
    const saved = window.localStorage.getItem("owner-console-theme");
    return saved === "light" ? "light" : "dark";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.dataset.theme = theme;
    window.localStorage.setItem("owner-console-theme", theme);
  }, [theme]);

  return { theme, setTheme };
}

export function ProductMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="grid size-11 shrink-0 place-items-center rounded-2xl border border-[color:var(--brand-border)] bg-[color:var(--brand-surface)] text-[color:var(--accent-primary)] shadow-[var(--shadow-mark)]">
        <ShieldCheck />
      </div>
      {!compact && (
        <div className="min-w-0">
          <div className="text-base font-semibold tracking-normal">BRC Owner Console</div>
          <div className="text-xs text-muted-foreground">个人量化系统控制台</div>
        </div>
      )}
    </div>
  );
}

export function Sidebar({ activeView, onSelect }: { activeView: NavigationKey; onSelect: (key: NavigationKey) => void }) {
  return (
    <aside className="hidden min-h-screen w-[240px] shrink-0 border-r border-sidebar-border bg-sidebar px-4 py-5 text-sidebar-foreground lg:flex lg:flex-col">
      <ProductMark />
      <nav className="mt-9 flex flex-col gap-2" aria-label="主导航">
        {navigation.map((item) => {
          const Icon = item.icon;
          const active = item.key === activeView;
          return (
            <button
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-12 cursor-pointer items-center gap-3 rounded-xl px-4 text-left text-sm font-medium transition",
                active
                  ? "bg-sidebar-primary text-sidebar-primary-foreground shadow-[var(--shadow-active-nav)]"
                  : "text-sidebar-foreground/72 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
              key={item.label}
              onClick={() => onSelect(item.key)}
              type="button"
            >
              <Icon />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="mt-auto border-t border-sidebar-border pt-5">
        <Button className="w-full justify-start text-sidebar-foreground/70" variant="ghost">
          <ChevronRight className="rotate-180" />
          收起菜单
        </Button>
      </div>
    </aside>
  );
}

export function MobileNav({ activeView, onSelect }: { activeView: NavigationKey; onSelect: (key: NavigationKey) => void }) {
  return (
    <nav className="grid grid-cols-3 gap-2 border-b bg-[color:var(--background-topbar)] px-3 py-3 lg:hidden" aria-label="移动导航">
      {navigation.map((item) => {
        const Icon = item.icon;
        const active = item.key === activeView;
        return (
          <button
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-10 cursor-pointer items-center justify-center gap-1.5 rounded-lg px-2 text-xs font-semibold transition",
              active
                ? "bg-sidebar-primary text-sidebar-primary-foreground"
                : "border bg-card/70 text-muted-foreground",
            )}
            key={item.label}
            onClick={() => onSelect(item.key)}
            type="button"
          >
            <Icon className="size-4" />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}

export function TopSafetyBar({
  summary,
  fundsLocked,
  connectionState,
  theme,
  setTheme,
}: {
  summary: OwnerProductSummary | null;
  fundsLocked: boolean | null;
  connectionState: BackendConnectionState;
  theme: ThemeMode;
  setTheme: (theme: ThemeMode) => void;
}) {
  const connectionLabel = connectionState === "loading" ? "连接中" : connectionState === "connected" ? "后端已连接" : "后端不可用";
  const connectionTone = connectionState === "loading" ? "neutral" : connectionState === "connected" ? "safe" : "danger";
  const businessDataUnavailable = isBusinessDataUnavailable(summary);
  const dataLabel = !summary ? "等待数据" : businessDataUnavailable ? "业务数据不可用" : "业务数据正常";
  const dataNote = !summary ? "等待只读接口" : businessDataUnavailable ? (summary.reason ?? "状态证据待刷新") : summary.dataFreshnessLabel;
  const dataTone = !summary ? "neutral" : businessDataUnavailable ? "danger" : "safe";
  const lockLabel = fundsLocked === null ? "加载中" : fundsLocked ? "资金锁定" : "资金未锁定";
  const lockTone = fundsLocked === null ? "neutral" : fundsLocked ? "safe" : "danger";

  return (
    <header className="flex min-h-[72px] items-center gap-3 border-b bg-[color:var(--background-topbar)] px-3 backdrop-blur-xl lg:gap-4 lg:px-7">
      <div className="lg:hidden">
        <ProductMark compact />
      </div>
      <div className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:flex sm:items-center sm:gap-3 sm:overflow-x-auto">
        <SafetyPill icon={<ShieldCheck />} label="LIVE-SAFE" note="资金安全模式" tone="safe" />
        <SafetyPill icon={<CheckCircle2 />} label={connectionLabel} note="只读接口" tone={connectionTone} />
        <SafetyPill icon={<Activity />} label={dataLabel} note={dataNote} tone={dataTone} />
        <SafetyPill icon={<Lock />} label={lockLabel} note="账户资金状态" tone={lockTone} />
      </div>
      <ThemeToggle setTheme={setTheme} theme={theme} />
      <Button aria-label="通知" className="relative rounded-full" size="icon" variant="ghost">
        <Bell />
        {(summary?.ownerAttentionCount ?? 0) > 0 && (
          <span className="absolute -right-0.5 -top-0.5 grid size-5 place-items-center rounded-full bg-[color:var(--status-danger)] text-[10px] font-semibold text-white">
            {summary?.ownerAttentionCount}
          </span>
        )}
      </Button>
      <Button className="hidden rounded-full sm:inline-flex" variant="ghost">
        <User />
        Owner
      </Button>
    </header>
  );
}

export function PageShell({ activeView, children }: { activeView: NavigationKey; children: ReactNode }) {
  return (
    <main className="flex-1 overflow-y-auto px-4 py-5 lg:px-7">
      <div className="mx-auto grid max-w-[1320px] gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-normal">{navigationTitles[activeView]}</h1>
          <p className="text-sm text-muted-foreground">{navigationDescriptions[activeView]}</p>
        </div>
        {children}
      </div>
    </main>
  );
}

export function LoadingState() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-md rounded-2xl">
        <CardHeader>
          <CardTitle>加载中</CardTitle>
          <CardDescription>正在准备 Owner 控制台</CardDescription>
        </CardHeader>
      </Card>
    </main>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <Alert className="max-w-xl border-[color:var(--status-danger-border)] bg-[color:var(--status-danger-bg)] text-[color:var(--status-danger)]">
        <AlertTriangle />
        <AlertTitle>运行状态不可用</AlertTitle>
        <AlertDescription className="text-[color:var(--status-danger)]">
          控制台暂时无法加载。资金路径保持关闭。{message ? ` ${message}` : ""}
        </AlertDescription>
      </Alert>
    </main>
  );
}

function ThemeToggle({ theme, setTheme }: { theme: ThemeMode; setTheme: (theme: ThemeMode) => void }) {
  return (
    <Button
      aria-label="切换深浅模式"
      className="rounded-full"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      size="icon"
      variant="outline"
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </Button>
  );
}

function SafetyPill({ icon, label, note, tone }: { icon: ReactNode; label: string; note: string; tone: Tone }) {
  return (
    <div className="flex h-11 min-w-0 items-center gap-2 rounded-lg border bg-card/70 px-2 shadow-[var(--shadow-pill)] sm:h-12 sm:min-w-[148px] sm:gap-3 sm:px-3">
      <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border sm:size-8", toneClass(tone))}>{icon}</span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-semibold sm:text-sm">{label}</span>
        <span className="hidden truncate text-[11px] text-muted-foreground sm:block">{note}</span>
      </span>
    </div>
  );
}
