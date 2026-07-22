---
title: P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN
status: ACTIVE
program_id: P0-TKR
last_verified: 2026-07-22
---

# P0 Trading Kernel Rebuild Implementation Plan

> Production behavior uses test-first red/green/refactor. Tasks execute serially
> because they replace one shared execution authority.

**Goal:** Deliver one clean multi-position kernel, destructive Tokyo cutover,
and one controlled real-funds terminal lifecycle.

**Architecture:** Typed StrategyGroup signals enter one PostgreSQL authority,
one global new-ENTRY lane issues immutable Tickets serially, and protected
Tickets progress concurrently through one reducer and durable command model.

## Global Constraints

- One Ticket per Exposure Episode.
- No add-to-position capability.
- One ENTRY generation per Ticket.
- No retry after authoritative ENTRY rejection.
- No blind resend after unknown outcome.
- Partial fill is incident plus controlled flatten.
- Long/short independent sides are required.
- No retired imports, tables, tests, documents, or fallback authority.
- No runtime JSON/Markdown source or recurring report writes.

## Completed Foundation

| Task | Result | Evidence |
| --- | --- | --- |
| 1-4 | Identities, Ticket, reducer, events, effects, durable commands | Unit tests |
| 5-7 | Clean baseline, repositories, global lane, budget and domain constraints | PostgreSQL integration tests |
| 8-10 | Venue dispatch, reconciliation, settlement, runtime and monitor | Integration and full-chain tests |
| 11 | Multi-position and fault certification | `104 passed`, Ruff, Mypy, schema and file-I/O audits |
| 12 | Retired production generations deleted | Commit `d570018a`, architecture tests |

## Task 13: Retire Current Documentation Generation

**Files:**

- Keep and rewrite only the current authority allowlist in
  `tests/trading_kernel/architecture/test_current_document_authority.py`.
- Delete every other Markdown file under `docs/current`.
- Rewrite `AGENTS.md`, `CLAUDE.md`, `README.md`, `MEMORY.md`, and
  `docs/README.md`.

**Done when:**

- [x] architecture test proves the exact current document allowlist;
- [x] entry documents reference only existing current documents;
- [x] retired execution markers are absent from current authority;
- [x] focused architecture suite passes.

## Task 14: Typed Signal Foundation

**Files:**

- Create: `src/trading_kernel/domain/signal.py`
- Create: `src/trading_kernel/application/ingest_signal.py`
- Create: `src/trading_kernel/application/issue_ready_signal.py`
- Create: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/integration/test_signal_to_ticket.py`

This task established the first typed persistence and issuance skeleton. Its
capital-bearing signal semantics were intentionally replaced by Tasks 16-24 and
are not current authority.

The current boundary is:

- `StrategySignal` contains only Event identity, occurrence/expiry, and an exact
  immutable Fact Bundle;
- `ingest_signal(uow, request) -> IngestSignalResult` persists the Signal, Fact
  lineage, and `candidate_ready` state after Registry/Scope/Fact/schema checks;
- Signal ingestion does not consume Owner capital, account mode, venue rule, or
  order authority;
- Ticket issuance requires the action-time `CapacityClaim` introduced by the
  active six-capability rebuild and cannot derive financial terms from Signal.

## Task 15: Crash-Safe Destructive Cutover

**Files:**

- Create: `scripts/trading_kernel/verify_flat_cutover.py`
- Create: `scripts/trading_kernel/cutover_tokyo.py`
- Create: `deploy/systemd/brc-trading-kernel-worker.service`
- Create: `deploy/systemd/brc-trading-kernel-worker.timer`
- Test: `tests/trading_kernel/integration/test_cutover_state_machine.py`

**TDD sequence:**

- [x] RED: exact plan phases and identities.
- [x] GREEN: side-effect-free plan mode.
- [x] RED: every flatness, order, protection, outcome, writer, and identity
  precondition independently blocks destruction.
- [x] RED: interrupted apply resumes at the first unverified phase.
- [x] GREEN: implement explicit phase journal, writer fence, final verification,
  short-lived backup, schema rebuild, seed, deploy, readonly certification, and
  staged capability restore.
- [x] Rehearse on disposable PostgreSQL and local service substitutes.
- [x] Commit with `ops(kernel): add destructive flat-state cutover`.

## Owner Gate Before Task 16

The trading main chain and local cutover capability are completed first. Tokyo,
server mutation, and controlled real-funds acceptance must not begin until the
Owner and Codex review and decide the separate aggressive StrategyGroup and
strategy-signal refactor. Existing strategy models and producers are not
implicitly accepted merely because the trading kernel is ready.

## Tasks 16-24: Six-Capability Strategy And Runtime Rebuild

The Owner approved the aggressive rebuild of the six formally registered Event
contracts before Tokyo deployment. The detailed task-by-task execution plan is
`docs/superpowers/plans/2026-07-22-six-capability-trading-system-rebuild.md`.

The accepted scope is:

1. deterministic Registry Seed for CPM-LONG, MPG-LONG, MI-LONG, SOR-LONG,
   SOR-SHORT, and BRF2-SHORT;
2. pure Event detectors and closed-market observation;
3. immutable Strategy Signals without capital authority;
4. deterministic candidate arbitration and action-time Capacity Claims;
5. Venue Truth and unknown-outcome recovery;
6. versioned Initial Stop, TP1, runner, lifecycle, settlement, review, and one
   Owner projection;
7. local six-Event full-chain certification and destructive-cutover rehearsal.

Current implementation evidence:

| Capability | Status | Evidence |
| --- | --- | --- |
| Registry Seed | Complete | Six exact Event contracts, 19 Fact bindings, and 22 candidate scopes |
| StrategySignal boundary | Complete | Immutable Fact Bundle and append-only lineage; no capital authority |
| Pure Event detectors | Complete | Six positive vectors and full negative matrix |
| Closed-market observation | Complete | Six-Event observation matrix, bounded current Facts, deterministic Signal identity, and Live/Replay parity; `52 passed`, Ruff and Mypy clean |
| Candidate arbitration and CapacityClaim | Complete | Five-level deterministic ordering, bounded 64-candidate selector, action-time sizing, immutable claim lineage, and atomic Claim-to-Ticket issuance |
| Venue Truth and unknown-outcome recovery | Active next task | One lookup authority must resolve unknown exchange outcomes without redispatch |

The accepted exit-policy family is 1R TP1 for 50% plus a right-tail structural
ATR runner. SOR-LONG retains its exact committed time-stop policy. Candidate
selection orders Owner Policy Priority, Candidate Scope Priority, Event Time,
Observed Time, then Signal Event ID.

Production Capacity values and the first real-submit scope remain Tokyo-stage
Owner Policy decisions. They do not block local implementation or local DB
rebuild tests.

## Task 25: Tokyo Cutover And Controlled Real-Funds Acceptance

Task 25 remains paused until Tasks 16-24 pass local certification and the Owner
explicitly confirms deployment.

- [ ] Read current Tokyo commit, schema, services, DB roles, account mode,
  positions, orders, protection, and unresolved outcomes.
- [ ] Fence and stop old writers.
- [ ] Run the committed destructive cutover tool.
- [ ] Verify exact new commit, `0001_initial`, seed identity, table allowlist,
  roles, services, and zero legacy tables.
- [ ] Enable readonly observation and monitor.
- [ ] Certify typed signal-to-Ticket with exchange writes disabled.
- [ ] Enable exchange-command capability after all hard gates pass.
- [ ] Run one bounded in-scope Ticket through ENTRY, Initial Stop, EXIT, flat,
  reconciliation, settlement, review, and completed Owner state.
- [ ] Delete short-lived backup and retired releases.

## Task 26: Final Completion Audit

- [ ] Run the complete current test suite, Ruff, Mypy, schema rebuild,
  downgrade/upgrade, file-I/O audit, and readonly certification.
- [ ] Prove every design acceptance item from current local and Tokyo evidence.
- [ ] Prove no retired import, table, current document, deployment unit, or
  compatibility fallback remains.
- [ ] Mark the active goal complete only after all evidence is current and
  direct.
