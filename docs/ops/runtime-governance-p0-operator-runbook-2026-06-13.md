# Runtime Governance P0 Operator Runbook - 2026-06-13

## Purpose

This runbook operationalizes the post-refactor P0 runtime loop. It turns the
current live runtime state into an auditable operator decision packet before
any fresh strategy-driven attempt.

## Authority And Boundaries

Authoritative inputs, in order:

1. Owner decisions recorded in the current thread.
2. Current tracked code and git status.
3. `docs/canon/*`, especially `PROJECT_BASELINE_CURRENT.md`,
   `BRC_TARGET_SEMANTICS.md`, `STRATEGY_RUNTIME_GUIDE.md`, and
   `RUNTIME_SAFETY_BOUNDARY.md`.
4. Current read-only Tokyo reports.
5. Historical `docs/ops/*` only when no canon file supersedes them.

Hard boundaries for this runbook:

- It does not authorize withdrawal or transfer.
- It does not bypass FinalGate, Operation Layer, idempotency, protection,
  reconciliation, or scoped action evidence.
- It does not replay old authorization as the basis for a new attempt.
- It does not create orders, execution intents, shadow candidates, runtime
  budget mutations, or OrderLifecycle calls.
- Real exchange submission remains outside this P0-A packet and can only happen
  through the official auditable runtime path when the action-time gates pass.

## Operator Inputs

Required read-only fact groups:

| Fact group | Required source | Blocking when missing |
|---|---|---:|
| Runtime identity | Runtime instance ID and deploy context | yes |
| Account facts | Read-only account facts report | yes |
| Position facts | Live position monitor report | yes |
| Open-order facts | Live position monitor report | yes |
| Protection facts | Live position monitor report | yes |
| Budget facts | Monitor, post-submit finalize, or gate report | yes |
| Next-attempt gate | Release, gate-classification, or finalize report | yes |

## Standard Procedure

1. Verify branch and worktree.

   ```bash
   git status --short --branch
   git rev-parse HEAD
   ```

2. Verify Tokyo deployment state with the read-only probe.

   ```bash
   python3 scripts/probe_tokyo_runtime_governance_readonly.py \
     --json \
     --expected-current-head 80da4d670a31ca313ef667d97460d7b6c806c085 \
     --expected-migration-count 84 \
     --expected-latest-migration 2026-06-11-084_create_runtime_post_submit_budget_settlements.py
   ```

3. Collect current read-only reports from Tokyo.

   Current known report families:

   | Report family | Example source |
   |---|---|
   | Deployment health | `probe_tokyo_runtime_governance_readonly.py` |
   | Account facts | `rtf052-action-time-bridge/.../account-facts-readonly.json` |
   | Active runtime monitor | `rtf099-live-refresh-probe/active-monitor.json` |
   | Live position monitor | `rtf099-live-refresh-probe/bnb-live-position-monitor.json` |
   | Lifecycle readiness | `rtf099-live-refresh-probe/bnb-position-lifecycle-exit-readiness.json` |
   | Continuation refresh | `rtf099-live-refresh-probe/live-continuation-refresh-flow.json` |
   | Continuation selector | `rtf099-live-refresh-probe/live-continuation-selector.json` |

4. Build the operator live-fact packet.

   ```bash
   python3 scripts/build_runtime_operator_live_fact_packet.py \
     --runtime-instance-id strategy-runtime-e6138ad7c88f \
     --account-facts-json /tmp/brc-p0a-account-facts-readonly.json \
     --live-position-monitor-json /tmp/brc-p0a-bnb-live-position-monitor.json \
     --active-position-resolution-json /tmp/brc-p0a-bnb-position-lifecycle-exit-readiness.json \
     --next-attempt-release-json /tmp/brc-p0a-live-continuation-refresh-flow.json \
     --observation-operator-json /tmp/brc-p0a-live-continuation-selector.json \
     --deployed-head 80da4d670a31ca313ef667d97460d7b6c806c085 \
     --release-name brc-runtime-governance-80da4d67-20260613Trtf107-cleanup-policy \
     --remote-report-path /home/ubuntu/brc-deploy/reports/brc-runtime-governance-b1009096-20260613Trtf099-refresh-flow/rtf099-live-refresh-probe \
     --output-json /tmp/brc-p0a-operator-live-fact-packet.json
   ```

5. Classify the next-attempt gate.

| Packet status | Operator meaning | Allowed action |
|---|---|---|
| `waiting_for_position_resolution` | Current position or protection still occupies the runtime slot | Continue read-only monitoring, or process a separately authorized reduce-only close |
| `ready_for_strategy_signal` | Runtime is flat enough for fresh signal observation | Start fresh strategy signal observation only |
| `incomplete_live_fact_packet` | At least one required fact group is missing | Collect missing read-only facts |
| `blocked_forbidden_effect` | A source report claims an order/exchange write/runtime mutation happened | Stop and review evidence |
| `blocked` | Gate exists but is not ready | Resolve current blockers without forcing an attempt |

## Fresh Attempt Rule

A new attempt must start from:

1. Fresh strategy signal.
2. Fresh candidate / shadow candidate path.
3. Fresh runtime grant or authorization evidence.
4. Fresh FinalGate and action-time fact revalidation.

Old first-real-submit authorization, old prepared authorization, and old
readiness evidence may be cited as history only. They must not be replayed as
current execution authority.

## Side Worker Boundary

Side workers may do non-core tasks only:

- Runbook drafting.
- UI status panel work.
- Read-only fact packet shaping.
- Focused tests.
- Archive namespace moves for P2 preservation.

Core execution and risk files remain controlled by the main Codex window unless
a bounded task card explicitly allows a worker to touch them.

## Current Runbook Status

As of 2026-06-13, this runbook has been exercised once against Tokyo read-only
reports and produced `waiting_for_position_resolution`. See
`docs/ops/runtime-governance-p0-live-fact-validation-2026-06-13.md`.
