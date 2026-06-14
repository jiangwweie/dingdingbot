# Runtime Next Safe Checkpoint - c71d8a73 - 2026-06-14

Status: LOCAL_CHECKPOINT_READY
Branch: `codex/runtime-signal-watcher-feishu`

## Known Facts

### Tokyo Deployment

| Fact | Value |
| --- | --- |
| Verified Tokyo head | `c71d8a73c190f6c3e2bc5e734aed6343d687af29` |
| Current release realpath | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c71d8a73-20260613-next-free-live-path` |
| Postdeploy verifier status | `postdeploy_acceptance_passed` |
| Migration count | `84` |
| Latest migration | `2026-06-11-084_create_runtime_post_submit_budget_settlements.py` |
| Health endpoint | `status=ok`, `runtime_bound=true`, `live_ready=false` |
| Warning | `release_identity_from_manifest_without_git_status` |

Evidence command:

```bash
python3 scripts/verify_tokyo_runtime_governance_postdeploy.py \
  --json \
  --expected-current-head c71d8a73c190f6c3e2bc5e734aed6343d687af29 \
  --expected-migration-count 84 \
  --expected-latest-migration 2026-06-11-084_create_runtime_post_submit_budget_settlements.py \
  --connect-timeout-seconds 10
```

Local evidence output:

```text
output/tokyo-postdeploy-verify-c71d8a73.json
```

### Tokyo Live Exchange Facts

Read-only signed `GET` probes were run from the Tokyo environment against the
live Binance USD-M Futures account. They did not use exchange write methods,
OrderLifecycle, ExecutionIntent creation, runtime budget mutation, withdrawal,
or transfer.

| Fact Area | Result |
| --- | --- |
| StrategyGroup exchange rules | `ready` |
| StrategyGroup account facts | `fresh`, `can_trade=true`, `assets_count=11` |
| StrategyGroup active positions | `active_count=0`, `status=no_active_position` |
| StrategyGroup open orders | `open_order_count=0`, `status=no_open_orders` |
| Account-wide active positions | `active_count=0`, `status=no_active_position` |
| Account-wide open orders | `open_order_count=0`, `status=no_open_orders` |

Local evidence outputs:

```text
output/tokyo-strategy-group-live-facts-readonly.json
output/tokyo-account-wide-position-open-order-readonly.json
```

### StrategyGroup Readiness

The first StrategyGroup handoff batch is now exchange-fact observable, but not
candidate-prepare ready.

| Metric | Count |
| --- | ---: |
| Strategy groups evaluated | `5` |
| Observe-ready strategy groups | `5` |
| Armed candidate-prepare ready groups | `0` |
| Candidate-prepare blocked groups | `5` |

Remaining blocker classes in the StrategyGroup readiness packet:

```text
budget:missing
next_attempt_gate:missing
protection:missing
```

Local evidence output:

```text
output/tokyo-strategy-group-live-facts-readiness-packet.json
```

### Runtime Signal Watcher

Tokyo watcher evidence now reports two runtime signals ready for non-executing
prepare review.

| Runtime | Strategy | Symbol | Side | Signal Status |
| --- | --- | --- | --- | --- |
| `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short` | `RBR-001-v0` | `ADA/USDT:USDT` | `short` | `ready_for_prepare` |
| `strategy-runtime-e6138ad7c88f` | `CPM-001-v0` | `BNB/USDT:USDT` | `long` | `ready_for_prepare` |
| `strategy-runtime-95655873b76c` | `BTPC-001-v0` | `AVAX/USDT:USDT` | `short` | `waiting_for_signal` |

Watcher packet summary:

| Packet | Status |
| --- | --- |
| `deployment-readiness-packet.json` | `ready` |
| `wakeup-packet.json` | `runtime_signal_ready_for_non_executing_prepare` |
| `operator-packet.json` | `runtime_signal_attention` |
| `post-signal-resume-pack.json` | `ready_for_steps_5_8`, `can_continue_steps_5_8=true` |
| `status-packet.json` | `attention` |

Safety invariants remain non-executing:

```text
exchange_write_called=false
order_created=false
order_lifecycle_called=false
runtime_budget_mutated=false
withdrawal_or_transfer_created=false
prepared_authorization_id=null
shadow_candidate_id=null
```

## Analysis

### Current Safe Checkpoint

The next safe checkpoint has moved from "wait for any signal" to
"review ready runtime signal and create non-executing prepare records through
the existing supervisor path after operator review".

This is not an action-time submit checkpoint. It does not authorize:

```text
executable ExecutionIntent
OrderLifecycle submit
exchange order placement
withdrawal or transfer
Operation Layer bypass
FinalGate bypass
```

### Local Fix Applied

`scripts/runtime_active_observation_followup.py` treated
`ready_for_prepare_records` as a normal follow-up packet status, but the CLI
`main()` returned exit code `2` for that status. This caused
`runtime_active_observation_supervisor.py` to record:

```text
followup_command_failed:2
```

even when the child packet had reached a legitimate operator-review stop.

The local fix makes `ready_for_prepare_records` return exit code `0` and adds a
unit test for the CLI behavior. This fix does not create prepare records by
itself and does not modify the explicit `--allow-prepare-records` guard.

### Remaining Boundaries Before Real Submit

The following stages still remain before any auditable real submit:

| Stage | Current State |
| --- | --- |
| Ready runtime signal | `2` signals ready for prepare review |
| Non-executing prepare records | Not created in this checkpoint |
| Shadow candidate / authorization evidence | Not created in this checkpoint |
| FinalGate | Not reached |
| Operation Layer gateway action | Not reached |
| Post-submit finalize / reconciliation / budget settlement | Not reached |

## Commands Verified Locally

```bash
/opt/homebrew/bin/pytest \
  tests/unit/test_runtime_active_observation_followup.py \
  tests/unit/test_runtime_active_observation_supervisor.py \
  tests/unit/test_runtime_signal_watcher_tick.py \
  tests/unit/test_runtime_signal_watcher_readiness_pack.py \
  tests/unit/test_collect_strategy_group_live_facts_readonly.py \
  tests/unit/test_strategy_group_live_facts_readiness_packet.py \
  -q
```

Result:

```text
36 passed
```

## Next Resume Point

Resume from the existing watcher path only after the local fix is committed and
reviewed:

```text
ready runtime signal
-> non-executing prepare records with --allow-prepare-records
-> shadow candidate / fresh authorization evidence review
-> action-time FinalGate
-> official Operation Layer only
-> post-submit finalize / reconciliation / budget settlement
```

Hard stop remains in force for any forbidden effect, stale evidence, active
position/open-order conflict, missing protection, missing budget, failed
FinalGate, or Operation Layer bypass.

## Continuation Refresh - 2026-06-14 10:17 UTC

### Refreshed Tokyo Watcher Facts

Tokyo still runs the c71d8a73 release:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c71d8a73-20260613-next-free-live-path
```

The latest watcher tick completed successfully at the systemd level. The
runtime packets remain at the non-executing prepare-review stop:

| Packet | Status | Important Fields |
| --- | --- | --- |
| `loop-packet.json` | `ready_for_prepare` | `prepare_records_created=false`, `shadow_candidate_created=false`, `submit_authorization_created=false` |
| `followup-packet.json` | `ready_for_prepare_records` | `blockers=[]`, `next_step=review_ready_signal_then_continue_prepare_record_path` |
| `supervisor-packet.json` | `supervisor_blocked` | `blockers=[followup_command_failed:2]` |
| `status-packet.json` | `attention` | `loop_status=ready_for_prepare`, `followup_status=ready_for_prepare_records` |

The `followup_command_failed:2` blocker is still present on Tokyo because
Tokyo has not deployed local commit `2247280b`. The child follow-up packet is
already semantically ready for prepare review; the remote supervisor wrapper
still treats that packet as a process failure because c71d8a73 lacks the local
exit-code fix.

### Refreshed Account-Wide Live Facts

Read-only signed `GET` facts were refreshed from Tokyo using the live readonly
environment key names `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET`.

| Fact Area | Result |
| --- | --- |
| Active positions | `active_count=0`, `status=no_active_position` |
| Open orders | `open_order_count=0`, `status=no_open_orders` |
| Endpoint errors | `{}` |
| Safety | `signed_get_only=true`, no exchange write, no OrderLifecycle, no budget mutation |

Local evidence output:

```text
output/tokyo-account-wide-position-open-order-readonly-refresh-20260614.json
```

### Deploy Decision Packet For Local Fix

A non-mutating git owner deploy decision packet was generated for local commit
`2247280b`:

```text
output/tokyo-owner-deploy-decision-2247280b.json
```

The packet is intentionally blocked:

| Field | Value |
| --- | --- |
| Candidate head | `2247280b` |
| Remote branch head | `cb25637d72e8cd2ccbb0fb6197eb8b2d11f14908` |
| Release ready for packaging | `true` |
| Tokyo readonly probe ready | `true` |
| Ready for owner git deploy decision | `false` |
| Blockers | `git_deploy_plan_not_ready`, `git_deploy_executor_dry_run_not_ready` |

This means the deploy system correctly refuses to deploy the local fix until
the target commit is available as the selected remote branch head and the owner
deploy packet becomes ready. The owner deploy confirmation phrase would
authorize only git fetch/export, remote PG backup, alembic migration, backend
restart, and postdeploy read-only smoke. It does not authorize real runtime
submit, exchange order placement, runtime live execution enablement, withdrawal,
or transfer.

### Current Safe Next Step

The safest forward path is:

```text
push reviewed branch head
-> regenerate owner git deploy decision packet for the pushed head
-> apply deploy only through the owner-gated git deploy executor
-> rerun postdeploy verifier
-> let watcher refresh without followup_command_failed:2
-> continue to non-executing prepare records
```

Manual continuation on c71d8a73 by ignoring `followup_command_failed:2` should
not be used as the mainline path, because it would preserve an avoidable audit
artifact exactly at the ready-signal to prepare-record transition.

## Codex Automation - Monitor Wakeup

Automation created in the Codex app:

| Field | Value |
| --- | --- |
| Automation id | `tokyo-runtime-monitor-wakeup` |
| Type | thread heartbeat |
| Interval | every 15 minutes |
| Status | `ACTIVE` |
| Workspace expectation | `/Users/jiangwei/Documents/final` |

The automation wakes this same controller thread to inspect only read-only
evidence first:

```text
git status
Tokyo current release path/head
runtime-signal-watcher JSON packets
post-signal-resume-pack.json
supervisor/loop/followup packets
signed GET-only account-wide position/open-order facts
```

Allowed automation behavior:

```text
detect fresh ready signals
detect whether followup_command_failed:2 is still only the c71d8a73 exit-code artifact
regenerate or update owner-gated deploy packet
continue to the next safe checkpoint when official packets prove readiness
```

Forbidden automation behavior:

```text
FinalGate bypass
Operation Layer bypass
exchange order placement without official action-time gate readiness
withdrawal or transfer
secret / live profile / credential / order-sizing default changes
manual continuation that ignores official blocker packets
```

The automation is a wakeup/checkpoint mechanism, not an independent trading
actor. It must keep using the current goal chain and the official auditable
runtime path.

## Deploy Packet Refresh - Full SHA

The earlier `cf48bfa0` deploy decision packet was blocked because the
short SHA was passed as `--target-commit`, while the git deploy planner compares
against the full remote branch head.

The packet was regenerated with the full remote SHA:

```text
cf48bfa07abf2f8b6655aae2fa19509c77c939d3
```

Local evidence output:

```text
output/tokyo-owner-deploy-decision-cf48bfa0-fullsha.json
```

### Deploy Decision Status

| Field | Value |
| --- | --- |
| Status | `ready_for_owner_git_deploy_decision` |
| Candidate head | `cf48bfa07abf2f8b6655aae2fa19509c77c939d3` |
| Remote ref head | `cf48bfa07abf2f8b6655aae2fa19509c77c939d3` |
| Release name | `brc-runtime-governance-cf48bfa0-20260614-prepare-review-exit` |
| Blockers | `[]` |
| Forbidden effects | `[]` |
| Git deploy plan ready | `true` |
| Git deploy dry-run ready | `true` |
| Tokyo readonly probe ready | `true` |

Safety invariants:

```text
deploy_apply_requested=false
remote_files_modified=false
services_restarted=false
migrations_run=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
exchange_called=false
withdrawal_or_transfer_created=false
```

### Latest Read-Only Tokyo Facts

Tokyo still runs:

```text
/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c71d8a73-20260613-next-free-live-path
```

Latest watcher packets remain consistent with the same blocker:

| Packet | Status | Important Fields |
| --- | --- | --- |
| `loop-packet.json` | `ready_for_prepare` | `prepare_records_created=false`, `shadow_candidate_created=false`, `submit_authorization_created=false` |
| `followup-packet.json` | `ready_for_prepare_records` | `blockers=[]`, `next_step=review_ready_signal_then_continue_prepare_record_path` |
| `supervisor-packet.json` | `supervisor_blocked` | `blockers=[followup_command_failed:2]` |
| `post-signal-resume-pack.json` | `ready_for_steps_5_8` | `can_continue_steps_5_8=true`, still carries old wrapper blocker |

Ready runtime signals remain:

| Runtime | Strategy | Symbol | Side | Status |
| --- | --- | --- | --- | --- |
| `strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short` | `RBR-001-v0` | `ADA/USDT:USDT` | `short` | `ready_for_prepare` |
| `strategy-runtime-e6138ad7c88f` | `CPM-001-v0` | `BNB/USDT:USDT` | `long` | `ready_for_prepare` |
| `strategy-runtime-95655873b76c` | `BTPC-001-v0` | `AVAX/USDT:USDT` | `short` | `waiting_for_signal` |

Latest signed `GET` account-wide refresh:

| Fact Area | Result |
| --- | --- |
| Active positions | `active_count=0`, `status=no_active_position` |
| Open orders | `open_order_count=0`, `status=no_open_orders` |
| Endpoint errors | `{}` |
| Safety | `signed_get_only=true`, no exchange write, no OrderLifecycle, no budget mutation |

Local evidence output:

```text
output/tokyo-account-wide-position-open-order-readonly-refresh-20260614-latest.json
```

### Current Boundary

`cf48bfa0` is ready for the owner-gated git deploy decision packet. Applying
that deploy is still a separate deploy-executor action and must use the
official deploy confirmation phrase and deploy packet path. It must not be
treated as real runtime submit authorization.

Until Tokyo is moved from c71d8a73 to the reviewed candidate, the mainline
should not ignore `followup_command_failed:2` to create prepare records.

## Deploy Packet Refresh - Current Remote Head

After the automation/checkpoint documentation commits were pushed, the current
remote branch head became:

```text
5ceedb0672a2bcab4851f3dff3181c5060e4efff
```

The owner-gated deploy decision packet was regenerated for that exact remote
head.

Local evidence output:

```text
output/tokyo-owner-deploy-decision-5ceedb06-fullsha.json
```

| Field | Value |
| --- | --- |
| Status | `ready_for_owner_git_deploy_decision` |
| Candidate head | `5ceedb0672a2bcab4851f3dff3181c5060e4efff` |
| Remote ref head | `5ceedb0672a2bcab4851f3dff3181c5060e4efff` |
| Release name | `brc-runtime-governance-5ceedb06-20260614-prepare-review-exit` |
| Blockers | `[]` |
| Forbidden effects | `[]` |
| Git deploy plan ready | `true` |
| Git deploy dry-run ready | `true` |
| Tokyo readonly probe ready | `true` |

This packet proved that the deployment path becomes ready when the target
commit exactly matches the remote branch head. Any later documentation-only
commit advances the remote branch head and therefore requires regenerating the
deploy decision packet for the new full SHA before deploy apply. Deploy apply
remains separate from packet-build and must still go through the owner-gated
git deploy executor with the generated packet path and confirmation phrase.
