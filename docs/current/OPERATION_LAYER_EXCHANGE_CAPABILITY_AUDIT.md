---
title: OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT
status: CURRENT_AUDIT
authority: docs/current/OPERATION_LAYER_EXCHANGE_CAPABILITY_AUDIT.md
last_verified: 2026-07-08
---

# Operation Layer Exchange Capability Audit

## Purpose

This audit records the current **Operation Layer / ExchangeGateway** capability
boundary for ticket-bound real-order lifecycle work.

It answers:

```text
Which official-path exchange actions exist?
Which lifecycle states depend on them?
Which failures must fail closed?
Which gaps remain before real lifecycle acceptance can be considered complete?
```

This audit does not authorize live profile expansion, order sizing expansion,
FinalGate bypass, Operation Layer bypass, exchange writes outside the official
ticket-bound path, withdrawal, transfer, credential mutation, or runtime
decisions from repo/output/report files.

## Known Objective Facts

| Fact | Evidence |
| --- | --- |
| **Ticket-bound protected submit API exists** | `src/interfaces/api_trading_console.py` exposes `/runtime-protected-submits/tickets/{ticket_id}/operation-submit-commands/{operation_submit_command_id}` |
| **Real protected submit requires PG** | API rejects missing or non-Postgres `PG_DATABASE_URL` before ticket-bound submit |
| **Real protected submit uses official gateway only in `real_gateway_action` mode** | `_run_ticket_bound_protected_submit` prepares PG attempt first, then calls `_execute_ticket_bound_real_gateway_submit` only when report status is `submit_prepared` and mode is `real_gateway_action` |
| **Submit envelope is sequential, not exchange-native atomic bracket** | `_submit_ticket_bound_orders` iterates ENTRY / SL / TP1 requests and calls `gateway.place_order` one by one |
| **ENTRY / SL / TP1 are generated from one ticket-bound request** | `protected_submit_attempt._submit_request` creates ENTRY, SL, and TP1 order requests |
| **SL and TP1 are reduce-only in submit request** | SL and TP1 order requests set `reduce_only=True`; ENTRY sets `reduce_only=False` |
| **Runner mutation uses injected gateway cancel/place** | `runner_mutation_executor` calls `gateway.cancel_order` for old SL and `gateway.place_order` for RUNNER_SL |
| **Protection recovery uses injected gateway place only** | `protection_recovery_command` calls `gateway.place_order` only for missing reduce-only SL/TP1 |
| **Protection reconciler does not call exchange** | `protection_reconciler` consumes caller-provided exchange snapshots and updates PG lifecycle state |
| **ExchangeGateway supports order writes and key reads** | `ExchangeGateway` exposes `place_order`, `cancel_order`, `fetch_open_orders`, `fetch_order`, `fetch_positions`, `fetch_account_balance`, `confirm_order_exists`, `watch_orders`, and now `fetch_my_trades` |
| **Gateway readiness evidence is non-executing** | `RuntimeExecutionExchangeGatewayReadiness` is constrained to no gateway injection, no exchange call, no order submit, no lifecycle submit |

## Capability Matrix

| Capability | Current status | Official path | Required lineage | Failure state |
| --- | --- | --- | --- | --- |
| **ENTRY submit** | Supported by `gateway.place_order` | Ticket-bound protected submit API / `_submit_ticket_bound_orders` | `ticket_id`, `finalgate_pass_id`, `operation_submit_command_id`, local ENTRY order id | `entry_submit_failed`, `entry_unknown`, `entry_orphaned` |
| **SL submit** | Supported by `gateway.place_order` with `reduce_only=True` | Initial protected submit or protection recovery command | `ticket_id`, `protected_submit_attempt_id`, ENTRY ref | `protection_missing`, `protection_submit_failed` |
| **TP1 submit** | Supported by `gateway.place_order` as limit reduce-only | Initial protected submit or protection recovery command | `ticket_id`, `protected_submit_attempt_id`, ENTRY ref | `protection_submit_failed`, `tp1_reference_missing` before submit |
| **RUNNER_SL submit** | Supported by `runner_mutation_executor` through `gateway.place_order` | Prepared runner mutation command | `ticket_id`, `exit_protection_set_id`, TP1 ref, old SL ref | `runner_mutation_failed`, `runner_reconciliation_mismatch` |
| **reduce-only close order** | Supported by normalized submit fields and gateway params | SL / TP1 / RUNNER_SL request builders | Local order role and reduce-only flag | `*_reduce_only_required`, `*_reduce_only_missing` |
| **cancel old SL** | Supported by `gateway.cancel_order` | Runner mutation executor | `runner_mutation_command_id`, old SL exchange id | `runner_mutation_failed`, `old_sl_cancel_not_confirmed` |
| **conditional stop cancel fallback** | Supported for Binance stop-order visibility | `ExchangeGateway.cancel_order` fallback through `fetch_open_orders(..., {"stop": True})` | exchange order id, symbol | `old_sl_cancel_failed`, `order_not_found` |
| **query open orders** | Supported by `gateway.fetch_open_orders` | Reconciler snapshot fetch must call this through official read adapter | symbol, params including stop-order variants | `protection_reconciliation_mismatch`, `runner_reconciliation_mismatch` |
| **query order by id** | Supported by `gateway.fetch_order`, including conditional open-order fallback | Submit projection recovery / confirmation | exchange order id, symbol | `entry_exchange_order_fetch_failed`, `final_exit_unknown` |
| **query positions** | Supported by `gateway.fetch_positions` | Account/reconciliation read adapter | symbol | `exchange_position_fetch_failed`, `exchange_position_snapshot_missing` |
| **query account/balance** | Supported by `gateway.fetch_account_balance` / cached polling | Runtime/account facts | account snapshot timestamp | account fact blockers outside this audit |
| **query recent fills** | Supported by new `gateway.fetch_my_trades` wrapper | Close projection recovery / recent fill snapshot | symbol, trade id or exchange order id | `exchange_close_trade_not_found`, `final_exit_unknown` |
| **watch order updates** | Supported by `gateway.watch_orders` | Runtime order watch / global callback | symbol, exchange order id | recovery marker via pending recovery orders |
| **clientOrderId idempotency** | Partially supported | `ExchangeGateway._build_ccxt_order_params` sends `clientOrderId`; submit request uses stable local order ids | local order id / client order id | duplicate guard depends on PG submit attempt and exchange lookup |
| **modify/amend order** | Not implemented as direct amend | Current runner mutation uses cancel + new | old SL ref, RUNNER_SL request | unsupported direct amend must use cancel+new or fail closed |
| **orphan protection cancel** | Not implemented as a generic automated command | Reconciler can detect orphan/flat-live-protection; cancellation command remains future controlled operation | orphan identity proof | `tp1_or_sl_orphaned`, `position_closed_protection_live` |

## Official Entry Point Map

| Entry point | Exchange write | Required upstream state | Current guard |
| --- | --- | --- | --- |
| **Ticket-bound protected submit** | `place_order` for ENTRY / SL / TP1 when mode is `real_gateway_action` | PG ticket finalgate-ready, Operation Layer handoff, Runtime Safety State submit allowed | PG DSN, ticket identity checks, submit request identity checks, gateway binding env, readiness evidence |
| **Protection recovery command** | `place_order` for missing SL/TP1 only | Existing ticket-bound attempt with ENTRY filled and lifecycle hard blocker | Existing PG attempt/lifecycle, missing-order plan, injected gateway, reduce-only orders |
| **Runner mutation executor** | `cancel_order` old SL, then `place_order` RUNNER_SL | TP1 filled, complete protection set, prepared PG runner command | Prepared command status, stale lifecycle checks, injected gateway |
| **Protection reconciler** | None | PG protection set plus exchange snapshot | Snapshot comparison only; no exchange mutation |
| **Runtime exchange gateway readiness** | None | Environment and Owner readiness review | DB/model constraints force no gateway injection and no exchange call |
| **Legacy execution intent real gateway path** | `place_order` for entry/protection preview requests | Older authorization chain | Must not be treated as the ticket-bound lifecycle readiness source |

## Lifecycle Dependency Map

| Lifecycle state | Required exchange / PG capability |
| --- | --- |
| **submit_prepared** | PG ticket, FinalGate pass, Operation Layer handoff, Runtime Safety State |
| **entry_accepted** | `place_order` ENTRY success and exchange order id |
| **entry_filled** | OrderLifecycle fill, `fetch_order`, order WebSocket, or accepted fill fact |
| **position_protected** | SL and TP1 exchange refs, reduce-only flags, valid open-order snapshot |
| **tp1_filled** | TP1 fill from recent fills, fetch order, or order WebSocket |
| **runner_mutation_pending** | TP1 filled, old SL ref, runner qty positive |
| **runner_protected** | old SL gone, RUNNER_SL open, PG and exchange refs reconciled |
| **final_exit_detected** | SL/TP1/RUNNER_SL final fill fact or close trade fact |
| **flat_reconciled** | position qty zero and no conflicting live protection |
| **lifecycle_closed** | final exit, reconciliation, settlement, review, and no live residual protection |

## Failure Mapping

| Failure | Required state | Required next action |
| --- | --- | --- |
| **ENTRY rejected before fill** | `submit_failed` | Release/expire ticket scope; no retry without new checks |
| **ENTRY timed out / unknown** | `entry_unknown` | Reconcile order/position before retry |
| **ENTRY accepted but local lifecycle write failed** | `entry_orphaned` | Reconcile exchange order into PG before any new submit |
| **ENTRY partial fill** | `entry_partial_fill_unhandled` | Reconcile actual filled qty and protect only actual exposure |
| **ENTRY filled but SL failed** | `protection_missing` | Official recovery command submit SL or flatten recovery |
| **ENTRY filled but TP1 failed** | `protection_submit_failed` | Official recovery command submit TP1 or mark degraded and block new entries |
| **PG says SL/TP1 exists but exchange lacks it** | `protection_reconciliation_mismatch` | Refresh exchange snapshot, repair or recover protection |
| **TP1 filled but runner SL missing** | `runner_mutation_pending` | Prepare and execute official runner mutation command |
| **Old SL cancel failed** | `runner_mutation_failed` | Repair runner mutation or flatten recovery |
| **Old SL cancelled but RUNNER_SL failed** | `runner_mutation_failed` with `runner_unprotected_after_old_sl_cancelled` | Retry runner SL or flatten recovery |
| **RUNNER_SL exists but old SL remains live** | `runner_reconciliation_mismatch` | Cancel old SL or reconcile identity |
| **Position flat but protection remains live** | `position_closed_protection_live` | Official cleanup cancel command after identity proof |
| **Close fill cannot be found** | `final_exit_unknown` | Refresh fills/order/position facts |

## P0-0 Findings

### Closed During This Audit

| Finding | Resolution |
| --- | --- |
| **Gateway readiness method set was too narrow** | `RUNTIME_EXCHANGE_LIFECYCLE_GATEWAY_METHODS` now includes submit, cancel, open orders, order query, positions, recent fills, ticker, and market info |
| **ExchangeGateway lacked first-class `fetch_my_trades` wrapper** | Added read-only `ExchangeGateway.fetch_my_trades` so close projection and recent fills have an explicit gateway capability |

### Remaining Engineering Gaps

| Gap | Severity | Impact | Next action |
| --- | --- | --- | --- |
| **No direct amend/modify order capability** | P1 | Runner mutation must use cancel+new; old SL cancelled before RUNNER_SL failure can create temporary unprotected state | Keep cancel+new failure mapping; consider exchange-specific amend only after official capability proof |
| **Orphan protection cancel is detected but not a first-class official cleanup command** | P1 | Flat position can retain live reduce-only orders until manual or future command cleanup | Add explicit ticket/orphan-bound cleanup command after reconciler identity proof |
| **Recent fills depend on `fetch_my_trades` availability and exchange permissions** | P1 | Final exit / outcome ledger can be blocked if account trade history read is unavailable | Validate in server capability audit and map failure to `final_exit_unknown` |
| **Legacy execution-intent real submit path still exists** | P1 | It can confuse readiness interpretation if treated as current ticket-bound path | Keep current planning anchored to PG Action-Time Ticket and ticket-bound protected submit |

## Current Capability Conclusion

```text
ENTRY submit: supported through ticket-bound place_order
SL submit: supported through reduce-only stop_market place_order
TP1 submit: supported through reduce-only limit place_order
RUNNER_SL submit: supported through runner mutation executor place_order
cancel old SL: supported through cancel_order
query open orders: supported
query order: supported
query positions: supported
query account: supported
query recent fills: supported through fetch_my_trades wrapper
clientOrderId: supported through stable local order ids, but retry semantics still require exchange lookup
modify/amend: not implemented; use cancel+new
orphan cleanup cancel: not yet first-class command
```

## Runtime Cadence And Performance

| Path | Cadence rule |
| --- | --- |
| **No-signal tick** | Must not call exchange write methods and must not create lifecycle rows |
| **Capability audit** | Code/static audit and mock tests only unless explicitly authorized |
| **Reconciler** | Bounded to open lifecycle runs and current snapshots |
| **Recent fills** | Bounded by symbol and limit; no broad history scan in production cadence |
| **Logs** | One-line summary; detailed refs stay in PG |
| **Retention** | Never delete ticket/order/fill/protection/reconciliation lineage |

## Acceptance

| Requirement | Status |
| --- | --- |
| **Capability matrix exists** | Complete in this document |
| **Official entry points mapped** | Complete in this document |
| **Lifecycle dependencies mapped** | Complete in this document |
| **Failure mapping exists** | Complete in this document |
| **Gateway readiness method gap closed** | Code updated and unit-tested |
| **No exchange write performed by audit** | This audit used code inspection and unit tests only |

## Chain Position

```text
chain_position: action_time_back_half_capability_audit
strategy_group_id: active 5 StrategyGroups
symbol: active candidate scopes
stage: operation_layer_exchange_capability_audit_complete
first_blocker: orphan_protection_cleanup_command_not_first_class
evidence: ExchangeGateway and ticket-bound APIs expose submit/cancel/read/fill capabilities; readiness method set now covers lifecycle methods; direct amend remains unsupported and cancel+new is the official runner path
next_action: proceed to P0-1 lifecycle invariant hardening and P0-2 failure-matrix harness; add orphan protection cleanup command before treating flat-with-live-protection as fully recoverable
stop_condition: next real ticket proves ENTRY, SL, TP1, RUNNER_SL, reconciliation, final exit, settlement, and live outcome, or stops at one exact lifecycle hard blocker
owner_action_required: no
authority_boundary: no FinalGate bypass / no Operation Layer bypass / no exchange write during audit / no live profile or sizing mutation
```
