---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: CURRENT_PLAN
program_id: P0-TKR
last_verified: 2026-10-12
---

# P0 Trading Kernel Rebuild Implementation Plan

## Goal

Deliver one readable multi-StrategyGroup, multi-position trading system from
natural market Observation through terminal Review, with one clean PostgreSQL
authority and one Tokyo runtime.

## Completed Operability Baseline

Scheduling fairness, continuous certification, flat Entry Promotion,
phase-aware deployment recovery, initial StrategyUniverse bootstrap, Generic
Selection, ExitProfile Authority and Capacity B are implemented and release
certified. Crypto SOR is retired, not an active acceptance target. Their stable
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
| PostgreSQL revision chain | Complete in the current tracked authority | Exact `0001_trading_kernel_baseline_v4 -> 0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability -> 0004_owner_control_plane -> 0005_tradfi_instrument_center -> 0006_sor_dynamic_selection_v0 -> 0007_exit_profile_authority_v1 -> 0008_generic_dynamic_selection_v1 -> 0009_capacity_policy_v0
-> 0010_dynamic_intent_v1 -> 0011_orb_session_1h_v1 -> 0012_generic_signal_path_v1 -> 0013_owner_directional_risk_v1`; exact deployed revision and release state belong only to `MAIN_CONTROL_ROADMAP.md` |
| Owner control plane | Complete | Explicit StrategyGroup pause/resume, global new-ENTRY pause/resume, durable flatten-all authorization and progress projection, authenticated Owner API, and `/trading/` console |
| Registered Strategy Events | Complete | CPM/MPG/MI/BRF2 Crypto Events; retained retired Crypto SOR and independent paused TradFi contracts are not implicit ENTRY permission |
| Observation and StrategySignal | Complete | Closed candles, bounded Facts, rising-edge or session Exposure Episode identity, deterministic Live/Replay parity |
| Arbitration and CapacityClaim | Complete | Deterministic priority, Policy v4 Family/directional/materialization limits, action-time fixed `5x` facts, demand-based remaining margin, and stop risk |
| Admission evidence and Shadow Outcome | Complete | One Signal-owned Outcome supports eligible portfolio rejection through `fixed_horizon_excursion_v1` and TradFi strategy observation through `sor_path_observation_v1`; Observation creates no simulated Ticket or PnL, while an eligible live Signal may independently continue through the same formal Ticket path: AdmissionDecision, CapacityClaim, Ticket and Command |
| Ticket issuance | Complete | Atomic Claim, budget, domain, Ticket, aggregate, event, and ENTRY command |
| Venue Truth and recovery | Complete | ENTRY, protection, EXIT, flatten, cancel, timeout and unknown resolution |
| Protected lifecycle | Complete | Initial Stop, TP1, Break-Even, immutable ExitProfile guards/TimeStop, rolling-extreme ATR Runner, controlled exit |
| Reconciliation, Settlement, Review | Complete | Exact typed Binance order identities, append-only Review revisions, explicit funding availability, and atomic terminal Owner projection |
| Runtime ownership | Complete | Persistent Observation, Entry, Lifecycle, and Reconciliation workers |
| StrategyUniverse capability | Implemented | Versioned 1..16 member pools, readonly certification, Warming with zero Signal, automatic atomic activation, frozen Ticket lineage, bounded CLI and PostgreSQL evidence |
| Generic Selection | Implemented and release certified | Four strategy-specific Specs, Candidate24 DB handoff, independent ComparisonUniverse, epochs, normal-close versus recovery rebase, Owner TOTP controls and resident hosting |
| Capacity B | Implemented and release certified | Same-strategy/side 2, continuation Family 2, distinct Instrument/Episode/Signal, unchanged global/risk limits and immutable Policy lineage |
| Deferred evidence | Not PASS | Full long-run soak, offline MAE/MFE projector and complete GS-13 task acceptance remain explicit follow-up, not prerequisites retroactively added to the Owner-approved deployment |
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
  --commit <exact-certified-commit> \
  --mode regular
```

The command stages the exact committed release, verifies database and exchange
flatness, zero open orders, approved leverage configuration, and current
identity, stops all Kernel and Owner API writers, rotates runtime identity, switches the
release, starts the three safety workers, repeats readonly certification, and
leaves Entry fenced. Owner Resume/TOTP and official current-Universe preparation
or promotion are separate operations. Any failure after service stop fences Entry and restores the
safety workers. This bounded regular-release path does not rebuild PostgreSQL
and does not run the historical destructive cutover.

The one approved schema-changing path is explicit `compatible_upgrade`. The
latest tracked transitions are exact flat `0007 -> 0008 -> 0009`; earlier transitions remain preservation
evidence. It requires zero active Ticket, position,
order, Reservation, Netting Domain, unresolved Command, unreviewed terminal
Ticket and open Incident, and requires Entry fenced with all old writers
stopped. It computes the exact source-column preservation digest,
runs the certified forward revisions, verifies the same digest, preserves the sole
`policy-main` lineage, Strategy controls, terminal lineage and Universe authority.
The formal release transaction installs approved Generic Specs and Capacity B,
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

These are evidence categories, not assertions that all historical tasks are
unfinished or a new permission to resume SOR/TradFi. Exact completed and pending
acceptance facts are owned only by `MAIN_CONTROL_ROADMAP.md`.

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

## Dynamic intent repair migration

`0009 -> 0010` changes only Generic first-activation proof functions. Every
source row, original authorization, pending epoch, earliest boundary and terminal
lineage must be preserved exactly before identity rotation. Release is stopped,
flat and forward-only; use the existing compatible deployment path with the exact
0009 source and certified 0010 target. Source failures and unfenced period expiry
do not revoke Owner Dynamic intent. Later attempts require current snapshots and
all existing closed-bar, certification, warming, Vacuum and atomic activation gates.
