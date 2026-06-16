---
title: OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE
status: CURRENT_PILOT_HARD_GATE
authority: docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md
last_verified: 2026-06-16
---

# Owner Runtime Console UI Visual Governance

## Purpose

This document is the hard visual-governance gate for **Owner Runtime Console
v1**.

The console is a product operating surface for the Owner. It is not an
engineering report, packet browser, source-health wall, or raw readmodel
viewer.

Any UI-impact change must preserve:

- the accepted dark and light visual references:
  - `docs/current/assets/owner-runtime-console-home-dark-v1.png`;
  - `docs/current/assets/owner-runtime-console-home-light-v1.png`;
- the multi-page Owner console structure;
- the terse Owner-facing language in `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md`;
- screenshot-based validation through `npm run visual:qa`.

## Design Authority

When visual or product rules conflict, follow this order:

| Rank | Authority | Meaning |
| --- | --- | --- |
| 1 | Owner explicit correction | Latest Owner decision wins. |
| 2 | Accepted visual references | `docs/current/assets/owner-runtime-console-home-dark-v1.png` and `docs/current/assets/owner-runtime-console-home-light-v1.png`. |
| 3 | `docs/current/*` | Current product, source, and UI contracts. |
| 4 | Product Design / Build Web Apps / Browser verification | Workflow and fidelity checks. |
| 5 | Code implementation | Code must follow the rules above. |

The repo-specific `ui-ux-pro-max` skill is a semantic guardrail. It is not the
primary visual design source for this console.

## Locked Decisions

| Item | Decision |
| --- | --- |
| Gate strength | Hard gate for UI-impact work. |
| Visual baseline | Accepted dark and light reference screenshots. |
| Stack | React + Vite + TypeScript + Tailwind v4 + shadcn/ui. |
| CSS policy | Prefer Tailwind and shadcn composition; only global tokens, theme variables, and layout foundations belong in handwritten CSS. |
| Auth | Login/auth comes last and must not block UI governance. |
| Live boundary | Do not connect real submit paths, mutate secrets, expand live profiles, or alter order sizing from UI work. |

## Layout Hard Rules

| Rule | Required Behavior | Hard Failure |
| --- | --- | --- |
| Desktop first | `1440`, `1600`, and `1920` wide desktop viewports must be usable. | A page works only in narrow or portrait review. |
| No clipping | Rows, top pills, side rails, fixed labels, and panel content must not be cut off. | Text or controls overflow outside the viewport or container. |
| No horizontal scroll | The page must not create accidental horizontal scrolling. | `documentElement.scrollWidth > innerWidth + 1`. |
| No red-chip flood | One strategy row may show at most one primary abnormal state. Detail facts move into tooltip, rail, or detail panel. | Rows show repeated funds/order/position/protection red chips at once. |
| No report layout | Pages must be operable product screens. | A page is mainly long explanations, repeated warning cards, or empty engineering panels. |
| Radius discipline | Major panels and cards use compact product geometry. | Main cards use oversized decorative rounding. Status pills may stay pill-shaped. |
| Density layering | Home is overview; strategy, funds, orders are detail; records and system are auxiliary. | Home tries to display all details at once. |
| Exception compression | Unavailable states use one Owner-readable reason. | Every missing source fact is promoted to a visible primary chip. |

## Page Contract

| Page | UI Goal | Forbidden Shape |
| --- | --- | --- |
| 首页 | Show whether the system is usable, which StrategyGroup is selected, and whether Owner intervention is needed. | Full funds/order/position diagnostic wall. |
| 策略组 | Select StrategyGroup and see runtime usability. | Rows packed with repeated red abnormal chips. |
| 资金 | Show account pool, budget, available, locked, and protection state. | Huge repeated `未声明` text or treating unknown as visual centerpiece. |
| 订单与持仓 | Cascade StrategyGroup -> fills/protection orders -> position/protection/reconciliation. | Treating `暂无订单` or `暂无持仓` as an error. |
| 记录 | Show important changes and trace handoff entry. | Warning-log wall. |
| 系统 | Show read-only connection and safety guarantees. | Developer diagnostic dashboard. |

## Owner Language

Primary UI may use only short Owner-facing state language:

```text
运行中
等待机会
处理中
暂不可用
需要介入
无需操作
资金正常
订单正常
持仓正常
保护正常
暂无订单
暂无持仓
状态暂不可用
```

The main UI must not expose these as labels, menu items, cards, buttons, or
primary actions:

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
readmodel
next step
下一步
检查器
```

Technical words may appear only in collapsed audit, developer, or trace detail
surfaces.

## Component Governance

Future UI work must consolidate through reusable console components before
adding new one-off Tailwind blocks:

| Component | Responsibility |
| --- | --- |
| `ConsoleShell` | Sidebar, top safety bar, scroll region, content safe area. |
| `PageHeader` | Title, short subtitle, page-level state. |
| `OwnerPanel` | Panel padding, border, radius, elevation, and density. |
| `StrategyRow` | Strategy identity, single primary state, current situation, detail entry. |
| `StatusPill` | Short semantic state with controlled color usage. |
| `EmptyState` | Real empty states such as `暂无订单` and `暂无持仓`. |
| `UnavailableState` | One-line unavailable state with detail behind tooltip or rail. |
| `DetailRail` | Right context panel with stable width and wrapping rules. |

Do not add nested cards inside cards unless the nested element is a modal,
repeated object card, or true framed control.

## Visual QA Gate

Run from `owner-runtime-console/`:

```bash
npm run visual:qa
```

The gate captures the matrix below:

| Dimension | Values |
| --- | --- |
| Pages | 首页, 策略组, 资金, 订单与持仓, 记录, 系统 |
| Themes | dark, light |
| Viewports | `1440x900`, `1600x1000`, `1920x1200`, `1024x768`, `390x844` |
| Scenarios | `normal`, `stale` by default |

The script writes screenshots and a ledger under
`owner-runtime-console/artifacts/visual-qa/`.

## Automatic Hard Failures

`npm run visual:qa` must fail when it detects:

- console errors or framework overlays;
- blank pages;
- accidental horizontal overflow;
- primary text clipped by containers or viewport;
- fixed badges or debug labels covering visible content;
- forbidden engineering terms in primary UI;
- strategy rows with repeated visible abnormal chips;
- active navigation mismatch on desktop;
- mobile inability to reach required pages;
- `暂无订单` or `暂无持仓` presented as abnormal.

## Manual Ledger

Every visual QA run must leave a ledger that can be reviewed before handoff.

For each page/theme/viewport/scenario, review:

| Check | Pass Meaning |
| --- | --- |
| Layout ratio | Sidebar, top bar, main area, and right rail match the accepted proportions. |
| Hierarchy | Owner can identify the main state within seconds. |
| Spacing | Rows and panels are not cramped, floating, or wastefully empty. |
| Typography | Page titles, labels, and table text are readable and not oversized. |
| Color | Red means real Owner attention, not missing implementation detail. |
| Exception expression | Unavailable states are compressed to one Owner-readable sentence. |

Build success is not visual acceptance. A UI-impact task is complete only after
build, smoke checks, visual QA, screenshot review, and ledger review.
