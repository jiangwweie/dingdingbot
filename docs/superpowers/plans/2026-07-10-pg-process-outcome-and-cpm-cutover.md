# PG Process Outcome And CPM v2 Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist action-time fact business outcomes in PG, derive materializer process exits from PG process state, and deploy CPM-LONG v2 with migration 107.

**Architecture:** Reuse `brc_runtime_process_outcomes` as the only process/business truth. Add action-time fact outcome materialization, centralize process-state-to-exit-code mapping, and make the existing promotion CLI use its PG outcome instead of raw result status. The server sequence remains exit-code driven and never parses stdout or JSON/MD files for business semantics.

**Tech Stack:** Python 3.14, Pydantic v2, SQLAlchemy, Alembic, PostgreSQL/SQLite migration tests, pytest, Tokyo git release tooling.

## Global Constraints

- PG/current services are the only runtime business-state authority.
- Do not parse stdout JSON for orchestration decisions.
- Do not add JSON/MD file readers, writers, sidecars, or runtime artifacts.
- CLI exit code represents process health, not market opportunity or business eligibility.
- No no-signal file writes; target remains `0`.
- Do not change Owner Policy, runtime profile, notional, leverage, candidate symbols, lane concurrency, FinalGate, Operation Layer, or exchange behavior.
- Deploy imports no historical signal, promotion, lane, ticket, or order.

---

### Task 1: Common PG Process Exit Contract

**Files:**
- Modify: `src/application/runtime_process_outcome.py`
- Modify: `tests/unit/test_runtime_process_outcome.py`

**Interfaces:**
- Consumes: `RuntimeProcessOutcome` or persisted process outcome mapping.
- Produces: `runtime_process_exit_code(outcome) -> int`.

- [ ] **Step 1: Write failing exit-code tests**

Assert `succeeded`, `noop`, and `business_blocked` map to `0`; assert
`retryable_failure` and `hard_failure` map to `1`.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/test_runtime_process_outcome.py -k exit_code
```

Expected: FAIL because the common function does not exist.

- [ ] **Step 3: Implement the typed mapping**

Accept either `RuntimeProcessOutcome` or a mapping containing `process_state`.
Reject an unknown process state rather than silently returning success.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q tests/unit/test_runtime_process_outcome.py
```

- [ ] **Step 5: Commit**

```bash
git add src/application/runtime_process_outcome.py tests/unit/test_runtime_process_outcome.py
git commit -m "feat(runtime): centralize PG process exit semantics"
```

### Task 2: Action-Time Fact Process Outcome

**Files:**
- Modify: `src/application/action_time/fact_snapshots.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`

**Interfaces:**
- Consumes: fact materializer result status and blockers.
- Produces: current `brc_runtime_process_outcomes` row for `action_time_fact_snapshots` and CLI exit derived from that row.

- [ ] **Step 1: Write failing PG outcome tests**

For an unsatisfied action-time fact, assert:

```text
fact snapshot blocker_class = computed_not_satisfied
process_name = action_time_fact_snapshots
process_state = business_blocked
business_state = temporarily_unavailable
```

For no current fresh signal, assert `noop / waiting_for_opportunity`.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py -k process_outcome
```

Expected: FAIL because the fact materializer does not write process outcomes.

- [ ] **Step 3: Materialize the outcome in the existing transaction**

Use `materialize_runtime_process_outcome` when the migration-106 table exists.
Attach the persisted row to the returned in-memory report for CLI transport and
tests; PG remains authoritative.

- [ ] **Step 4: Make main derive its exit from the PG outcome**

Use `runtime_process_exit_code(report["process_outcome"])`. Preserve input,
DSN, SQL, and unknown-state failures as non-zero.

- [ ] **Step 5: Run GREEN**

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py
```

- [ ] **Step 6: Commit**

```bash
git add src/application/action_time/fact_snapshots.py tests/unit/test_pg_promotion_action_time_lane_materialization.py
git commit -m "fix(runtime): persist action-time fact process outcomes"
```

### Task 3: Promotion CLI Uses PG Process State

**Files:**
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_server_product_state_refresh_sequence.py`

**Interfaces:**
- Consumes: existing promotion `process_outcome` row.
- Produces: process-success exit for `promotion_candidates_blocked`, process-failure exit for retryable/hard failures.

- [ ] **Step 1: Write failing promotion CLI and server-sequence tests**

Assert a PG business-blocked promotion exits `0` and does not make the server
sequence fail. Assert repository/SQL failure remains non-zero.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_server_product_state_refresh_sequence.py -k 'business_block or process_exit'
```

- [ ] **Step 3: Replace raw status exit mapping**

Use `runtime_process_exit_code` when a persisted outcome is present. Do not
change promotion eligibility, lane selection, or downstream authority.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q tests/unit/test_runtime_process_outcome.py tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_server_product_state_refresh_sequence.py
```

- [ ] **Step 5: Commit**

```bash
git add src/application/action_time/promotion_action_time_lane.py tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_server_product_state_refresh_sequence.py
git commit -m "fix(runtime): keep business blocks process-healthy"
```

### Task 4: Local CPM Cutover Acceptance

**Files:**
- Modify only if a scoped regression proves a real defect.

- [ ] **Step 1: Run the CPM/action-time vertical suite**

Run the existing 345-test suite plus process-outcome, server-sequence, and
watcher-systemd tests.

- [ ] **Step 2: Run governance validators**

```bash
python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
python3 scripts/validate_no_runtime_file_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
git diff --check
```

- [ ] **Step 3: Verify scope**

CPM v2 is the only trial-grade event; all other events stay observe-only; one
real lane maximum remains; profile/sizing/exchange behavior is unchanged.

### Task 5: Merge, Push, Deploy, And Accept Tokyo

**Files:**
- No source changes unless a reviewed merge conflict requires them.

- [ ] **Step 1: Merge into the clean `dev` worktree**

Preserve the dirty main worktree on its separate branch. Re-run bounded
merge-result acceptance from `dev`.

- [ ] **Step 2: Push `dev`**

Confirm the target commit is available to Tokyo's approved git fetch/export
transport.

- [ ] **Step 3: Deploy migration 107**

Use the repository deploy planner/executor with expected remote head
`ac0f61d9`, remote migration count `106`, and target latest migration 107.

- [ ] **Step 4: Postdeploy verification**

Verify target release head, migration count `107`, healthy backend/watcher/
monitor/timers, CPM v1 historical observe-only, CPM v2 current trial-grade,
four CPM v2 bindings, all other events observe-only, and zero forbidden effects.

- [ ] **Step 5: Continue to Wave 2**

Do not wait for a CPM market signal. Begin the approved shared comparative-fact
design and MPG/MI certification work after production acceptance.
