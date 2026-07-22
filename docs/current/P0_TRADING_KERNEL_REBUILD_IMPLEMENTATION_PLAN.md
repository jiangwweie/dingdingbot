---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: ACTIVE
authority: docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md
program_id: P0-TKR
design: docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md
last_verified: 2026-07-22
---

# P0 Trading Kernel Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:test-driven-development` for every production behavior and
> `superpowers:verification-before-completion` before any completion claim.
> Execute tasks serially because they replace one shared execution authority.

**Goal:** Replace the three existing execution generations with one isolated,
multi-position Ticket trading kernel, one clean PostgreSQL baseline, and one
certified Tokyo runtime that completes a controlled real-funds lifecycle.

**Architecture:** Build the new kernel under `src/trading_kernel` without old
execution imports. Model one Ticket/TradeAggregate per Exposure Episode, persist
durable ExchangeCommands and TradeEvents, and keep new ENTRY globally
serialized while existing Ticket lifecycle work runs concurrently. After full
offline certification, delete the old code/schema and perform one destructive
flat-state cutover.

**Tech Stack:** Python 3.10+, Pydantic 2, `decimal.Decimal`, SQLAlchemy 2,
PostgreSQL, Alembic, pytest, pytest-asyncio, CCXT through one typed venue port,
systemd on Tokyo.

## Global Constraints

- Owner policy and live scope do not expand during the rebuild.
- New code must not import old execution/application services.
- Domain code must not import SQLAlchemy, CCXT, filesystem, subprocess, or web
  frameworks.
- No production code is written before a failing test is observed.
- No production PG/file dual authority or JSON/Markdown runtime source.
- No ENTRY retry after authoritative rejection.
- No add-to-position capability.
- A reported partial ENTRY fill is an incident and controlled-flatten path, not
  a normal lifecycle.
- One active Ticket per `venue + account + instrument + position_side`.
- Long and short are separate Netting Domains and may coexist.
- One global new-ENTRY claim; existing lifecycle work remains concurrent.
- All external writes require durable command identity and official gates.
- Production no-signal ticks create zero JSON/Markdown files.
- Cutover requires exchange-flat, no orders, no protection residue, and all old
  writers stopped.

---

## File Structure

### New production package

```text
src/trading_kernel/
  __init__.py
  domain/
    __init__.py
    identities.py
    ticket.py
    aggregate.py
    events.py
    commands.py
    effects.py
    position.py
    incident.py
    reducer.py
  application/
    __init__.py
    ports.py
    issue_ticket.py
    advance_ticket.py
    dispatch_exchange_command.py
    reconcile_ticket.py
    settle_ticket.py
    runtime.py
  infrastructure/
    __init__.py
    pg_models.py
    pg_unit_of_work.py
    pg_repositories.py
    venue_adapter.py
    runtime_bootstrap.py
  interfaces/
    __init__.py
    worker.py
    readonly_api.py
```

### New tests

```text
tests/trading_kernel/unit/
tests/trading_kernel/integration/
tests/trading_kernel/full_chain/
```

### New schema and operations

```text
migrations/trading_kernel/
scripts/trading_kernel/bootstrap_schema.py
scripts/trading_kernel/verify_schema.py
scripts/trading_kernel/verify_flat_cutover.py
scripts/trading_kernel/run_worker_once.py
scripts/trading_kernel/certify_readonly.py
scripts/trading_kernel/cutover_tokyo.py
```

## Task 1: Freeze New Domain Identity

**Files:**

- Create: `src/trading_kernel/domain/identities.py`
- Create: `src/trading_kernel/domain/__init__.py`
- Create: `src/trading_kernel/__init__.py`
- Test: `tests/trading_kernel/unit/test_identities.py`

**Interfaces:**

- Produces `NettingDomain`, `TicketIdentity`, and `RuntimeIdentity` frozen
  Pydantic models.
- `NettingDomain.key() -> str` is the canonical active-domain uniqueness key.

- [ ] Write a failing test proving long and short produce different Netting
  Domain keys while identical identities produce the same key.
- [ ] Run `pytest tests/trading_kernel/unit/test_identities.py -q` and observe
  import failure for the missing production module.
- [ ] Implement the minimal frozen models with `extra="forbid"`, explicit
  non-empty string validation, and `Literal["long", "short"]` position side.
- [ ] Run the test and require a clean pass.
- [ ] Add a failing test proving blank identifiers and unsupported position side
  are rejected.
- [ ] Implement only the required validation and rerun the test.
- [ ] Commit with `feat(kernel): define canonical trading identities`.

Expected public shape:

```python
class NettingDomain(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]

    def key(self) -> str: ...
```

## Task 2: Define Immutable Trade Ticket

**Files:**

- Create: `src/trading_kernel/domain/ticket.py`
- Test: `tests/trading_kernel/unit/test_ticket.py`

**Interfaces:**

- Consumes `TicketIdentity` and `NettingDomain`.
- Produces `TradeTicket`, `TicketStatus`, and `TicketDecisionDigest`.
- `TradeTicket` contains the complete frozen post-Action-Time execution
  decision; downstream code must not reconstruct policy or sizing.

- [ ] Write a failing test constructing one valid immutable Ticket with Decimal
  quantity/notional/risk values and exact policy/fact/version references.
- [ ] Run the test and confirm missing module/type failure.
- [ ] Implement the minimal Pydantic Ticket and enums.
- [ ] Run the test and require pass.
- [ ] Add failing tests for non-positive quantity, missing deadline, deadline not
  after creation, and mutation attempts.
- [ ] Implement validation and rerun.
- [ ] Add a failing test proving one Signal ID cannot be represented twice with
  different Ticket identity under the same deterministic Ticket ID builder.
- [ ] Implement `build_ticket_id(...) -> str` from the frozen causal identity.
- [ ] Commit with `feat(kernel): add immutable trade ticket`.

## Task 3: Define Aggregate, Events, Effects, And Reducer

**Files:**

- Create: `src/trading_kernel/domain/aggregate.py`
- Create: `src/trading_kernel/domain/events.py`
- Create: `src/trading_kernel/domain/effects.py`
- Create: `src/trading_kernel/domain/reducer.py`
- Test: `tests/trading_kernel/unit/test_reducer.py`

**Interfaces:**

- Produces `TradeAggregate`, typed `TradeEvent` variants, typed `KernelEffect`
  variants, and `reduce_event(current, event) -> Reduction`.
- `Reduction` contains one new aggregate plus zero or more typed effects.

- [ ] Write a failing test for `TicketIssued -> entry_pending` and one
  `PrepareEntryCommand` effect.
- [ ] Observe RED, then implement the minimum reducer branch.
- [ ] Add one failing test per accepted transition: authoritative ENTRY
  acceptance, full fill, protection confirmation, exit request, flat position,
  reconciliation match, settlement, and terminal review.
- [ ] Implement one transition at a time and run only the relevant test after
  each change.
- [ ] Add failing negative tests for adding to a position, same-domain second
  active Ticket, status regression, stale aggregate version, and post-terminal
  mutation.
- [ ] Implement fail-closed errors without generic exception swallowing.
- [ ] Add a failing partial-fill test requiring `OpenIncident`,
  `CancelEntryRemainder`, and `RequestControlledFlatten` effects rather than a
  normal position-management state.
- [ ] Implement the abnormal partial-fill transition.
- [ ] Commit with `feat(kernel): add deterministic lifecycle reducer`.

## Task 4: Define Durable Exchange Commands

**Files:**

- Create: `src/trading_kernel/domain/commands.py`
- Test: `tests/trading_kernel/unit/test_commands.py`

**Interfaces:**

- Produces `ExchangeCommand`, `ExchangeCommandKind`, `ExchangeCommandStatus`,
  `ExchangeCommandResult`, and deterministic client-order identity.
- Command kinds cover all venue writes; no separate recovery/runner/orphan
  command tables are permitted.

- [ ] Write a failing deterministic identity test.
- [ ] Implement minimal immutable command models.
- [ ] Add failing tests for unique Ticket/role/generation identity, no ENTRY
  generation after authoritative rejection, and blocked generation after
  unknown outcome.
- [ ] Implement validations.
- [ ] Add failing tests proving EXIT/protection recovery may create a new
  generation while ENTRY may not retry.
- [ ] Implement the explicit command-generation policy.
- [ ] Commit with `feat(kernel): define durable exchange commands`.

## Task 5: Create The Clean PostgreSQL Baseline

**Files:**

- Create: `src/trading_kernel/infrastructure/pg_models.py`
- Create: `migrations/trading_kernel/alembic.ini`
- Create: `migrations/trading_kernel/env.py`
- Create: `migrations/trading_kernel/versions/0001_initial.py`
- Create: `scripts/trading_kernel/bootstrap_schema.py`
- Test: `tests/trading_kernel/integration/test_schema_baseline.py`

**Interfaces:**

- Produces the exact target tables from the design and a single baseline
  revision `0001`.
- Uses typed columns for stable identity/state and JSONB only for bounded
  extensible metadata.

- [ ] Write a PostgreSQL integration test that creates an empty schema, upgrades
  to head, and asserts the exact table allowlist.
- [ ] Run with the disposable PostgreSQL fixture and observe RED because the new
  migration environment is absent.
- [ ] Implement the baseline migration and ORM/Core metadata.
- [ ] Rerun and require the exact table set.
- [ ] Add failing constraint tests for one active Ticket per Netting Domain,
  unique Signal-to-Ticket, command idempotency, positive Decimal quantities,
  monotonic aggregate version, and event sequence uniqueness.
- [ ] Add the constraints and rerun.
- [ ] Add a downgrade/re-upgrade test on the disposable database.
- [ ] Commit with `feat(kernel): add clean postgres baseline`.

## Task 6: Implement Unit Of Work And Repositories

**Files:**

- Create: `src/trading_kernel/application/ports.py`
- Create: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Create: `src/trading_kernel/infrastructure/pg_repositories.py`
- Test: `tests/trading_kernel/integration/test_pg_unit_of_work.py`

**Interfaces:**

- Produces `KernelUnitOfWork`, `TicketRepository`, `AggregateRepository`,
  `EventRepository`, `ExchangeCommandRepository`, `BudgetRepository`, and
  `IncidentRepository` protocols plus PostgreSQL implementations.
- One `commit_reduction(...)` transaction appends events, updates current
  aggregate, and materializes effects atomically.

- [ ] Write a failing integration test proving one reduction commits Ticket,
  Aggregate, Event, and Command atomically.
- [ ] Implement the smallest transaction path.
- [ ] Add a failing rollback test that injects an event uniqueness failure and
  proves no current state or command remains.
- [ ] Implement rollback behavior.
- [ ] Add a two-worker optimistic version conflict test.
- [ ] Implement `SELECT ... FOR UPDATE` plus expected-version enforcement.
- [ ] Commit with `feat(kernel): add atomic postgres unit of work`.

## Task 7: Implement Ticket Issuance And Global Entry Lane

**Files:**

- Create: `src/trading_kernel/application/issue_ticket.py`
- Test: `tests/trading_kernel/integration/test_issue_ticket.py`

**Interfaces:**

- Produces `IssueTicketRequest`, `IssueTicketResult`, and
  `issue_ticket(uow, request) -> IssueTicketResult`.
- Atomically claims the one global entry lane, checks same-domain absence,
  reserves budget, and persists the immutable Ticket.

- [ ] Write a failing valid issuance test.
- [ ] Implement minimal issuance.
- [ ] Add failing tests for an occupied global lane, active same-domain Ticket,
  expired facts, duplicate Signal, absent policy, and insufficient budget.
- [ ] Implement one fail-closed branch at a time.
- [ ] Add a failing two-worker race test proving only one Ticket can win the
  global lane.
- [ ] Implement transactional claim semantics.
- [ ] Commit with `feat(kernel): issue tickets through one entry lane`.

## Task 8: Implement Command Dispatch And Venue Port

**Files:**

- Create: `src/trading_kernel/application/dispatch_exchange_command.py`
- Create: `src/trading_kernel/infrastructure/venue_adapter.py`
- Test: `tests/trading_kernel/unit/test_command_dispatch.py`
- Test: `tests/trading_kernel/integration/test_command_worker_recovery.py`

**Interfaces:**

- Produces `VenuePort`, `VenueCommandRequest`, `VenueCommandResult`, and
  `dispatch_one_command(...)`.
- Network I/O occurs outside PostgreSQL transactions.

- [ ] Write a failing unit test for claim -> venue call -> authoritative result
  recording.
- [ ] Implement the port and command dispatcher using a fake venue.
- [ ] Add failing timeout/unknown/duplicate-delivery/restart tests.
- [ ] Implement lease and result recording without redispatch after unknown.
- [ ] Add failing tests proving ENTRY rejection terminalizes the Ticket and does
  not create another ENTRY command.
- [ ] Implement the result-to-event mapping.
- [ ] Implement the real venue adapter only after all fake-venue behavior tests
  pass.
- [ ] Commit with `feat(kernel): dispatch durable venue commands`.

## Task 9: Implement Reconciliation, Exit, Settlement, And Review

**Files:**

- Create: `src/trading_kernel/application/reconcile_ticket.py`
- Create: `src/trading_kernel/application/settle_ticket.py`
- Create: `src/trading_kernel/domain/position.py`
- Create: `src/trading_kernel/domain/incident.py`
- Test: `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

**Interfaces:**

- Produces typed venue snapshot comparison, reconciliation events, terminal
  settlement, and review creation.

- [ ] Write failing full-chain tests for one protected Ticket to terminal review.
- [ ] Implement minimal reconciliation and settlement actions.
- [ ] Add failing tests for long/short isolation on one instrument.
- [ ] Add failing tests for external flat, owned orphan command recovery,
  unowned order incident, EXIT unknown, protection residue, and budget release
  only after matched flatness.
- [ ] Implement one behavior per red/green cycle.
- [ ] Commit with `feat(kernel): close ticket lifecycle and settlement`.

## Task 10: Implement Runtime, Monitor, And Readonly API

**Files:**

- Create: `src/trading_kernel/application/runtime.py`
- Create: `src/trading_kernel/interfaces/worker.py`
- Create: `src/trading_kernel/interfaces/readonly_api.py`
- Create: `scripts/trading_kernel/run_worker_once.py`
- Test: `tests/trading_kernel/integration/test_runtime_worker.py`

**Interfaces:**

- Produces bounded one-shot runtime processing and one current Owner-facing
  status projection.

- [ ] Write failing tests proving one worker invocation processes a bounded
  action and never scans unrelated history.
- [ ] Implement exact-ID/current-state queries only.
- [ ] Add failing no-signal tests proving zero file writes and bounded PG writes.
- [ ] Add failing monitor tests for processing, waiting, incident, paused, and
  completed product states.
- [ ] Implement current projection upserts and material transition events only.
- [ ] Commit with `feat(kernel): add bounded runtime and monitor`.

## Task 11: Full-Chain Certification

**Files:**

- Create: `tests/trading_kernel/full_chain/test_multi_position_certification.py`
- Create: `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Create: `scripts/trading_kernel/certify_readonly.py`
- Modify: `scripts/audit_production_runtime_file_io.py`

**Interfaces:**

- Produces one machine-readable stdout certification result; it does not write
  report files.

- [ ] Add production-shaped tests for two serial Ticket issuances resulting in
  two concurrent protected positions.
- [ ] Add same-instrument long/short coexistence tests.
- [ ] Add two-worker, restart, duplicate, timeout, unknown, partial-fill
  incident, missing protection, and external-change tests.
- [ ] Add performance assertions for exact-ID hot paths and no full-schema
  reflection.
- [ ] Extend file-I/O audit rules to reject any new runtime file reader/writer.
- [ ] Run the full new suite, Ruff, type checks if configured, Alembic baseline
  rebuild, and file-I/O audit.
- [ ] Commit with `test(kernel): certify rebuilt multi-position chain`.

## Task 12: Delete Old Program And Tests

**Files:**

- Delete: old execution orchestration, `runtime_execution_*`, replaced
  `action_time` modules, obsolete repositories/ORM, old migrations, old CLIs,
  old systemd units, and tests that encode retired semantics.
- Modify: application assembly, API wiring, deployment manifests, current docs,
  and validation scripts to reference only `src/trading_kernel`.

**Interfaces:**

- Produces one repository with zero production import/table reference to the
  retired execution models.

- [ ] Generate the exact delete manifest from source/import/table references.
- [ ] Add a failing architecture test that rejects imports and table names from
  the manifest.
- [ ] Delete one old family at a time and repair only new-kernel assembly.
- [ ] Run the new suite after each family deletion.
- [ ] Remove old tests rather than changing the new kernel to satisfy them.
- [ ] Require `rg` scans to return zero retired production references.
- [ ] Commit by coherent deleted family, finishing with
  `refactor(kernel): remove retired execution generations`.

## Task 13: Destructive Cutover Tooling And Rehearsal

**Files:**

- Create: `scripts/trading_kernel/verify_flat_cutover.py`
- Create: `scripts/trading_kernel/cutover_tokyo.py`
- Create: `deploy/systemd/brc-trading-kernel-worker.service`
- Create: `deploy/systemd/brc-trading-kernel-worker.timer`
- Modify: Tokyo deploy state machine and postdeploy verifier.
- Test: `tests/trading_kernel/integration/test_cutover_state_machine.py`

**Interfaces:**

- Produces a crash-safe, resume-safe cutover state machine that refuses schema
  destruction unless all flat/quiescent checks pass.

- [ ] Write failing plan-mode tests for the exact cutover phases.
- [ ] Implement plan mode without external mutation.
- [ ] Add failing apply-mode tests with fake SSH/PG/exchange boundaries.
- [ ] Implement writer fence, final readonly verification, short-lived backup,
  schema drop/create, seed, exact-head deploy, and staged capability restore.
- [ ] Rehearse against a disposable production-shaped PostgreSQL database and
  local systemd substitutes.
- [ ] Commit with `ops(kernel): add destructive flat-state cutover`.

## Task 14: Tokyo Cutover And Controlled Real-Funds Acceptance

**Files:**

- No ad hoc server edits. Use committed cutover/deploy tools and current
  deployment contracts.

**Acceptance sequence:**

- [ ] Prove Tokyo is flat, order-free, protection-free, and quiescent.
- [ ] Fence and stop all old writers.
- [ ] Execute the reviewed destructive cutover state machine.
- [ ] Verify exact commit, baseline revision, seed identity, PG role, service
  units, and zero legacy tables.
- [ ] Enable readonly observation and monitor.
- [ ] Enable non-writing Ticket/FinalGate/Operation Layer certification.
- [ ] Enable exchange-command capability only after current safety passes.
- [ ] Allow one natural or explicitly bounded in-scope Ticket to perform the
  controlled real-funds acceptance lifecycle.
- [ ] Prove terminal position flatness, no residual orders, budget settlement,
  reconciliation match, review record, and Owner-facing state.
- [ ] Remove short-lived rollback material and old releases.
- [ ] Update current project authority documents and complete the final audit.

## Verification Commands

The exact final command set will be kept current as files are added. The minimum
required gates are:

```bash
pytest tests/trading_kernel -q
ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
python3 -m alembic -c migrations/trading_kernel/alembic.ini upgrade head
python3 scripts/trading_kernel/verify_schema.py
python3 scripts/trading_kernel/certify_readonly.py
```

Final completion additionally requires Tokyo read-only evidence and the one
controlled real-funds terminal lifecycle described in Task 14.

