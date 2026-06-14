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
