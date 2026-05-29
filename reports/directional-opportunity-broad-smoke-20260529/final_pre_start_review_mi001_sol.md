# Final Pre-start Review Packet: MI-001 SOL Long

Generated: 2026-05-29

Scope: `MI-001-SOL-LONG` / `SOL/USDT:USDT` / long.

## 1. Summary

This is a final pre-start review packet after Owner Console Web acceptance for MI-001 SOL.

This is not trial start. It does not start runtime, create an execution intent, create an order, grant execution permission, change leverage, transfer funds, withdraw funds, or modify exchange state.

The current terminal state remains:

`blocked_startup_guard_runtime_coupled`

## 2. Candidate

| field | value |
| --- | --- |
| candidate_id | MI-001-SOL-LONG |
| strategy_family_id | MI-001 |
| strategy_family | Momentum Impulse |
| variant_label | 12h close-to-close momentum impulse |
| symbol | SOL/USDT:USDT |
| side | long |
| current_status | blocked_startup_guard_runtime_coupled |

## 3. Evidence

Broad smoke evidence:

| metric | value |
| --- | --- |
| signal_count | 8135 |
| 72h mean | 1.9531 |
| 72h positive_rate | 0.5175 |
| 7d mean | 4.7372 |
| 7d positive_rate | 0.5398 |

Evidence limitations:

- no cost
- no slippage
- no funding
- no random baseline
- no campaign replay
- research evidence is not execution permission

## 4. Risk Boundary

| boundary | value |
| --- | --- |
| capital_source | dedicated_subaccount |
| trial_risk_capital_rule | current_dedicated_subaccount_equity |
| max_total_loss_rule | current_dedicated_subaccount_equity |
| max_leverage | 5x |
| max_notional_rule | min(current_dedicated_subaccount_equity * 5, available_margin * 5, Operation Layer notional cap) |
| Operation Layer notional cap | 18262.85481460 |
| allowed_candidate | MI-001 only |
| allowed_symbol | SOL/USDT:USDT only |
| allowed_side | long only |
| max_attempts | 3 |

Prohibitions:

- no auto top-up
- no transfer
- no withdrawal
- no symbol expansion
- no side expansion
- no leverage expansion above 5x
- no bypass of Operation Layer

## 5. Account Facts

Account facts are read-only readiness inputs only.

| field | value |
| --- | --- |
| source | Binance USDT futures read-only account facts |
| read method | read-only account query |
| account_equity | 4663.39779623 |
| available_margin | 3652.57096292 |
| timestamp_ms | 1780062738890 |
| freshness | acceptable at checklist generation |
| external_call_type | read_only_account_query |
| exchange write methods called | no |

These values are readiness facts, not permanent execution config. If a future start-preflight is authorized, account facts must be refreshed again.

## 6. Readiness Checklist

| check | status | evidence | blocking |
| --- | --- | --- | --- |
| PG registration | pass | MI-001 registration chain applied to PG metadata/admission records | no |
| Owner plan-preparation approval | pass | MI-001-SOL-LONG-owner-risk-acceptance-v1 | no |
| Owner trial-start metadata approval | pass | MI-001-SOL-LONG-owner-trial-start-approval-v1 | no |
| Account facts | pass | live read-only Binance USDT futures account facts available | no |
| Capital readiness | pass | computed_max_notional_candidate 18262.85481460 | no |
| Operation Layer notional cap | pass | 18262.85481460 | no |
| Operation Layer loss cap | pass | 4663.39779623 | no |
| GKS | pass | active=False in readiness transition facts | no |
| startup guard | blocked | runtime-owned process-local guard is not armed in this session | yes |
| SOL active position | pass | 0 | no |
| SOL open orders | pass | 0 | no |
| active trial/campaign binding | pass | none active from this readiness flow | no |
| evidence logging | pass | PG readiness transition apply evidence available | no |

## 7. Current Terminal State

`blocked_startup_guard_runtime_coupled`

The only remaining blocker is the runtime-owned startup guard. Offline arming would not be valid because `StartupTradingGuardService` is process-local runtime state. The guard-only control surface exists at:

`POST /api/brc/readiness/startup-guard/preflight-arm`

That endpoint still requires an actual bound runtime context and initialized runtime-owned startup guard. Calling it is not trial start, but it is a separate Owner-authorized readiness action.

## 8. Owner Console Web Review

Owner Web review has been completed on `/command-center`.

The console can display:

- candidate
- evidence
- risk policy
- account facts
- readiness checklist
- blocker
- startup guard preflight action
- non-permissions

Web acceptance verdict:

`accepted_for_owner_console_review`

The page shows startup guard preflight as guarded/disabled when runtime guard is unavailable. Order and execution actions are not exposed as executable actions.

## 9. Non-permissions

This pre-start review packet grants none of the following:

- no trial start
- no execution permission
- no order permission
- no runtime start
- no leverage change
- no transfer
- no withdrawal
- no exchange API write permission
- no symbol expansion
- no side expansion
- no automatic trial start

## 10. Remaining Blocker

Remaining blocker:

`blocked_startup_guard_runtime_coupled`

Resolution requires a separate Owner-authorized action against the actual runtime-owned startup guard. That next action must still remain preflight-only unless Owner separately authorizes a manual start command.

## 11. Safety Check

| question | answer |
| --- | --- |
| 是否启动 trial？ | no |
| 是否下单？ | no |
| 是否创建 execution intent？ | no |
| 是否授予 execution permission？ | no |
| 是否修改杠杆？ | no |
| 是否触碰 exchange_gateway？ | no |

## 12. Next Recommended Task

Owner decides whether to authorize runtime-bound startup guard preflight.
