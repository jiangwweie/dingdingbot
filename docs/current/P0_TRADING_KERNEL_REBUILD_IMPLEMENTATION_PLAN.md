---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: CURRENT_PLAN
program_id: P0-TKR
last_verified: 2026-07-24
---

# P0 Trading Kernel Rebuild Implementation Plan

## Goal

Deliver one readable multi-StrategyGroup, multi-position trading system from
natural market Observation through terminal Review, with one clean PostgreSQL
authority and one Tokyo runtime.

## Architecture

```text
Observation
-> StrategySignal
-> Readiness/Authority
-> CapacityClaim
-> immutable Ticket
-> durable Exchange Command
-> protected lifecycle
-> reconciliation
-> settlement
-> review
```

New ENTRY is globally serialized. Existing Tickets protect, exit, reconcile,
settle, and review concurrently.

## Global Constraints

- One Ticket per Exposure Episode; no add-to-position capability.
- One ENTRY generation per Ticket; authoritative rejection is terminal.
- Unknown outcomes are reconciled and never blindly resent.
- Partial fill creates an Incident and controlled flatten.
- Long and short require independent exchange position sides.
- No retired imports, tables, tests, deployment units, file authority, dual
  writes, compatibility fallback, or parallel execution chain.
- All production behavior follows test-first red/green/refactor.

## Completed Implementation

| Capability | Status | Evidence |
| --- | --- | --- |
| Kernel identities and reducer | Complete | Pure domain models, immutable Ticket, events, effects, and fault branches |
| Clean PostgreSQL baseline | Complete | One 33-table `0001_initial`, clean rebuild and downgrade/upgrade certification |
| Six Strategy Events | Complete | CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG, SOR-SHORT, BRF2-SHORT |
| Observation and StrategySignal | Complete | Closed candles, bounded Facts, deterministic identity, Live/Replay parity |
| Arbitration and CapacityClaim | Complete | Deterministic priority, action-time fixed `5x` facts, demand-based remaining margin, and stop risk |
| Ticket issuance | Complete | Atomic Claim, budget, domain, Ticket, aggregate, event, and ENTRY command |
| Venue Truth and recovery | Complete | ENTRY, protection, EXIT, flatten, cancel, timeout and unknown resolution |
| Protected lifecycle | Complete | Initial Stop, TP1, Break-Even, structural runner, controlled exit |
| Reconciliation, Settlement, Review | Complete | Exact Ticket identities and explicit funding availability semantics |
| Runtime ownership | Complete | Persistent Observation, Entry, Lifecycle, and Reconciliation workers |

Exact production identity, certification, runtime state, and remaining progress
belong only to `MAIN_CONTROL_ROADMAP.md`.

## Deployment Implementation

The deployed service set is:

```text
deploy/systemd/brc-trading-kernel-observation-worker.service
deploy/systemd/brc-trading-kernel-entry-worker.service
deploy/systemd/brc-trading-kernel-lifecycle-worker.service
deploy/systemd/brc-trading-kernel-reconciliation-worker.service
deploy/systemd/brc-trading-kernel.slice
```

All four workers are persistent long-running processes. Their current activation
state belongs to `MAIN_CONTROL_ROADMAP.md`. New Tickets freeze the approved
exchange leverage configuration and do not produce `SET_LEVERAGE`. Timer
deployment is forbidden. The service slice and bounded polling protect the
constrained host from repeated Python cold-start overhead.

Regular releases use one command:

```text
python3 scripts/trading_kernel/deploy_tokyo_release.py \
  --commit <exact-commit> \
  --enable-entry
```

The command stages the exact committed release, verifies database and exchange
flatness, zero open orders, approved leverage configuration, and current
identity, stops the four workers, rotates runtime identity, switches the
release, starts the three safety workers, repeats readonly certification, and
starts Entry last. Any failure after service stop fences Entry and restores the
safety workers. This bounded regular-release path does not rebuild PostgreSQL
and does not run the historical destructive cutover.

## Completed Destructive Cutover

The Owner authorized a clean, no-backup replacement of BRC-only runtime state.
Execution therefore:

1. stopped and fenced every BRC writer;
2. verified exchange and old-runtime preconditions;
3. deleted BRC program services, containers, releases, and PostgreSQL data;
4. rebuilt PostgreSQL from `0001_initial` and deterministic seeds;
5. deployed one exact committed release;
6. enabled only Observation while preserving the ENTRY write fence;
7. preserved non-quantitative Nginx, PostgreSQL host, Docker, and unrelated
   services/data;
8. activated hourly read-only runtime supervision.

No retired BRC backup is a current rollback source. Fixes proceed forward from
the immutable production tag recorded in `MAIN_CONTROL_ROADMAP.md`.

## Remaining Execution Stages

### Stage 1: Controlled Natural Acceptance

- Preserve the prior rejection evidence and keep production leverage mutation
  retired.
- Let the official chain create one natural real-funds Ticket and install
  Initial Stop protection.
- Let the official Lifecycle worker reach the accepted exit policy.
- Confirm terminal Ticket and exchange-flat position with no residual order.

### Stage 2: Internal Closure

- Confirm budget and Netting Domain release.
- Confirm Reconciliation matches exact exchange truth.
- Confirm Settlement and Review persisted exact economics.
- Confirm zero open Incident and zero unknown command outcome.

### Stage 3: Full Capability Promotion

- Run `promote-full` only after Stages 1-2 pass.
- Verify runtime capability, commit, schema, seed, account, policy, and
  acceptance-Ticket identity together.
- Keep exchange writes fail-closed if any gate disagrees.

### Stage 4: Final Audit

- Run the complete Trading Kernel test suite, Ruff, Mypy, schema rebuild,
  downgrade/upgrade, production file-I/O audit, and readonly Tokyo certification.
- Prove every design acceptance item from current evidence.
- Prove no retired code, table, migration, service, document, Skill
  reference, or compatibility path remains.
- Mark the program complete only when every item is direct and current.

The completion state of these stages is recorded only in
`MAIN_CONTROL_ROADMAP.md`.
