# MI-001 SOL Trial Readiness Transition Plan

Generated: 2026-05-29

Scope: `MI-001 SOL/USDT:USDT long` readiness transition planning.

This is a review artifact and proposal plan only. It is not runtime source of truth, does not start a trial, does not create an execution intent, does not grant execution permission, does not place or cancel orders, does not modify leverage, does not disable GKS, and does not arm startup guard.

## 1. Summary

This task reviewed the remaining `trial_start_checklist` blockers for `MI-001 SOL/USDT:USDT long`:

- GKS state
- startup guard state
- Operation Layer gate / notional cap / loss cap
- evidence logging readiness
- no active position / open orders / active trial
- Owner final trial-start approval metadata

The current checklist remains blocked. The correct current verdict is still:

`blocked_gks_active`

No transition action was executed. The next step should be a separate Owner-authorized transition apply for GKS/startup/notional-cap readiness.

## 2. Current Blockers

| blocker | current_state | source | impact | can_resolve_in_this_task | notes |
| --- | --- | --- | --- | --- | --- |
| GKS active | `active=True`; reason `BRC R3 LLM rehearsal restore safe state` | PG `global_kill_switch_state` and `GlobalKillSwitchService` | Blocks all new entries fail-closed | no | Disabling GKS is a runtime safety state change and was not performed. |
| startup guard not armed | default/fail-closed not armed | `StartupTradingGuardService`; checklist closeout report | Blocks new entries before runtime gate | no | Arming is a runtime control action and was not performed. |
| Operation Layer notional cap missing | no MI-001-specific notional cap fact available | checklist closeout + trial constraint policy | Keeps readiness blocked at cap stage | no | Existing constraint stores policy rule, not concrete current cap. |
| Operation Layer loss cap | available as policy rule/equity readiness | trial constraint snapshot + account facts | Not a current blocker | n/a | Rule is `max_total_loss = current_dedicated_subaccount_equity`. |
| evidence logging | available | `brc_operations`, `brc_preflight_snapshots`, `brc_execution_results`; read-only PG counts all available | Not a current blocker | n/a | Ledger exists; this task did not create operation records. |
| active SOL position | `0` | PG `positions` read-only query | Not a current blocker | n/a | No close/flatten action performed. |
| open SOL orders | `0` | PG `orders` read-only query | Not a current blocker | n/a | No cancel action performed. |
| active trial/campaign binding | none; planned binding has `campaign_id=null`, `runtime_carrier_id=null` | PG `brc_admission_trial_bindings` | Not a current blocker | n/a | Planned binding remains non-runtime metadata. |
| Owner final start approval | metadata-only approval recorded | PG `brc_owner_risk_acceptances` | Not a current blocker | n/a | Approval scope is `trial_start_metadata_only`; auto execution/order/runtime permissions are false. |

## 3. Required Transition Actions

| action_id | action | type | runtime_effect | owner_authorization_required | can_do_now | recommended_next_step |
| --- | --- | --- | --- | --- | --- | --- |
| RT-001 | Record an Owner-approved readiness transition package covering GKS disable window, startup guard arm, and MI-001 cap install | metadata_proposal | none | yes | yes, as a report/proposal only | Use this report as the package; do not treat it as execution authorization. |
| RT-002 | Set MI-001 Operation Layer notional cap fact | config_record | no direct order effect, but changes readiness gate input | yes | no | Implement/apply a PG-backed cap record or Operation decision in a separate task. |
| RT-003 | Arm startup guard for the bounded readiness window | runtime_safety_state_change | allows entries past startup guard if other gates also pass | yes | no | Execute only via existing runtime control path after cap is installed and GKS transition is authorized. |
| RT-004 | Disable GKS for the bounded readiness/trial-start window | runtime_safety_state_change | allows new entries past GKS if other gates also pass | yes | no | Execute only as a separate Owner-authorized runtime control action; restore GKS active afterward. |
| RT-005 | Re-run MI-001 trial_start_checklist after RT-002/RT-003/RT-004 | read_only_check | none | no, after transition authorization | no | Expected verdict becomes `ready_for_trial_start_after_owner_approval` only if all facts remain clean. |
| RT-006 | Start trial or create execution/order intent | blocked | would affect runtime/execution/order | yes, separate explicit task | no | Out of scope; do not bundle with readiness transition. |

## 4. GKS Transition

Current semantics:

- `GlobalKillSwitchService` defines `active=True` as all new entries blocked.
- Missing/corrupt/unavailable PG state also fails closed to `active=True`.
- Runtime entry checks reject when `gks_svc.is_active()` is true.
- Current PG state is `active=True`.

Resolution mechanism:

- Existing runtime control surface can call `GlobalKillSwitchService.set_state(active=False, ...)`.
- That is a real runtime safety state change, not metadata.

Should this task execute it?

- No.
- This task is planning only and explicitly must not disable GKS.

Required preconditions before execution:

- Owner explicitly authorizes the bounded transition apply.
- Operation Layer notional cap fact is installed.
- Startup guard transition is paired with GKS transition.
- No active position/open orders remain true.
- Evidence logging remains available.
- Plan includes restoring GKS active after the bounded window.

## 5. Startup Guard Transition

Current semantics:

- `StartupTradingGuardService` starts fail-closed by default.
- `armed=False` blocks new entries.
- Runtime entry checks reject if guard is absent or not armed.

Resolution mechanism:

- Existing runtime control surface can call `StartupTradingGuardService.manual_arm(...)`.
- That is a real runtime safety state change, not metadata.

Should this task execute it?

- No.
- This task is planning only and explicitly must not arm startup guard.

Required preconditions before execution:

- Owner explicitly authorizes the bounded transition apply.
- GKS transition window and rollback path are defined.
- Operation Layer notional cap fact is installed.
- No active position/open orders remain true.
- Startup guard should be blocked again after the bounded trial-start window if readiness does not proceed.

## 6. Operation Layer Cap Transition

Recommended cap model:

- `capital_source = dedicated_subaccount`
- `trial_risk_capital = current_dedicated_subaccount_equity`
- `max_total_loss = current_dedicated_subaccount_equity`
- `max_leverage = 5`
- `max_notional = min(current_dedicated_subaccount_equity * 5, available_margin * 5, Operation Layer notional cap if exists)`

Current PG state:

- Trial constraint snapshot exists but is still `pending_risk_capital_resolution`.
- It records `max_leverage=5`, `max_attempts=3`, and a policy rule for max notional.
- It does not provide a concrete MI-001 Operation Layer notional cap fact for checklist readiness.

Recommended source of truth:

- Use a PG-backed Operation Layer cap/config/decision record if one is added or already selected in the next task.
- Do not hard-code the cap in Markdown.
- Do not write the cap into strategy family registry.
- Do not grant execution permission when writing the cap.

Owner approval requirement:

- Required, because this cap turns policy into a readiness gate input for a real-live account candidate.
- The approval should still be metadata/config only and must not start runtime or create orders.

## 7. Proposed Next Checklist Verdict

If only this plan is accepted:

- Checklist remains `blocked_gks_active`.

If the next task installs a PG-backed MI-001 Operation Layer notional cap but does not change runtime safety state:

- Expected checklist remains `blocked_gks_active`.

If a separate Owner-authorized transition apply installs the cap, arms startup guard, and disables GKS for a bounded window while active positions/open orders remain zero:

- Expected checklist can become `ready_for_trial_start_after_owner_approval`.

This does not mean `trial_started`.

## 8. Safety Check

| check | answer |
| --- | --- |
| 是否 push？ | no |
| 是否下单？ | no |
| 是否取消订单？ | no |
| 是否修改杠杆？ | no |
| 是否 set_leverage？ | no |
| 是否转账/提现？ | no |
| 是否创建 execution intent？ | no |
| 是否启动 trial？ | no |
| 是否解除 GKS？ | no |
| 是否 arm startup guard？ | no |
| 是否授予 execution permission？ | no |
| 是否写 runtime/campaign/execution/order 表？ | no |

## 9. Current Strategy Progress

| item | status | next |
| --- | --- | --- |
| MI-001 SOL long | Trial readiness closeout complete; blocked by GKS/startup/notional-cap transition | Owner-authorized readiness transition apply |
| VI-001 ETH long | Research/control candidate; not in current trial readiness | No action in this task |
| MI-001 BNB long | Not in current trial readiness | No action in this task |
| other strategy families | Not expanded | No action in this task |
| Tier 1 data families | Not touched | No action in this task |

## 10. Next Recommended Task

Owner-authorized transition apply for GKS/startup/cap.
