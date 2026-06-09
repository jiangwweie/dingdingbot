# Sprint 6 Trading Console Productization Design Spec

Status: DESIGN_SPEC_DRAFT
Created: 2026-06-09
Scope: Trading Console / Owner operation surface productization

## 1. Goal

Sprint 6 turns Trading Console into an Owner operation surface.

It is not:

- a read-only dashboard;
- a backend/API field browser;
- a Markdown/documentation page;
- a trading terminal;
- a forced review workflow.

It is:

- a calm Owner control surface;
- a strategy runtime governance workspace;
- a place to understand strategy assets, runtime boundaries, trades, analysis,
  incidents, and evidence.

Authoritative product semantics remain in `docs/canon/*`. This spec translates
those semantics into UI direction.

## 2. Owner Model

Owner normally should not have many tasks.

Default state:

```text
current system is within boundary
no Owner intervention required
attention items may exist
analysis is available when Owner wants to inspect history
```

Owner is not expected to approve every candidate trade. Strategies run inside
authorized boundaries. Owner mainly manages:

- strategy assets;
- runtime authorization boundaries;
- risk and protection state;
- incidents;
- trade/history analysis;
- evidence when needed.

## 3. Visual Direction

Selected direction:

```text
Dense Professional Control Surface
```

Use this visual language:

- dark graphite / charcoal base;
- compact but readable professional density;
- panes, rails, rows, inspector columns;
- fewer rounded dashboard cards;
- precise dividers and alignment;
- restrained green / amber / red / blue status accents;
- Chinese product language as primary copy;
- technical IDs only in evidence/inspector layers.

Avoid:

- generic SaaS card grid;
- neon exchange terminal style;
- large marketing headings;
- long explanatory blocks;
- raw JSON as UI;
- endpoint names or backend enums as primary labels.

## 4. Theme And Dark Mode

Dark mode is a required product capability for Sprint 6, not an optional skin.

The default visual direction should support dark mode because the console is a
risk and operations surface:

- long watch sessions should remain low-fatigue;
- normal state should stay quiet;
- attention/intervention states should stand out immediately;
- unavailable/unknown state should remain visible without looking like danger;
- evidence and technical detail should be readable without dominating the main
  operation surface.

Dark mode should be implemented through theme tokens, not one-off page colors.

Minimum token groups:

- app background;
- elevated pane;
- rail/sidebar;
- divider;
- primary text;
- secondary text;
- muted text;
- status normal;
- status attention;
- status intervention;
- status blocked;
- status unavailable;
- focus ring;
- chart line/fill colors.

Light mode can be deferred if Sprint 6 scope is tight, but the component model
must not hard-code colors in a way that blocks a later light theme.

## 5. Visual References

Use these visual drafts as the Sprint 6 source direction:

- Home: `docs/product/assets/sprint6-home-control-overview-direction-c.png`
- Strategy: `docs/product/assets/sprint6-strategy-library-direction-c.png`
- Runtime: `docs/product/assets/sprint6-runtime-governance-direction-c.png`
- Analysis: `docs/product/assets/sprint6-analysis-direction-c.png`

The Home / Strategy / Runtime / Analysis concepts are visual references, not
pixel-perfect implementation specs. Preserve their layout language:

```text
left nav
top status bar
status rail
split panes
right inspector
short nudges / popovers
compact rows
```

## 6. Navigation

Primary navigation:

```text
控制总览
策略库
运行治理
交易与仓位
分析
异常介入
证据
```

Do not expose old implementation-shaped navigation as the main Owner route.

`分析` replaces a forced `复盘` workflow. Analysis is for tracing orders,
strategy-level history, runtime-level history, and trade outcome inspection.

## 7. Page Responsibilities

### 控制总览

Answer:

```text
Do I need to intervene?
Is the system within boundary?
What should I pay attention to?
What changed recently?
```

Use:

- global status capsule;
- primary status sentence;
- horizontal operational status rail;
- runtime overview rows;
- strategy performance/history module;
- right inspector for short state explanation.

Do not use:

- task-heavy language such as mandatory review due;
- large card soup;
- raw technical blockers as the main screen.

### 策略库

Answer:

```text
What strategies exist?
Which are active / observing / parked / data-incomplete?
Which version is being governed?
What facts or admission layer are missing?
```

Use strategy rows/cards as strategy assets, not database rows.

Show:

- strategy family;
- version;
- status;
- applicable market / direction;
- runtime binding;
- missing facts;
- admission state;
- compact guidance.

Important rule:

```text
admitted does not mean executable
```

### 运行治理

Answer:

```text
Which runtime instances are active?
Are they still inside boundary?
How much budget / attempts are used?
Is protection complete?
What governance action is available?
```

Show boundary before action:

- max budget loss;
- budget reserved / used;
- max attempts / attempts used;
- leverage;
- active position limit;
- protection requirement;
- validity / expiration;
- pause / revoke / mark-for-analysis / evidence actions.

Do not show buy/sell/execute as primary controls.

### 交易与仓位

Answer:

```text
What positions, orders, protection, and trade facts exist?
Are they associated with a strategy/runtime?
Is risk currently exposed?
```

This can use refined tables, but table rows must connect to strategy/runtime and
analysis/evidence.

Unavailable fee, funding, slippage, or fills must be explicit.

### 分析

Answer:

```text
How did a strategy perform historically?
What happened to a trade/order/runtime?
Where did profit/loss come from?
What facts are unavailable?
```

Analysis is optional inspection, not a forced task flow.

Use:

- strategy performance list;
- compact charts/sparklines;
- trade history rows;
- selected trade inspector;
- optional Owner note/mark.

Do not use:

- mandatory review due language;
- forced step-by-step review completion;
- required conclusions for every trade.

### 异常介入

Answer:

```text
What happened?
What risk exists now?
What did the system already stop?
What can Owner do?
What is forbidden?
What restores normal operation?
```

Use intervention panels with short guidance, not long documentation.

### 证据

Evidence is for tracing and verification, not daily operation.

Default view should be human-readable summary first, technical IDs second,
raw/JSON last.

## 8. Productized Guidance

Guidance must be contextual and productized.

Use:

- tooltip;
- popover;
- inline hint;
- nudge;
- right inspector;
- drawer;
- compact stepper only for incident flows.

Do not use long documentation blocks.

Every important warning/blocker should express:

```text
meaning
impact
system protection already applied
Owner handling path
recovery condition
```

Example:

```text
保护状态无法确认
影响：新尝试已暂停
处理：查看仓位和保护单，必要时进入异常介入
恢复：保护重新确认或仓位关闭
```

## 9. Component Set

Core components:

- `GlobalStatusCapsule`
- `OperationalStatusRail`
- `StrategyAssetRow`
- `StrategyVersionInspector`
- `RuntimeBoundaryPanel`
- `RiskBudgetMeter`
- `AttemptCounter`
- `ProtectionStatusStrip`
- `GovernanceActionRow`
- `TradeHistoryRow`
- `AnalysisInspector`
- `IncidentInterventionPanel`
- `EvidenceDrawer`
- `GuidancePopover`
- `ActionNudge`

Component states:

```text
normal
attention
intervention
blocked
disabled
unavailable
not_connected
empty
loading
```

Owner-facing labels:

```text
正常
待关注
需要介入
已阻断
当前不可用
数据不可用
未确认
暂无数据
正在读取
```

## 10. Copy Rules

Use product language:

- 当前无需操作
- 有待关注项
- 需要介入
- 策略保持观察
- 数据待补
- 边界内
- 保护正常
- 新尝试已暂停
- 查看缺失事实
- 进入异常介入
- 查看证据

Avoid main-surface copy like:

- `candidate_executable=false`
- `submit_adapter_not_enabled`
- `runtime_status=...`
- `not_execution_intent=true`
- endpoint names;
- raw blocker codes.

Technical values may appear in Evidence, drawers, or inspector detail only.

## 11. Safety Display Rules

Do not imply unavailable capability.

In particular:

- shadow runtime is not executable runtime;
- preview is not execution readiness;
- readmodel is not action authority;
- admission is not execution authorization;
- FinalGate preview is not order placement;
- passing a gate does not bypass Operation Layer;
- no UI action may imply live/real-funds order placement without explicit Owner
  authorization and official backend path.

## 12. Implementation Handoff Notes

For Sprint 6 implementation:

- start with shell/navigation/status bar;
- implement the selected visual system before adding more pages;
- prefer panes/rows/inspectors over card grids;
- keep Analysis optional and non-task-like;
- keep Evidence behind drawers/detail views;
- every disabled or unavailable control must explain why;
- do not invent backend action capability to satisfy a visual design.

Owner requirement:

```text
If retrofitting the old frontend is more expensive or distorts the product
direction, Sprint 6 may rebuild the Trading Console as a new frontend project.
The goal is the Owner operation surface, not preservation of the old frontend
implementation.
```

Use the old frontend only when it helps preserve verified API integration,
typing, routing, or reusable components without compromising the selected
product direction. If the old frontend forces generic dashboard layout,
documentation-like screens, brittle styling, or excessive cleanup before the
first usable slice, prefer a new project or new app shell.

If current API/readmodel lacks a needed field, show honest unavailable/unknown
state and record the dependency; do not infer safety or actionability in the
frontend.

## 13. Acceptance Checklist

Sprint 6 UI direction passes when:

- Home feels calm and professional, not task-heavy;
- Strategy feels like strategy asset governance;
- Runtime shows boundary before action;
- Trades connects facts to strategy/runtime context;
- Analysis supports investigation, not mandatory review;
- Incident provides handling paths;
- Evidence is reachable but not dominant;
- dark mode supports low-noise monitoring and high-signal alerts;
- guidance appears as tooltip/popover/nudge/drawer, not documentation;
- the interface no longer reads as a generic dashboard or backend debug page.
