---
title: Terminal Recovery Structural Repair Test Cases
status: IMPLEMENTED_LOCAL_PENDING_TOKYO_RELEASE
authority: NOT_CURRENT_AUTHORITY
date: 2026-07-27
design: 2026-07-27-terminal-recovery-structural-repair-design.md
---

# Terminal Recovery Structural Repair Test Cases

## Purpose

This document defines the complete regression matrix for the repair. The
implemented assertions are marked by the local verification record below;
remaining rows are retained as expansion coverage, not claimed as completed
tests.

## Local Verification Record

- RED observed for frozen cancel namespace/purpose, multi-Incident closure,
  external-flat Review fallback, and purpose/state mismatch.
- Targeted unit and PostgreSQL integration regression suites pass.
- Full local suite: `420 passed` before the final frozen-purpose mapper
  correction; the mapper correction then passed its focused 65-test suite.
- Changed-file Ruff 0.15.0 and production runtime file-I/O audit pass.

Each behavior has one primary observable assertion. Unit tests prove pure
decisions, integration tests prove PostgreSQL and command boundaries, and
full-chain tests prove that no fixture bypasses the real producer path.

## Test Rules

- Use typed in-memory fixtures or disposable PostgreSQL.
- Never call a real exchange.
- Record every venue call and assert endpoint, namespace, identity, and count.
- Use `Decimal` for all quantities and economics.
- Assert both the expected state change and prohibited side effects.
- Run each new test RED before implementation.
- Do not weaken existing unknown-outcome, partial-fill, or release tests.

## Proposed Test Files

| File | Boundary |
| --- | --- |
| `tests/trading_kernel/unit/test_cancel_target.py` | Exact target and purpose invariants |
| `tests/trading_kernel/unit/test_reducer.py` | Event transitions and closure effects |
| `tests/trading_kernel/unit/test_review_economics.py` | Typed Review completeness |
| `tests/trading_kernel/unit/test_reconciliation_worker_review.py` | Visibility and fallback decisions |
| `tests/trading_kernel/unit/test_venue_adapter.py` | One exact cancel endpoint |
| `tests/trading_kernel/integration/test_command_dispatch.py` | Durable command and event mapping |
| `tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py` | Same-namespace unknown recovery |
| `tests/trading_kernel/integration/test_ticket_incident_closure.py` | Atomic multi-Incident resolution |
| `tests/trading_kernel/full_chain/test_terminal_recovery_structural_closure.py` | Production-failure regression |
| `tests/trading_kernel/architecture/test_terminal_recovery_architecture.py` | No fallback, DDL, parallel path, or file authority |

## A. Exact Cancel Identity

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| CAN-001 | Unit/model | Build new cancel target with regular namespace and complete identities | Model is frozen; normalized identities and namespace are retained |
| CAN-002 | Unit/model | Build new cancel target with conditional namespace | Model is frozen and retains `conditional` |
| CAN-003 | Unit/model | Omit exchange order identity | Validation fails |
| CAN-004 | Unit/model | Omit namespace or purpose from a new executable command | Preparation/validation fails |
| CAN-005 | Unit/model | Supply only one of namespace or purpose on historical-shape payload | Validation fails; partial exact identity is forbidden |
| CAN-006 | Unit/model | Parse a terminal historical cancel command without new metadata | Historical record is readable but cannot become claimable |
| CAN-007 | Unit/effect | Prepare partial ENTRY remainder cancellation | Target namespace is `regular`; purpose is `entry_remainder` |
| CAN-008 | Unit/effect | Prepare runner old-stop cancellation | Target namespace is `conditional`; purpose is `runner_old_stop` |
| CAN-009 | Unit/effect | Prepare cleanup of known Initial Stop/TP1/runner residue | Namespace is `conditional`; purpose is `reconciliation_cleanup` |
| CAN-010 | Unit/effect | Prepare cleanup from a regular venue snapshot row | Snapshot namespace is copied exactly; no inference from numeric ID |
| CAN-011 | Unit/effect | Prepare cleanup from a conditional venue snapshot row | Snapshot namespace is copied exactly |
| CAN-012 | Integration/UOW | Commit any new cancel effect | Complete payload commits before adapter invocation |
| CAN-013 | Integration/UOW | Create generation 2 after a rejected or proven-ineffective generation 1 | Namespace, target identities, and purpose equal generation 1 exactly |
| CAN-014 | Unit/dispatch | Dispatch accepted `entry_remainder` while aggregate has a compatible state | Emits only `EntryRemainderCancelConfirmed` |
| CAN-015 | Unit/dispatch | Dispatch accepted `runner_old_stop` | Emits only `ProtectionCancelConfirmed` |
| CAN-016 | Unit/dispatch | Dispatch accepted `reconciliation_cleanup` | Emits only `OwnedOrphanCancelConfirmed` |
| CAN-017 | Unit/dispatch | Frozen purpose contradicts aggregate state | Dispatch result is not mapped; identity contradiction fails closed |
| CAN-018 | Unit/adapter | Execute regular cancel | Exactly one regular cancel call; zero conditional cancel calls |
| CAN-019 | Unit/adapter | Execute conditional cancel | Exactly one conditional cancel call; zero regular cancel calls |
| CAN-020 | Unit/adapter | Regular cancel returns order-not-found | Terminal rejected result; no conditional fallback |
| CAN-021 | Unit/adapter | Conditional cancel returns order-not-found | Terminal rejected result; no regular fallback |
| CAN-022 | Unit/adapter | Exact cancel times out | One call, `OUTCOME_UNKNOWN`, no alternate endpoint call |
| CAN-023 | Unit/adapter | Accepted response identifies another target | Not accepted; identity contradiction enters exact recovery |
| CAN-024 | Unit/truth | Recover unknown regular cancel | Query only regular namespace |
| CAN-025 | Unit/truth | Recover unknown conditional cancel | Query only conditional namespace |
| CAN-026 | Integration/recovery | Target remains open after deadline | Original command becomes proven ineffective; generation 2 is allowed with identical namespace |
| CAN-027 | Integration/recovery | Target is absent after deadline | Command reconciles absent; no retry generation |
| CAN-028 | Integration/cutover | Nonterminal historical cancel lacks metadata | Release preflight fails before service stop |
| CAN-029 | Integration/cutover | Only terminal historical cancel rows lack metadata | Release preflight passes this gate; rows remain non-executable |

## B. Atomic Multi-Incident Closure

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| INC-001 | Integration/repository | Open two Incident kinds for one Ticket and list them | Exact bounded query returns both identities |
| INC-002 | Integration/repository | Open duplicate Incident kinds for one Ticket | Both rows remain independently addressable |
| INC-003 | Unit/reducer | Apply `ReconciliationMatched` after complete closure proof | Emits Incident-closure effect before capital-release effect |
| INC-004 | Unit/reducer | Known cleanup order remains | Transition is rejected; no closure or release effect |
| INC-005 | Unit/reducer | Pending cancel identity remains | Transition is rejected |
| INC-006 | Application | Ticket command remains `OUTCOME_UNKNOWN` | Reconciliation does not emit `ReconciliationMatched` |
| INC-007 | Integration/UOW | One Ticket has post-fill risk and external-flat Incidents | Both resolve in the same commit |
| INC-008 | Integration/UOW | One Ticket has two Incidents with the same kind | Both resolve in the same commit |
| INC-009 | Integration/UOW | Ticket has no open Incident | Match and release remain valid and idempotent |
| INC-010 | Integration/UOW | Exact Ticket plus another Ticket each have Incidents | Only the matched Ticket rows resolve |
| INC-011 | Integration/UOW | Runtime-global Incident has `ticket_id = NULL` | Runtime Incident remains open |
| INC-012 | Integration/UOW | Inject failure while resolving one Incident | Event, aggregate, all resolutions, budget, capacity, and domain release all roll back |
| INC-013 | Integration/UOW | Inject failure while releasing budget after Incident update | Incident updates roll back with the transaction |
| INC-014 | Integration/UOW | Successful match resolves Incidents and releases authority | No instant exists with authority released while a Ticket Incident is open |
| INC-015 | Integration/idempotence | Run reconciliation twice after a successful match | No second release, event, or Incident mutation |
| INC-016 | Integration/admission | Account-capacity Incident is the final blocker | New ENTRY remains blocked before match and unblocks only after atomic closure |
| INC-017 | Projection | Read resolved Incident history | Original kind, opening event, resolution event, and timestamps remain auditable |

## C. External-Flat Review

| ID | Layer | Setup/action | Required assertions |
| --- | --- | --- | --- |
| REV-001 | Unit/model | Calculate complete exact economics | Existing `complete` result is unchanged |
| REV-002 | Unit/model | Exact fills exist but funding is not attributable | Existing `funding_unavailable` result is unchanged |
| REV-003 | Unit/model | Build external-exit-unavailable metrics | Completeness and reason are required; strategy eligibility is false |
| REV-004 | Unit/model | Add zero or nonzero PnL/R fields to unavailable metrics | Validation fails because unavailable is not zero economics |
| REV-005 | Unit/model | Omit external-flat event time or visibility deadline | Validation fails |
| REV-006 | Unit/worker | External flat, no exit fills, current time before deadline | No Review; next check is scheduled |
| REV-007 | Unit/worker | Exact fills appear before deadline | Complete Review is recorded |
| REV-008 | Unit/worker | External flat, no exit fills, current time equals deadline | External-exit-unavailable Review is recorded |
| REV-009 | Unit/worker | External flat, no exit fills, current time after deadline | Same unavailable Review is recorded |
| REV-010 | Unit/worker | External flat has only a partial attributable exit fill set after deadline | Review is unavailable; no partial PnL or R is persisted |
| REV-011 | Unit/worker | Kernel-commanded exit has no fills after deadline | No unavailable Review; explicit Review Incident remains fail-closed |
| REV-012 | Unit/worker | Exit facts contain Ticket, instrument, side, quantity, or client identity contradiction | No Review; identity Incident opens |
| REV-013 | Unit/worker | Review economics source is temporarily unavailable before deadline | Retry only; no Incident or thin Review |
| REV-014 | Unit/worker | Review economics source fails after deadline for an external-flat Ticket without contradictory facts | Honest unavailable Review |
| REV-015 | Integration/application | Call Review use case with arbitrary free-form thin metrics | Typed boundary rejects the request |
| REV-016 | Integration/application | Record valid unavailable Review twice | One deterministic Review and one `ReviewRecorded` event |
| REV-017 | Projection | Project unavailable Review to Owner state | Displays unavailable reason; no zero PnL/R fields |
| REV-018 | Projection | Feed unavailable Review into strategy evidence | Excluded from payoff, expectancy, win-rate, and R calculations |
| REV-019 | Projection | Feed unavailable Review into lifecycle evidence | Included in closure and reliability counts |
| REV-020 | Integration/worker | Two Review-pending Tickets exist | One bounded Ticket is processed per tick; scheduling remains fair |

## D. Full-Chain Regressions

| ID | Scenario | Required chain and assertions |
| --- | --- | --- |
| CHN-001 | July 27 unknown conditional cancel | Durable conditional cancel generation 1 -> timeout -> same-namespace truth shows target open -> generation 2 -> one conditional cancel -> target absent -> all Incidents resolved -> budget/domain released -> Settlement -> Review |
| CHN-002 | Partial ENTRY regular cancel | Partial fill -> durable regular remainder cancel -> exactly one regular endpoint -> flatten -> flat/order-free -> all Incidents resolved |
| CHN-003 | Post-fill degraded plus external flat | Post-fill risk Incident -> Initial Stop -> external flat Incident -> exact conditional cleanup -> both Incidents resolve atomically -> unavailable Review after deadline |
| CHN-004 | Duplicate same-kind Incidents from historical fault injection | Two exact rows -> flat/order-free proof -> both resolved without DML -> terminal Review |
| CHN-005 | Accepted cancel but contradictory residual truth | No blind alternate cancel; residue blocks release and enters explicit recovery |
| CHN-006 | Two independent protected Tickets | One Ticket's cancel/recovery/Incident closure never mutates the other Ticket |
| CHN-007 | Runtime Incident plus terminal Ticket Incidents | Ticket Incidents close; runtime Incident continues to fence Entry |
| CHN-008 | Normal owned EXIT | Existing exact complete economics path remains complete and strategy-eligible |

Every full-chain case must assert:

```text
one Exposure Episode owns one Ticket
one ENTRY generation only
no exchange mutation before durable command
no mutation endpoint fallback
no unresolved command outcome
exchange-flat position
zero residual order
released budget and Netting Domain
zero open Ticket Incident
Settlement complete
Review complete or explicitly unavailable
no fabricated economics
```

## E. Architecture, Persistence, And Deployment

| ID | Boundary | Required assertions |
| --- | --- | --- |
| ARC-001 | Source scan | No regular-to-conditional cancel fallback remains |
| ARC-002 | Source scan | Dispatch does not infer cancel purpose from aggregate status or order-ID membership |
| ARC-003 | Source scan | No new recovery service, timer, table, migration generation, report file, or alternate chain |
| ARC-004 | Domain audit | Domain models remain pure, frozen, and `Decimal`-based |
| ARC-005 | Transaction audit | Venue I/O remains outside database transactions |
| ARC-006 | Command audit | Every cancel mutation originates from one durable command |
| ARC-007 | Schema audit | Clean baseline remains the single `0001_initial` migration and 33-table schema |
| ARC-008 | File-I/O audit | Healthy cadence creates zero Markdown/JSON/runtime report files |
| DEP-001 | Target preflight | Nonterminal legacy cancel command blocks release |
| DEP-002 | Target preflight | Unknown command outcome blocks release |
| DEP-003 | Service order | Safety workers start before Entry |
| DEP-004 | Postflight | Exact commit/schema/services plus position/order/Incident/Review facts agree |
| DEP-005 | Fix-forward | After a new payload is persisted, old release is not selected as rollback authority |

## F. Required RED Sequence

The approved implementation starts with failing tests in this order:

1. `CAN-018`, `CAN-019`, and `CAN-022` prove the current two-endpoint adapter is
   wrong.
2. `CAN-014` through `CAN-017` prove mutable-state purpose inference is wrong.
3. `INC-007`, `INC-008`, and `INC-014` prove single-Incident closure is wrong.
4. `REV-008`, `REV-011`, and `REV-015` prove manual Review closure and
   free-form metrics are wrong.
5. `CHN-001` and `CHN-003` prove the complete production-failure sequences are
   not yet closed.

Each test must fail for the intended missing behavior before production code is
changed.

## G. Verification Commands

Targeted verification:

```bash
python3 -m pytest -q \
  tests/trading_kernel/unit/test_cancel_target.py \
  tests/trading_kernel/unit/test_reducer.py \
  tests/trading_kernel/unit/test_review_economics.py \
  tests/trading_kernel/unit/test_reconciliation_worker_review.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/integration/test_command_dispatch.py \
  tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py \
  tests/trading_kernel/integration/test_ticket_incident_closure.py \
  tests/trading_kernel/full_chain/test_terminal_recovery_structural_closure.py
```

Final local certification:

```bash
python3 -m pytest -q tests/trading_kernel
python3 -m ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
python3 -m mypy src/trading_kernel
python3 scripts/trading_kernel/audit_production_file_io.py
git diff --check
```

Database certification must also rebuild the disposable PostgreSQL schema from
`0001_initial`, verify the expected table set, and repeat the existing
downgrade/upgrade checks.

## H. Completion Evidence

The implementation may claim completion only with:

- the RED evidence for every new behavioral family;
- all listed tests green with exact counts;
- one full-chain proof for each of `CHN-001` through `CHN-008`;
- zero skipped tests in the new repair suite;
- Ruff, Mypy, schema, architecture, and file-I/O audits green;
- reviewed diff showing no DDL, runtime DML path, fallback endpoint, parallel
  execution path, or generated runtime output; the separately guarded one-time
  reset script is reviewed as deployment-only DML;
- current Tokyo readonly evidence only after separate deployment authority.
