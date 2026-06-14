# StrategyGroup Runtime Pilot Checkpoint - 71981a78 - 2026-06-14

Status: CURRENT_SAFE_CHECKPOINT

## Known Facts

### Branch And Version

| Field | Value |
| --- | --- |
| Workspace | `/Users/jiangwei/Documents/final` |
| Branch | `codex/strategygroup-runtime-pilot` |
| Remote branch | `origin/codex/strategygroup-runtime-pilot` |
| Current HEAD | `71981a78392abffc9cf19feda467a852e19a84ee` |
| Base program branch | `program/live-safe-v1` |
| Tokyo previous deployed head | `62bb43d33342d3276032b4c0ff45113c65e62323` |
| Tokyo deployed head after this checkpoint | `71981a78392abffc9cf19feda467a852e19a84ee` |

The current branch includes selected watcher / StrategyGroup P0 capabilities
from `codex/runtime-signal-watcher-feishu` and a merge parent for the deployed
watcher baseline `62bb43d3`. The large docs reset / history compression commits
from that side branch were not merged into this pilot branch.

### Current Constraint Overlay

The active Owner / agent constraint source is:

```text
docs/canon/STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md
```

That overlay says:

- deploy apply for the active pilot stage is standing-authorized when packet /
  manifest evidence passes;
- official in-boundary real order action is standing-authorized only when the
  official runtime / Operation Layer path and action-time FinalGate pass;
- old docs must not reintroduce per-deploy or per-order chat confirmation
  blockers;
- withdrawal, transfer, Operation Layer bypass, FinalGate bypass, unauditable
  exchange writes, stale facts as allow signals, missing protection, and
  duplicate-submit risk remain hard stops.

### Watcher Capabilities Brought Forward

The following watcher branch capabilities are now in the pilot branch:

| Capability | Status |
| --- | --- |
| Runtime signal watcher tick | Brought forward |
| Feishu env reuse for watcher notification | Brought forward |
| Dry-run notification behavior fix | Brought forward |
| Watcher systemd service / timer files | Brought forward |
| Watcher readiness / resume pack builder | Brought forward |
| Watcher status console page | Brought forward |
| StrategyGroup handoff intake packet | Brought forward |
| StrategyGroup live facts readiness packet | Brought forward |
| StrategyGroup read-only live facts collector | Brought forward |
| `ready_for_prepare_records` followup exit-code fix | Brought forward |

### Tokyo Deployment

| Field | Value |
| --- | --- |
| Release name | `brc-runtime-governance-71981a78-20260614-strategygroup-runtime-pilot` |
| Current realpath | `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-71981a78-20260614-strategygroup-runtime-pilot` |
| Deploy executor status | `applied` |
| Commands planned / executed | `16 / 16` |
| Migration count | `84` |
| Latest migration | `2026-06-11-084_create_runtime_post_submit_budget_settlements.py` |
| Health | `status=ok`, `runtime_bound=true`, `live_ready=false` |
| Postdeploy acceptance | `postdeploy_acceptance_passed` |

Deploy effects:

| Effect | Value |
| --- | --- |
| Remote files modified | `true` |
| Database backup created | `true` |
| Migrations run | `true` |
| Services restarted | `true` |
| ExecutionIntent created | `false` |
| Order created | `false` |
| OrderLifecycle called | `false` |
| Exchange called | `false` |
| Secrets read by Codex | `false` |

Local evidence files:

```text
output/strategygroup-runtime-pilot/tokyo-git-owner-deploy-packet-71981a78.json
output/strategygroup-runtime-pilot/tokyo-postdeploy-verify-71981a78.json
output/strategygroup-runtime-pilot/tokyo-readonly-probe-71981a78.json
```

### Watcher Postdeploy State

Tokyo watcher timer state:

| Unit | State |
| --- | --- |
| `brc-runtime-signal-watcher.timer` | `enabled`, `active` |
| `brc-runtime-signal-watcher.service` | `static`, `inactive` between timer runs |

Latest watcher report directory:

```text
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher
```

Latest packet summary after the 71981a78 deploy:

| Packet | Status | Notes |
| --- | --- | --- |
| `deployment-readiness-packet.json` | `ready` | Watcher deployment readiness passes |
| `loop-packet.json` | `waiting_for_signal` | No fresh ready signal in current tick |
| `followup-packet.json` | `observation_window_complete_no_signal` | No prepare records created |
| `supervisor-packet.json` | `supervisor_completed` | Old `followup_command_failed:2` is no longer present |
| `watcher-tick.json` | `owner_attention_pending` | Attention only because runtime signals are not candidate-prepare ready |
| `post-signal-resume-pack.json` | `operator_packet_needs_review` | Cannot continue steps 5-8 without fresh ready signal |

Current watcher blockers:

```text
strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short:strategy_signal_not_ready_for_shadow_candidate_prepare
strategy-runtime-e6138ad7c88f:strategy_signal_not_ready_for_shadow_candidate_prepare
strategy-runtime-95655873b76c:strategy_signal_not_ready_for_shadow_candidate_prepare
```

These are market / signal readiness blockers, not deploy or safety regressions.

### StrategyGroup Intake And Live Facts

StrategyGroup handoff intake:

| Metric | Value |
| --- | ---: |
| Strategy groups | `5` |
| Armed observation intake ready | `4` |
| Observe-only intake ready | `1` |
| Required fact rows | `140` |
| Supplements present | `6 / 6` |

Tokyo signed GET-only live facts:

| Fact Area | Value |
| --- | --- |
| Collector status | `ready` |
| Supported symbol count | `26` |
| Account | `fresh`, `can_trade=true`, `assets_count=11` |
| Active positions | `active_count=0`, `status=no_active_position` |
| Open orders | `open_order_count=0`, `status=no_open_orders` |
| Collector errors | `{}` |
| Exchange writes | `false` |
| OrderLifecycle calls | `false` |
| Runtime budget mutation | `false` |
| Withdrawal / transfer | `false` |

StrategyGroup live-facts readiness:

| Metric | Value |
| --- | ---: |
| Strategy groups | `5` |
| Observe ready | `5` |
| Armed candidate prepare ready | `0` |
| Blocked for candidate prepare | `5` |

Remaining candidate-prepare blockers for each group:

```text
protection:missing
budget:missing
next_attempt_gate:missing
```

The current operator path is:

```text
can_continue_observation=true
can_prepare_fresh_candidate=false
next_gate=wait_for_or_generate_fresh_strategy_signal
requires_action_time_final_gate_before_submit=true
requires_official_operation_layer=true
```

Local evidence files:

```text
output/strategygroup-runtime-pilot/strategy-group-handoff-intake-71981a78.json
output/strategygroup-runtime-pilot/strategy-group-live-facts-readonly-71981a78.tokyo.json
output/strategygroup-runtime-pilot/strategy-group-live-facts-readiness-71981a78.tokyo.json
output/strategygroup-runtime-pilot/watcher-readiness-71981a78/
```

## Analysis

### What Is Now Working

The server is deployed on the current StrategyGroup runtime pilot commit. The
backend is running, the watcher timer is active, Feishu-capable watcher code is
present, postdeploy verification passes, and live account facts prove the
account is flat with no open orders.

The system can now keep observing StrategyGroups. The current no-signal state
is a market wait, not a deploy blocker.

### What Is Still Not Reached

The system has not reached steps 5-8 because there is no fresh ready signal.

The following are not created at this checkpoint:

- non-executing prepare records;
- shadow candidate;
- runtime grant;
- submit authorization;
- action-time FinalGate packet;
- Operation Layer gateway action;
- post-submit finalize / reconciliation / budget settlement.

### Current Safe Resume Point

Resume from:

```text
watcher active
-> wait for fresh strategy signal
-> build candidate-specific protection / budget / next-attempt facts
-> non-executing prepare records
-> shadow candidate / runtime grant / authorization evidence
-> action-time FinalGate
-> official Operation Layer only
-> post-submit finalize / reconciliation / budget settlement
```

Hard stop remains in force for stale facts, active position / open-order
conflict, missing protection at action time, duplicate submit risk, FinalGate
failure, Operation Layer bypass, withdrawal, or transfer.
