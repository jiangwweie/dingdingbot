---
title: EXIT_PROFILE_AUTHORITY_V1_IMPLEMENTATION_PLAN
status: LOCAL_IMPLEMENTATION_COMPLETE
date: 2026-08-28
program: EX-P1
design_authority_path: ../specs/2026-08-28-exit-profile-authority-v1-design.md
design_authority_commit: 50e94cea15445f1c3e268f524dfa6e440581bf3e
design_authority_semantic_digest: sha256:68415c06387d4cdc13aebc500a095e205fe389ea96be137df07350c4a6364477
base_candidate: 1c57b407c8f7ae5dcd2a15b40fb4f49366012b00
implementation_authority: CODE_AND_TEST_ONLY
active_execution_scope: NONE
production_authority: NONE
owner_approval: 2026-08-28 active task decision authorizing EX-00 through EX-08
---

# ExitProfile Authority V1 Implementation Plan

## 1. Objective

Implement the approved ExitProfile V1 design in the single Trading Kernel so
that every active/entry-eligible EventSpec resolves exactly one versioned
EventExitBinding and immutable ExitProfile, while CapacityClaim and Ticket
freeze exact Binding/Profile lineage and Lifecycle continues one TP1 + Runner
semantics.

The implementation installs the Owner-frozen V1 Profiles directly. It does not
perform Replay, Shadow, parameter search or profitability certification.

## 2. Authority And Current Gate

```text
design_status = DESIGN_APPROVED
plan_status = PLAN_APPROVED
implementation_authority = CODE_AND_TEST_ONLY
active_execution_scope = NONE
production_authority = NONE
```

This plan is based on stacked branch `codex/exit-profile-v1` from exact
candidate `1c57b407`. PR #4 remains frozen and is not modified by any Task.

Its upstream Design Authority is exact and immutable for this Plan:

```text
path = docs/superpowers/specs/2026-08-28-exit-profile-authority-v1-design.md
commit = 50e94cea15445f1c3e268f524dfa6e440581bf3e
semantic_digest = sha256:68415c06387d4cdc13aebc500a095e205fe389ea96be137df07350c4a6364477
base_candidate = 1c57b407c8f7ae5dcd2a15b40fb4f49366012b00
```

Any Design content change invalidates this Plan review and requires a new
digest/reference.

The Owner has authorized the complete local EX-00 through EX-08 sequence. Each
Task may advance automatically only after its own RED/GREEN and proportional
acceptance passes. Production actions remain independently forbidden.

## 3. Owner-Frozen Product Decisions

1. no YAML/YML configuration or runtime file authority;
2. no Replay/Shadow gate;
3. eight side-bound Profile records across six semantic families;
4. MPG uses exact `Decimal("0.33")`, 5-bar rolling extreme and 0.75ATR;
5. MI/BRF2 use 12-boundary PRE_TP1 TimeStop;
6. Crypto SOR uses 96-boundary ABSOLUTE TimeStop;
7. SOR-US uses 8-boundary ABSOLUTE TimeStop;
8. SOR Profiles consume reclaim and session-expiry guards;
9. one TP1 + one Runner remains the only reducer shape;
10. production cutover is exact-flat, forward-only and separately authorized.

## 4. Known State And Earliest Gap

| Boundary | Current fact | Earliest missing capability |
| --- | --- | --- |
| Exit domain | Event-bound ExitPolicy, post-TP1 TimeStop exists | generic guard-aware PRE_TP1/ABSOLUTE model |
| Registry | one Policy synthesized per Strategy Contract | independent Profile Catalog and Binding Catalog |
| PostgreSQL | EventSpec↔Policy 1:1 | immutable Binding facts/current/events and composite identities |
| CapacityClaim | freezes Policy ID/hash | Binding ID/hash/authority version and exact leg notional proof |
| Ticket | copies Policy ID/hash | exact Binding lineage copy and issuance ABA rejection |
| Lifecycle | uses Ticket-created time and implicit SOR guards | earliest authoritative non-zero exposure boundary, explicit guards and Profile modes |
| Deployment | 0006 candidate frozen | NEXT_AFTER_0006 R4 preservation/cutover evidence |

The earliest executable gap is the pure domain contract. Schema and runtime
work must not start before EX-01 freezes those types and semantics.

## 5. Global Engineering Rules

Every Task follows RED/GREEN/refactor:

1. add the smallest failing current-semantics test;
2. confirm the expected failure;
3. implement the minimum behavior in the existing Kernel boundary;
4. run focused tests;
5. run proportional Fast/Integration/Architecture checks;
6. delete or rewrite replaced tests instead of preserving dual semantics;
7. do not run complete R4 until EX-08 freezes one exact candidate.

Global hard stops:

- no modification to PR #4 branch or candidate;
- no production PostgreSQL/systemd/exchange action;
- no YAML/JSON/Markdown runtime authority;
- no active-position handover;
- no compatibility fallback to EventSpec Policy;
- no Profile mutation in place;
- no hidden TP split repair;
- no Strategy detector/rank logic in Lifecycle;
- no second Ticket/Command/Lifecycle chain;
- no capital, leverage, capacity or instrument expansion.

## 6. Task Sequence

| Task | Goal | Depends on | Exit gate |
| --- | --- | --- | --- |
| **EX-00** | Freeze baseline, architecture guards and verification portfolio | Approved design | characterization and guards committed GREEN; temporary RED evidence recorded only |
| **EX-01** | Pure ExitProfile/Binding/TimeStop/guard domain contracts | EX-00 | deterministic domain semantics pass |
| **EX-02** | Forward Schema and PostgreSQL repositories | EX-01 | empty/production-shaped migration and constraints pass |
| **EX-03** | Typed Profile/Binding catalogs and initial seed | EX-02 | eight Profiles/eight initial current Bindings exact; no runtime mutation path |
| **EX-04** | All post-install Binding/Profile mutations and Strategy retirement | EX-02/03 | TOTP, idempotency, advisory lock, switch and retirement invariants pass |
| **EX-05** | CapacityClaim/Ticket authority and two-leg materialization | EX-02/03 | Binding/Profile lineage and ABA rejection pass |
| **EX-06** | Lifecycle guard/time/runner execution | EX-00/01/05 | exposure-start fact gate, closed-boundary and exit modes pass |
| **EX-07** | HTTP/readonly/release/deployment integration | EX-02–06 | bounded operations and R4 recovery gates pass |
| **EX-08** | Exact-candidate R4 certification and deployment evidence | EX-00–07 | complete exact command-set manifest and reviewable runbook; no production action |

Tasks are sequential because Domain, Migration, Registry, Claim/Ticket and
Lifecycle files share authority surfaces. Parallel edits to these boundaries
are forbidden.

## 7. EX-00 — Baseline, Architecture Guards And Test Portfolio

### Goal

Freeze the exact pre-change behavior and add tests that expose the approved
gaps without implementing new production behavior.

### Allowed files

- `tests/trading_kernel/unit/test_exit_policy.py`
- `tests/trading_kernel/unit/test_capacity_sizing.py`
- `tests/trading_kernel/unit/test_strategy_registry.py`
- `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`
- `tests/trading_kernel/architecture/**`
- `scripts/trading_kernel/verification_portfolios.py`
- design/plan execution evidence only

### Forbidden files

- `src/trading_kernel/**`
- `migrations/trading_kernel/**`
- deployment scripts other than verification portfolio membership

### Requirements

1. freeze current SOR Crypto 96 and SOR-US 8 behavior;
2. characterize current non-SOR pre-TP1 path as `NO_CHANGE` when reclaim/session
   references are absent;
3. characterize current Lifecycle request as using Ticket creation time rather
   than earliest EntryFilled/EntryPartiallyFilled exposure time;
4. characterize current 33% leg validation as lacking per-leg minNotional;
5. add an architecture guard that passes immediately because current runtime
   has no YAML/YML reader;
6. characterize current EventSpec exit-policy resolution without asserting the
   future replacement yet;
7. classify new tests into Focused/Fast/R4 without duplicating full-chain
   fixtures;
8. audit Entry reduction/fill semantics and freeze that full fill uses
   `EntryFilled`, retained partial exposure starts at `EntryPartiallyFilled`,
   and `VacuumPartialRetained` does not reset the time.

### Temporary RED evidence

- MI 12 PRE_TP1 test currently returns `NO_CHANGE`;
- Entry at 10:23 incorrectly uses Ticket-created time;
- `A/v10 -> B/v11 -> A/v12` Claim currently lacks authority version;
- current Registry cannot represent shared independent Profile;
- a local, uncommitted future architecture assertion fails on current EventSpec
  resolution.

Temporary RED tests/output are recorded in execution evidence and then removed
or moved into their owning implementation Task. The EX-00 checkpoint itself
must be clean and fully GREEN. The no-YAML guard is a direct GREEN baseline,
not a fabricated RED defect.

### Done

Current behavior is frozen by GREEN characterization tests; temporary RED
evidence identifies the owner Task for each gap; earliest non-zero exposure
semantics are explicitly classified; no source behavior changed; the planned portfolio
remains explicit and bounded.

### Hard stops

- do not write tests that demand Profile parameters before Domain approval;
- do not duplicate existing lifecycle support fixtures;
- do not commit an intentionally failing tree;
- do not run R4.

### EX-00 Execution Evidence — 2026-08-28

**Status: `EX00_COMPLETE / GREEN_CHECKPOINT`.** Current behavior is frozen by
GREEN characterization tests:

- Crypto SOR 96 and SOR-US 8 TimeStop baselines remain exact;
- non-SOR pre-TP1 without reclaim/session references returns `NO_CHANGE`;
- Lifecycle request currently uses Ticket creation time;
- current sizing can select a plan whose Runner leg is below per-leg
  minNotional;
- current Policy authority is Event-bound;
- runtime imports no YAML parser and has no ExitProfile YAML catalog.

Temporary, uncommitted RED evidence confirmed the owner gaps:

```text
TimeStopMode missing
registered_exit_profiles missing
CapacityClaim.exit_binding_authority_version missing
```

The temporary test was removed before commit. Existing reducer evidence proves
full fill uses `EntryFilled`, partial non-zero exposure uses
`EntryPartiallyFilled`, and legal Vacuum retention preserves that partial
exposure rather than creating a new start. The approved Design Authority was
therefore narrowed to earliest authoritative non-zero exposure and the Plan
digest was updated before implementation.

Verification:

| Check | Result |
| --- | ---: |
| Focused characterization | **55 passed** |
| Partial exposure semantic audit | **3 passed** |
| Checkpoint | **clean and GREEN** |

No production code, Migration, PostgreSQL production state, Policy, Ticket or
exchange fact was changed. Active execution scope advances to **EX-01**.

## 8. EX-01 — Pure ExitProfile And Generic Exit Semantics

### Goal

Implement pure, strategy-neutral ExitProfile and EventExitBinding contracts,
guard-aware pre-TP1 evaluation, exact TimeStop modes and truthful runner naming.

### Allowed files

- `src/trading_kernel/domain/exit_policy.py`
- new pure domain module only if the existing file becomes unreadable
- `tests/trading_kernel/unit/test_exit_policy.py`
- `tests/trading_kernel/unit/test_strategy_registry.py` only for pure type usage

### Forbidden files

- SQLAlchemy/PostgreSQL modules;
- application services;
- venue adapter;
- Migration files;
- Profile seed/cutover parameters outside the approved catalog contract.

### Requirements

1. add `RunnerRuleKind.ROLLING_EXTREME_ATR`;
2. add `TimeStopMode.PRE_TP1/ABSOLUTE`;
3. add `PreTp1GuardKind.RECLAIM_REFERENCE/SESSION_EXPIRY`;
4. define frozen `ExitProfile` and `EventExitBinding` models with forbidden
   extra fields and Decimal values;
5. semantic hashes include every field and canonical serialization;
6. explicit guard consumption replaces presence-implies-behavior;
7. deterministic precedence is Session → Reclaim → Absolute → PRE_TP1;
8. Runner stage ignores PRE_TP1 and honors ABSOLUTE;
9. retain one TP1 + Runner split type;
10. remove misleading confirmed-swing names from new current semantics.

### RED tests

- same Profile with changed guard has a different hash;
- same Binding with changed Profile hash has a different hash;
- session/reclaim same candle resolves `session_expired`;
- PRE_TP1 at boundary 11/12;
- ABSOLUTE before and after TP1;
- Profile content mutation rejected;
- rolling long/short price calculations remain exact.

### Done

Pure tests completely describe Profile/Binding/guard/time semantics and import
no infrastructure dependency.

### Hard stops

- no Strategy IDs inside ExitProfile;
- no YAML parser;
- no detector/rank exit;
- no Multi-TP abstraction.

### EX-01 Execution Evidence — 2026-08-28

**Status: `EX01_COMPLETE`.** Added pure frozen `ExitProfile` and
`EventExitBinding` contracts, truthful `rolling_extreme_atr` identity,
`PRE_TP1/ABSOLUTE` TimeStop modes, explicit reclaim/session guards, canonical
semantic hashes and deterministic evaluation precedence.

Legacy Event-bound `ExitPolicy` remains only to keep the 0006 baseline green
until EX-03 replaces current Registry authority; no PostgreSQL/application/
venue behavior changed in this Task.

| Verification | Result |
| --- | ---: |
| EX-01 focused domain | **28 passed** |
| Fast Unit + Architecture | **1,044 passed** |
| Ruff | **passed** |
| Mypy changed domain | **zero issues** |
| `git diff --check` | **passed** |

Active execution scope advances to **EX-02**. Production authority remains
`NONE`.

## 9. EX-02 — Forward Schema And PostgreSQL Authority

### Goal

Implement `NEXT_AFTER_0006` forward Schema, Profile/Binding facts/current/events,
Claim/Ticket Binding lineage and exact PostgreSQL constraints.

### Allowed files

- `migrations/trading_kernel/**`
- `src/trading_kernel/infrastructure/pg_models.py`
- `src/trading_kernel/infrastructure/pg_repositories.py`
- `src/trading_kernel/infrastructure/strategy_registry_seed.py` repository
  types only; catalog semantics remain EX-03
- `src/trading_kernel/application/ports.py`
- new `pg_exit_profile_repository.py` only if separation materially improves
  ownership
- focused Migration/repository/architecture tests

### Forbidden files

- Lifecycle behavior;
- Capacity sizing/business decisions;
- Owner HTTP routes;
- exchange adapter;
- deployment execution.

### Requirements

1. retain physical `brc_exit_policies` and preserve historical rows;
2. drop unique Event relation, make legacy Event column nullable and add
   Profile schema version;
3. add composite unique `(exit_policy_id, semantic_hash)`;
4. add immutable Binding facts, current pointers and append-only events;
5. add composite Profile and Binding FKs;
6. add `UNIQUE(exit_binding_id, operation)`;
7. add nullable historical-safe Binding ID/hash/authority version columns to
   CapacityClaim and Ticket;
8. add all-null/all-present CHECK constraints for those three columns on both
   tables;
9. add composite `(exit_binding_id, exit_binding_semantic_hash)` FK with
   PostgreSQL `MATCH FULL` and require positive authority version when present;
10. historical rows remain exact all-null without forced backfill; every new
    runtime Claim/Ticket is all-present;
11. install content immutability and legal status-transition guards;
12. migration creates zero Ticket, Command, Position or Incident;
13. downgrade raises fix-forward error;
14. legacy `brc_event_specs.exit_policy_id` remains data only.

### RED tests

- current 0006 rejects shared Profile;
- duplicate current Binding or hash drift rejected;
- duplicate Binding ACTIVATED/RETIRED event rejected;
- half-null Claim/Ticket Binding lineage rejected;
- all-null historical lineage accepted;
- all-present composite Binding lineage accepted;
- mismatched Binding hash rejected by `MATCH FULL` composite FK;
- retired Binding reactivation shape rejected;
- Profile content update rejected;
- non-flat source migration rejected;
- source terminal lineage digest preserved.

### Done

Empty and production-shaped `0006 -> NEXT` pass with exact preservation and zero
runtime side effects.

### Hard stops

- no DROP of historical policy/ticket facts;
- no dual-write or old-table reader;
- no active-position handover;
- final revision number remains integration-owned until merge.

### EX-02 Execution Evidence — 2026-08-28

**Status: `EX02_COMPLETE`.** Added forward-only
`0007_exit_profile_authority_v1`, immutable Profile physical extensions,
Binding facts/current/events, composite `MATCH FULL` identities and nullable
historical-safe Claim/Ticket Binding lineage.

The migration rejects non-flat source state, preserves legacy Policy rows,
creates zero runtime trading facts and rejects downgrade. Profile content and
Binding facts/events are immutable; duplicate Binding lifecycle operations are
database-rejected.

Necessary current-head identity updates move the local deployment target from
`0006` to `0007` while retaining `0006` as the exact compatible source. Existing
older preservation manifests project only their source-owned columns; this is a
bounded preservation query, not a runtime schema fallback.

| Verification | Result |
| --- | ---: |
| EX-02 Migration/constraint focused | **3 passed** |
| Cross-version/schema/Registry integration | **38 passed** |
| Fast Unit + Architecture | **1,044 passed** |
| Ruff | **passed** |
| Mypy | **173 source files, zero issues** |
| `git diff --check` | **passed** |

Active execution scope advances to **EX-03**. Production Migration was not
executed.

## 10. EX-03 — Typed Catalog And Initial Seed

### Goal

Replace `_policy_for_contract()` generation with exact typed catalogs, install
eight Owner-frozen Profiles and eight initial active Event bindings. This Task
defines retirement ownership but implements no post-install Binding/Profile
mutation path.

### Allowed files

- `src/trading_kernel/domain/exit_policy.py` catalog functions
- `src/trading_kernel/domain/strategy_registry.py`
- `src/trading_kernel/infrastructure/strategy_registry_seed.py`
- `src/trading_kernel/infrastructure/runtime_authority_seed.py` only when exact
  target Seed identity requires it
- the single `NEXT_AFTER_0006` Migration seed section created in EX-02
- unit/integration Registry/Migration tests

### Forbidden files

- Lifecycle behavior;
- Capacity/Ticket application logic;
- Owner HTTP;
- exchange adapter.

### Requirements

1. implement `registered_exit_profiles()` and
   `registered_event_exit_bindings()` in typed Python;
2. explicitly populate every hashed field; constructor defaults forbidden;
3. install exact eight Profiles and eight Bindings/current pointers for active
   EventSpecs;
4. zero current Binding for retired EventSpecs;
5. validate Event position side against Profile side;
6. validate guard/reference shape for SOR and empty guards elsewhere;
7. freeze the rule that Strategy retirement must later remove current Binding
   without retiring shared Profile, but leave the runtime mutation to EX-04;
8. expose no repository-only current-pointer delete/retire helper for runtime
   use;
9. Profile lookup for issued Ticket ignores current active/retired status;
10. old Event-bound rows remain provenance only;
11. Profile/Binding manifest digest is deterministic.

### RED tests

- Profile Catalog exact payload/hash matrix;
- current eight Event mappings exact;
- retired Profile cannot back a new Binding;
- retired Profile exact-load succeeds for frozen Ticket identity;
- Strategy seed does not read EventSpec legacy policy authority.

### Done

Registry/seed produces one deterministic initial Profile/Binding manifest with
no YAML/file dependency, strategy-generated Policy or runtime mutation path.

### Hard stops

- no implicit parameter default;
- no `_policy_for_contract()` compatibility path;
- no runtime read from legacy EventSpec policy ID.
- no temporary Strategy-retirement pointer mutation.

### EX-03 Execution Evidence — 2026-08-28

**Status: `EX03_COMPLETE / INITIAL_AUTHORITY_ONLY`.** Added the exact typed
eight-Profile/eight-Binding Catalog, deterministic Catalog digest and
idempotent initial PostgreSQL seed for Profile rows, Binding facts, current
pointers and ACTIVATED events.

Every hashed field is explicit. Source `0006` runtime seeding excludes the new
authority tables; target `0007` seed identity includes the Catalog digest.
StrategyVersion retirement no longer retires Event-bound Policy/Profile rows.
No post-install Binding/Profile mutation helper exists in this Task.

The pre-existing Event-bound lookup remains only as an unmodified intermediate
trading path until EX-05/EX-06 switch Claim/Lifecycle to current Binding/Profile
authority; it is not used to seed the new current pointers.

| Verification | Result |
| --- | ---: |
| Catalog/Binding focused | **41 passed** |
| Cross-version seed/migration | **16 passed** |
| Fast Unit + Architecture | **1,047 passed** |
| Ruff/Mypy/diff | **passed** |

Active execution scope advances to **EX-04**. Production authority remains
`NONE`.

## 11. EX-04 — Owner Binding Authority And Write Serialization

### Goal

Implement the sole post-install authority boundary for Binding/Profile
mutations and Strategy retirement, and serialize rare control-plane writes with
one PostgreSQL transaction lock.

### Allowed files

- `src/trading_kernel/application/owner_control.py`
- new focused application boundary for ExitProfile authority if needed
- `src/trading_kernel/application/ports.py`
- ExitProfile PostgreSQL repository
- `src/trading_kernel/domain/owner_control.py`
- `src/trading_kernel/interfaces/owner_console_http/routes/controls.py`
- PostgreSQL/HTTP/unit tests

### Forbidden files

- Claim/Ticket hot path;
- Lifecycle;
- exchange adapter;
- new Worker, lease, Redis or distributed lock;
- YAML configuration.

### Requirements

1. add OwnerAuthorization purpose `exit_profile_bind` and exact expected
   current pointer version;
2. require TOTP step-up, idempotency key and canonical reason;
3. define tracked Python constant `EXIT_PROFILE_AUTHORITY_WRITE_LOCK`;
4. acquire one `pg_advisory_xact_lock` for Binding activate/retire/switch and
   Profile retire;
5. perform row locks/CAS after acquiring the advisory lock;
6. create a new Binding for every switch; retired Binding never reactivates;
7. Profile retirement rejects an active current Binding;
8. initial Migration seed uses typed `system_migration` source;
9. StrategyVersion/EventSpec retirement removes its current Binding through
   this same serialized application boundary and never retires the shared
   ExitProfile;
10. Claim/Ticket/Lifecycle/Reconciliation never acquire this advisory lock;
11. no direct repository-only or SQL pointer mutation.

### RED tests

- Profile retire racing Binding activate cannot commit retired-current state;
- two Binding switches yield exactly one expected-version sequence;
- replayed idempotency key returns exact committed result;
- mismatched idempotency payload rejects;
- missing/weak authentication rejects;
- active Binding blocks Profile retire;
- retired Binding activation rejects;
- retiring one Event removes only its current Binding and preserves a shared
  Profile used by another Event/issued Ticket;
- hot-path recording repository sees zero advisory-lock calls.

### Done

All Profile Authority writes are low-cost serial control-plane transactions;
trading hot paths remain lock-free from the global Authority advisory lock.

### Hard stops

- no new concurrency framework;
- no Profile content edit endpoint;
- no automatic binding switch.

### EX-04 Execution Evidence — 2026-08-28

**Status: `EX04_COMPLETE`.** Added the sole post-install ExitProfile Authority
repository and Owner application boundary for Profile switching and retirement.
All Authority writes acquire one PostgreSQL transaction-scoped advisory lock,
then revalidate the current Binding/Profile and apply immutable Binding events
plus pointer CAS. Exact TOTP step-up, canonical idempotency replay and payload
mismatch rejection are enforced.

StrategyVersion retirement now removes only the retired Events' current
Bindings under the same lock domain and preserves shared Profiles and issued
Ticket lookup authority. The retirement event uses the actual retirement seed
time. Historical preservation verification now accepts only known forward
successors through the current `0007` head while still requiring the exact
source-owned digest.

| Verification | Result |
| --- | ---: |
| Authority/Owner/Migration/Registry focused | **45 passed** |
| Fast Unit + Architecture | **1,047 passed** |
| Ruff | **passed** |
| Mypy | **174 source files, zero issues** |
| `git diff --check` | **passed** |

Active execution scope advances to **EX-05**. No production Migration, Profile
switch, Strategy resume or exchange mutation was executed.

## 12. EX-05 — CapacityClaim, Ticket And Exit-Leg Materialization

### Goal

Resolve and freeze exact Binding/Profile authority during sizing, enforce both
exit legs, and reject Binding drift/ABA before Ticket issuance.

### Allowed files

- `src/trading_kernel/domain/capacity.py`
- `src/trading_kernel/domain/capacity_sizing.py`
- `src/trading_kernel/domain/ticket.py`
- `src/trading_kernel/application/build_capacity_claim.py`
- `src/trading_kernel/application/issue_ready_signal.py`
- `src/trading_kernel/application/issue_ticket.py`
- `src/trading_kernel/application/ports.py`
- Capacity/Claim/Ticket repositories
- focused unit/integration/full-chain tests

### Forbidden files

- Lifecycle exit evaluation;
- Profile mutation/control routes;
- exchange dispatch semantics;
- risk/capital defaults.

### Requirements

1. build Claim from exact current Binding pointer, Binding fact and Profile;
2. freeze Binding ID/hash/current projection version and Profile ID/hash;
3. require active Binding/Profile and exact side/reference shape;
4. calculate TP1 floor-to-step and Runner residue from exact fraction;
5. require both legs positive, step-aligned, minQty and minNotional;
6. use TP1 limit price and Initial Stop price as frozen conservative notional
   bases;
7. return terminal `exit_leg_materialization_unmet` without Ticket/Reservation/
   Command;
8. Ticket locks current pointer and checks ID/hash/version;
9. `A/v10 -> B/v11 -> A-new/v12` rejects v10 Claim;
10. Ticket copies Claim lineage exactly and never re-sizes or re-resolves.

### RED tests

- MPG 100 units → 33/67;
- step-size floor residue Runner;
- TP1/Runner minQty failures;
- TP1/Runner minNotional failures;
- no 50/50 fallback;
- Profile side/reference mismatch;
- Binding switch and ABA rejection;
- admitted Decision/Claim/Ticket frozen lineage equality;
- no change to risk quantity, margin or initial stop risk.

### Done

Every new Ticket has one exact Binding authority generation and executable
Profile legs; no Profile drift can cross Ticket issuance.

### Hard stops

- no automatic Claim rebuild;
- no quantity/risk expansion;
- no new TP tranche;
- no exchange call inside transaction.

### EX-05 Execution Evidence — 2026-08-28

**Status: `EX05_COMPLETE`.** Claim construction now resolves and freezes the
exact current Binding pointer, immutable Binding fact and active Profile.
CapacityClaim and Ticket persist Binding ID/hash/authority version together
with the physical Profile ID/hash. Ticket issuance locks the current pointer
and rejects drift or `A -> B -> A-new` ABA as `exit_binding_changed` without
re-sizing or substituting the Profile.

Sizing now derives the exact TP1 fraction from the Profile and validates both
TP1 and Runner legs against quantity step, `minQty` and conservative
`minNotional` bases. MPG remains exact `0.33`, producing `33/67` for 100 units;
floor residue belongs only to Runner. An invalid leg returns the terminal
`exit_leg_materialization_unmet` blocker and creates no Ticket, Reservation or
Command.

| Verification | Result |
| --- | ---: |
| Claim/Ticket/Sizing focused | **79 passed** |
| Core PostgreSQL Integration | **68 passed** |
| Related Full-chain | **13 passed** |
| Fast Unit + Architecture | **1,056 passed** |
| Ruff/Mypy/diff | **passed** |

Active execution scope advances to **EX-06**. No capital, leverage, Initial
Stop, concurrent-capacity, production state or exchange authority changed.

## 13. EX-06 — Lifecycle Profile Execution And Time Identity

### Goal

Make Lifecycle exact-load the Ticket Profile, evaluate Profile guards/modes,
use earliest authoritative non-zero exposure time, and preserve current
Command/Reducer/Reconciliation chain.

### Allowed files

- `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- `src/trading_kernel/interfaces/lifecycle_worker.py`
- `src/trading_kernel/application/runtime_facts.py`
- `src/trading_kernel/infrastructure/venue_adapter.py`
- pure ExitProfile domain refinements required by integration
- lifecycle unit/integration/full-chain tests

### Forbidden files

- Reducer state expansion beyond existing events/effects;
- new Command kind;
- Strategy detector/rank queries;
- current Binding lookup in Lifecycle;
- file cache or report output.

### Requirements

0. require EX-00 evidence that full fill starts at `EntryFilled`, legally
   retained partial exposure starts at the earlier `EntryPartiallyFilled`, and
   later retention events do not reset time;
1. Lifecycle exact-loads Profile by Ticket ID/hash regardless of Profile status;
2. current Binding is never queried;
3. PRE_TP1 stage depends on exact TP1 fill truth;
4. Profile guards decide whether reclaim/session references are consumed;
5. deterministic Session → Reclaim → Absolute → PRE_TP1 precedence;
6. Runner honors ABSOLUTE and ignores PRE_TP1;
7. use earliest authoritative `EntryFilled`/`EntryPartiallyFilled` non-zero
   exposure time, not Ticket creation;
8. count final venue closes strictly later than that exposure time;
9. request market facts whenever guards/TimeStop/Runner require them;
10. candle limit is bounded by ATR, Runner and applicable TimeStop, maximum 97;
11. market failure retains protection and retries;
12. EXIT remains existing `ExitRequested -> durable EXIT Command` chain.

### RED tests

- full or retained-partial exposure at 10:23, close 11:00 = boundary 1;
- `VacuumPartialRetained` does not reset the retained partial clock;
- equal-to-fill close excluded;
- MI/BRF2 11/12 PRE_TP1;
- TP1 complete permanently disables PRE_TP1;
- SOR session+reclaim collision returns session reason;
- SOR reclaim only when guard enabled;
- Crypto 96 and SOR-US 8 ABSOLUTE before/after TP1;
- 97-row maximum and no full-history scan;
- retired Profile issued Ticket continues;
- current Binding repository is unused;
- source timeout produces zero exchange mutation.

### Done

All eight Profiles execute deterministically through the existing reducer and
durable Command path with no Strategy-specific branch.

### Hard stops

- no direct venue exit;
- no Multi-TP/reducer rewrite;
- no detector or comparison-universe dependency;
- no wall-clock fabricated TradFi bars.

### EX-06 Execution Evidence — 2026-08-28

**Status: `EX06_COMPLETE`.** Lifecycle and the retained-partial Vacuum branch
now exact-load only the Ticket-frozen ExitProfile ID/hash and never read the
current Binding or legacy Event-bound Policy. A Profile retired after Ticket
issuance remains exact-loadable and continues the protected Ticket lifecycle.

PRE_TP1 uses exact TP1 fill truth and explicit Profile guards. MI/BRF2 exit at
the 12th final closed bar before TP1; PRE_TP1 is permanently ignored after TP1.
Crypto SOR ABSOLUTE 96 and SOR-US ABSOLUTE 8 apply before and after TP1, with
Session -> Reclaim -> Absolute -> PRE_TP1 precedence. Runner execution uses the
truthful rolling-extreme ATR rule through the unchanged one-TP1/Runner reducer.

Lifecycle Worker derives exposure start from the earliest positive
`EntryFilled` or `EntryPartiallyFilled` event. `VacuumPartialRetained` does not
reset that time. Venue holding count includes only final candle closes strictly
later than exposure start, and the frozen maximum market request is **97 rows**.
Target Registry seed installs only the eight typed Profiles/Bindings; legacy
Event Policies remain source-revision preservation facts rather than target
runtime authority. The `_policy_for_contract()` path and runtime
`get_exit_policy()` port were removed.

| Verification | Result |
| --- | ---: |
| Profile/Lifecycle/venue focused | **124 passed** |
| Registry/Migration/seed regression | **29 passed** |
| Lifecycle Full-chain | **15 passed** |
| Fast Unit + Architecture | **1,063 passed** |
| Ruff/Mypy/diff | **passed** |

Active execution scope advances to **EX-07**. No new Command kind, direct venue
exit, detector dependency, production mutation or exchange write was added.

## 14. EX-07 — Readonly, HTTP, Release And Deployment Integration

### Goal

Expose bounded Profile/Binding authority, certify manifests and integrate the
new R4 release without coupling deployment to Profile control operations.

### Allowed files

- `src/trading_kernel/interfaces/readonly_api.py`
- Owner Console read/write application/routes required by approved controls
- `scripts/trading_kernel/certify_readonly.py`
- `scripts/trading_kernel/certify_release_candidate.py`
- `scripts/trading_kernel/verification_portfolios.py`
- `scripts/trading_kernel/deploy_tokyo_release.py`
- `scripts/trading_kernel/verify_schema.py`
- focused readonly/HTTP/release/deployment tests
- current deployment contract only after test evidence

### Forbidden files

- frontend UI implementation;
- production deployment execution;
- strategy resume or Policy mutation;
- YAML configuration/export.

### Requirements

1. readonly exact Event/Profile/Binding view with bounded recent events;
2. Profile status, current Binding ID/hash/version and full Catalog digest;
3. Owner API switch/retire routes reuse EX-04 application boundary and TOTP;
4. R4 portfolio includes Migration, Profile/Binding manifest and architecture
   gates;
5. deployment class remains R4 and exact-flat;
6. Phase A performs an advisory PostgreSQL/Binance flatness precheck before
   service stop and aborts early when non-flat;
7. Phase B fences Entry, stops every writer, then re-reads PostgreSQL and
   Binance positions, orders, Reservations, Commands, Incidents and terminal
   Review coverage; only this second exact-flat result authorizes Migration;
8. Phase A evidence is never reused after writer stop and any drift blocks;
9. target postflight verifies eight Profiles, eight active Bindings, zero
   retired-Event pointers and zero unexpected Ticket/Command activity;
10. deployment does not execute Binding switch beyond immutable seed;
11. software deployment and later Owner Profile switch remain separate actions;
12. fix-forward recovery binds exact source/target commit and Schema identities;
13. no YAML file is installed or read.

### RED tests

- readonly query bounded/exact/read-only;
- stale expected Binding version HTTP 409;
- missing TOTP rejects;
- manifest hash/profile count drift blocks R4;
- non-flat source blocks before service stop;
- flat Phase A followed by new internal/external activity before service stop is
  caught by Phase B and blocks Migration;
- Phase B proves Entry fenced and all writers stopped before authoritative
  reads;
- target recovery missing exact release fact fails closed;
- postflight unexpected Profile/Binding state blocks;
- no frontend/static release mutation.

### Done

The exact candidate can be reviewed and deployed as one R4 capability/parameter
release while Entry remains fenced until postflight.

### Hard stops

- no second release classifier;
- no synchronous wait for control-plane Profile switch;
- no production action.

### EX-07 Execution Evidence — 2026-08-28

**Status: `EX07_COMPLETE`.** Added a bounded exact Event/Profile/Binding
readonly projection with Catalog digest, Profile status, current pointer
ID/hash/version, immutable Binding fact and recent transition events. The HTTP
readonly route executes through the existing repeatable-read Owner transaction
with PostgreSQL `READ ONLY` enforced.

Owner HTTP Binding switch and Profile retirement routes reuse the EX-04
application boundary, require non-replayable TOTP step-up and preserve the
existing 409 conflict / 422 blocked response contract. Missing TOTP and stale
Binding versions are covered with a production-shaped FastAPI/PostgreSQL test.

R4 certification now includes the `0007` Migration/Authority suites and a
Profile/Binding manifest. Target postflight requires the exact Catalog digest,
eight Profiles, eight initial Binding facts, eight current pointers and eight
initial ACTIVATED events, with zero unexpected runtime activity. The existing
deployment engine already performs the required Phase A advisory precheck and
Phase B post-fence/post-stop fresh PostgreSQL/Binance reread; tests prove that
Phase A is never reused and drift blocks Migration.

Current authority documents now consistently record the forward chain through
`0007_exit_profile_authority_v1` and the stopped-flat/fix-forward/no-YAML
deployment boundary without copying any undeployed Commit or runtime state.

| Verification | Result |
| --- | ---: |
| Fast Unit + Architecture | **1,064 passed** |
| HTTP/Authority/Migration focused | **47 passed** |
| Deployment/portfolio/certification focused | **93 passed** |
| Ruff/Mypy/diff | **passed** |

Active execution scope advances to **EX-08**. Production deployment, Strategy
resume and Owner Profile switch remain separately unauthorized.

## 15. EX-08 — Integrated R4 Certification And Evidence Package

### Goal

Freeze one exact candidate, run the complete R4 portfolio once, and prepare but
do not execute the stopped-flat deployment.

### Required evidence

| Tier | Proof |
| --- | --- |
| Domain | complete Profile/Binding/time/guard semantic matrix |
| Schema | empty and production-shaped forward migration, preservation, constraints, downgrade rejection |
| Authority | Owner switch, advisory lock, ABA, idempotency and retirement races |
| Claim/Ticket | exact Binding/Profile/version lineage and leg materialization |
| Lifecycle | earliest non-zero exposure boundaries, guards, PRE_TP1/ABSOLUTE, 97-row bound |
| Full chain | Signal → Claim → Ticket → protection → Profile exit → Command → closure |
| Architecture | no YAML, legacy Event resolution, parallel chain or current Binding lifecycle lookup |
| Static | Ruff, repository Mypy, diff check |

### Release commands

Use the existing exact-candidate certification entry point. The final R4
portfolio must include complete Unit/Architecture, Integration, Full-chain,
Ruff, Mypy, diff, Profile/Binding manifest and Migration audit commands.

### Deployment evidence

Prepare:

1. exact source/target revision and release manifest;
2. stopped-and-flat preflight;
3. preservation digest;
4. eight-Profile/eight-Binding postflight;
5. four Worker identity/restart checks;
6. PostgreSQL/Binance zero activity/flatness checks;
7. fix-forward recovery branches;
8. explicit confirmation that no YAML artifact is installed;
9. separate authorities for software deployment, Crypto SOR resume and future
   Profile switch.

### Done

```text
exact clean HEAD
AND R4 manifest status=pass
AND Profile/Binding manifest exact
AND worktree clean
AND deployment runbook reviewable
AND production unchanged
```

### Hard stops

- do not certify an uncommitted worktree;
- any fix creates a new candidate and invalidates the manifest;
- do not push/merge/deploy without the next explicit authority.

### EX-08 Execution Evidence — 2026-08-29

**Status: `EX08_COMPLETE / LOCAL_IMPLEMENTATION_COMPLETE`.** The final local
candidate is identified only by its clean-HEAD R4 manifest; this document does
not copy a mutable candidate SHA. Release classification is **R4** with the
`stopped_flat_forward_upgrade` blocker and Schema target
`0007_exit_profile_authority_v1`.

The complete exact-candidate command set passed Unit/Architecture, PostgreSQL
Integration, Full-chain, Ruff, repository Mypy, diff check, the tracked
961×24 Decimal Golden integrity check, Production SelectionCore parity and the
explicit Migration/Authority/clean-rebuild audit. The Golden artifact-set
digest and all 23,064 member decisions / 961 snapshots remained unchanged;
Golden semantic source identity was narrowed to the actual SOR detector and
SelectionCore while Registry/Exit sources remain research provenance.

Deployment evidence is reviewable in the current Tokyo deployment contract:
exact `0006 -> 0007` source/target identity, Phase A advisory precheck, Phase B
fresh post-fence/post-stop PostgreSQL/Binance reread, preservation digest,
eight-Profile/eight-Binding postflight, four Worker identity checks, zero
runtime activity, zero YAML/YML installation and target-Schema fix-forward
recovery.

The following authorities remain separate and absent:

```text
software_deployment_authority = NONE
crypto_sor_resume_authority = NONE
future_profile_switch_authority = NONE
```

No Tokyo PostgreSQL Migration, systemd action, Strategy resume, Profile switch,
manual flatten or exchange write was executed. The branch remains local and
unmerged until the next explicit integration/deployment decision.

## 16. Required Test Portfolio Maintenance

Tests are not append-only. During implementation:

1. consolidate Event-bound Policy fixtures into Profile/Binding factories;
2. delete tests that preserve `_policy_for_contract()` current authority;
3. retain distinct historical-preservation tests;
4. share lifecycle fact builders instead of duplicating eight strategy fixtures;
5. keep Profile Catalog parity table-driven;
6. review suite duration before EX-08;
7. do not count test quantity as acceptance evidence.

## 17. Migration And Git Discipline

1. branch remains `codex/exit-profile-v1` stacked on `1c57b407`;
2. PR #4 remains frozen;
3. Migration filename stays `NEXT_AFTER_0006` until integration assigns the
   final revision number;
4. if 0006 is not yet merged when code completes, ExitProfile remains a stacked
   candidate and does not target production directly;
5. no merge into `dev` without Owner integration decision;
6. no generated runtime output is committed.

## 18. Stop Conditions

Stop the active Task if:

1. a requirement needs YAML or file-backed runtime authority;
2. EventSpec legacy policy must remain a runtime fallback;
3. active-position handover becomes necessary;
4. Profile content must mutate in place;
5. Ticket cannot freeze Binding authority version;
6. a two-leg plan can pass only by changing the frozen fraction;
7. Profile retirement cannot remain exact-loadable for issued Tickets;
8. Binding write serialization requires a new Worker/lease/distributed lock;
9. Lifecycle requires current Binding or Strategy detector facts;
10. Reducer requires Multi-TP/add/merge behavior;
11. capital/risk/scope expansion becomes necessary;
12. PR #4 identity changes under this branch.

## 19. Final Done Contract

Implementation is complete only when:

```text
Typed Python Catalog is the sole install source
AND PostgreSQL current Binding is the sole new-Claim authority
AND every active EventSpec has exactly one current Binding
AND every retired EventSpec has zero current Binding
AND Profile content is immutable
AND Binding cannot reactivate
AND control-plane writes are advisory-lock serialized
AND Claim/Ticket freeze Binding ID/hash/version and Profile ID/hash
AND Ticket rejects drift/ABA without re-sizing
AND both exit legs satisfy exact venue minimums
AND holding boundaries use final closes strictly after earliest authoritative non-zero exposure
AND Profile guards and TimeStop modes are deterministic
AND Lifecycle uses no current Binding or Strategy detector
AND EventSpec policy ID has zero runtime authority
AND no YAML/YML runtime source exists
AND exact stopped-flat R4 certification passes
```

Production deployment remains separately authorized even after all local Tasks
and R4 certification complete.
