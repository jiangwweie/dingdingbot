---
title: P0_ACTION_TIME_INVOCATION_CONSISTENCY_AND_FAILURE_TRUTH_IMPLEMENTATION_PLAN
status: CURRENT_IMPLEMENTATION_PLAN
authority: docs/current/P0_ACTION_TIME_INVOCATION_CONSISTENCY_AND_FAILURE_TRUTH_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-13
---

# P0 Action-Time Invocation Consistency And Failure Truth Implementation Plan

> **Execution boundary:** This plan is executed inline by Codex. The repository
> forbids sub-agent implementation for this task. Every behavior change follows
> a RED -> GREEN -> regression cycle before the next task starts.

**Goal:** Replace implicit Action-Time temporal coupling with one PG-backed,
identity-bound invocation so a natural signal can reach a Ticket or preserve one
exact non-market blocker without false market-wait reporting.

**Architecture:** Add a durable ActionTimeInvocation causal context before
Ticket creation, bind actual account/action fact observations to it, and keep
invocation evidence transient inside the atomic sequence. Promotion consumes
the exact evidence rather than Candidate Pool readiness rows. Process outcomes
carry the Invocation identity/source lineage; watcher coverage carries the same
immutable identity plus its own independent, nonblank watcher watermark.

**Tech Stack:** Python 3, Pydantic, SQLAlchemy, Alembic/PostgreSQL, existing
RuntimeLaneIdentity model, SQLite in-memory fixtures, pytest.

## Local Execution Status — 2026-07-13

| Boundary | Local status | Production status | Evidence |
| --- | --- | --- | --- |
| **Invocation data and fact-time binding** | complete | deployment pending | migration `119`, typed `ActionTimeInvocation`, actual observation timestamps |
| **Exact Ticket-chain materialization** | complete | deployment pending | invocation-bound transient evidence; generic candidate readiness cannot directly create a Ticket |
| **Failure and identity conservation** | complete | deployment pending | zero-exit semantic blocks remain `business_blocked`; process outcomes retain exact lane lineage |
| **Watcher coverage** | complete | deployment pending | all 22 active lanes require full identity and an independent watcher watermark |
| **Regression and authority validation** | complete | deployment pending | focused chain suite `418 passed`; full suite `3015 passed, 1 skipped`; validators clear |

The retained unchecked commit and deployment steps below are deliberate: this
task has not created an integrated commit, deployed to Tokyo, or observed a
new natural event. No exchange write, order creation, profile change, or sizing
change occurred during local execution.

## Global Constraints

- PG/current is the sole production authority; no JSON/Markdown reader or
  recurring JSON/Markdown writer is added.
- Ticket remains the only post-intent business lifecycle owner.
- ActionTimeInvocation is causal context only and must not add order, position,
  protection, reconciliation, or settlement status.
- Fact observation time is never backdated to invocation opening time.
- All production Invocation stages are bounded by the existing 30-second
  Action-Time timeout and use indexed exact-key PG lookups.
- No strategy, symbol, side, profile, leverage, notional, risk policy, or
  execution authority expands.
- No FinalGate bypass, Operation Layer bypass, exchange write, order creation,
  withdrawal, transfer, credential mutation, profile mutation, or sizing
  mutation is introduced.
- Financial calculations retain `Decimal` behavior.
- No-signal ticks create zero invocation rows and zero recurring files.

---

### Task 1: Invocation Data Contract and Migration 119

**Files:**
- Create: `src/domain/action_time_invocation.py`
- Create: `src/application/action_time/action_time_invocation.py`
- Create: `migrations/versions/2026-07-13-119_action_time_invocation_consistency.py`
- Modify: `src/application/action_time/runtime_pg_fact_snapshots.py`
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`
- Test: `tests/unit/test_action_time_invocation.py`
- Test: `tests/unit/test_runtime_lane_identity_migration.py`

**Interfaces:**
- Consumes: one typed `brc_live_signal_events` row and its `RuntimeLaneIdentity`.
- Produces: `ActionTimeInvocation`, `start_action_time_invocation(...)`,
  `load_action_time_invocation(...)`, and
  `bind_action_time_invocation_fact_refs(...)`.

- [ ] **Step 1: Write failing domain and PG tests.**

  ```python
  def test_invocation_binds_one_typed_signal_and_deadline(pg_control_connection):
      invocation = start_action_time_invocation(
          pg_control_connection,
          signal_event_id="signal:sor-eth-long",
          opened_at_ms=NOW_MS,
      )
      assert invocation.signal_event_id == "signal:sor-eth-long"
      assert invocation.lane_identity.identity_key
      assert invocation.opened_at_ms == NOW_MS
      assert invocation.expires_at_ms > NOW_MS

  def test_invocation_rejects_untyped_or_expired_signal(pg_control_connection):
      with pytest.raises(ActionTimeInvocationBlocked, match="runtime_lane_identity"):
          start_action_time_invocation(
              pg_control_connection,
              signal_event_id="signal:untyped",
              opened_at_ms=NOW_MS,
          )
  ```

- [ ] **Step 2: Run the focused RED tests.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_invocation.py -q
  ```

  Expected: failure because `ActionTimeInvocation` and its PG materializer do
  not yet exist.

- [ ] **Step 3: Implement the smallest typed contract and migration.**

  ```python
  class ActionTimeInvocation(BaseModel):
      action_time_invocation_id: str
      signal_event_id: str
      lane_identity: RuntimeLaneIdentity
      source_watermark: str
      opened_at_ms: int
      expires_at_ms: int
      account_safe_fact_snapshot_id: str | None = None
      account_mode_fact_snapshot_id: str | None = None
      action_time_fact_snapshot_id: str | None = None
      ticket_id: str | None = None
  ```

  Migration `119` creates `brc_action_time_invocations`, adds nullable
  `action_time_invocation_id` to `brc_runtime_fact_snapshots`, adds indexed
  foreign-reference fields, and preserves current PG history. It must not add
  a second current readiness table.

- [ ] **Step 4: Run GREEN and migration regression tests.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_invocation.py tests/unit/test_runtime_lane_identity_migration.py -q
  ```

  Expected: all selected tests pass.

- [ ] **Step 5: Commit the data-contract slice.**

  ```bash
  git add src/domain/action_time_invocation.py src/application/action_time/action_time_invocation.py migrations/versions/2026-07-13-119_action_time_invocation_consistency.py src/application/action_time/runtime_pg_fact_snapshots.py docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md tests/unit/test_action_time_invocation.py tests/unit/test_runtime_lane_identity_migration.py
  git commit -m "feat: bind action-time invocation context"
  ```

### Task 2: Bind Actual Account Facts Without Backdating

**Files:**
- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `src/application/action_time/runtime_pg_fact_snapshots.py`
- Modify: `scripts/run_server_product_state_refresh_sequence.py`
- Test: `tests/unit/test_action_time_invocation.py`
- Test: `tests/unit/test_server_product_state_refresh_sequence.py`

**Interfaces:**
- Consumes: `--action-time-invocation-id` and signed GET-only account facts.
- Produces: actual-timestamp account-safe/account-mode fact IDs attached to the
  invocation; no future fact is treated as visible at an earlier stage.

- [ ] **Step 1: Write failing temporal tests.**

  ```python
  def test_account_fact_after_opening_is_visible_only_to_later_stage(pg_control_connection):
      invocation = _fresh_invocation(pg_control_connection, opened_at_ms=NOW_MS)
      bind_action_time_invocation_fact_refs(
          pg_control_connection,
          action_time_invocation_id=invocation.action_time_invocation_id,
          account_safe_fact_snapshot_id="fact:account-safe:T1",
          account_mode_fact_snapshot_id="fact:account-mode:T1",
          observed_at_ms=NOW_MS + 1,
      )
      assert load_action_time_invocation_evidence(
          pg_control_connection, invocation.action_time_invocation_id, stage_at_ms=NOW_MS
      ).blockers == ["action_time_stage_before_account_fact"]
      assert load_action_time_invocation_evidence(
          pg_control_connection, invocation.action_time_invocation_id, stage_at_ms=NOW_MS + 1
      ).account_safe_fact_snapshot_id == "fact:account-safe:T1"
  ```

- [ ] **Step 2: Run the RED tests.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_invocation.py::test_account_fact_after_opening_is_visible_only_to_later_stage -q
  ```

  Expected: failure because account facts are not invocation-bound and stage
  time is still inferred from unrelated wall clocks.

- [ ] **Step 3: Implement exact account-fact attachment.**

  Extend the account-safe CLI with `--action-time-invocation-id`; preserve its
  real collection/observation timestamps; bind returned fact IDs to the
  invocation in the same PG transaction. The refresh orchestrator starts the
  invocation before the account collector and passes only that opaque ID.

- [ ] **Step 4: Run GREEN and wrapper regressions.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_invocation.py tests/unit/test_server_product_state_refresh_sequence.py -q
  ```

  Expected: all selected tests pass; the test asserts that the account collector
  receives the invocation ID, not a fabricated historical `--now-ms`.

- [ ] **Step 5: Commit the fact-time slice.**

  ```bash
  git add src/application/action_time/account_safe_facts.py src/application/action_time/runtime_pg_fact_snapshots.py scripts/run_server_product_state_refresh_sequence.py tests/unit/test_action_time_invocation.py tests/unit/test_server_product_state_refresh_sequence.py
  git commit -m "fix: bind fresh account facts to action-time invocation"
  ```

### Task 3: Replace Candidate-Pool Readiness in the Atomic Ticket Sequence

**Files:**
- Create: `src/domain/action_time_invocation.py`
- Create: `src/application/action_time/action_time_invocation.py`
- Modify: `src/application/action_time/fact_snapshots.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/ticket_materialization_sequence.py`
- Modify: `scripts/materialize_action_time_ticket_sequence.py`
- Modify: `src/application/action_time/full_chain_simulation_harness.py`
- Test: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Test: `tests/unit/test_action_time_full_chain_impact.py`

**Interfaces:**
- Consumes: `action_time_invocation_id`, a stage-local `stage_at_ms`, exact
  signal/fact references, and the existing RuntimeLaneIdentity.
- Produces: transient `ActionTimeInvocationEvidence`, normal promotion/lane
  rows, and an Action-Time Ticket only for the invocation source signal.

- [ ] **Step 1: Write the direct root-cause RED tests.**

  ```python
  def test_sequence_does_not_hide_its_own_evidence_at_one_millisecond_offset(
      pg_control_connection,
  ):
      invocation = _fresh_invocation(pg_control_connection, opened_at_ms=NOW_MS)
      _bind_fresh_account_facts(pg_control_connection, invocation, observed_at_ms=NOW_MS + 1)
      report = materialize_action_time_ticket_sequence(
          pg_control_connection,
          action_time_invocation_id=invocation.action_time_invocation_id,
          stage_at_ms=NOW_MS + 1,
      )
      assert report["status"] == "action_time_ticket_sequence_committed"

  def test_sequence_cannot_switch_to_a_different_concurrent_signal(pg_control_connection):
      invocation_a = _fresh_invocation(pg_control_connection, signal_id="signal:a")
      _insert_higher_priority_fresh_signal(pg_control_connection, signal_id="signal:b")
      report = materialize_action_time_ticket_sequence(
          pg_control_connection,
          action_time_invocation_id=invocation_a.action_time_invocation_id,
          stage_at_ms=NOW_MS + 1,
      )
      assert report["ticket"]["signal_event_id"] == "signal:a"
  ```

- [ ] **Step 2: Run RED.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_ticket_materialization_sequence.py -q
  ```

  Expected: failure because the current sequence invokes the generic publisher
  and selects all fresh signals from current PG state.

- [ ] **Step 3: Implement direct invocation evidence.**

  Make the sequence require `action_time_invocation_id` in the production CLI.
  `materialize_action_time_fact_snapshots(...)` resolves exactly the invocation
  signal and persists its action-time fact reference. Build a Pydantic
  `ActionTimeInvocationEvidence` in memory, pass it directly to promotion, and
  remove `publish_action_time_pretrade_readiness` from the atomic Action-Time
  path. Keep generic readiness publishing for read-model cadence only.

- [ ] **Step 4: Run GREEN, replay parity, and source-boundary regression.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_ticket_materialization_sequence.py tests/unit/test_action_time_full_chain_impact.py tests/unit/test_l2_l7_mainline_chain_invariants.py -q
  ```

  Expected: all selected tests pass, the one-millisecond case commits, and
  replay explicitly supplies the same invocation/stage clock without creating a
  live signal or exchange write.

- [ ] **Step 5: Commit the action-time core slice.**

  ```bash
  git add src/domain/action_time_invocation.py src/application/action_time/action_time_invocation.py src/application/action_time/fact_snapshots.py src/application/action_time/promotion_action_time_lane.py src/application/action_time/ticket_materialization_sequence.py scripts/materialize_action_time_ticket_sequence.py src/application/action_time/full_chain_simulation_harness.py tests/unit/test_action_time_ticket_materialization_sequence.py tests/unit/test_action_time_full_chain_impact.py tests/unit/test_l2_l7_mainline_chain_invariants.py
  git commit -m "fix: make action-time evidence invocation-bound"
  ```

### Task 4: Preserve Semantic Failure and Full Lane Identity Across Processes

**Files:**
- Modify: `src/application/runtime_process_outcome.py`
- Modify: `src/application/action_time/fact_snapshots.py`
- Modify: `src/application/action_time/ticket_materialization_sequence.py`
- Modify: `scripts/run_server_product_state_refresh_sequence.py`
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Test: `tests/unit/test_runtime_process_outcome.py`
- Test: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Test: `tests/unit/test_server_product_state_refresh_sequence.py`
- Test: `tests/unit/test_strategy_live_candidate_pool.py`
- Test: `tests/unit/test_tokyo_runtime_server_monitor.py`

**Interfaces:**
- Consumes: structured child JSON containing `process_outcome`, invocation
  identity, and source watermark.
- Produces: typed child and outer `business_blocked` outcomes; Owner-facing
  non-market engineering status; no FinalGate/Operation Layer child calls after
  a Ticket-sequence business stop.

- [ ] **Step 1: Write failing semantic-outcome tests.**

  ```python
  def test_outer_refresh_preserves_zero_exit_business_block_as_blocked(tmp_path):
      report = run_server_product_state_refresh_sequence(
          python=sys.executable,
          env_file=tmp_path / "live-readonly.env",
          mode="action_time_if_needed",
          action_time_trigger_state=_triggered_invocation_state(),
          runner=_business_blocked_ticket_sequence_runner,
      )
      assert report["status"] == "server_product_state_refresh_sequence_business_blocked"
      assert report["summary"]["business_blocked_by_required_step"] == "materialize_action_time_ticket_sequence"
      assert "materialize_action_time_finalgate_preflight" not in _attempted_steps(report)
  ```

- [ ] **Step 2: Run RED.**

  Run:

  ```bash
  pytest tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_runtime_process_outcome.py -q
  ```

  Expected: failure because a `business_blocked` child has exit code `0` and the
  parent currently marks completion.

- [ ] **Step 3: Implement structured child parsing and typed outcome writes.**

  Parse the final JSON payload of each required child. Treat `business_blocked`
  as a semantic stop, not a crashed process. Write outer and inner outcomes with
  `lane_identity=invocation.lane_identity`; retain the current exit-code mapping
  for systemd health. Candidate Pool and monitor project unresolved invocation
  failures as `action_time_boundary_not_reproduced`, with plain Owner language.

- [ ] **Step 4: Run GREEN across failure and monitor paths.**

  Run:

  ```bash
  pytest tests/unit/test_runtime_process_outcome.py tests/unit/test_action_time_ticket_materialization_sequence.py tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_strategy_live_candidate_pool.py tests/unit/test_tokyo_runtime_server_monitor.py -q
  ```

  Expected: all selected tests pass and typed outcome assertions reject null
  lane identity for invocation-backed rows.

- [ ] **Step 5: Commit the truth-conservation slice.**

  ```bash
  git add src/application/runtime_process_outcome.py src/application/action_time/fact_snapshots.py src/application/action_time/ticket_materialization_sequence.py scripts/run_server_product_state_refresh_sequence.py src/application/readmodels/strategy_live_candidate_pool.py scripts/run_tokyo_runtime_server_monitor.py tests/unit/test_runtime_process_outcome.py tests/unit/test_action_time_ticket_materialization_sequence.py tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_strategy_live_candidate_pool.py tests/unit/test_tokyo_runtime_server_monitor.py
  git commit -m "fix: conserve action-time business failure truth"
  ```

### Task 5: Complete Typed Watcher Coverage and Cross-Scope Rejection

**Files:**
- Modify: `scripts/runtime_active_observation_monitor.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md`
- Test: `tests/unit/test_runtime_active_observation_monitor.py`
- Test: `tests/unit/test_runtime_lane_identity_migration.py`
- Test: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`

**Interfaces:**
- Consumes: resolved `RuntimeLaneIdentity` from the runtime observation monitor.
- Produces: fully typed current coverage rows; Action-Time coverage checks that
  reject generic or wrong-identity coverage.

- [ ] **Step 1: Write 22-lane and negative-coverage tests.**

  ```python
  @pytest.mark.parametrize("strategy_group_id,symbol,side", ACTIVE_LANES)
  def test_current_covered_row_has_full_runtime_lane_identity(
      strategy_group_id, symbol, side
  ):
      row = _coverage_after_monitor_tick(strategy_group_id, symbol, side)
      assert row["runtime_profile_id"]
      assert row["runtime_instance_id"]
      assert row["lane_identity_key"]

  def test_generic_coverage_cannot_satisfy_action_time_identity_check(pg_control_connection):
      _insert_untyped_covered_row(pg_control_connection)
      assert "runtime_lane_identity_mismatch:coverage_typed_identity" in _promotion_blockers(pg_control_connection)
  ```

- [ ] **Step 2: Run RED.**

  Run:

  ```bash
  pytest tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_lane_identity_migration.py tests/unit/test_pg_promotion_action_time_lane_materialization.py -q
  ```

  Expected: failure because coverage rows presently omit the typed identity and
  can carry a null runtime profile.

- [ ] **Step 3: Implement typed coverage writing and validation.**

  Populate coverage from `RuntimeLaneIdentity`, invalidate untyped current
  covered rows in migration `119`, and require coverage identity to equal the
  invocation identity before promotion. Coverage must also carry its own
  nonblank watcher watermark; it is independent evidence and does not reuse the
  signal watermark. Retain old coverage only as historical,
  non-authoritative evidence.

- [ ] **Step 4: Run GREEN.**

  Run:

  ```bash
  pytest tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_lane_identity_migration.py tests/unit/test_pg_promotion_action_time_lane_materialization.py -q
  ```

  Expected: all selected tests pass for all 22 active lanes and all untyped or
  mismatched coverage paths fail closed.

- [ ] **Step 5: Commit coverage completion.**

  ```bash
  git add scripts/runtime_active_observation_monitor.py src/infrastructure/runtime_control_state_repository.py src/application/action_time/promotion_action_time_lane.py docs/current/PRE_TRADE_RUNTIME_CONTRACT.md tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_lane_identity_migration.py tests/unit/test_pg_promotion_action_time_lane_materialization.py
  git commit -m "fix: require typed watcher coverage for action-time"
  ```

### Task 6: Contract Closure, Full Regression, and Tokyo Acceptance

**Files:**
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/P0_ACTION_TIME_FAILURE_CONSERVATION_AND_NATURAL_EVENT_ACCEPTANCE_DESIGN.md`
- Modify: `docs/current/P0_ACTION_TIME_INVOCATION_CONSISTENCY_AND_FAILURE_TRUTH_IMPLEMENTATION_PLAN.md`
- Test: existing focused suites plus repository validators

**Interfaces:**
- Consumes: completed migration, focused RED/GREEN evidence, and deployment
  target commit.
- Produces: current contract truth, exact deployment record, and an armed
  future natural-event acceptance boundary.

- [ ] **Step 1: Run the focused production-chain suite.**

  Run:

  ```bash
  pytest tests/unit/test_action_time_invocation.py tests/unit/test_action_time_ticket_materialization_sequence.py tests/unit/test_action_time_full_chain_impact.py tests/unit/test_server_product_state_refresh_sequence.py tests/unit/test_runtime_active_observation_monitor.py tests/unit/test_runtime_lane_identity_migration.py tests/unit/test_pg_promotion_action_time_lane_materialization.py tests/unit/test_runtime_process_outcome.py tests/unit/test_strategy_live_candidate_pool.py tests/unit/test_tokyo_runtime_server_monitor.py -q
  ```

  Expected: all selected tests pass with no exchange-write path exercised.

- [ ] **Step 2: Run authority, I/O, output, and document checks.**

  Run:

  ```bash
  python3 scripts/audit_production_runtime_file_io.py --fail-on-risk
  python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
  python3 scripts/validate_current_docs_authority.py
  git diff --check
  ```

  Expected: all commands exit `0`; production cadence performance risk is
  `clear`; no generated output is staged.

- [ ] **Step 3: Run the full test suite only after focused suites are green.**

  Run:

  ```bash
  pytest -q
  ```

  Expected: all tests pass; record exact count and warnings without treating
  pre-existing warnings as success evidence.

- [ ] **Step 4: Commit the integrated task.**

  ```bash
  git add docs/current src scripts migrations tests
  git commit -m "fix: make action-time invocation truth durable"
  ```

- [ ] **Step 5: Deploy through the official Tokyo path and verify read-only.**

  Run the current deploy planner/apply flow with the exact 40-character commit,
  migration `119`, quiesced watcher lifecycle sequence, then the existing
  postdeploy verifier. The verification must prove no active Ticket/order is
  modified, services are healthy, all current coverage rows are typed, and all
  forbidden effects are false.

- [ ] **Step 6: Arm natural-event acceptance.**

  The next natural fresh signal preempts ordinary engineering work. It must
  produce either a Ticket with the original signal/lane lineage or one durable
  typed non-market blocker. It must not be reported as market wait merely
  because the signal later expires.
