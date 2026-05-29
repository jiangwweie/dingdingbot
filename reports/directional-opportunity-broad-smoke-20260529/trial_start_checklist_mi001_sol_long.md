# Trial Start Checklist MI-001 SOL Long

Generated: 2026-05-29

This file is a review/checklist artifact. It is not runtime source of truth and does not authorize trial start.

## 1. Summary

This is a PG-backed trial start readiness checklist for `MI-001 SOL/USDT:USDT long`.

It does not start a trial, grant execution permission, create orders, connect to an exchange, or call account APIs.

## 2. Source Inputs

| input | status |
| --- | --- |
| pg_registration_records | available |
| cached_account_facts | unsafe_to_read |
| operation_layer_facts | missing |
| kill_switch_facts | available |
| owner_trial_start_approval | blocked |

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
| cached AccountSnapshot exists | unsafe_to_read | runtime_exchange_gateway_cache_path_not_invoked | missing | yes | The only visible runtime account snapshot helper reads through `_exchange_gateway.get_account_snapshot`; this task did not invoke it because the standalone safety boundary requires cached/local/PG facts only and no runtime/exchange gateway access. |
| wallet_equity/account_equity available | blocked | runtime_exchange_gateway_cache_path_not_invoked | missing | yes | No safe cached account facts provider was supplied, so trial risk capital cannot be derived. |
| available_margin available | blocked | runtime_exchange_gateway_cache_path_not_invoked | missing | yes | No safe cached account facts provider was supplied, so available margin cannot be derived. |
| freshness acceptable | blocked | runtime_exchange_gateway_cache_path_not_invoked | missing | yes | No timestamped cached AccountSnapshot was available through a safe read-only path. |
| read-only source | unsafe_to_read | unsafe_to_read | missing | yes | The runtime cache helper was not called; no real exchange or account API call was made. |

## 6. Capital Readiness

| field | value |
| --- | --- |
| status | blocked |
| current_dedicated_subaccount_equity | blocked |
| available_margin | blocked |
| max_leverage | 5 |
| computed_max_notional_candidate | blocked |
| max_total_loss_rule | current_dedicated_subaccount_equity |
| evidence | fresh cached account equity and available margin are required |

## 7. Operation Layer / Safety Checks

| check | status | evidence | blocking | notes |
| --- | --- | --- | --- | --- |
| Operation Layer gate available | missing | not_provided | yes | No safe Operation Layer facts provider was supplied; runtime preflight was not invoked. |
| Operation Layer notional cap available | missing | not_provided | yes | No safe Operation Layer cap source was available for this checklist evaluation. |
| startup guard state available | not_checked | not_provided | yes | Startup guard is process-local/runtime state; this task did not inspect or mutate runtime. |
| evidence logging available | missing | not_provided | yes | Evidence logging readiness was not checked through Operation Layer facts. |
| no active trial position | not_checked | not_provided | yes | No runtime/position repository was queried; this remains blocked until a safe no-active-trial-position fact is available. |
| kill switch state available | pass | active=True,source=pg:BRC R3 LLM rehearsal restore safe state | no | active=True means Global Kill Switch blocks all new entries. This is safe fail-closed state, not trial-start readiness. |

## 8. GKS Interpretation

`active=True` means the Global Kill Switch is engaged and blocks all new entries.

Checklist consequence:

- GKS state is readable from PG and therefore the state check is available.
- The current `active=True` state is fail-closed and does not authorize trial start.
- Any future bounded trial start would still require separate Owner trial-start approval and a separate authorized safety transition; this checklist does not perform that transition.

## 9. Owner Trial-start Approval

| check | status | evidence | blocking |
| --- | --- | --- | --- |
| Owner plan preparation approved | pass | True | no |
| Owner trial start approved | blocked | False | yes |

## 10. Final Verdict

Verdict: `blocked_fresh_account_facts_required`

Blockers:

- cached AccountSnapshot exists
- wallet_equity/account_equity available
- available_margin available
- freshness acceptable
- read-only source
- capital readiness calculation unavailable
- Operation Layer gate available
- Operation Layer notional cap available
- startup guard state available
- evidence logging available
- no active trial position
- Owner trial start approved

## 11. Non-permissions

This checklist does not grant:

- execution permission
- order permission
- runtime start
- exchange API permission
- leverage change permission
- symbol/side expansion
- automatic trial start
