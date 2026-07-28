---
title: TP1 Runner And Protected Handover Structural Repair Test Cases
status: LOCAL_ACCEPTED_DEPLOYMENT_PENDING
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-28
revision: 3
design: 2026-07-28-tp1-runner-and-protected-handover-structural-repair-design.md
---

# TP1 Runner And Protected Handover Structural Repair Test Cases

## Purpose

This document converts the approved target behavior into executable
assertions. Existing green behavior is retained as characterization coverage.
Missing structural behavior must be observed RED before production code changes.
The inventory contains 102 cases across lifecycle, deployment, persistence,
full-chain, architecture, and canonical-only compatibility boundaries.

No test in this suite may call a real exchange or change Tokyo state.

## Test Rules

- Use frozen typed fixtures and `Decimal`.
- Use disposable PostgreSQL for transaction and persistence assertions.
- Assert the required state and prohibited side effects.
- Record every fake venue call and assert identity, namespace, and count.
- Do not infer full-chain success from a reducer-only fixture.
- Run every new behavioral family RED before implementation.
- Do not mark expected RED tests as `xfail` or skip them.
- Keep Entry, unknown-outcome, partial-fill, and Runtime Fence semantics intact.
- Reject noncanonical historical state; never test or implement translation,
  fallback, synthetic backfill, dual read, or dual write as success behavior.

## Proposed Test Files

| File | Boundary |
| --- | --- |
| `tests/trading_kernel/unit/test_venue_adapter.py` | Exact TP1 and protected-order truth |
| `tests/trading_kernel/unit/test_deploy_tokyo_release.py` | Handover plan and phase behavior |
| `tests/trading_kernel/unit/test_production_runtime.py` | Exact protected manifest output |
| `tests/trading_kernel/unit/test_reducer.py` | TP1, replacement, cancel, and monotonic Runner |
| `tests/trading_kernel/integration/test_runtime_fact_workers.py` | Worker-owned TP1-to-Runner chain |
| `tests/trading_kernel/integration/test_runtime_authority_seed.py` | Exact Reservation and Exposure gate |
| `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py` | Restart-safe Event and Runner movement |
| `tests/trading_kernel/full_chain/test_tp1_runner_structural_closure.py` | Producer-to-Review lifecycle |
| `tests/trading_kernel/architecture/test_event_registry_parity.py` | Persisted Event completeness |
| `tests/trading_kernel/architecture/test_protected_handover_architecture.py` | No replay option, DDL, or alternate path |

## A. Exact TP1 Truth

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| TP1-001 | Unit/adapter | Persisted TP1 exchange order is fully filled | Exact ID is queried; filled quantity and average price are returned |
| TP1-002 | Unit/adapter | User-trade rows omit parent clientOrderId | Exact order lookup still proves the fill |
| TP1-003 | Unit/adapter | TP1 order is open and unfilled | Quantity is zero; no average fill price |
| TP1-004 | Unit/adapter | TP1 order is partially filled | Exact partial quantity is returned for fail-closed application handling |
| TP1-005 | Unit/adapter | Filled quantity is positive but average price is absent | Fact collection fails; no lifecycle mutation |
| TP1-006 | Application | TP1 quantity is zero | `NO_CHANGE`; no Event or replacement command |
| TP1-007 | Application | TP1 quantity is between zero and target | Reject unsupported partial TP1; old Stop remains active |
| TP1-008 | Application | TP1 full fill but venue runner quantity differs | Reconciliation required; no `TakeProfitFilled` |
| TP1-009 | Application | TP1 full fill and remaining quantity matches | Exactly one `TakeProfitFilled` commits |
| TP1-010 | Idempotence | Same full-fill facts repeat after commit | No duplicate `TakeProfitFilled` or replacement generation |

## B. Break-Even Replacement

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| BE-001 | Unit/domain | Long TP1 completes | Cost-adjusted floor is tick-rounded upward |
| BE-002 | Unit/domain | Short TP1 completes | Cost-adjusted floor is tick-rounded downward |
| BE-003 | Integration/UOW | Commit `TakeProfitFilled` | Aggregate quantity becomes runner quantity and one durable replacement commits atomically |
| BE-004 | Integration/dispatch | New Stop is accepted | Exact new order identity, runner quantity, floor price, and old order identity are recorded |
| BE-005 | Integration/dispatch | New Stop is rejected | Old Stop remains active; no cancel command |
| BE-006 | Integration/dispatch | New Stop outcome is unknown | Old Stop remains active; no cancel; unknown recovery owns progress |
| BE-007 | Integration/dispatch | New Stop is confirmed | Only then is exact old conditional Stop cancel prepared |
| BE-008 | Integration/dispatch | Old Stop cancel is rejected | New Stop remains active and Ticket does not lose protection |
| BE-009 | Integration/dispatch | Old Stop cancel outcome is unknown | Exact old ID and conditional namespace are retained |
| BE-010 | Integration/dispatch | Old Stop absence is confirmed | Aggregate reaches `runner_protected` |
| BE-011 | Safety | Any failure occurs before new Stop confirmation | Last confirmed Stop is never cancelled |

## C. Runner Tracking

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| RUN-001 | Unit/policy | Long closed-candle candidate improves Stop | One `RunnerStopRequested` with higher Stop |
| RUN-002 | Unit/policy | Short closed-candle candidate improves Stop | One `RunnerStopRequested` with lower Stop |
| RUN-003 | Unit/policy | Candidate does not improve by one tick | No command |
| RUN-004 | Unit/policy | Candle is not closed | No command |
| RUN-005 | Unit/policy | Candle watermark repeats | No duplicate Event or command |
| RUN-006 | Unit/adapter | Latest candle is open | It is excluded while a complete ATR/structure window remains |
| RUN-007 | Unit/adapter | ATR/structure window is still insufficient | Keep old Stop; fact read fails closed |
| RUN-008 | Integration/UOW | Runner movement commits | Event and durable replacement generation commit atomically |
| RUN-009 | Integration/restart | Process reloads after `RunnerStopRequested` | Event deserializes and Aggregate reconstructs |
| RUN-010 | Integration/restart | Same worker tick repeats after restart | No duplicate generation |
| RUN-011 | Multi-position | Two independent runners are actionable | One Ticket movement does not mutate the other |
| RUN-012 | Safety | Position quantity differs from Aggregate runner | Reconciliation required; no replacement |

## D. Full Normal Lifecycle

| ID | Scenario | Required chain and assertions |
| --- | --- | --- |
| CHN-001 | Natural long TP1 and Runner | Worker-produced ENTRY -> Initial Stop -> TP1 -> exact full fill -> break-even replacement -> old Stop cancel -> `runner_protected` -> higher closed-candle Stop |
| CHN-002 | Natural short TP1 and Runner | Same chain with short-side rounding and monotonically lower Stop |
| CHN-003 | Replacement rejection | TP1 recorded, old Stop retained, no unprotected interval, Incident visible |
| CHN-004 | Replacement unknown outcome | No blind resend or old-Stop cancel before exact recovery |
| CHN-005 | Final runner exit | Position flat -> residual orders absent -> budget/domain release -> Settlement -> Review |
| CHN-006 | Restart between every phase | Each persisted Event reloads; no duplicate command generation |
| CHN-007 | Two Tickets | Independent domains progress concurrently while Entry remains globally serialized |

Every full-chain case asserts:

```text
one Exposure Episode -> one Ticket
one ENTRY generation
every exchange mutation has a durable command
exact TP1 target and remaining quantity
new Stop before old-Stop cancel
one active runner protection generation after convergence
no unresolved command outcome
no open Ticket Incident at terminal closure
released Budget Reservation and Netting Domain
Settlement and Review preserve exact economics
```

## E. Protected Deployment Plan

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| DEP-001 | Unit/model | Protected Tickets plus `enable_entry=True` | Plan validation rejects before release installation |
| DEP-002 | Unit/CLI | Pass protected IDs and `--enable-entry` | CLI exits before SSH/backend construction |
| DEP-003 | Unit/model | TP1 replay deployment argument is supplied | Parser rejects because the option no longer exists |
| DEP-004 | Unit/flow | Protected postflight succeeds | All workers remain stopped through exact target certification |
| DEP-005 | Unit/flow | Protected target certification fails | Lifecycle and Reconciliation are not started |
| DEP-006 | Unit/flow | Failure occurs before identity rotation | Source safety workers restart only after source re-certification |
| DEP-007 | Unit/flow | Failure occurs after identity rotation | No old or target mutating worker starts; Entry fence remains |
| DEP-008 | Unit/flow | Safety service start is partial | Partial set is stopped and deployment fails closed |
| DEP-009 | Unit/flow | Protected handover succeeds | Observation, Lifecycle, Reconciliation start; Entry remains inactive |
| DEP-010 | Unit/flow | Regular flat release succeeds with explicit Entry | Existing Entry-last behavior remains unchanged |

## F. Exact Exchange Handover Manifest

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| EXT-001 | Unit/model | Complete `position_protected` Ticket | Exact position, full Stop, and TP1 identities are retained |
| EXT-002 | Unit/model | Complete `runner_protected` Ticket | Exact runner position and one active Runner Stop are retained |
| EXT-003 | Certification | Correct counts but wrong Netting Domains | Handover fails |
| EXT-004 | Certification | Correct domain count but `position_protected` TP1 is absent | Handover fails |
| EXT-005 | Certification | Stop ID differs from Aggregate | Handover fails |
| EXT-006 | Certification | Stop quantity is larger or smaller than protected quantity | Handover fails |
| EXT-007 | Certification | Stop is not reduce-only or uses regular namespace | Handover fails |
| EXT-008 | Certification | Stop side or trigger price contradicts Ticket | Handover fails |
| EXT-009 | Certification | Runner retains old Stop in addition to current Stop | Handover fails |
| EXT-010 | Certification | Unowned extra position or order exists | Handover fails |
| EXT-011 | Certification | Exact manifest is complete | Semantic digest is deterministic and excludes credentials |
| EXT-012 | Freshness | Manifest expires before service stop | Handover repeats certification; stale facts cannot rotate identity |

## G. PostgreSQL Handover Exactness

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| DB-001 | Integration | Named Ticket lacks active Reservation | Identity rotation is refused |
| DB-002 | Integration | Extra active Reservation belongs to another Ticket | Identity rotation is refused |
| DB-003 | Integration | Reservation notional differs from Ticket | Identity rotation is refused |
| DB-004 | Integration | Reservation risk, margin, policy, venue, or account differs | Identity rotation is refused |
| DB-005 | Integration | Account Exposure Ticket count differs | Identity rotation is refused |
| DB-006 | Integration | Account Exposure notional differs from active Ticket sum | Identity rotation is refused |
| DB-007 | Integration | Account Exposure risk differs from active Ticket sum | Identity rotation is refused |
| DB-008 | Integration | Active domain key is absent or duplicated | Identity rotation is refused |
| DB-009 | Integration | Position projection belongs to no Ticket | Identity rotation is refused |
| DB-010 | Integration | Aggregate has a pending replacement or cancel | Identity rotation is refused |
| DB-011 | Integration | Entry lane is not idle | Identity rotation is refused |
| DB-012 | Integration | Command is prepared, claimed, dispatch-started, or unknown | Identity rotation is refused |
| DB-013 | Integration | Ticket or runtime Incident is unresolved | Identity rotation is refused |
| DB-014 | Integration | Every exact row agrees | Only runtime and capability commit identities rotate |
| DB-015 | Transaction | Inject failure during identity update | All identity rows roll back |

## H. Event Persistence

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| EVT-001 | Architecture | Compare `TradeEvent` union and PostgreSQL registry | Exact type-name sets are equal |
| EVT-002 | Architecture | Add duplicate persisted event name | Audit fails |
| EVT-003 | Integration | Append and reload every registered Event fixture | Every Event round-trips to the same type and payload |
| EVT-004 | Integration | Persist unknown event type by fault injection | Repository fails closed with exact diagnostic |
| EVT-005 | Integration | Append `RunnerStopRequested` then run next Lifecycle tick | Worker remains healthy and progresses |

## I. Architecture And Persistence

| ID | Boundary | Required assertions |
| --- | --- | --- |
| ARC-001 | Source scan | No `tp1_replay_ticket_ids` production surface remains |
| ARC-002 | Source scan | Protected handover has no path that starts Entry |
| ARC-003 | Source scan | Count-only exchange facts cannot authorize protected handover |
| ARC-004 | Source scan | No worker starts before target protected certification |
| ARC-005 | Domain audit | Domain remains pure, frozen, and Decimal-based |
| ARC-006 | Transaction audit | Venue I/O occurs outside database transactions |
| ARC-007 | Command audit | Every Stop placement and cancel originates from a durable command |
| ARC-008 | Schema audit | No migration is added; baseline remains `0001_initial` and 33 tables |
| ARC-009 | Runtime audit | No new service, timer, report file, or second execution chain |
| ARC-010 | File-I/O audit | Healthy no-op cadence creates zero Markdown/JSON files |

## J. No Compatibility Or Glue Layer

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| CMP-001 | Unit/model | Supply the removed TP1 replay CLI option or an alias | Parser rejects it; no replacement recovery flag exists |
| CMP-002 | Integration | Active Ticket uses a noncanonical Aggregate status | Handover is refused; status is not translated |
| CMP-003 | Integration | Canonical Reservation or Exposure fact is absent | Handover is refused; no row is inferred or synthesized |
| CMP-004 | Persistence | Event stream contains an unknown retired Event type | Reload/certification fails closed; no current Event is fabricated |
| CMP-005 | Venue | Persisted order namespace contradicts exchange truth | Exact lookup fails; no regular-to-conditional or conditional-to-regular fallback |
| CMP-006 | Architecture | Scan production module names and imports | No `legacy`, `compat`, or `compatibility` package/module is introduced |
| CMP-007 | Architecture | Inspect changed persistence paths | No old-table reader, old-column alias, schema fallback, dual read, or dual write |
| CMP-008 | Side-effect | Build protected handover manifest | Zero database writes, Events, commands, files, or exchange mutations |
| CMP-009 | Full chain | Canonical current Ticket completes TP1 and starts Runner | Uses only the existing Lifecycle, reducer, UOW, and command dispatcher |
| CMP-010 | Full chain | Noncanonical active Ticket is presented to target release | Release remains blocked until source convergence or terminal flatness |

## Required RED Sequence

The first implementation cycle runs these tests before production edits:

1. `DEP-001`, proving protected handover can currently enable Entry.
2. `DEP-005`, proving failed protected postflight currently starts Lifecycle.
3. `EXT-003` and `EXT-004`, proving count equality is not exact protection
   evidence.
4. `DB-001`, `DB-006`, and `DB-007`, proving Reservation and Exposure gates
   are incomplete.
5. `EVT-001`, establishing permanent Event registry parity.
6. `ARC-001`, proving the generic TP1 replay deployment option remains.
7. `CMP-001` through `CMP-010`, proving the repair rejects historical
   incompatibility rather than creating glue.

`CHN-001`, `RUN-006`, and existing exact TP1 order tests are expected to be
green characterization tests. They protect the already-correct business chain
while structural repairs are implemented.

## Verification Commands

Focused no-database tests:

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_deploy_tokyo_release.py \
  tests/trading_kernel/unit/test_production_runtime.py \
  tests/trading_kernel/architecture/test_event_registry_parity.py \
  tests/trading_kernel/architecture/test_protected_handover_architecture.py
```

PostgreSQL and lifecycle integration:

```bash
uv run pytest -q \
  tests/trading_kernel/integration/test_runtime_authority_seed.py \
  tests/trading_kernel/integration/test_runtime_fact_workers.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/full_chain/test_ticket_lifecycle.py \
  tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py
```

Final implementation certification:

```bash
uv run pytest -q tests/trading_kernel
uvx ruff check --select E4,E7,E9,F src/trading_kernel tests/trading_kernel scripts/trading_kernel
uvx --with-requirements requirements-dev.txt mypy src/trading_kernel
uv run python scripts/audit_production_runtime_file_io.py
git diff --check
```

Disposable PostgreSQL verification must rebuild the `0001_initial` baseline,
verify the exact 33-table allowlist, and leave no test database behind.

## Local Implementation Record

Recorded locally on 2026-07-28 after implementation, before deployment:

| Suite | Result | Meaning |
| --- | --- | --- |
| Full Trading Kernel suite | **440 GREEN** | Architecture, full-chain, PostgreSQL integration, unit, TP1, Runner, and protected-handover coverage pass |
| Focused protected lifecycle suite | **47 GREEN** | Exact Ticket manifest, wrong Stop price, Reservation, Exposure, TP1/Runner, and canonical-event checks pass |
| Static syntax/lint | **GREEN** | `py_compile`, `E4/E7/E9/F` Ruff, diff whitespace, and runtime file-I/O audit pass |
| Type checking | **Baseline debt only** | Isolated Mypy reports 34 pre-existing errors in unrelated modules; no error is attributed to this repair |

The original seven RED acceptance tests now pass through production
implementation. They were not marked `xfail`, skipped, weakened, or replaced
with a compatibility branch.

## Completion Evidence

Implementation may claim completion only with:

- recorded RED output for every missing behavioral family;
- all listed tests green with exact counts and zero new skips;
- full-chain proof for long, short, rejection, unknown, restart, and terminal
  closure scenarios;
- exact Event registry parity;
- Ruff, Mypy, schema, architecture, and file-I/O audits green;
- reviewed diff proving no DDL, direct business-state DML, replay deployment
  exception, Entry-capable protected handover, alternate execution chain, or
  generated runtime authority;
- reviewed diff and architecture tests proving no compatibility module, legacy
  reader, old-field alias, schema/namespace fallback, synthetic Event,
  dual-read, or dual-write path;
- separate Owner authorization before any Tokyo deployment or exchange write.
