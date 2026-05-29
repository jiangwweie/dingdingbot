# Trial Start Checklist MI-001 SOL Long

Generated: 2026-05-29

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
| cached AccountSnapshot exists | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| wallet_equity/account_equity available | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| available_margin available | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| freshness acceptable | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| read-only source | pass | read_only_account_query | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |
| reconciliation acceptable | pass | binance_usdt_futures_read_only:binance_usdt_futures_live_read_only | 1780062738890 | no | candidate=MI-001-SOL-LONG; symbol=SOL/USDT:USDT; side=long; source=Binance USDT futures balance read; account_equity_prefers_totalMarginBalance; available_margin_prefers_availableBalance; exchange timestamp missing; using local read timestamp; external_call_type=read_only_account_query |

## 6. Capital Readiness

| field | value |
| --- | --- |
| status | pass |
| current_dedicated_subaccount_equity | 4663.39779623 |
| available_margin | 3652.57096292 |
| max_leverage | 5 |
| computed_max_notional_candidate | 18262.85481460 |
| max_total_loss_rule | current_dedicated_subaccount_equity |
| evidence | readiness calculation only; not persisted as execution config |

## 7. Operation Layer / Safety Checks

| check | status | evidence | blocking | notes |
| --- | --- | --- | --- | --- |
| Operation Layer gate available | pass | pg_readiness_transition_apply | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| Operation Layer notional cap available | pass | 18262.85481460 | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| Operation Layer loss cap available | pass | 4663.39779623 | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| startup guard armed | blocked | False | yes | startup_guard_runtime_coupled; process_local_only; no_pg_persistence; manual_arm_requires_runtime_control_surface; no_runtime_started |
| evidence logging available | pass | pg_readiness_transition_apply | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| no active trial position | pass | True | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| no open orders | pass | 0 | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| no active trial/campaign binding | pass | True | no | operation_layer_notional_cap_pg_applied; gks_pg_set_inactive; startup_guard_not_armed_no_runtime_process; positions_orders_read_from_pg_only |
| GKS allows new entries | pass | active=False,source=pg:MI-001 SOL readiness transition authorized by Owner; not trial start; startup guard still required | no | active=False means GKS no longer blocks readiness; this still does not grant execution permission or start trial. |

## 8. GKS Interpretation

active=False means GKS no longer blocks readiness; this still does not grant execution permission or start trial.

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

Verdict: `blocked_startup_guard`

Blockers:
- startup guard armed (blocked_startup_guard_runtime_coupled: process-local runtime guard is not armed; no persistent PG startup-guard source exists; no runtime was started)

## 11. Non-permissions

This checklist does not grant:
- execution permission
- order permission
- runtime start
- exchange API write permission
- leverage change permission
- symbol/side expansion
- automatic trial start
