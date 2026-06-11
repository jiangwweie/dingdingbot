# Runtime Observation API Prepare Ready Rehearsal Tokyo Smoke - 2026-06-11

## Scope

This note records deployment and Tokyo smoke verification for the local
ready-signal rehearsal verifier:

```text
scripts/verify_runtime_observation_api_prepare_ready_rehearsal.py
```

The verifier exercises the observation API to prepare-flow bridge with an
in-memory ready signal. It proves that the bridge stops before prepare records
unless explicitly allowed, and that explicit allow reaches FinalGate preflight
without submitting orders or calling the exchange.

## Deployment

- Worktree: `/Users/jiangwei/Documents/final-sprint6-integration`
- Branch: `program/live-safe-v1`
- Deployed head: `3ccb88ff23edc7d7f28422ceea468bdffdce36a1`
- Release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-3ccb88ff-20260611Treadyrehearsal`
- Previous release:
  `/home/ubuntu/brc-deploy/releases/brc-runtime-governance-9a1c7027-20260611Tobsapiprepare`
- Backup:
  `/home/ubuntu/brc-deploy/backups/brc-runtime-governance-3ccb88ff-20260611Treadyrehearsal.pgdump`

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
secrets_read_by_codex=false
```

## Tokyo Smoke

Remote artifact:

```text
/home/ubuntu/brc-deploy/reports/runtime-observation-api-prepare-ready-rehearsal/report.json
```

Observed result:

```text
current_head=3ccb88ff23edc7d7f28422ceea468bdffdce36a1
ready_rehearsal_present=yes
status=rehearsal_passed
ready_without_allow=true
allow_prepare_reaches_final_gate=true
prepared_authorization_id_present=true
forbidden_execution_flags=[]
dry_status=ready_for_prepare
allow_status=ready_for_final_gate_preflight
order_created=false
exchange_write_called=false
order_lifecycle_called=false
```

## Decision

The Tokyo ready-signal rehearsal is accepted.

The deployed bridge can represent a ready signal and can advance to FinalGate
preflight only when the operator explicitly enables prepare-record creation.
The verifier remains non-executing and does not create orders, submit to the
exchange, mutate runtime attempt counters, or mutate runtime budgets.

## Safety Invariants

- No real submit was authorized or attempted.
- No exchange write occurred.
- No `OrderLifecycle` call occurred.
- No order was created.
- No attempt counter was mutated.
- No runtime budget was mutated.
- No withdrawal or transfer instruction was created.
