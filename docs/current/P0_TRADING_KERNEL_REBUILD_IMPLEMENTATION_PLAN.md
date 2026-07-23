---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: ACCEPTANCE_ACTIVE
program_id: P0-TKR
last_verified: 2026-07-23
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
| Arbitration and CapacityClaim | Complete | Deterministic priority, bounded selector, action-time facts and stop risk |
| Ticket issuance | Complete | Atomic Claim, budget, domain, Ticket, aggregate, event, and ENTRY command |
| Venue Truth and recovery | Complete | ENTRY, protection, EXIT, flatten, cancel, timeout and unknown resolution |
| Protected lifecycle | Complete | Initial Stop, TP1, Break-Even, structural runner, controlled exit |
| Reconciliation, Settlement, Review | Complete | Exact Ticket identities and explicit funding availability semantics |
| Runtime ownership | Complete | Persistent Observation, Entry, Lifecycle, and Reconciliation workers |
| Local certification | Complete | `331 passed`; Ruff clean; Mypy clean; production file-I/O audit clean |
| Tokyo zero rebuild | Complete | Commit `f9fda21c91482b050e2a630e163f3213386ae6d7` deployed from an empty BRC database baseline |

## Deployment Implementation

The deployed service set is:

```text
deploy/systemd/brc-trading-kernel-observation-worker.service
deploy/systemd/brc-trading-kernel-entry-worker.service
deploy/systemd/brc-trading-kernel-lifecycle-worker.service
deploy/systemd/brc-trading-kernel-reconciliation-worker.service
deploy/systemd/brc-trading-kernel.slice
```

All four workers are persistent long-running processes. Timer deployment is
forbidden. The service slice and bounded polling protect the 2c4g host from the
retired high-frequency Python cold-start failure mode.

## Completed Destructive Cutover

The Owner authorized a clean, no-backup replacement of BRC-only runtime state.
Execution therefore:

1. stopped and fenced every BRC writer;
2. verified exchange and old-runtime preconditions;
3. deleted BRC program services, containers, releases, and PostgreSQL data;
4. rebuilt PostgreSQL from `0001_initial` and deterministic seeds;
5. deployed exact commit `f9fda21c`;
6. enabled the four persistent workers;
7. preserved non-quantitative Nginx, PostgreSQL host, Docker, and unrelated
   services/data;
8. activated hourly read-only runtime supervision.

No retired BRC backup is a current rollback source. Fixes proceed forward from
the production anchor `tokyo-runtime-2026.07.23.1`.

## Active Acceptance Ticket

| Field | Value |
| --- | --- |
| Ticket | `ticket:c1ebc24a178a3ae4d87978e2fa1204ae` |
| Origin | Natural Observation, not constructed signal |
| Event | `SOR-001 / SOR-SHORT / SOLUSDT` |
| Exposure | 0.25 SOL short |
| Entry | 77.51 |
| Initial Stop | 78.50 |
| TP1 | 76.52 |
| Verified state | `position_protected` |
| Accepted effects | ENTRY, Initial Stop, TP1 |

## Remaining Execution Stages

### Stage 1: Terminal Lifecycle

- [ ] Let the official Lifecycle worker reach the accepted exit policy.
- [ ] Confirm terminal Ticket and exchange-flat position.
- [ ] Confirm no residual protection, TP, EXIT, cancel, or ENTRY order.

### Stage 2: Internal Closure

- [ ] Confirm budget and Netting Domain release.
- [ ] Confirm Reconciliation matches exact exchange truth.
- [ ] Confirm Settlement and Review persisted exact economics.
- [ ] Confirm zero open Incident and zero unknown command outcome.

### Stage 3: Full Capability Promotion

- [ ] Run `promote-full` only after Stages 1-2 pass.
- [ ] Verify runtime capability, commit, schema, seed, account, policy, and
  acceptance-Ticket identity together.
- [ ] Keep exchange writes fail-closed if any gate disagrees.

### Stage 4: Final Audit

- [ ] Run the complete Trading Kernel test suite, Ruff, Mypy, schema rebuild,
  downgrade/upgrade, production file-I/O audit, and readonly Tokyo certification.
- [ ] Prove every design acceptance item from current evidence.
- [ ] Prove no retired code, table, migration, service, document, Skill
  reference, or compatibility path remains.
- [ ] Mark the program complete only when every item is direct and current.
