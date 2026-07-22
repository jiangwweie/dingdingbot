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

- [ ] architecture test proves the exact current document allowlist;
- [ ] entry documents reference only existing current documents;
- [ ] retired execution markers are absent from current authority;
- [ ] focused architecture suite passes.

## Task 14: Typed Signal To Frozen Ticket

**Files:**

- Create: `src/trading_kernel/domain/signal.py`
- Create: `src/trading_kernel/application/ingest_signal.py`
- Create: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/integration/test_signal_to_ticket.py`

**Interfaces:**

- `ActionableSignal` is the frozen strategy-to-kernel input.
- `ingest_signal(uow, request) -> IngestSignalResult` persists the immutable
  signal and readiness result after current authority validation.
- `issue_ready_signal(uow, request) -> IssueTicketResult` selects one ready
  unexpired signal, revalidates authority, builds the deterministic Ticket, and
  uses the existing atomic issuance path.

**TDD sequence:**

- [ ] RED: valid typed signal persists readiness and issues one Ticket.
- [ ] RED: wrong scope, version, side, account mode, capability, instrument,
  fact digest, or expiry fails before Ticket creation.
- [ ] RED: two ready signals persist concurrently but issue Tickets serially.
- [ ] RED: lane release permits the second still-fresh signal to issue.
- [ ] RED: duplicate signal cannot create a second Ticket identity.
- [ ] RED: policy or budget changes are revalidated at issuance.
- [ ] GREEN: implement only the typed models, repository queries, and services
  required by each failing test.
- [ ] Run focused unit, integration, schema, Ruff, and Mypy checks.
- [ ] Commit with `feat(kernel): connect typed signals to ticket issuance`.

## Task 15: Crash-Safe Destructive Cutover

**Files:**

- Create: `scripts/trading_kernel/verify_flat_cutover.py`
- Create: `scripts/trading_kernel/cutover_tokyo.py`
- Create: `deploy/systemd/brc-trading-kernel-worker.service`
- Create: `deploy/systemd/brc-trading-kernel-worker.timer`
- Test: `tests/trading_kernel/integration/test_cutover_state_machine.py`

**TDD sequence:**

- [ ] RED: exact plan phases and identities.
- [ ] GREEN: side-effect-free plan mode.
- [ ] RED: every flatness, order, protection, outcome, writer, and identity
  precondition independently blocks destruction.
- [ ] RED: interrupted apply resumes at the first unverified phase.
- [ ] GREEN: implement explicit phase journal, writer fence, final verification,
  short-lived backup, schema rebuild, seed, deploy, readonly certification, and
  staged capability restore.
- [ ] Rehearse on disposable PostgreSQL and local service substitutes.
- [ ] Commit with `ops(kernel): add destructive flat-state cutover`.

## Task 16: Tokyo Cutover And Controlled Real-Funds Acceptance

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

## Task 17: Final Completion Audit

- [ ] Run the complete current test suite, Ruff, Mypy, schema rebuild,
  downgrade/upgrade, file-I/O audit, and readonly certification.
- [ ] Prove every design acceptance item from current local and Tokyo evidence.
- [ ] Prove no retired import, table, current document, deployment unit, or
  compatibility fallback remains.
- [ ] Mark the active goal complete only after all evidence is current and
  direct.
