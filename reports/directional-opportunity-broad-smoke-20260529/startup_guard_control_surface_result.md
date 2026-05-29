# MI-001 SOL Startup Guard Control Surface Result

Generated: 2026-05-29

Scope: safe startup guard control surface for `MI-001 SOL/USDT:USDT long` readiness.

This report is a review artifact only. It does not start a trial, does not start strategy execution, does not grant execution permission, does not create execution intents, does not place or cancel orders, does not modify leverage, does not transfer or withdraw funds, and does not modify `exchange_gateway`.

## 1. Summary

Added a guard-only BRC Console readiness action:

`POST /api/brc/readiness/startup-guard/preflight-arm`

The endpoint can arm the actual runtime-owned `StartupTradingGuardService` only when:

- a runtime context is already bound;
- `_startup_trading_guard_service` is already initialized;
- `RUNTIME_CONTROL_API_ENABLED=true`;
- the caller is an authenticated BRC operator through the existing Owner Console auth dependency.

The endpoint does not start runtime, does not start trial, does not create execution intents, does not grant execution permission, does not create orders, and does not call exchange write methods.

No actual runtime-owned guard was armed in this shell because no runtime control listener was available and starting the broader runtime remains outside this task.

## 2. Path Chosen

Path B: added a minimal guard-only endpoint.

Reason:

- Existing runtime API already has a startup guard arm endpoint, but it belongs to the broader runtime control surface.
- The Owner Console needed a narrow readiness action that can be used by the main workflow without naming it as trial start or execution.
- The new endpoint fails closed if the actual runtime-owned guard is unavailable.

## 3. Startup Guard Control Surface

| field | value |
| --- | --- |
| endpoint | `POST /api/brc/readiness/startup-guard/preflight-arm` |
| request | `reason`, `updated_by` |
| response | `armed_before`, `armed_after`, `runtime_effect`, permission false flags, `trial_started=false`, `next_checklist_verdict`, notes |
| auth | existing BRC operator session dependency |
| mutation env gate | requires `RUNTIME_CONTROL_API_ENABLED=true` |
| runtime requirement | existing runtime context and `_startup_trading_guard_service` |
| runtime effect | `startup_guard_process_state_only` when successful |
| execution/order effect | none |
| Owner Console usable | yes |

Response guarantees:

- `execution_permission_granted=false`
- `order_permission_granted=false`
- `trial_started=false`
- `strategy_runtime_started=false`
- `execution_intent_created=false`
- `order_created=false`
- `exchange_write_methods_called=false`

## 4. Checklist Impact

Previous verdict:

`blocked_startup_guard_runtime_coupled`

Current checklist verdict:

`blocked_startup_guard_runtime_coupled`

Reason: the safe control surface now exists, but it was not run against a live runtime-owned guard in this shell. The checklist should advance only after the endpoint is called against an initialized runtime control process and then the checklist is regenerated from that runtime safety state.

Expected verdict after successful endpoint call and checklist regeneration, assuming all prior facts remain valid:

`ready_for_trial_start_after_owner_approval`

This does not mean `trial_started`, `execution_enabled`, or `order_capable`.

## 5. Safety Check

| check | answer |
| --- | --- |
| 是否 push？ | no |
| 是否启动 trial？ | no |
| 是否启动 strategy runtime？ | no |
| 是否下单？ | no |
| 是否取消订单？ | no |
| 是否创建 execution intent？ | no |
| 是否授予 execution permission？ | no |
| 是否修改杠杆？ | no |
| 是否 set_leverage？ | no |
| 是否转账/提现？ | no |
| 是否写 execution/order 表？ | no |
| 是否修改 exchange_gateway？ | no |
| 是否 arm startup guard？ | no |

## 6. Current Strategy Progress

| item | status | next |
| --- | --- | --- |
| MI-001 SOL long | PG registration, account facts, Operation cap, GKS, Owner metadata approval ready; startup guard endpoint added; actual guard still not armed in this shell | Owner Console E2E acceptance walkthrough |
| VI-001 ETH long | backup/control candidate | no trial chain action |
| MI-001 BNB long | reference candidate with shorter history | no trial chain action |
| other strategy families | not in current readiness chain | no action |
| Tier 1 data families | research-only context | no action |

## 7. Next Recommended Task

Owner Console E2E acceptance walkthrough.
