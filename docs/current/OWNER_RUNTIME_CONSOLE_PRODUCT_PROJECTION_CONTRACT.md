---
title: OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT
status: CURRENT_PILOT_SUPPLEMENT
authority: docs/current/OWNER_RUNTIME_CONSOLE_PRODUCT_PROJECTION_CONTRACT.md
last_verified: 2026-06-16
---

# Owner Runtime Console Product Projection Contract

## Purpose

The **Owner Product Projection** is the product boundary for the new Owner
Runtime Console.

It exists so the frontend does not inherit legacy readmodel shape, internal
execution-chain terms, or packet/evidence workflow semantics.

## Product Flow

The product flow is:

```text
Owner selects StrategyGroup
-> Owner confirms risk boundary
-> StrategyGroup enters bounded runtime
-> system observes, processes, protects, reconciles, and records inside boundary
-> Owner supervises safety and intervenes only when needed
```

## Service Boundary

| Layer | Responsibility |
| --- | --- |
| Main runtime readmodel | Collect current StrategyGroup, watcher, live facts, and source-health facts |
| Frontend adapter | Map source-readiness facts into Owner-facing product semantics |
| Frontend | Render only Owner product states and hide internal execution terms |

Current production target:

```text
GET /api/trading-console/owner-console-source-readiness
```

The older isolated/compatibility projection path is not the mainline production
target:

```text
GET /api/owner-runtime-console/product-projection
```

The older endpoint remains available for audit and compatibility:

```text
GET /api/owner-runtime-console/readmodel
```

The frontend should not bind to the older endpoint as its product surface.

## Product Fields

| Field | Meaning |
| --- | --- |
| `automationState` | What the system is doing for the StrategyGroup |
| `ownerAttention` | Whether the Owner needs to act |
| `fundPool` | Safe budget pool shown to the Owner |
| `sourceHealth` | Backend-source readiness mapped into product states |
| `importantChanges` | Short product events worth showing on the homepage |
| `noActionGuarantee` | Explicit read-only and no-action guarantees |

## State Split

StrategyGroup state is split into two dimensions.

| Dimension | Values |
| --- | --- |
| Automation state | `运行中`, `等待机会`, `处理中`, `暂不可用`, `已暂停`, `已完成` |
| Owner attention | `无需操作`, `系统处理`, `需处理` |

This prevents internal runtime states such as signal readiness, evidence
readiness, or gate readiness from becoming Owner tasks.

## Mapping Rules

| Backend condition | Product state | Owner attention |
| --- | --- | --- |
| Runtime observing with no usable market condition | `等待机会` | `无需操作` |
| Signal/evidence/gate boundary is being handled by the system | `处理中` | `无需操作` |
| Post-submit finalize, reconciliation, or settlement in progress | `处理中` | `无需操作` |
| Missing or stale facts | `暂不可用` | `系统处理` |
| Deployment/status source unavailable | `暂不可用` | `系统处理` |
| Active position or open-order resolution needs Owner decision | `暂不可用` | `需处理` |
| Hard safety stop requiring Owner review | `暂不可用` | `需处理` |
| Settled or trace-ready lifecycle | `已完成` | `无需操作` |

## Fund Pool Language

Homepage copy should present the capital surface as:

```text
安全资金池
```

`LIVE-SAFE-1` is a fund-pool code, not the primary business concept.

## Source Health

The product projection must distinguish empty states from unavailable sources.

| Source state | Owner meaning |
| --- | --- |
| `ready` | Source is readable and usable |
| `ready_empty` | Source is readable and currently empty |
| `ready_nonempty` | Source is readable and has active items |
| `degraded` | Source is partial, stale, or not confirmed enough for detail |
| `unavailable` | Source cannot currently be read |

StrategyGroup catalog visibility and runtime overlay availability are separate.
If the StrategyGroup catalog is ready but runtime overlay is degraded or
unavailable, MPG / TEQ / FBS / SOR / PMR must remain visible and show one plain
unavailable reason.

Orders and positions must not collapse source failure into a zero count:

| Source | Empty state | Unavailable state |
| --- | --- | --- |
| Orders | `暂无订单` | `订单状态暂不可用` |
| Positions | `暂无持仓` | `持仓状态暂不可用` |

## Important Changes

Homepage changes should include only Owner-relevant product events:

| Event | Show on homepage |
| --- | --- |
| StrategyGroup enabled, paused, resumed, or disabled | Yes |
| StrategyGroup becomes unavailable | Yes |
| Owner attention appears or clears | Yes |
| Funds, orders, positions, protection, or reconciliation changes materially | Yes |
| Lifecycle settles or becomes review-ready | Yes |
| Repeated no-signal observation | No |
| Internal evidence or gate movement | No |
| Raw packet / ref id / proof / route changes | No |

## Forbidden Product Surface

The product projection must not expose these as homepage fields or Owner tasks:

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
nextAction
blocker code
```

They may remain available behind audit or developer surfaces.

## Hard Boundary

The product projection is read-only.

It must not:

- place, cancel, replace, or flatten orders;
- start runtimes;
- grant auto execution;
- mutate PG state;
- call FinalGate;
- call Operation Layer;
- call exchange write paths;
- mutate credentials, live profile, or order sizing.
