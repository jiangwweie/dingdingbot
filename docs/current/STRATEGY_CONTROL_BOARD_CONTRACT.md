---
title: STRATEGY_CONTROL_BOARD_CONTRACT
status: CURRENT
authority: docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md
last_verified: 2026-06-19
---

# Strategy Control Board Contract

The Strategy Control Board is the Owner-facing automation supervision surface.
It must not become a packet browser, research-doc index, manual gate assembly
tool, or operator workflow for internal execution gates.

## Required Row Fields

| Field | Meaning |
| --- | --- |
| `strategy_group` | StrategyGroup id and display name |
| `enabled_state` | `not_enabled`, `enabled`, or `paused` |
| `owner_status` | `running`, `waiting_for_opportunity`, `processing`, `temporarily_unavailable`, `needs_intervention`, or `completed` |
| `automation_summary` | One short Owner-facing sentence, for example `系统自动运行中` |
| `funds_status` | `资金正常`, `预算不足`, or a similarly terse Owner-facing phrase |
| `order_position_status` | `订单正常`, `有订单处理中`, `有持仓处理中`, or similar |
| `protection_status` | `保护正常`, `保护未就绪`, or similar |
| `intervention` | `无需操作` unless Owner action is required |
| `reason` | One plain sentence when unavailable or intervention is required |
| `review_outcome` | `保留`, `调整`, `暂停`, `停用`, or `待复盘` |

## Strategy Learning Surface

The main control board may summarize StrategyGroup Decision Ledger state,
but it must not become a raw diagnostic table.

| Internal source | Main Owner meaning |
| --- | --- |
| high-priority no-action | 有观察机会，系统正在复盘 |
| would-enter observe-only | 有观察机会，暂不具备实盘权限 |
| missing replay coverage that changes a decision | 样本不足，等待本地补充 |
| classifier / facts gap that changes a decision | 策略条件待调整 |
| parked low-priority vocabulary | 暂停观察，不影响主线 |

The board should show one compact strategy-learning status only when it changes
the Owner-relevant state. Healthy background replay, low-priority observation,
or no-action review should stay quiet.

### Review Outcome Vocabulary Mapping

Backend/internal English values map to Owner-facing Chinese labels:

| Backend/internal value | Owner-facing label |
| --- | --- |
| `promote` | `保留` |
| `revise` | `调整` |
| `park` | `暂停` |
| `kill` | `停用` |
| `pending` | `待复盘` |
| `keep_observing` | `待复盘` |

Backend/internal English values are not primary Owner UI labels. The Owner
surface displays the Chinese vocabulary defined above.

## Main UI Language

Main Owner screens should use only small, plain product vocabulary:

```text
未启用
运行中
等待机会
处理中
暂不可用
需要介入
已暂停
已完成
无需操作
资金正常
订单正常
持仓正常
保护正常
```

Internal gate names such as `FinalGate`, `Operation Layer`, `RequiredFacts`,
`candidate`, `authorization`, `preflight`, `proof`, `route`, `refId`, and
`blocker code` are not allowed as primary Owner table columns, cards, or
actions. They belong in details, audit, or developer drawers.

## Internal Lifecycle Mapping

Developer and audit surfaces may retain compact lifecycle labels, but the main
Owner surface must translate them into plain product states.

| Internal lifecycle | Main Owner wording |
| --- | --- |
| `observing` | `等待机会` |
| `signal_ready` | `处理中` |
| `candidate_ready` | `处理中` |
| `submitted` | `处理中` |

## Notification Rule

Notify the Owner when deployment changes, watcher health regresses, a
StrategyGroup becomes usable/unusable, automation starts processing, funds/order/
position/protection safety changes, reconciliation fails or settles, or Owner
intervention is needed.

Stay quiet when all selected runtimes remain observing with repeated
`no_signal` and no safety regression.
