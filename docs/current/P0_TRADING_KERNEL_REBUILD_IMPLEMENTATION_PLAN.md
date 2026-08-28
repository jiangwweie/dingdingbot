---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: CURRENT_PLAN
program_id: P0-TKR
last_verified: 2026-08-11
---

# P0 Trading Kernel Rebuild Implementation Plan

## Goal

Deliver one readable multi-StrategyGroup, multi-position trading system from
natural market Observation through terminal Review, with one clean PostgreSQL
authority and one Tokyo runtime.

## Completed Operability Baseline

Scheduling fairness, continuous certification, flat Entry Promotion,
phase-aware deployment recovery, StrategyUniverse batch bootstrap, SOR v3, and
multi-Ticket capacity are implemented, certified, and deployed. Their stable
semantics belong to the P0 design, experiment profile, and Tokyo deployment
contract. Exact production identity and the remaining natural-Ticket acceptance
belong only to `MAIN_CONTROL_ROADMAP.md`.

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
| PostgreSQL revision chain | Complete in the current tracked authority | Exact `0001_trading_kernel_baseline_v4 -> 0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability -> 0004_owner_control_plane -> 0005_tradfi_instrument_center -> 0006_sor_dynamic_selection_v0 -> 0007_exit_profile_authority_v1`; exact deployed revision and release state belong only to `MAIN_CONTROL_ROADMAP.md` |
| Owner control plane | Complete | Explicit StrategyGroup pause/resume, global new-ENTRY pause/resume, durable flatten-all authorization and progress projection, authenticated Owner API, and `/trading/` console |
| Eight Strategy Events | Complete | Six Crypto CPM/MPG/MI/BRF2/SOR Events plus independent TradFi SOR LONG/SHORT Registry contracts |
| Observation and StrategySignal | Complete | Closed candles, bounded Facts, rising-edge or session Exposure Episode identity, deterministic Live/Replay parity |
| Arbitration and CapacityClaim | Complete | Deterministic priority, Policy v4 Family/directional/materialization limits, action-time fixed `5x` facts, demand-based remaining margin, and stop risk |
| Admission evidence and Shadow Outcome | Complete | One Signal-owned Outcome supports eligible portfolio rejection through `fixed_horizon_excursion_v1` and TradFi strategy observation through `sor_path_observation_v1`; Observation creates no simulated Ticket or PnL, while an eligible live Signal may independently continue through the same formal Ticket path: AdmissionDecision, CapacityClaim, Ticket and Command |
| Ticket issuance | Complete | Atomic Claim, budget, domain, Ticket, aggregate, event, and ENTRY command |
| Venue Truth and recovery | Complete | ENTRY, protection, EXIT, flatten, cancel, timeout and unknown resolution |
| Protected lifecycle | Complete | Initial Stop, TP1, Break-Even, immutable ExitProfile guards/TimeStop, rolling-extreme ATR Runner, controlled exit |
| Reconciliation, Settlement, Review | Complete | Exact typed Binance order identities, append-only Review revisions, explicit funding availability, and atomic terminal Owner projection |
| Runtime ownership | Complete | Persistent Observation, Entry, Lifecycle, and Reconciliation workers |
| StrategyUniverse capability | Complete and deployed | Versioned 1..10 member pools, readonly certification, Warming with zero Signal, automatic atomic activation, frozen Ticket lineage, bounded CLI and PostgreSQL evidence |
Exact production identity, certification, runtime state, and remaining progress
belong only to `MAIN_CONTROL_ROADMAP.md`.

## StrategyUniverse Verification Contract

Every behavior below requires direct automated evidence. These are release
predicates, not runtime inputs and not a substitute for action-time Tokyo
readonly facts.

| Boundary | Required local evidence | Rejected outcome |
| --- | --- | --- |
| Revision integrity | Disposable PostgreSQL upgrades from empty base to the single head, historical production-shaped `0002` to `0003`, flat `0003` to `0004`, and exact flat `0004` to `0005`; each source authority remains preserved | A branch, downgrade, schema fallback, old-table reader, dual write, active handover, or changed historical value is accepted |
| Batch bootstrap | The eight Registry Events receive their approved RuntimeProfile-specific initial member sets in one bounded run; no operator configures members one Event at a time | A second Warming Universe is required for every Event or member |
| Warming and readiness | Warming performs readonly market/account certification, produces zero StrategySignal, preserves observation time separately from certification time, and activates only after every member passes | Warming can submit an order, stale evidence activates, or a failed member becomes eligible |
| Concurrency and recovery | One global Warming slot is enforced; the official `abandon_strategy_universe.py` CLI permanently abandons one exact Warming Universe with an audited reason so the slot is released | A failed Warming state blocks all later deployment work, is changed by direct SQL, or can be silently reused |
| Active scope lineage | Only the current Active pointer is eligible; Signal, Claim, and Ticket freeze Universe identity and digest; a replacement does not rewrite exposure already in progress | Registry defaults or a later Universe changes an existing Ticket's scope |
| Entry promotion | Safety workers start while Entry stays fenced; postflight verifies the exact Active Universe, profile, policy, schema, and runtime identity before the final unfence; retry is idempotent only for that exact state | Universe configuration or worker startup implicitly permits ENTRY |
| Exchange boundary | Recording fakes prove local bootstrap, Warming, and promotion make zero exchange mutations; full-chain fault tests retain durable-command, unknown-outcome, partial-fill, and Netting Domain protections | A fixture bypasses the real producer boundary or hides an exchange write |

The release candidate must run focused tests first, then the complete
unit/integration/full-chain/architecture suite, Ruff, repository-wide Mypy,
the production file-I/O audit, and `git diff --check`. A server deployment
only verifies current external facts and must not be used to discover a
deterministic defect already reproducible locally.

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

The one approved schema-changing path is explicit `compatible_upgrade`. The
current tracked transition is exact flat `0006_sor_dynamic_selection_v0` to
`0007_exit_profile_authority_v1`; earlier transitions remain preservation
evidence. It requires zero active Ticket, position,
order, Reservation, Netting Domain, unresolved Command, unreviewed terminal
Ticket and open Incident, and requires Entry fenced with all old writers
stopped. It computes the canonical `0006` source-column preservation digest,
runs the single Alembic revision, verifies the same digest, preserves the sole
`policy-main` lineage, Strategy controls and Universe authority, installs the
immutable typed ExitProfile Catalog plus initial EventExitBinding authority,
and starts safety workers while Entry stays fenced. Historical `0002 -> 0003`,
`0003 -> 0004`, `0004 -> 0005` and `0005 -> 0006` evidence remains intact;
none of these transitions is an active-position handover or a runtime
compatibility reader.

## Completed Destructive Cutover

The Owner authorized a clean, no-backup replacement of BRC-only runtime state.
Execution therefore:

1. stopped and fenced every BRC writer;
2. verified exchange and old-runtime preconditions;
3. deleted BRC program services, containers, releases, and PostgreSQL data;
4. rebuilt PostgreSQL to the then-tracked schema head and deterministic seeds;
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

- Run the complete Trading Kernel test suite, Ruff, Mypy, empty schema rebuild,
  forward-only downgrade rejection, production file-I/O audit, and readonly Tokyo
  certification.
- Prove every design acceptance item from current evidence.
- Prove no retired code, table, migration, service, document, Skill
  reference, or compatibility path remains.
- Mark the program complete only when every item is direct and current.

The completion state of these stages is recorded only in
`MAIN_CONTROL_ROADMAP.md`.
