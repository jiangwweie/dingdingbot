---
title: LIVE_OUTCOME_LEDGER_CONTRACT
status: CURRENT_CONTRACT
authority: docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md
last_verified: 2026-07-08
---

# Live Outcome Ledger Contract

## Purpose

The **Live Outcome Ledger** records the structured result of every real
ticket-bound trade lifecycle.

It answers:

```text
Which exact ticket traded?
How far did the lifecycle progress?
Was the position protected?
What was the realized and risk-normalized result?
Did any lifecycle defect occur?
What strategy governance decision should the result inform?
```

It is not an Owner policy surface, not a submit authority, and not a runtime
fallback. Review rows may recommend future governance changes, but only Owner
policy events can change enabled scope, runtime profile, capital scope, or
submit authority.

## Authority Boundary

| Layer | Owns | Does not own |
| --- | --- | --- |
| **Action-Time Ticket** | Exact trade identity | Review or strategy promotion |
| **Order Lifecycle** | ENTRY / SL / TP1 / RUNNER_SL / final exit facts | Strategy governance decision |
| **Protection Reconciler** | Exchange/PG protection truth | Policy mutation |
| **Live Outcome Ledger** | Structured trade result and lifecycle defects | Runtime submit permission |
| **Owner policy** | Future enable/pause/promote/park/kill decisions | Raw order reconstruction |

## Required Row Scope

There must be at most one current live outcome row per **ticket_id**.

The row is created only after one of these lifecycle conditions:

```text
submitted ticket accepted by Operation Layer
final exit detected
lifecycle hard stop reached after exchange/order interaction
ticket expires after submit boundary
manual recovery closes an incident
```

No row is required for pure no-signal periods or computed-not-satisfied market
states.

## Required Fields

### Identity

| Field | Rule |
| --- | --- |
| `live_outcome_id` | Stable id derived from `ticket_id` |
| `ticket_id` | Required and unique |
| `strategy_group_id` | Required |
| `symbol` | Required |
| `side` | Required |
| `runtime_profile_id` | Required |
| `policy_version_id` | Required when available |
| `strategy_version_id` | Required when available |
| `signal_time_ms` | Required for signal-backed tickets |
| `ticket_created_at_ms` | Required |

### Entry And Initial Risk

| Field | Rule |
| --- | --- |
| `entry_time_ms` | Required after entry fill |
| `entry_price` | Required after entry fill |
| `entry_qty` | Required after entry fill |
| `stop_price` | Required when stop protection is expected |
| `tp1_price` | Required when TP1 protection is expected |
| `tp1_qty` | Required when TP1 protection is expected |
| `risk_at_stop` | `abs(entry_price - stop_price) * entry_qty` after entry/stop known |
| `initial_notional` | Entry notional after fill |
| `leverage` | Runtime leverage used or intended |

### Protection And Exit

| Field | Rule |
| --- | --- |
| `sl_exchange_order_id` | Required when SL is submitted/confirmed |
| `tp1_exchange_order_id` | Required when TP1 is submitted/confirmed |
| `tp1_fill_time_ms` | Required after TP1 fill |
| `tp1_fill_price` | Required after TP1 fill |
| `runner_qty` | Remaining qty after TP1 fill |
| `runner_sl_price` | Required when runner protection is expected |
| `runner_sl_exchange_order_id` | Required when runner protection is confirmed |
| `final_exit_time_ms` | Required after final exit |
| `final_exit_price` | Required after final exit |
| `flat_reconciled_at_ms` | Required before closed outcome |

### Result Quality

| Field | Rule |
| --- | --- |
| `fees` | Required after settlement if available |
| `funding` | Required after settlement if available |
| `realized_pnl` | Required after final settlement |
| `unrealized_pnl` | Optional while position remains open |
| `mae` | Maximum adverse excursion when measurable |
| `mfe` | Maximum favorable excursion when measurable |
| `r_multiple` | `realized_pnl / risk_at_stop` when both are known |
| `stage_reached` | Highest lifecycle stage reached |
| `first_blocker` | Required when not lifecycle closed |
| `lifecycle_defects` | Array of lifecycle hard defects |

### Review

Allowed `review_decision` values:

```text
continue_same
promote_observe
revise
park
kill
needs_more_samples
```

| Field | Rule |
| --- | --- |
| `review_decision` | Required when outcome is reviewed |
| `review_reason_code` | Bounded reason code, not long narrative |
| `reviewed_at_ms` | Required when reviewed |
| `review_source` | `system`, `owner`, or `agent_review` |

## Lifecycle Defect Vocabulary

Allowed initial defect values:

```text
entry_unknown
entry_orphaned
entry_partial_fill_unhandled
protection_missing
protection_submit_failed
protection_reconciliation_mismatch
tp1_or_sl_orphaned
runner_mutation_failed
runner_reconciliation_mismatch
position_closed_protection_live
final_exit_unknown
settlement_blocked
review_blocked
```

New defect values must be added through this contract or a successor contract,
not ad hoc free-form text.

## Retention

Live outcome rows and their ticket/order/fill/protection/reconciliation lineage
must not be deleted by no-signal or monitor retention jobs.

Allowed compaction:

| Data | Rule |
| --- | --- |
| Raw bulky exchange snapshots | May be archived after compact facts are preserved |
| Duplicate monitor summaries | May be deleted |
| Outcome row | Retained |
| Ticket/order/fill refs | Retained |
| Review decision | Retained |

## Acceptance

| Requirement | Acceptance proof |
| --- | --- |
| **One outcome per real ticket** | Unique current row by `ticket_id` |
| **No runtime authority** | Outcome rows cannot unlock FinalGate, Operation Layer, or exchange write |
| **Structured result quality** | Entry, stop, TP1, runner, final exit, PnL, MAE/MFE, and R multiple are typed fields |
| **Defects are enumerable** | Lifecycle defects use the bounded vocabulary above |
| **Review is governance input only** | Review recommends future policy; it cannot mutate runtime scope |

## Chain Position

```text
chain_position: post_submit_learning_boundary
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: live_outcome_ledger_contract
first_blocker: live_outcome_ledger_not_implemented_as_pg_current_projection
evidence: ticket-bound lifecycle and review concepts exist, but real order outcome rows are not yet a first-class current projection
next_action: implement PG live outcome ledger projection after lifecycle state machine and operation capability audit are accepted
stop_condition: every real submitted ticket has one structured live outcome row or one exact lifecycle hard blocker
owner_action_required: no
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write from review rows
```
