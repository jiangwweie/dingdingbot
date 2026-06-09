# Sprint 6 Trading Console Productization Handoff

Status: HANDOFF_DRAFT
Created: 2026-06-09
Consumer: Sprint 6 implementation / refactor window

## Refactor Window Prompt

Read this handoff and its linked design spec/assets first, then decide whether
to reuse the old frontend or create a new frontend project; implement the first
Owner operation-surface slice with dark mode as the primary theme, without
touching backend/core/runtime files.

## 1. Objective

Implement the Trading Console productization direction from:

- `docs/product/sprint6-trading-console-productization-design-spec.md`
- visual references under `docs/product/assets/sprint6-*.png`

The goal is to make the console feel like an Owner operation surface, not a
generic dashboard, read-only report, or backend debug tool.

## 2. Required Product Stance

Implement from the Owner point of view:

```text
default calm
strategy assets
runtime boundaries
trade/history analysis
incident handling
evidence on demand
```

Do not implement from endpoint/table/page-history structure.

## 3. First Implementation Slice

Recommended first slice:

```text
App shell
left navigation
top status capsule
Control Overview / Home
shared pane/rail/inspector primitives
```

Why:

- establishes the selected visual system;
- removes the generic dashboard feel early;
- creates reusable layout primitives for Strategy / Runtime / Analysis;
- avoids premature backend/action changes.

## 4. Proposed Navigation

Use:

```text
控制总览
策略库
运行治理
交易与仓位
分析
异常介入
证据
```

Do not expose old implementation-shaped navigation as the primary Owner route.
Old routes can remain during migration but should not define the product IA.

## 5. Visual System Rules

Adopt Direction C:

```text
Dense Professional Control Surface
```

Implementation rules:

- dark graphite / charcoal base;
- compact professional density;
- panes, rails, rows, inspector columns;
- fewer rounded dashboard cards;
- precise dividers and alignment;
- restrained status accents;
- Chinese product language as primary UI copy.

Dark mode is required as the primary Sprint 6 theme. Treat it as an operations
and risk-reminder capability:

- calm state stays quiet;
- attention/intervention state is visually obvious;
- long watch sessions remain low-fatigue;
- unavailable/unknown state is distinct from danger;
- colors come from reusable theme tokens, not one-off page styles.

Avoid:

- card soup;
- oversized hero headings;
- generic SaaS admin template look;
- Markdown/report layouts;
- raw JSON in main surface;
- neon trading terminal styling.

## 6. Frontend Project Strategy

Owner requirement:

```text
If the old frontend is too expensive to retrofit, Sprint 6 may rebuild the
Trading Console as a new frontend project instead of adopting the old frontend
工程.
```

Decision rule:

- reuse the existing frontend when it preserves useful API wiring, types,
  routing, or components without fighting the product direction;
- create a new app shell or new frontend project when the existing frontend
  forces generic dashboard structure, documentation-style pages, brittle
  styling, or large cleanup before the first usable Owner operation surface;
- in both paths, keep backend/core/runtime files untouched for the first
  visual/productization slice.

The success criterion is not "old frontend retained". The success criterion is
"Owner can operate from the new console surface with the Sprint 6 visual system
and correct safety boundaries".

## 7. Core Layout Primitives

Create or adapt reusable primitives:

- `ConsoleShell`
- `ConsoleSidebar`
- `GlobalStatusCapsule`
- `OperationalStatusRail`
- `SplitPaneLayout`
- `InspectorPanel`
- `ActionNudge`
- `GuidancePopover`
- `StatusChip`
- `MetricRailItem`
- `EntityRow`
- `EvidenceDrawer`

Use these primitives before adding page-specific one-off styling.

## 8. Page Implementation Order

Recommended order:

1. `控制总览`
2. `策略库`
3. `运行治理`
4. `分析`
5. `交易与仓位`
6. `异常介入`
7. `证据`

`分析` replaces a forced `复盘` workflow. Do not create mandatory review due
task language unless a current product decision explicitly adds it back.

## 9. Copy Rules

Main UI should say:

- 当前无需操作
- 有待关注项
- 需要介入
- 边界内
- 保护正常
- 数据待补
- 保持观察
- 查看缺失事实
- 进入异常介入
- 查看证据

Main UI should not say:

- `runtime_status=...`
- `candidate_executable=false`
- `submit_adapter_not_enabled`
- `not_execution_intent=true`
- endpoint names;
- raw blocker codes.

Technical text belongs in evidence/inspector/drawer surfaces.

## 10. Guidance Rules

Warnings and blockers must not become documentation blocks.

Use productized guidance:

- tooltip for one-line explanation;
- popover for capsule/status detail;
- nudge for next available path;
- inspector for current selection context;
- drawer for deeper evidence;
- stepper only for incident handling.

Every important status should answer:

```text
what it means
what system already did
what Owner can do
what restores normal operation
```

## 11. Safety Rules

Do not imply unavailable capability.

Specifically:

- shadow runtime is not executable runtime;
- readmodel/preview is not action authority;
- admission is not execution authorization;
- FinalGate preview is not order placement;
- no buy/sell/execute button unless an official backend path and Owner
  authorization boundary exist;
- disabled controls must explain why.

## 12. Suggested File Surface

If reusing the existing frontend, prefer changes under:

```text
trading-console/src/App.tsx
trading-console/src/components/
trading-console/src/components/ui/
trading-console/src/pages/
trading-console/src/lib/
trading-console/src/index.css
```

If creating a new frontend project, preserve the same product IA and component
names from this handoff, and keep the implementation isolated from backend/core
runtime files.

Do not touch backend/core/runtime files for the first visual/productization slice.

If a required field is missing, render honest unavailable/unknown state and
record a backend dependency; do not infer safety or actionability in the
frontend.

## 13. Done When

First slice is acceptable when:

- shell/nav/status bar match Direction C;
- dark mode is the primary theme and uses reusable tokens;
- Home no longer feels like a generic dashboard or document page;
- Home uses status rail, split panes, and right inspector;
- no forced review task language appears;
- unavailable/disabled states include productized guidance;
- no backend enum/raw JSON dominates the main surface;
- Browser visual QA confirms desktop layout is readable and professional.

## 14. Validation

For visual/productization work:

- run the frontend locally only when the implementation task allows it;
- use Browser or Playwright screenshot validation;
- compare rendered UI against the visual references;
- check desktop first;
- check that text does not overlap or wrap awkwardly;
- check console errors;
- verify key interactions: nav, status capsule popover, nudge link, inspector,
  drawer if implemented.

Do not claim Sprint 6 productization is complete from code review alone.
