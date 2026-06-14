# StrategyGroup Runtime Pilot Current Checkpoint

Date: 2026-06-15
Status: CURRENT_CHECKPOINT

## Scope

This checkpoint records the active StrategyGroup runtime pilot state after
selective watch-branch intake, watcher resume dispatcher implementation, Tokyo
deploy, and postdeploy live-readonly verification.

Workspace and branch:

| Field | Value |
| --- | --- |
| Workspace | `/Users/jiangwei/Documents/final` |
| Branch | `codex/strategygroup-runtime-pilot` |
| Current code head | `0329f3922aace5d687d84e89006730396601d2f8` |
| Current release | `brc-runtime-governance-0329f392-20260615-resume-dispatcher` |
| Tokyo release path | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-0329f392-20260615-resume-dispatcher` |

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

## Tokyo Deployment

Deployment status:

| Field | Value |
| --- | --- |
| Previous deployed head | `bbdbb61ad4b7bab77c99cc5163a6ae80963abd8d` |
| Deployed head | `0329f3922aace5d687d84e89006730396601d2f8` |
| Deploy apply status | `applied` |
| Commands executed | `16` |
| Postdeploy acceptance | `postdeploy_acceptance_passed` |
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
output/strategygroup-runtime-pilot/deploy-0329f392/git-deploy-dry-run.json
output/strategygroup-runtime-pilot/deploy-0329f392/git-deploy-apply-report.json
output/strategygroup-runtime-pilot/deploy-0329f392/postdeploy-acceptance.json
```

## Watcher / Resume Dispatcher

Systemd update:

| Unit | Current state |
| --- | --- |
| `brc-runtime-signal-watcher.timer` | `active` |
| `brc-runtime-signal-watcher.service` | `Result=success`, `ExecMainStatus=0` on manual postdeploy tick |
| `40-resume-dispatcher.conf` | Installed and daemon-reloaded |

The watcher now runs this post step after the readiness pack:

```text
scripts/runtime_signal_watcher_resume_dispatcher.py
-> /home/ubuntu/brc-deploy/reports/runtime-signal-watcher/resume-dispatch-packet.json
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

It will still not call Operation Layer or submit an order.

## Live-Readonly Facts

Postdeploy account-wide signed GET-only facts:

| Fact | Value |
| --- | --- |
| Status | `ready` |
| Account can trade | `true` |
| Assets count | `11` |
| Active positions | `0` |
| Open orders | `0` |
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

## Not Yet Reached

The following stages remain unreached because no fresh signal is present:

- RequiredFacts readiness for a fresh signal;
- fresh candidate preparation;
- runtime grant / fresh authorization evidence;
- action-time FinalGate pass;
- official Operation Layer gateway action;
- post-submit finalize / reconciliation / budget settlement.

## Verification

Local verification:

```text
python3 -m py_compile scripts/runtime_signal_watcher_resume_dispatcher.py scripts/build_runtime_signal_watcher_readiness_pack.py src/application/runtime_execution_intent_adapter_service.py src/interfaces/api_trading_console.py
/opt/homebrew/bin/pytest tests/unit/test_runtime_signal_watcher_resume_dispatcher.py tests/unit/test_runtime_signal_watcher_readiness_pack.py tests/unit/test_tokyo_runtime_governance_deploy_executor.py tests/unit/test_tokyo_runtime_governance_git_deploy.py tests/unit/test_strategygroup_runtime_pilot_overlay_docs.py -q
git diff --check
```

Result:

```text
33 passed
```

Tokyo verification:

```text
deploy_apply=applied
postdeploy_acceptance=postdeploy_acceptance_passed
watcher_service_result=success
resume_dispatch_status=waiting_for_market
account_can_trade=true
active_positions=0
open_orders=0
```
