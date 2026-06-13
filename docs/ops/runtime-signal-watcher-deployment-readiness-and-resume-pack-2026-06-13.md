# Runtime Signal Watcher Deployment Readiness And Resume Pack - 2026-06-13

## Known Objective

This document is the handoff anchor for three scoped goals:

| Goal | Name | Status | Primary Artifact |
|---|---|---:|---|
| A | Signal Watcher Deployment Readiness | implemented | `deployment-readiness-packet.json` |
| B | Post-Signal Resume Pack | implemented | `post-signal-resume-pack.json` |
| C | Console Watcher Status | implemented | `GET /api/trading-console/runtime-signal-watcher-status` |

## Verified Deployment Facts

Current Tokyo facts verified on 2026-06-13:

| Fact | Value |
|---|---:|
| systemd timer | `brc-runtime-signal-watcher.timer` enabled and active |
| service user | `ubuntu:ubuntu` |
| active app path | `/home/ubuntu/brc-deploy/app/current` |
| watcher report dir | `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher` |
| Feishu env file | `/home/ubuntu/brc-deploy/env/runtime-signal-watcher.env` |
| Feishu env key | `FEISHU_WEBHOOK_URL=PRESENT` |
| first real notification | sent successfully, HTTP 200, Feishu `StatusCode=0` |
| duplicate suppression | verified with `duplicate_suppressed=true` on repeated event |

## Evidence Files

The watcher writes these files every tick:

```text
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/watcher-tick.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/wakeup-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/operator-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/status-packet.json
/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/notification-state.json
```

The readiness pack builder writes:

```text
deployment-readiness-packet.json
post-signal-resume-pack.json
```

`brc-runtime-signal-watcher.service` refreshes both packets after each successful
watcher tick via `ExecStartPost`.

## Current Runtime Observation State

Latest verified state before this handoff:

| Field | Value |
|---|---:|
| watcher status | `owner_attention_pending` |
| wakeup status | `operator_packet_needs_review` |
| operator status | `strategy_group_signal_review_available` |
| notification required | `true` |
| duplicate suppressed | `true` |
| exchange write called | `false` |
| order created | `false` |
| order lifecycle called | `false` |
| runtime budget mutated | `false` |

Current blockers remain signal-readiness blockers, not active-position blockers:

```text
strategy-runtime-rbr-001-rbr-001-v0-ada-usdt-usdt-short: strategy_signal_not_ready_for_shadow_candidate_prepare
strategy-runtime-e6138ad7c88f: strategy_signal_not_ready_for_shadow_candidate_prepare
strategy-runtime-95655873b76c: strategy_signal_not_ready_for_shadow_candidate_prepare
```

## Post-Signal Resume Boundary

The watcher is only allowed to resume the next phase when evidence reports one
of these wakeup statuses:

```text
runtime_signal_ready_for_non_executing_prepare
prepared_shadow_evidence_ready_for_owner_review
```

When the resume gate is ready, continue only through this chain:

1. fresh candidate
2. runtime grant
3. fresh authorization evidence
4. action-time FinalGate
5. official Operation Layer gateway action
6. post-submit finalize / reconciliation / budget settlement

## Hard Stops

Stop before any real submit if any of these appear:

| Stop | Meaning |
|---|---|
| missing watcher evidence | evidence packet cannot prove current watcher state |
| stale watcher evidence | watcher has not refreshed inside the configured freshness window |
| forbidden effect flag | watcher evidence reports order/exchange/budget mutation |
| active position or open order blocker | next attempt gate is not flat |
| FinalGate failure | action-time official preflight failed |
| Operation Layer bypass | proposed path is not the official auditable runtime path |

## Safety Boundary

Signal Watcher must remain non-executing.

It must not:

- place exchange orders;
- create executable `ExecutionIntent` records;
- call `OrderLifecycle` submit;
- mutate runtime budget or attempt counters;
- create withdrawal or transfer instructions;
- bypass FinalGate or Operation Layer.

## Console Surface

Console entry:

```text
GET /api/trading-console/runtime-signal-watcher-status
```

Frontend page:

```text
/watcher
```

The Console shows:

- deployment readiness;
- evidence file freshness;
- Feishu notification state;
- duplicate suppression state;
- resume gate for steps 5-8;
- no-action safety invariants.

The Console page is a read-model operating surface. It does not add submit,
cancel, flatten, transfer, withdrawal, or budget mutation controls.

## Rebuild Pack Command

Tokyo command:

```bash
cd /home/ubuntu/brc-deploy/app/current
/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python \
  scripts/build_runtime_signal_watcher_readiness_pack.py \
  --report-dir /home/ubuntu/brc-deploy/reports/runtime-signal-watcher \
  --output-dir /home/ubuntu/brc-deploy/reports/runtime-signal-watcher \
  --stale-after-seconds 180 \
  --label tokyo-runtime-signal-watcher
```

## Next Session Entry

When a new Feishu push arrives, inspect this order:

1. `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/wakeup-packet.json`
2. `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/operator-packet.json`
3. `/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/post-signal-resume-pack.json`
4. `GET /api/trading-console/runtime-signal-watcher-status`

Only continue steps 5-8 when `post-signal-resume-pack.json` reports:

```json
{
  "can_continue_steps_5_8": true
}
```
