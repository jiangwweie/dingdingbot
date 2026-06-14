# StrategyGroup Runtime Pilot Current Checkpoint

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the active StrategyGroup runtime pilot state after
selective watch-branch intake, watcher resume dispatcher implementation,
repo-local MPG pilot handoff, candidate prerequisite derivation, standing
authorization handoff cleanup, Tokyo deploy, and postdeploy live-readonly
verification.

Workspace and branch:

| Field | Value |
| --- | --- |
| Workspace | `/Users/jiangwei/Documents/final` |
| Branch | `codex/strategygroup-runtime-pilot` |
| Current deployed code head | `09791efe0a13c460a8c4ab9940e5d81f0dbb15a9` |
| Current release | `brc-runtime-governance-09791efe-20260615-standing-auth-handoff` |
| Tokyo release path | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-09791efe-20260615-standing-auth-handoff` |

## Watch Branch Intake

`codex/runtime-signal-watcher-feishu` was not merged wholesale. Its large docs
reset and historical compression remain a separate docs-governance item.

Useful content now carried in the pilot branch:

| Content | Current status |
| --- | --- |
| Standing authorization for deploy apply and in-boundary runtime advancement | Present in canon, deploy plans, executors, and tests |
| Owner-facing Strategy Control Board contract | Present in `docs/canon/STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md` and `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` |
| Short current SSOT / AI constraints | Present in `docs/current/AI_AGENT_CONSTRAINTS.md` and `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` |
| Post-signal resume metadata | Present in watcher readiness and Trading Console readmodel |
| Ready-signal dispatch record | Present in `scripts/runtime_signal_watcher_resume_dispatcher.py` |
| Action-time FinalGate preflight auto-call | Present behind dispatcher `--execute-preflight`; waiting-market state does not call it |
| Repo-local MPG pilot handoff | Present in `docs/current/strategy-group-handoffs/MPG-001/handoff.json` |
| Owner-readable live-facts readiness state | Present in `scripts/build_strategy_group_live_facts_readiness_packet.py` |
| Candidate prerequisite derivation | Present in `scripts/collect_strategy_group_live_facts_readonly.py` |
| Real submit chat-confirmation blocker removal | Present in `src/domain/runtime_official_submit_handoff.py` and related handoff scripts |

## Tokyo Deployment

Deployment status:

| Field | Value |
| --- | --- |
| Previous deployed head | `a9b065836b3dd8606f42039fdfe14846c0646376` |
| Deployed head | `09791efe0a13c460a8c4ab9940e5d81f0dbb15a9` |
| Deploy apply status | `applied` |
| Commands executed | `16` |
| Postdeploy acceptance | `postdeploy_acceptance_ready` |
| Backend service | `active` |
| Watcher timer | `active` |
| Migration count | `84` |
| Latest migration | `2026-06-11-084_create_runtime_post_submit_budget_settlements.py` |

Deploy effects:

| Effect | Value |
| --- | --- |
| Remote files modified | `true` |
| Database backup created | `true` |
| Migrations run | `true` |
| Services restarted | `true` |
| Exchange called | `false` |
| ExecutionIntent created | `false` |
| Order created | `false` |
| OrderLifecycle called | `false` |
| Secrets read by Codex | `false` |

Local deploy evidence:

```text
output/strategygroup-runtime-pilot/deploy-9316dc1e/git-deploy-apply-report.json
output/strategygroup-runtime-pilot/deploy-9316dc1e/postdeploy-acceptance-packet.json
output/strategygroup-runtime-pilot/deploy-a9b06583/git-deploy-apply-report.json
output/strategygroup-runtime-pilot/deploy-a9b06583/postdeploy-acceptance-packet.json
output/strategygroup-runtime-pilot/deploy-09791efe/git-deploy-dry-run.json
output/strategygroup-runtime-pilot/deploy-09791efe/git-owner-deploy-packet.stdout.json
output/strategygroup-runtime-pilot/deploy-09791efe/git-deploy-apply-report.json
output/strategygroup-runtime-pilot/deploy-09791efe/postdeploy-verify.json
output/strategygroup-runtime-pilot/deploy-09791efe/postdeploy-acceptance-packet.json
```

## Watcher / Resume Dispatcher

Systemd update:

| Unit | Current state |
| --- | --- |
| `brc-runtime-signal-watcher.timer` | `active` |
| `brc-runtime-signal-watcher.service` | `Result=success`, `ExecMainStatus=0` on manual postdeploy tick after `09791efe` deploy |
| `40-resume-dispatcher.conf` | Installed and daemon-reloaded |

The watcher now runs this post step after the readiness pack:

```text
scripts/runtime_signal_watcher_resume_dispatcher.py
-> /home/ubuntu/brc-deploy/reports/runtime-signal-watcher/resume-dispatch-packet.json
--execute-preflight
```

Latest dispatch packet:

| Field | Value |
| --- | --- |
| Path | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/resume-dispatch-packet.json` |
| Status | `waiting_for_market` |
| Blocker class | `waiting_for_market` |
| Dispatch action | `continue_watcher_observation` |
| Dispatch status | `no_action_continue_observation` |
| Command plan | `null` |
| Selected runtimes | `strategy-runtime-93353f4cf30e`, `strategy-runtime-579e407cc03a`, `strategy-runtime-3a25a46a535f` |

Latest dispatch safety invariants:

| Invariant | Value |
| --- | --- |
| Dispatcher only | `true` |
| Places order | `false` |
| Calls OrderLifecycle | `false` |
| Exchange write called | `false` |
| Mutates PG | `false` |
| Runtime budget mutated | `false` |
| Withdrawal / transfer created | `false` |
| Official Operation Layer submit called | `false` |

When `post-signal-resume-pack.json` reaches
`ready_for_action_time_final_gate`, the dispatcher will require:

- `signal_input_json`;
- `shadow_candidate_id`;
- `prepared_authorization_id`;
- allowed auto action `run_official_action_time_final_gate_preflight`;
- no unsafe effect flags.

It will then emit an official GET command plan for:

```text
/api/trading-console/runtime-execution-controlled-submit-preflights/authorizations/{prepared_authorization_id}
```

With `--execute-preflight`, the dispatcher calls the official GET endpoint only
when the resume pack is `ready_for_action_time_final_gate`. If the preflight
passes, the dispatch packet moves to `finalgate_ready`, exits successfully, and
exposes the next checkpoint as `prepare_official_operation_layer_submit` with
the official endpoint:

```text
/api/trading-console/runtime-execution-first-real-submit-actions/authorizations/{prepared_authorization_id}
```

The plan requires concrete evidence ids for trusted submit facts, idempotency,
attempt outcome policy, protection failure policy, local registration,
Owner/runtime grant, OrderLifecycle submit enablement, exchange submit adapter
enablement, exchange submit action authorization, and deployment readiness
before the official real gateway action may run.

If the preflight blocks, it writes Owner-readable `blocked_at`, `blocked_reason`,
`next_recover_condition`, `automatic_recovery_action`, and `downgrade_mode`.
Waiting-market packets do not call the endpoint.

The dispatcher still does not call Operation Layer or submit an order by
default. It records the official next checkpoint so later automation can
continue only after the evidence ids are present and the official endpoint path
is used.

## StrategyGroup Pilot Handoff

The deployed release now contains a repo-local MPG pilot handoff:

```text
docs/current/strategy-group-handoffs/MPG-001/handoff.json
```

Current pilot scope:

| Field | Value |
| --- | --- |
| StrategyGroup | `MPG-001` |
| Mode | `armed_observation` |
| Risk profile | `tiny` |
| Leverage | `1x` |
| Max active positions | `1` |
| Pilot symbols | `COINUSDT`, `INTCUSDT`, `MSTRUSDT` |

Tokyo can now build:

```text
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-handoff-intake-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-live-facts.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-live-facts-readiness.json
```

## Live-Readonly Facts

Postdeploy account-wide signed GET-only facts:

| Fact | Value |
| --- | --- |
| Status | `ready` |
| Account can trade | `true` |
| Assets count | `11` |
| Pilot supported symbols | `3` |
| Pilot exchange rules | `COINUSDT`, `INTCUSDT`, `MSTRUSDT` all `TRADING` |
| Active positions | `0` |
| Open orders | `0` |
| Tiny budget prerequisite | `available_for_candidate_specific_reservation` |
| Protection prerequisite | `ready_for_candidate_specific_plan` |
| Next-attempt gate | `ready_for_strategy_signal` |
| Signed GET only | `true` |
| Exchange write called | `false` |
| Order created | `false` |
| OrderLifecycle called | `false` |
| Withdrawal / transfer created | `false` |
| Secrets printed | `false` |

## Current State

The system is deployed, the watcher is running, the dispatch packet is generated
automatically after watcher ticks, and the account is flat with no open orders.

Current product state:

```text
observing
-> waiting_for_market
-> no fresh strategy signal
-> continue_watcher_observation
```

Current live-facts readiness:

```text
strategy_group_live_facts_ready_for_armed_observation
-> can_continue_observation=true
-> can_prepare_fresh_candidate=true
-> blocked_at=none
-> blocked_reason=none
-> next_recover_condition=fresh_strategy_signal_arrives
-> automatic_recovery_action=continue_watcher_observation
```

## Not Yet Reached

The following stages remain unreached because no fresh signal is present:

- fresh candidate preparation;
- runtime grant / fresh authorization evidence;
- action-time FinalGate pass;
- official Operation Layer gateway action;
- post-submit finalize / reconciliation / budget settlement.

## Standing Authorization Cleanup

The old `owner_real_submit_action_confirmation_missing` blocker is no longer a
valid blocker for in-boundary `real_gateway_action` handoff during this
development-stage pilot. `RuntimeOfficialSubmitHandoff` now records standing
authorization metadata and produces
`owner_confirmed_for_first_real_submit_action=true` for real gateway handoff
plans after readiness passes.

This does not allow:

- FinalGate bypass;
- Operation Layer bypass;
- missing evidence ids;
- stale facts;
- missing protection;
- duplicate submit risk;
- unauditable exchange write;
- withdrawal or transfer.

## Verification

Local verification:

```text
python3 -m py_compile scripts/runtime_signal_watcher_resume_dispatcher.py scripts/build_runtime_signal_watcher_readiness_pack.py src/application/runtime_execution_intent_adapter_service.py src/interfaces/api_trading_console.py scripts/build_strategy_group_handoff_intake_packet.py scripts/collect_strategy_group_live_facts_readonly.py scripts/build_strategy_group_live_facts_readiness_packet.py
/opt/homebrew/bin/pytest tests/unit/test_collect_strategy_group_live_facts_readonly.py tests/unit/test_strategy_group_live_facts_readiness_packet.py tests/unit/test_runtime_signal_watcher_resume_dispatcher.py tests/unit/test_runtime_signal_watcher_tick.py tests/unit/test_strategygroup_runtime_pilot_status.py tests/unit/test_trading_console_readmodels.py tests/unit/test_tokyo_runtime_governance_postdeploy_verify.py tests/unit/test_tokyo_runtime_governance_postdeploy_acceptance_packet.py tests/unit/test_tokyo_runtime_governance_readonly_probe.py tests/unit/test_tokyo_runtime_governance_git_deploy.py -q
git diff --check
```

Result:

```text
115 passed
```

Latest focused local verification after the standing-authorization handoff and
dispatcher next-checkpoint cleanup:

```text
/opt/homebrew/bin/pytest tests/unit/test_runtime_official_submit_handoff.py tests/unit/test_runtime_official_submit_handoff_service_api.py tests/unit/test_runtime_official_submit_handoff_from_readiness.py tests/unit/test_runtime_official_submit_handoff_api_flow.py tests/unit/test_runtime_signal_watcher_resume_dispatcher.py tests/unit/test_runtime_fresh_signal_readiness_bridge.py tests/unit/test_runtime_full_next_attempt_submit_cycle.py tests/unit/test_runtime_cycle_executable_submit_handoff.py -q
git diff --check
```

Result:

```text
43 passed
```

Tokyo verification:

```text
deploy_apply=applied
postdeploy_acceptance=postdeploy_acceptance_ready
current_release=brc-runtime-governance-09791efe-20260615-standing-auth-handoff
resume_dispatch_status=waiting_for_market
account_can_trade=true
strategy_group_intake=ready_for_main_control_intake
live_facts_readiness=strategy_group_live_facts_ready_for_armed_observation
active_positions=0
open_orders=0
budget=available_for_candidate_specific_reservation
protection=ready_for_candidate_specific_plan
next_attempt_gate=ready_for_strategy_signal
```
