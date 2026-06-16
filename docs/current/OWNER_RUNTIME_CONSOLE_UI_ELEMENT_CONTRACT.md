---
title: OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT
status: CURRENT_PILOT_UI_CONTRACT
authority: docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md
last_verified: 2026-06-16
---

# Owner Runtime Console UI Element Contract

## Purpose

This contract freezes the first implementation surface for **Owner Runtime
Console v1**.

It defines:

- which elements appear on each Owner-facing screen;
- which labels and product states are allowed in the main UI;
- which actions the Owner can take;
- which details are hidden behind detail or developer surfaces;
- which fields the frontend projection needs from mock data or the API;
- how dark and light themes must preserve the same structure.

In the main-control repository, this file is the implementation bridge between:

- `docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md`;
- `docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md`;
- `docs/current/OWNER_CONSOLE_SOURCE_READINESS_CONFIRMATION.md`;
- `owner-runtime-console/README.md`.

Earlier isolated-design documents remain handoff/reference material only unless
they are explicitly integrated into `docs/current/` in this repository.

## Product Stance

The Owner is a supervisor, not a manual execution operator.

The console does not ask the Owner to advance internal execution steps. When a
StrategyGroup is usable and enabled, the system observes and handles the
official bounded runtime path automatically. The Owner sees whether the system
is safe, whether automation is active, and whether intervention is needed.

## Global Layout

The desktop layout is fixed for v1:

```text
AppShell
-> Sidebar
-> TopSafetyBar
-> PageWorkspace
   -> MainColumn
   -> RightContextPanel
```

## Desktop Proportions

Implementation and visual QA use full-width screens, not side-by-side theme
drafts.

| Region | Target |
| --- | --- |
| Viewport | `1440 x 1024` primary QA size |
| Sidebar | `220-240px` |
| Top safety bar | `64-76px` high |
| Page padding | `24-32px` |
| Right context panel | `280-320px` |
| Main workspace | Flexible dominant region |
| Strategy row height | `64-76px` |
| Bottom safety panel | Visible, but lighter than the main runtime area |

## Theme Contract

Dark and light themes share the same elements, layout, spacing, components, and
state language.

Only semantic theme tokens change:

| Token | Purpose |
| --- | --- |
| `background.app` | App root |
| `background.sidebar` | Sidebar surface |
| `background.panel` | Major page panels |
| `background.card` | Object cards and stat cards |
| `background.subtle` | Low-emphasis grouped surfaces |
| `border.subtle` | Quiet separation |
| `border.strong` | Active or selected surfaces |
| `text.primary` | Main text |
| `text.secondary` | Supporting text |
| `text.muted` | Low-priority metadata |
| `accent.primary` | Brand and active navigation |
| `status.safe` | Normal / running |
| `status.waiting` | Waiting for opportunity |
| `status.processing` | System processing |
| `status.danger` | Owner intervention |
| `status.paused` | Paused / not enabled |
| `shadow.panel` | Theme-appropriate panel depth |

## Product States

Main UI uses this state vocabulary only.

| State Key | Label | Main Meaning | Owner Action |
| --- | --- | --- | --- |
| `not_enabled` | 未启用 | StrategyGroup is not active | Can enable from 策略组 |
| `running` | 运行中 | Automation is healthy and active | No action needed |
| `waiting_for_opportunity` | 等待机会 | System is healthy, market condition is not ready | No action needed |
| `processing` | 处理中 | System is handling order, protection, reconciliation, or settlement | No action needed unless it becomes abnormal |
| `temporarily_unavailable` | 暂不可用 | StrategyGroup cannot be used right now | Show one plain reason |
| `needs_intervention` | 需要介入 | Owner should inspect or pause/recover | Show intervention action |
| `paused` | 已暂停 | Owner or system pause is active | Can resume when allowed |
| `completed` | 已完成 | Latest run is settled and recorded | Record available |

## Health Labels

Health chips must stay short.

| Field | Normal Label | Abnormal Label |
| --- | --- | --- |
| Funds | 资金正常 | 资金异常 |
| Orders | 订单正常 | 订单异常 |
| Position | 持仓正常 | 持仓异常 |
| Protection | 保护正常 | 保护异常 |
| Reconciliation | 对账正常 | 对账异常 |
| Intervention | 无需操作 | 需要介入 |

## Forbidden Main UI Terms

These terms are forbidden in primary navigation, homepage cards, table headers,
primary buttons, and Owner action labels:

```text
FinalGate
Operation Layer
RequiredFacts
candidate
authorization
preflight
proof
route
refId
blocker code
next step
下一步
检查器
系统自动观察中
暂无可用机会
```

They may appear only inside collapsed technical detail, audit, or developer
surfaces.

## Navigation Contract

| Menu | Route Key | Purpose | Default Density |
| --- | --- | --- | --- |
| 首页 | `home` | Supervise overall automation safety | Low |
| 策略组 | `strategy-groups` | Enable, pause, resume, risk profile, and runtime state | Medium |
| 资金 | `funds` | Account, budget, used funds, available funds, lock, settlement | Medium |
| 订单与持仓 | `orders-positions` | Active orders, positions, protection, reconciliation | Medium |
| 记录 | `records` | Recent events and trace handoff | Low-medium |
| 系统 | `system` | Data freshness, deployment, watcher, internal details | High |

## AppShell Elements

### Sidebar

| Element | Required | Notes |
| --- | --- | --- |
| Product mark | Yes | Shield-like mark, not exchange logo |
| Product name | Yes | `BRC Owner Console` |
| Subtitle | Yes | `个人量化系统控制台` |
| Menu items | Yes | 首页 / 策略组 / 资金 / 订单与持仓 / 记录 / 系统 |
| Active menu state | Yes | Strong enough in both themes |
| Collapse control | Yes | Local UI state only in v1 |

### TopSafetyBar

| Element | Required | Display |
| --- | --- | --- |
| Live-safe mode | Yes | `LIVE-SAFE` |
| System health | Yes | `系统正常` or `需要介入` |
| Data freshness | Yes | `数据新鲜 < 60秒` or one plain stale label |
| Funds lock | Yes | `资金锁定` |
| Notification indicator | Yes | Count only for intervention or important state changes |
| Owner menu | Yes | Display only; auth is later |
| Theme toggle | Yes | Dark / light theme state |

## Homepage Contract

The homepage answers:

```text
Is the system safe?
Is automation running?
Does the Owner need to intervene?
Are funds, orders, positions, and protection normal?
```

### Home Sections

| Section | Required | Priority | Notes |
| --- | --- | --- | --- |
| Safety overview strip | Yes | P0 | First visual anchor |
| Runtime summary metrics | Yes | P0 | Compact state counts |
| StrategyGroup status | Yes | P0 | Grouped list or object rows |
| Current StrategyGroup panel | Yes | P0 | Right context panel |
| Funds safety panel | Yes | P0 | Bottom or secondary major panel |
| Recent records preview | Optional | P1 | Small, not review-led |
| Technical detail drawer | Optional | Dev-only | Collapsed by default |

### Safety Overview Strip

| Element | Label | Source Field |
| --- | --- | --- |
| Overall status | `系统安全运行` / `需要介入` | `productSummary.overallStatus` |
| Intervention count | `需要介入 0` | `productSummary.needsInterventionCount` |
| Processing count | `处理中 1` | `productSummary.processingCount` |
| Waiting count | `等待机会 2` | `productSummary.waitingCount` |
| Running count | `运行中 2` | `productSummary.runningCount` |

### Runtime Summary Metrics

| Tile | Required | Display |
| --- | --- | --- |
| Enabled | Yes | `已启用 5` |
| Running | Yes | `运行中 2` |
| Waiting | Yes | `等待机会 2` |
| Processing | Yes | `处理中 1` |
| Intervention | Yes | `需要介入 0` |

The intervention tile may be visually quiet when the count is zero.

### StrategyGroup Status

The homepage uses a refined grouped list or object rows. It must not feel like a
spreadsheet.

| Field | Required | Example |
| --- | --- | --- |
| Strategy avatar | Yes | `MPG` |
| Strategy name | Yes | `MPG` |
| Short description | Yes | `动量趋势` |
| Product state | Yes | `运行中` |
| Funds chip | Yes | `资金正常` |
| Orders chip | Yes | `订单正常` / `有订单处理中` |
| Position chip | Yes | `持仓正常` |
| Protection chip | Yes | `保护正常` |
| Intervention label | Yes | `无需操作` / `需要介入` |
| Selected state | Yes | Drives right context panel |

### StrategyGroup Reference Rows

These rows are semantic reference data for UI states and labels. Live state must
come from the mainline source-readiness API, not from hard-coded UI defaults.

| StrategyGroup | Name | Description | Reference Product State | Main Note |
| --- | --- | --- | --- | --- |
| `MPG-001` | MPG | 动量持续观察 | 运行中 | Momentum continuation observation |
| `TEQ-001` | TEQ | 美股永续动量 | 等待机会 | TradFi perpetual momentum observation |
| `FBS-001` | FBS | 资金费率 / 基差压力 | 等待机会 | Funding and basis stress observation |
| `SOR-001` | SOR | 开盘区间结构 | 处理中 | Session/opening-range structure observation |
| `PMR-001` | PMR | 贵金属短线 / overlay | 已暂停 | Metals short-horizon overlay observation |

### Current StrategyGroup Panel

Right context panel reflects the selected StrategyGroup.

| Element | Required | Notes |
| --- | --- | --- |
| Panel title | Yes | `当前策略组` |
| Strategy avatar/name | Yes | Example `MPG` |
| Short description | Yes | Example `动量趋势` |
| Mini trend chart | Yes | Visual quality element; mock is acceptable |
| Status row | Yes | `状态 运行中` |
| Funds row | Yes | `资金 正常` |
| Orders row | Yes | `订单 正常` |
| Position row | Yes | `持仓 正常` |
| Protection row | Yes | `保护 正常` |
| Intervention row | Yes | `介入 无需操作` |
| View record button | Yes | `查看记录` |

### Funds Safety Panel

| Element | Required | Example |
| --- | --- | --- |
| Account | Yes | `LIVE-SAFE-1` |
| Budget | Yes | `$5,000` |
| Used | Yes | `$3,160` |
| Available | Yes | `$1,840` |
| Open orders | Yes | `1` |
| Active positions | Yes | `5` |
| Protection status | Yes | `正常` |
| Progress bars | Yes | Used and available, theme-token driven |

## StrategyGroups Page Contract

The StrategyGroups page is the main management surface for enabling and pausing
automation.

| Section | Required | Notes |
| --- | --- | --- |
| StrategyGroup list/grid | Yes | Object cards or detailed rows |
| Filter by state | Yes | All / running / waiting / processing / paused / intervention |
| Selected StrategyGroup detail | Yes | Drawer or right panel |
| Enable / pause / resume | Yes | Local state in prototype |
| Risk profile control | Yes | Conservative / standard / aggressive labels can be productized later |
| One-sentence unavailable reason | Yes, when applicable | No long blocker list |
| Technical detail drawer | Dev-only | Collapsed by default |

### Allowed StrategyGroup Actions

| Action | Label | Allowed In Main UI | Notes |
| --- | --- | --- | --- |
| Enable | 启用 | Yes | Prototype local state |
| Pause | 暂停 | Yes | Always bounded and reversible in UI |
| Resume | 恢复 | Yes | Disabled when unsafe |
| Risk profile | 风险档 | Yes | Does not expand order size defaults by itself |
| View records | 查看记录 | Yes | Opens records filtered by StrategyGroup |
| Technical details | 技术详情 | Dev-only | Hidden behind detail surface |

## Funds Page Contract

The Funds page is a safety center, not a finance report.

| Section | Required | Notes |
| --- | --- | --- |
| Account summary | Yes | Account, mode, lock state |
| Budget summary | Yes | Budget, used, available |
| Usage breakdown | Yes | Open orders, active positions, reserved funds |
| Reconciliation state | Yes | Normal / processing / abnormal |
| Funds lock state | Yes | Prominent |
| Intervention reason | Conditional | One sentence only |
| Technical accounting detail | Detail-only | Not homepage |

## Orders And Positions Page Contract

This page shows live operational exposure.

| Section | Required | Notes |
| --- | --- | --- |
| Active orders | Yes | Current open or processing orders |
| Active positions | Yes | Current positions |
| Protection state | Yes | TP/SL/protection summary, product wording |
| Reconciliation state | Yes | Normal / processing / abnormal |
| Processing items | Conditional | Show when order or settlement work is active |
| Intervention items | Conditional | Only abnormal items |
| Historical order list | Optional | Secondary, not page lead |

## Records Page Contract

Records are for later trace handoff and AI-assisted interpretation, not primary
manual review.

| Section | Required | Notes |
| --- | --- | --- |
| Recent events | Yes | Short event stream |
| StrategyGroup filter | Yes | MPG / TEQ / FBS / SOR / PMR |
| Trace availability | Yes | Available / not available |
| Settlement marker | Yes | Complete / processing |
| Outcome marker | Optional | Lightweight |
| Raw evidence | Detail-only | Collapsed |

## System Page Contract

The System page contains details that should not pollute the Owner homepage.

| Section | Required | Notes |
| --- | --- | --- |
| Data freshness | Yes | Current freshness and stale state |
| Watcher status | Yes | Product wording first |
| Deployment/version | Yes | Build and runtime version |
| API/readmodel state | Yes | Health, last refresh |
| Technical detail drawer | Yes | Internal terms allowed here only |
| Dev evidence panel | Yes, dev-only | Raw packets / JSON hidden by default |

## Owner Action Rules

Main UI actions should be few and obvious.

| Condition | Main UI Behavior |
| --- | --- |
| All healthy | Show `无需操作`; no primary action pressure |
| Waiting for opportunity | Show `等待机会`; no intervention action |
| Processing | Show `处理中`; no intervention action unless stale or abnormal |
| Paused | Show `恢复` when allowed |
| Not enabled | Show `启用` on StrategyGroups page |
| Temporarily unavailable | Show one sentence reason and disable enable/resume |
| Needs intervention | Show one action such as `查看处理` or `暂停` |

## Data Projection Contract

The frontend should consume or derive this product projection. Internal API
fields may be richer, but main UI should map them to this shape.

```ts
type OwnerProductState =
  | "not_enabled"
  | "running"
  | "waiting_for_opportunity"
  | "processing"
  | "temporarily_unavailable"
  | "needs_intervention"
  | "paused"
  | "completed";

type OwnerHealthState = "normal" | "processing" | "abnormal" | "unknown";

type OwnerProductSummary = {
  overallStatus: "safe" | "attention" | "degraded";
  enabledCount: number;
  runningCount: number;
  waitingCount: number;
  processingCount: number;
  needsInterventionCount: number;
  pausedCount: number;
  dataFreshnessLabel: string;
  fundsLocked: boolean;
};

type StrategyGroupProductRow = {
  id: string;
  code: "MPG" | "TEQ" | "FBS" | "SOR" | "PMR";
  name: string;
  description: string;
  productState: OwnerProductState;
  funds: OwnerHealthState;
  orders: OwnerHealthState;
  position: OwnerHealthState;
  protection: OwnerHealthState;
  reconciliation: OwnerHealthState;
  interventionLabel: "无需操作" | "需要介入";
  reason?: string;
  selected?: boolean;
};

type FundsSafetySummary = {
  account: string;
  budget: string;
  used: string;
  available: string;
  openOrders: number;
  activePositions: number;
  protectionLabel: "正常" | "异常" | "处理中";
};
```

## Mock Scenarios

| Scenario | Purpose | Required Main UI Result |
| --- | --- | --- |
| `normal` | Default product surface | Safe, no intervention, all key panels populated |
| `processing` | Order/lifecycle work active | SOR shows `处理中`; no false intervention |
| `paused` | Paused StrategyGroup | PMR shows `已暂停`; resume available in StrategyGroups page |
| `intervention` | Owner attention needed | One clear intervention item, no internal gate language |
| `stale` | Data freshness failure | One plain stale reason, money path visually closed |
| `empty` | No runtime data | Empty product state, no legacy dashboard fallback |
| `error` | Readmodel failure | Fatal readmodel state, no fake healthy UI |

## Component Inventory

| Component | Role | First Screen |
| --- | --- | --- |
| `AppShell` | Global layout | Yes |
| `Sidebar` | Navigation | Yes |
| `TopSafetyBar` | Safety status and theme toggle | Yes |
| `StatusPill` | Compact status pill | Yes |
| `MetricTile` | Runtime summary count | Yes |
| `SafetyOverviewStrip` | First visual anchor | Yes |
| `StrategyGroupList` | Homepage strategy status | Yes |
| `StrategyGroupRow` | Strategy row/object row | Yes |
| `HealthChip` | Funds/orders/position/protection labels | Yes |
| `CurrentStrategyPanel` | Right context panel | Yes |
| `FundsSafetyPanel` | Funds safety module | Yes |
| `ThemeToggle` | Dark/light mode | Yes |
| `DetailDrawer` | Non-primary detail | P1 |
| `DevEvidenceDrawer` | Raw/internal evidence | Dev-only |

## Visual QA Acceptance

The first implementation pass must capture:

```text
1440 x 1024 dark mode homepage
1440 x 1024 light mode homepage
mobile smoke viewport
intervention scenario
stale scenario
```

Acceptance checks:

- no internal forbidden terms in primary UI;
- dark and light themes keep identical layout proportions;
- sidebar, top bar, main column, and right panel are not crowded;
- StrategyGroup status is scannable in under five seconds;
- healthy state does not pressure the Owner to act;
- abnormal state is obvious without exposing internal execution machinery;
- raw evidence is collapsed by default.

## Implementation Handoff

Mainline implementation scope:

1. Theme tokens for dark and light mode.
2. `AppShell`, `Sidebar`, and `TopSafetyBar`.
3. Homepage with mainline source-readiness API projection.
4. Theme toggle with persistent local state.
5. Product-state mock scenarios for explicit QA mode only.
6. Visual QA screenshots for dark and light 1440px home.

Login/auth must follow the mainline API/auth boundary and must not introduce
credential storage in frontend code or documentation.
