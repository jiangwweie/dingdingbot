---
title: P1_OPPORTUNITY_FEEDBACK_CALIBRATION_IMPLEMENTATION_PLAN
status: IN_PROGRESS_DEPLOYMENT_AND_HISTORICAL_CALIBRATION
authority: docs/current/P1_OPPORTUNITY_FEEDBACK_CALIBRATION_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-12
---

# P1 Opportunity Feedback Calibration Implementation Plan

> **For agentic workers:** Execute tasks in order with TDD. No task may change
> strategy semantics, candidate scope, Owner policy, sizing, FinalGate,
> Operation Layer, or exchange-write authority.

**Goal:** Build a typed evidence-to-decision opportunity calibration core and
complete nullable ticket-bound funding/exit-slippage enrichment for the
existing Live Outcome Ledger.

**Architecture:** Reuse `RuntimeStrategySignalEvaluationService` for strategy
semantics, aggregate already evaluated replay/live observations in a pure
domain module, and extend the existing read-only exchange snapshot and Outcome
paths for post-trade economics. No new runtime report or source of truth is
introduced.

**Tech Stack:** Python 3.14, Pydantic, `decimal.Decimal`, SQLAlchemy Core, CCXT,
pytest.

## Global Constraints

- PG/current remains production truth.
- Replay and calibration are non-authoritative.
- No automatic Event Spec, RequiredFacts, scope, risk, leverage, or policy mutation.
- No new JSON/Markdown runtime reader or recurring writer.
- No heavy calibration work in watcher/monitor cadence.
- Funding/slippage remain post-trade facts and never block submit.
- Natural fresh signal is a P0 interrupt.

## Task 1: Typed Opportunity Calibration Core

**Files:**

- Create: `src/domain/opportunity_feedback_calibration.py`
- Test: `tests/unit/test_opportunity_feedback_calibration.py`

**Produces:** `OpportunityEvaluation`, `OpportunityCalibrationWindow`,
`OpportunityCalibrationResult`, and `calibrate_opportunity_feedback(...)`.

- [x] Write failing tests for identity validation, 90/365-day aggregation,
  near-miss counts, missing counterparts, fact/result parity, bounded proposals,
  and forbidden authority payloads.
- [x] Run the focused test and confirm red failure for missing implementation.
- [x] Implement pure typed models and deterministic reducer with no I/O.
- [x] Run the focused test and confirm all cases pass.

## Task 2: Production Evaluator Observation Adapter

**Files:**

- Create: `src/application/opportunity_feedback_calibration_service.py`
- Test: `tests/unit/test_opportunity_feedback_calibration_service.py`
- Reuse: `src/application/runtime_strategy_signal_evaluation_service.py`

**Produces:** `evaluate_replay_observation(...)` and
`build_calibration_result(...)`.

- [x] Write failing tests proving the service calls the existing production
  evaluator and maps signal/no-signal/invalid plus exact fact observations.
- [x] Prove CPM, MPG, MI, SOR long/short, and BRF2 Event Spec identities are
  supported without copying evaluator rules.
- [x] Implement the adapter and reject unsupported side/version/event mappings.
- [x] Run service and existing evaluator tests.

## Task 3: Ticket-Bound Funding Snapshot

**Files:**

- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `src/application/action_time/exchange_snapshot_provider.py`
- Modify: `src/application/action_time/ticket_bound_fill_projector.py`
- Test: `tests/unit/test_ticket_bound_exchange_snapshot_provider.py`
- Test: `tests/unit/test_live_outcome_ledger.py`
- Test: `tests/unit/test_ticket_bound_runtime_safety_state_materialization.py`

**Produces:** `ExchangeGateway.fetch_funding_income(...)`, normalized
`funding_income` rows, and exact exit-order reference values on projected fills.

- [x] Write failing tests for signed funding rows, exact symbol/time filtering,
  timeout behavior, and zero exchange writes.
- [x] Implement Binance USD-M read-only income retrieval through the supported
  CCXT raw income method; reject unsupported capability explicitly.
- [x] Normalize income identity, symbol, amount, asset, type, and timestamp.
- [x] Project exact exit order price/trigger reference into fill lifecycle events.
- [x] Run focused snapshot and fill tests.

## Task 4: Live Outcome Economics

**Files:**

- Modify: `src/application/action_time/live_outcome_ledger.py`
- Create: `migrations/versions/2026-07-12-116_add_opportunity_feedback_economics.py`
- Modify: `tests/support/runtime_control_state_schema.py`
- Test: `tests/unit/test_live_outcome_ledger.py`
- Test: `tests/unit/test_opportunity_feedback_migration.py`

**Produces:** signed `funding`, signed `exit_slippage`,
`net_pnl = realized_pnl - fees + funding`, and fee/funding-adjusted `r_multiple`.

- [x] Write failing tests for funding paid/received, ambiguous attribution,
  unrelated rows, SL/TP1/RUNNER_SL exit references, net PnL, and R.
- [x] Implement exact ticket-window funding attribution under the current
  single-active-position boundary.
- [x] Keep unavailable or ambiguous funding/exit reference nullable.
- [x] Add nullable `exit_slippage` and `net_pnl` columns at PG migration `116`.
- [x] Run focused Outcome and migration tests.

## Task 5: Current Planning And Contract Closure

**Files:**

- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/LIVE_OUTCOME_LEDGER_CONTRACT.md`
- Modify: `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`

- [x] Make P1-OFC the only active medium-scale mainline and mark P1-TFC as a
  deployed baseline.
- [x] Document calibration as non-authority and Outcome enrichment as nullable.
- [x] Confirm no current document calls fixed 20 USDT/2x sizing or P1-TFC the
  active program.

## Task 6: Verification

- [x] Run focused OFC, evaluator, snapshot, fill, Outcome, and lifecycle tests.
- [x] Run `python3 scripts/validate_current_docs_authority.py`.
- [x] Run `python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked`.
- [x] Run `python3 scripts/validate_no_runtime_file_authority.py`.
- [x] Run `python3 scripts/audit_production_runtime_file_io.py` and require
  `performance_risk.status=clear`.
- [x] Run `git diff --check`.
- [x] Run the full pytest suite and require zero failures.

## Task 7: Event-Side Projection And No-Action Fact Observability

**Files:**

- Modify: `src/application/opportunity_feedback_calibration_service.py`
- Modify: current production evaluator modules only where required to expose
  already-computed facts
- Test: `tests/unit/test_opportunity_feedback_calibration_service.py`
- Test: focused evaluator tests

- [x] Write failing tests proving opposite-side output cannot abort or become
  the selected Event Spec signal.
- [x] Write failing tests proving valid `NO_ACTION` outputs expose known false
  Event Spec facts without changing signal semantics.
- [x] Implement event-side projection and evaluator fact observability.
- [x] Run focused evaluator and OFC adapter regression tests.

## Task 8: Manual PG-Owned Historical Replay Lab

**Files:**

- Create: `src/application/opportunity_feedback_historical_replay.py`
- Create: `src/infrastructure/binance_usdm_historical_candle_source.py`
- Create: `scripts/run_opportunity_feedback_historical_calibration.py`
- Test: `tests/unit/test_opportunity_feedback_historical_replay.py`
- Test: `tests/unit/test_run_opportunity_feedback_historical_calibration.py`

- [x] Write failing tests for PG scope loading, 1h/4h alignment, SOR UTC
  session windows, MPG/MI comparative universes, 90/365 aggregation, and zero
  runtime authority/file writes.
- [x] Implement bounded public-candle pagination and typed in-memory replay.
- [x] Keep the command manual, stdout-only, timeout-bounded, and read-only.
- [ ] Run all 22 current scopes and retain only terminal stdout evidence.

## Task 9: Push, Tokyo Deploy, Migration 116, And Watcher Acceptance

- [ ] Re-run focused tests, full regression, authority validators, and file-I/O
  performance audit.
- [ ] Push the exact focused branch and build a commit-bound deploy plan.
- [ ] Require no active real lifecycle, critical command, domain hold, or
  unprotected real attempt before release switch.
- [ ] Deploy the exact commit, apply migration 116, recertify lifecycle
  mutation, and complete readonly postdeploy acceptance.
- [ ] Confirm the Tokyo watcher and monitor timers remain active and inspect PG
  current signal/Ticket state; a natural signal preempts Replay work.

## Done When

The typed calibration core and production-evaluator adapter are complete, all
six Event Spec identities are covered, replay cannot create authority, actual
funding and exit slippage enrich existing real Outcomes without blocking
trading, current docs name one active program, and full regression plus
authority/file-I/O validators pass.
