# Trial Start Checklist MI-001 SOL Long

Generated: 2026-05-29

This file is a review/checklist artifact. It is not runtime source of truth and does not authorize trial start.

## 1. Summary

This is a PG-backed trial start readiness checklist for `MI-001 SOL/USDT:USDT long`.

It does not start a trial, grant execution permission, create orders, or modify account/exchange state. Any account facts shown here are read-only readiness inputs only.

## 2. Source Inputs

| input | status |
| --- | --- |
| pg_registration_records | available |
| cached_account_facts | available |
| operation_layer_facts | available |
| kill_switch_facts | available |
| owner_trial_start_approval | available |

## 3. PG Registration Checks

| check | status | evidence | blocking |
| --- | --- | --- | --- |
| MI-001 strategy family record exists | pass | MI-001:MI-001-smoke-v0 | no |
| MI-001 playbook record exists | pass | MI-001-SOL-LONG-BT-001 | no |
| MI-001-SOL-LONG candidate/admission version exists | pass | MI-001-SOL-LONG-admission-v1 | no |
| broad smoke evidence packet exists | pass | MI-001-SOL-LONG-broad-smoke-evidence-v1 | no |
| admission request exists | pass | MI-001-SOL-LONG-admission-request-v1 | no |
| Owner plan-preparation approval exists | pass | MI-001-SOL-LONG-owner-risk-acceptance-v1 | no |
| trial constraint snapshot exists | pass | MI-001-SOL-LONG-trial-constraints-v1 | no |
| planned binding exists | pass | MI-001-SOL-LONG-planned-binding-v1 | no |
| binding status is planned or binding_reserved | pass | planned | no |
| binding has no campaign_id | pass | None | no |
| binding has no runtime_carrier_id | pass | None | no |
| Owner trial-start approval is false or absent | pass | False | no |
| automatic execution approval is false | pass | False | no |
| no execution permission record created by this flow | pass | owner_confirm_each_entry | no |

## 4. Scope Checks

| check | expected | actual | status | blocking |
| --- | --- | --- | --- | --- |
| candidate | MI-001 | MI-001 | pass | no |
| symbol | SOL/USDT:USDT | SOL/USDT:USDT | pass | no |
| side | long | long | pass | no |
| allowed_candidate only | MI-001 | MI-001 | pass | no |
| allowed_symbol only | [SOL/USDT:USDT] | [SOL/USDT:USDT] | pass | no |
| allowed_side only | long | long | pass | no |
| max_attempts | 3 | 3 | pass | no |
| max_leverage | 5 | 5 | pass | no |
| no symbol expansion | true | true | pass | no |
| no side expansion | true | true | pass | no |
| no leverage expansion above 5x | true | true | pass | no |
| no transfer | true | true | pass | no |
| no withdrawal | true | true | pass | no |
| no auto top-up | true | true | pass | no |
| required_execution_capabilities empty | [] | [] | pass | no |
| binding remains non-runtime | campaign_id=null,runtime_carrier_id=null | campaign_id=null,runtime_carrier_id=null | pass | no |
| decision execution mode | owner_confirm_each_entry | owner_confirm_each_entry | pass | no |

## 5. Account Facts Checks

| check | status | source | timestamp | blocking | notes |
| --- | --- | --- | --- | --- | --- |
| cached AccountSnapshot exists | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| wallet_equity/account_equity available | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| available_margin available | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| freshness acceptable | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| read-only source | pass | read_only_account_query | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| reconciliation acceptable | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780060724639 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |

## 6. Capital Readiness

| field | value |
| --- | --- |
| status | pass |
| current_dedicated_subaccount_equity | 4663.88006276 |
| available_margin | 3653.11368275 |
| max_leverage | 5 |
| computed_max_notional_candidate | 18265.56841375 |
| max_total_loss_rule | current_dedicated_subaccount_equity |
| evidence | readiness calculation only; not persisted as execution config |

## 7. Operation Layer / Safety Checks

| check | status | evidence | blocking | notes |
| --- | --- | --- | --- | --- |
| Operation Layer gate available | pass | pg_readonly_closeout_facts | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| Operation Layer notional cap available | blocked | None | yes | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| Operation Layer loss cap available | pass | 4663.88006276 | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| startup guard armed | blocked | False | yes | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| evidence logging available | pass | pg_readonly_closeout_facts | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| no active trial position | pass | True | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| no open orders | pass | 0 | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| no active trial/campaign binding | pass | True | no | pg_brc_operation_repository_available; operation_layer_gate_code_available_but_no_live_start_preflight_invoked; operation_layer_notional_cap_fact_missing; startup_guard_default_fail_closed_not_armed; positions_orders_read_from_pg_only |
| GKS allows new entries | blocked | active=True,source=pg:BRC R3 LLM rehearsal restore safe state | yes | active=True means Global Kill Switch blocks all new entries. This is safe fail-closed state, not trial-start readiness. |

## 8. GKS Interpretation

active=True means Global Kill Switch blocks all new entries. This is safe fail-closed state, not trial-start readiness.

Checklist consequence:

- GKS state availability is a readiness fact, not execution permission.
- This checklist does not change GKS state.
- Any future trial start still requires separate Owner trial-start approval and an authorized safety transition.

## 9. Owner Trial-start Approval

| check | status | evidence | blocking |
| --- | --- | --- | --- |
| Owner plan preparation approved | pass | True | no |
| Owner trial start approved | pass | MI-001-SOL-LONG-owner-trial-start-approval-v1 | no |

## 10. Final Verdict

Verdict: `blocked_gks_active`

Blockers:
- Operation Layer notional cap available
- startup guard armed
- GKS allows new entries

## 11. Non-permissions

This checklist does not grant:
- execution permission
- order permission
- runtime start
- exchange API write permission
- leverage change permission
- symbol/side expansion
- automatic trial start
