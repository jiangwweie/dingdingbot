---
title: P0_RUNTIME_CAUSAL_INTEGRITY_AND_ADVERSARIAL_CERTIFICATION_IMPLEMENTATION_PLAN
status: CURRENT
authority: docs/current/P0_RUNTIME_CAUSAL_INTEGRITY_AND_ADVERSARIAL_CERTIFICATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P0 Runtime Causal Integrity And Adversarial Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Subagents
> are disabled by repository constraint.

**Goal:** Certify the deployed Ticket-bound execution chain under real
PostgreSQL transactions, independent process death, concurrency, exchange
ambiguity, lifecycle replay, and projection overwrite attempts.

**Architecture:** A pytest-only harness creates a disposable PostgreSQL
database, applies production Alembic migrations, invokes production
repositories/services, and records fake external exchange effects in a
test-local unique ledger. Production code changes are allowed only after a
scenario demonstrates an existing invariant violation.

**Tech Stack:** Python 3, pytest, SQLAlchemy 2, psycopg 3, Alembic, PostgreSQL
16, multiprocessing, existing BRC application services.

## Global Constraints

1. **PG/current only:** no runtime JSON/Markdown source or recurring writer.
2. **No production fault injection:** all kills and fake exchange effects are
   local-test only.
3. **No authority expansion:** no profile, capital, leverage, symbol, side, or
   trading-permission change.
4. **TDD:** each demonstrated production defect stays RED before its minimal
   implementation fix.
5. **Bounded waits:** every process/event/network wait has an explicit timeout.
6. **Natural-event conservation:** R1B remains the only real venue proof.

---

## Task 1: Disposable PostgreSQL Certification Harness

**Files:**

- Create: `tests/integration/runtime_causal_integrity_pg_support.py`
- Create: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Consume: `alembic.ini`, `migrations/env.py`, `docker-compose.pg.yml`

**Produces:**

- `postgres_certification_database()` session fixture.
- `postgres_certification_engine` function fixture with per-test transaction
  cleanup.
- `FakeExchangeLedgerGateway` keyed by production `client_order_id`.
- timeout-bounded child-process helpers.

- [x] Create a random database name prefixed `brc_rci_test_` using an admin
  connection with autocommit.
- [x] Apply the production bootstrap order through Alembic revision `119`.
- [x] Assert dialect is PostgreSQL and current revision is `119`.
- [x] Create only test-local fake exchange tables in that database.
- [x] On teardown, dispose engines, terminate only that database's sessions,
  and drop only that database.
- [ ] Run:

```bash
BRC_TEST_POSTGRES_ADMIN_URL='postgresql+psycopg://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres' \
python3 -m pytest -q tests/integration/test_runtime_causal_integrity_postgres.py -k harness
```

Expected: the first harness assertion fails before the fixture exists, then
passes after the fixture is implemented.

## Task 2: Signal To Ticket Transaction Certification

**Files:**

- Modify: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Reuse: `src/application/action_time/ticket_materialization_sequence.py`
- Reuse: `src/application/action_time/action_time_invocation.py`

**Produces:** scenarios **RCI-S1**, **RCI-S2**, and **RCI-S3**.

- [x] Write RCI-S1 with two fresh signals and assert the committed Ticket,
  invocation, facts, lane, and source watermark all name one selected event.
- [x] Run RCI-S1 and confirm any failure is identity divergence, not fixture
  setup.
- [x] Write RCI-S2 by raising before outer commit and assert zero partial
  promotion, reservation, lane, or Ticket rows.
- [x] Write RCI-S3 with an expired invocation, reconnect, and assert no Ticket
  plus the exact lane-scoped TTL blocker.
- [x] Run only `-k 'rci_s1 or rci_s2 or rci_s3'` until all three pass.

## Task 3: Ticket To Exchange Process Certification

**Files:**

- Modify: `tests/integration/runtime_causal_integrity_pg_support.py`
- Modify: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Reuse: `src/application/action_time/exchange_command.py`
- Reuse: `src/application/action_time/exchange_command_worker.py`

**Produces:** scenarios **RCI-E1**, **RCI-E2**, **RCI-E3**, and **RCI-E4**.

- [x] RCI-E1: child commits a claim, signals parent, and is terminated before
  gateway call; after lease expiry, production worker must persist unknown and
  perform zero fake exchange writes.
- [x] RCI-E2: child commits claim and fake exchange acceptance, signals parent,
  and is terminated before PG outcome commit; recovery must preserve exactly
  one external order and block redispatch.
- [x] RCI-E3: start two processes on one prepared command; unique fake ledger
  and production command state must both show one side effect.
- [x] RCI-E4: timeout after gateway dispatch begins; assert `outcome_unknown`,
  active domain hold, and zero later dispatch.
- [x] Run only `-k 'rci_e1 or rci_e2 or rci_e3 or rci_e4'` until all four pass.

## Task 4: Fill, Protection, And Runner Certification

**Files:**

- Modify: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Reuse: `src/application/action_time/exchange_truth.py`
- Reuse: `src/application/action_time/order_fill_projection.py`
- Reuse: lifecycle protection and runner materializers under
  `src/application/action_time/`

**Produces:** scenarios **RCI-L1**, **RCI-L2**, and **RCI-L3**.

- [x] RCI-L1: record partial entry truth and assert protection amount equals
  confirmed cumulative fill using `Decimal`.
- [x] RCI-L2: replay identical snapshot, then contradictory snapshot; assert
  idempotent duplicate handling and no lifecycle regression.
- [x] RCI-L3: commit TP1, reconnect, run runner mutation materialization twice,
  and assert one command generation and one fake external mutation.
- [x] Run only `-k 'rci_l1 or rci_l2 or rci_l3'` until all three pass.

## Task 5: Projection Failure-Conservation Certification

**Files:**

- Modify: `tests/integration/test_runtime_causal_integrity_postgres.py`
- Reuse: `src/application/runtime_process_outcome_service.py`
- Reuse: current Owner/readiness projection services.

**Produces:** scenarios **RCI-P1** and **RCI-P2**.

- [x] RCI-P1: write a lane failure followed by a newer success; assert current
  status clears while both history rows remain queryable.
- [x] RCI-P2: write unresolved engineering failure then run no-signal refresh;
  assert it cannot become `market_wait_validated`.
- [x] Run only `-k 'rci_p1 or rci_p2'` until both pass.

## Task 6: Finding Gate And Minimal Repairs

**Files:**

- Modify only the production file owning a demonstrated failed invariant.
- Modify the corresponding test in
  `tests/integration/test_runtime_causal_integrity_postgres.py`.

**Procedure:**

1. Preserve the failing assertion and record the first divergent PG row.
2. Classify it as `coverage_gap`, `implementation_defect`,
   `architecture_gap`, or `live_only_unknown`.
3. For `implementation_defect`, implement the smallest fix inside the current
   state machine and rerun focused RED-GREEN.
4. For `architecture_gap`, amend the design before changing production code.
5. Do not modify production behavior for `coverage_gap` or
   `live_only_unknown`.

## Task 7: Verification, Documentation, And Deployment Decision

**Files:**

- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify this plan with final scenario/finding status.

- [x] Run the full real-PG P0-RCI file.
- [x] Run the existing Action-Time, exchange-command, lifecycle, and projection
  focused suites.
- [x] If production code changed, run the full pytest suite.
- [x] Run:

```bash
python3 scripts/audit_production_runtime_file_io.py --all
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
```

- [x] Inspect `git diff --check`, `git status`, and the exact changed-file set.
- [x] Deploy because two production runtime behaviors changed.
- [x] Verify exact head, migration count/revision, backend,
  watcher, monitor, lifecycle timer, and no-active zero exchange effect.
- [x] Record R1B as pending if no different-identity natural event occurred.

## Completion Record

This section is updated only from fresh command evidence.

| Item | Status | Evidence |
| --- | --- | --- |
| **RCI-S1..S3** | passed | Exact invocation identity, atomic rollback, and TTL persistence passed on PostgreSQL 16 |
| **RCI-E1..E4** | passed | Claim crash, accepted-before-result crash, two-worker race, and ambiguous timeout produced no duplicate external order |
| **RCI-L1..L3** | passed | Partial-fill protection, duplicate/contradictory fill handling, and restart-idempotent runner generation passed |
| **RCI-P1..P2** | passed | Newer success clears current blocker; no-signal projection preserves unresolved engineering failure |
| **Regression** | passed | P0-RCI `13 passed`; focused lifecycle/deploy additions passed; full suite `3030 passed, 1 skipped` |
| **Runtime file-I/O audit** | passed | `suspicious_runtime_file_authority=0`, `frequent_report_write=0`, output scope valid |
| **Deployment** | accepted | Official exact-head Tokyo flow and read-only no-active acceptance completed without exchange effect |
| **R1B natural live calibration** | pending natural event | Cannot be replaced by fake exchange evidence |

## Findings

| Classification | Finding | Resolution |
| --- | --- | --- |
| **coverage_gap** | SQLite and one-process fixtures did not certify PostgreSQL locks, process death, or the exchange-accept/result-commit window | Retained all 12 bounded PostgreSQL/process scenarios as the new certification boundary |
| **implementation_defect** | A filled exit order skipped every repeated snapshot, so contradictory quantity or price truth was silently ignored | Preserve duplicate idempotency, but hard-stop contradictory truth with immutable lifecycle evidence |
| **implementation_defect** | Candidate projection filtered successful outcomes before selecting the latest lane outcome, so an older blocker could survive a newer success | Select the latest typed outcome per lane first, then project it only when that latest outcome still has blocking authority |
| **implementation_defect** | Lifecycle maintenance requested a gateway for every pending exchange command even though its worker owns only recovery, runner, and orphan-cleanup sources | Bind the gateway precondition to the same command-source tuple consumed by the lifecycle worker; historical `protected_submit` commands no longer cause a restart loop |
| **implementation_defect** | Deploy preflight did not verify the non-secret account/exchange identity required by the lifecycle gateway contract | Fail before remote mutation unless the runtime order-capable overlay contains a nonblank account identity and canonical `binance_usdm` exchange identity |
| **architecture_gap** | None demonstrated | Existing lifecycle, deploy, command-source, and PG process-outcome authority expressed all repairs without schema or state-model expansion |
| **live_only_unknown** | Real venue latency, fills, fees, funding, slippage, and protection acceptance | Remains **R1B** and may close only from a different-identity natural live event |
