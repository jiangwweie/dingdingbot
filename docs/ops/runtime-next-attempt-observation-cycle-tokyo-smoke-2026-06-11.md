# Runtime Next-attempt Observation Cycle Tokyo Smoke - 2026-06-11

## Scope

This note records deployment and Tokyo smoke verification for the non-executing
runtime next-attempt observation cycle.

The purpose was to prove that the deployed runtime can repeatedly perform:

```text
next-attempt gate
-> fresh strategy signal input
-> wait when signal is observe-only
```

without creating a shadow candidate, `ExecutionIntent`, order, or exchange
write.

## Deployment

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Deployed head: `c0710ae1e6a3061d247dd637e23d96318cf7582f`
- Release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-c0710ae1-20260611Tobscycle`
- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-28b9cc20-20260611Tsignalinput`
- Backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-c0710ae1-20260611Tobscycle.pgdump`

Git deploy result:

```text
status=applied
commands_executed=16
database_backup_created=true
migrations_run=true
services_restarted=true
exchange_called=false
execution_intent_created=false
order_created=false
order_lifecycle_called=false
```

## Tokyo Smoke

Command target:

```text
scripts/runtime_next_attempt_observation_cycle.py
runtime=strategy-runtime-95655873b76c
symbol=AVAX/USDT:USDT
strategy=BTPC-001 / BTPC-001-v0
mode=default read-only
```

Remote artifacts:

```text
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-cycle/avax-btpc-observation-cycle.json
/home/ubuntu/brc-deploy/reports/runtime-next-attempt-observation-cycle/avax-btpc-signal-input.json
```

Observed result:

```text
cycle_status=waiting_for_signal
blocked_stage=strategy_signal
gate_status=clear_for_next_attempt_preflight
signal_status=observe_only
signal_eval_status=observe_only
evaluator_blockers=[strategy_signal_not_would_enter]
prepare_packet=false
creates_shadow_candidate=false
creates_execution_intent=false
order_created=false
exchange_write_called=false
next_step=observe_only_or_wait_for_next_closed_bar
```

## Decision

The Tokyo smoke is accepted.

The runtime lifecycle is clear for next-attempt preflight, but current market
facts do not satisfy the BTPC signal. The correct behavior is to wait for the
next closed-bar observation rather than force candidate planning.

## Safety Invariants

- No real submit was authorized or attempted.
- No shadow candidate was created.
- No `ExecutionIntent` was created.
- No `OrderLifecycle` call occurred.
- No exchange write occurred.
- No order was created.
- No attempt counter or runtime budget was mutated by the observation cycle.
- No withdrawal or transfer instruction was created.
