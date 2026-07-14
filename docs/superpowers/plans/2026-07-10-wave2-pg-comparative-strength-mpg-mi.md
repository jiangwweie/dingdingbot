# Wave 2 PG Comparative Strength And MPG/MI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce aligned PG comparative-strength facts, certify MPG-LONG v2, then reuse the capability for MI-LONG v2.

**Architecture:** A pure Decimal rank calculator consumes aligned closed candles. A PG application service derives its universe from active candidate scopes, fetches each unique symbol once, and writes bounded `strategy_comparative` fact snapshots. Runtime signal inputs consume those PG snapshots; event evaluators emit typed observations; migrations 108 and 109 independently grant Event Spec eligibility.

**Tech Stack:** Python 3.14, Pydantic v2, Decimal, SQLAlchemy/Alembic, PostgreSQL fact snapshots, pytest.

## Global Constraints

- PG current state is the only universe and fact authority.
- No JSON/MD runtime files or stdout authority.
- Missing, stale, partial, or time-misaligned peer inputs fail closed.
- Fetch each unique symbol at most once per watcher tick.
- Keep MPG and MI Event Spec versions and eligibility independent.
- Do not change profile, capital, leverage, notional, symbol scope, side scope, lane concurrency, FinalGate, Operation Layer, or exchange behavior.

---

### Task 1: Pure Comparative Strength Contract

**Files:**
- Create: `src/domain/comparative_strength.py`
- Modify: `src/domain/strategy_family_signal.py`
- Create: `tests/unit/test_comparative_strength.py`

**Interfaces:**
- Produces: `ComparativeStrengthSnapshot`, `ComparativeStrengthMember`, and `compute_comparative_strength(...)`.
- Adds: optional `comparative_strength_snapshot` to `StrategyFamilySignalInput`.

- [ ] Write failing tests for Decimal returns, deterministic competition rank, aligned close-time enforcement, missing member rejection, and typed input serialization.
- [ ] Run `pytest -q tests/unit/test_comparative_strength.py` and verify RED.
- [ ] Implement the pure models/calculator with no I/O imports.
- [ ] Run the tests and verify GREEN.
- [ ] Commit `feat(strategy): add comparative strength contract`.

### Task 2: PG Comparative Fact Materialization

**Files:**
- Create: `src/application/comparative_strength_fact_service.py`
- Modify: `scripts/fetch_binance_usdm_public_facts.py`
- Modify: `src/application/action_time/runtime_pg_fact_snapshots.py`
- Create: `tests/unit/test_comparative_strength_fact_service.py`

**Interfaces:**
- Consumes: active MPG/MI PG candidate scopes and bounded closed 1h candles.
- Produces: `fact_surface=strategy_comparative` snapshots with rank/return/universe lineage.

- [ ] Write failing tests proving PG-derived universe, five unique fetches, seven fact rows, and exact partial/misaligned blockers.
- [ ] Implement one-fetch-per-symbol collection and bounded PG upserts.
- [ ] Verify no JSON/MD writes and all tests GREEN.
- [ ] Commit `feat(runtime): materialize PG comparative strength facts`.

### Task 3: Runtime Signal Input PG Overlay

**Files:**
- Modify: `src/application/readmodels/runtime_strategy_signal_input.py`
- Modify: `tests/unit/test_runtime_strategy_signal_input.py`

**Interfaces:**
- Consumes: latest fresh `strategy_comparative` PG fact for exact StrategyGroup + symbol + side.
- Produces: typed `comparative_strength_snapshot` on signal input.

- [ ] Write failing fresh/missing/stale/cross-group rejection tests.
- [ ] Implement exact-scope PG overlay; do not read artifact files.
- [ ] Run focused tests and commit `feat(runtime): attach PG comparative strength context`.

### Task 4: MPG-LONG v2 Certification

**Files:**
- Modify: `src/domain/mpg_momentum_persistence_evaluator.py`
- Create: `migrations/versions/2026-07-10-108_certify_mpg_long_trial_event.py`
- Modify: `scripts/seed_runtime_control_state_foundation.py`
- Modify: `tests/unit/test_strategy_family_signal_contract.py`
- Create: `tests/unit/test_mpg_long_v2_migration.py`

**Interfaces:**
- Produces typed MPG facts and current `event_spec:MPG-001:MPG-LONG:v2` trial authority.

- [ ] Write failing evaluator and migration tests.
- [ ] Emit trial grade only when rank is 1, return is positive, momentum persists, and protection reference exists.
- [ ] Preserve MPG v1 observe-only and atomically switch four MPG bindings.
- [ ] Run focused vertical regression and commit `feat(strategy): certify MPG-LONG v2`.

### Task 5: MI-LONG v2 Reuse Certification

**Files:**
- Modify: `src/application/runtime_strategy_signal_evaluation_service.py`
- Create: `migrations/versions/2026-07-10-109_certify_mi_long_trial_event.py`
- Modify: `scripts/seed_runtime_control_state_foundation.py`
- Create: `tests/unit/test_mi_long_v2_migration.py`

**Interfaces:**
- Reuses the Task 1-3 comparative snapshot.
- Produces typed MI facts and current `event_spec:MI-001:MI-LONG:v2` trial authority.

- [ ] Write failing reuse/evaluator/migration tests.
- [ ] Require existing 3% impulse plus rank 1; use lookback close as invalidation reference.
- [ ] Preserve MI v1 observe-only and atomically switch three MI bindings.
- [ ] Run Wave 2 vertical regression and commit `feat(strategy): certify MI-LONG v2`.

### Task 6: Governance And Production Acceptance

- [ ] Run file-I/O, no-file-authority, output-scope, migration-chain, watcher, candidate-pool, lane, ticket, Runtime Safety, and protected-submit tests.
- [ ] Verify one real lane maximum and unchanged policy/profile/sizing scope.
- [ ] Deploy each certification as an independently accepted checkpoint; do not wait for a market signal before starting the next engineering wave.
