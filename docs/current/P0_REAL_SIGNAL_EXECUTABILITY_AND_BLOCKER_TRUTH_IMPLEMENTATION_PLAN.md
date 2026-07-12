---
title: P0_REAL_SIGNAL_EXECUTABILITY_AND_BLOCKER_TRUTH_IMPLEMENTATION_PLAN
status: IN_PROGRESS
authority: docs/current/P0_REAL_SIGNAL_EXECUTABILITY_AND_BLOCKER_TRUTH_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-12
---

# P0 Dynamic Risk Sizing And Blocker Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace fixed notional, fixed leverage, and fixed loss-unit sizing with one PG-backed dynamic planned-stop-risk decision, then conserve exact feasibility blockers through the real-signal-to-Ticket chain.

**Architecture:** One pure domain decision consumes fresh instrument rules, side-aware entry price, protective Stop, fresh account capacity, and versioned Owner risk policy. It returns quantity, selected leverage, margin, and planned stop risk once; promotion, Ticket, FinalGate, Operation Layer, and protected submit validate that lineage without recomputation.

**Tech Stack:** Python 3.10+, Pydantic v2, `decimal.Decimal`, SQLAlchemy 2, Alembic, PostgreSQL, pytest, Binance USD-M signed read-only account facts.

## Implementation Status

| Task | Status | Current evidence |
| --- | --- | --- |
| 1. Pure sizing decision | **implemented** | 3% wallet risk, 90% available margin, lowest sufficient integer leverage, ceiling shrink, minimum-quantity blockers |
| 2. Exact account/rule facts | **implemented** | exact wallet/available strings, market-entry min qty/step/notional, exchange leverage bracket |
| 3. PG Owner policy | **implemented locally** | migration 115 and seed values `0.03/0.90/10` |
| 4. Ticket lineage | **implemented locally** | budget/Ticket explicit fields and ENTRY `desired_leverage` command |
| 5. Blocker truth | **implemented locally** | expiry conservation plus exact certified resolution surface |
| 6. Post-trade costs | **partial, non-blocking** | actual commission and entry slippage implemented; funding remains nullable pending income-row ingestion |
| 7. Regression/deploy | **in progress** | focused and 22-scope full-chain suites green; validators, commit, Tokyo deploy, and postdeploy acceptance remain |

## Global Constraints

- Owner policy is exactly `planned_stop_risk_fraction=0.03`, `max_initial_margin_utilization=0.90`, `max_leverage=10`, `attempt_cap=1`.
- The entire subaccount is Owner-reviewed loss-capable experiment capital; do not add a fixed notional cap or hidden de-risking layer.
- Fees, slippage, and funding do not enter the pre-submit risk gate; they remain post-trade Outcome facts.
- `planned_stop_risk` is not named or represented as guaranteed maximum loss.
- The system selects the lowest sufficient integer leverage, never above Owner or exchange authority; if the ceiling binds, it shrinks quantity.
- Only the exchange minimum executable quantity exceeding risk or margin capacity blocks execution.
- PG/current services are runtime truth; no JSON/MD/output authority or recurring report writes.
- Use `Decimal`, fail closed on stale/missing facts, preserve atomic Action-Time rollback, and do not bypass FinalGate or Operation Layer.
- No credential mutation, withdrawal, transfer, unauthorized scope expansion, or synthetic production signal/Ticket insertion.
- Every behavior change follows RED -> GREEN -> REFACTOR.

---

### Task 1: Pure Dynamic Execution Sizing Decision

**Files:**
- Create: `src/domain/execution_sizing.py`
- Create: `tests/unit/test_execution_sizing.py`

**Interfaces:**
- Consumes: `ExecutionInstrumentRules`, `ExecutionAccountCapacity`, `ExecutionSizingPolicy`, and `protective_stop_price`.
- Produces: `ExecutionSizingDecisionResult` with one optional immutable `ExecutionSizingDecision` and exact blockers.

- [ ] **Step 1: Write failing policy, leverage, shrink, and minimum-quantity tests**

```python
def test_one_hundred_usdt_half_percent_stop_selects_seven_x():
    result = decide_execution_sizing(
        rules=_rules(price="100", min_qty="0.001", step="0.001", min_notional="5"),
        account=_account(wallet="100", available="100"),
        policy=_policy(risk="0.03", margin="0.90", max_leverage=10),
        protective_stop_price=Decimal("99.5"),
    )
    assert result.blockers == ()
    assert result.decision.intended_qty == Decimal("6")
    assert result.decision.effective_notional == Decimal("600")
    assert result.decision.selected_leverage == 7
    assert result.decision.reserved_margin == Decimal("600") / Decimal("7")
    assert result.decision.planned_stop_risk == Decimal("3")


def test_max_leverage_shrinks_quantity_without_blocking():
    result = decide_execution_sizing(
        rules=_rules(price="100", min_qty="0.001", step="0.001", min_notional="5"),
        account=_account(wallet="100", available="100"),
        policy=_policy(risk="0.03", margin="0.90", max_leverage=5),
        protective_stop_price=Decimal("99.5"),
    )
    assert result.blockers == ()
    assert result.decision.selected_leverage == 5
    assert result.decision.intended_qty == Decimal("4.5")
    assert result.decision.planned_stop_risk == Decimal("2.25")


def test_minimum_executable_quantity_above_risk_budget_blocks():
    result = decide_execution_sizing(
        rules=_rules(price="100", min_qty="1", step="1", min_notional="100"),
        account=_account(wallet="10", available="10"),
        policy=_policy(),
        protective_stop_price=Decimal("95"),
    )
    assert result.decision is None
    assert result.blockers == (
        "minimum_executable_quantity_exceeds_planned_stop_risk_budget",
    )
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/unit/test_execution_sizing.py`

Expected: collection fails because `src.domain.execution_sizing` does not exist.

- [ ] **Step 3: Implement the immutable domain model**

Required types:

```python
class ExecutionSizingPolicy(BaseModel):
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    max_leverage: int
    policy_version: str

class ExecutionAccountCapacity(BaseModel):
    total_wallet_balance: Decimal
    available_balance: Decimal
    source_fact_snapshot_id: str
    observed_at_ms: int
    valid_until_ms: int

class ExecutionSizingDecision(BaseModel):
    intended_qty: Decimal
    effective_notional: Decimal
    selected_leverage: int
    reserved_margin: Decimal
    planned_stop_risk_budget: Decimal
    planned_stop_risk: Decimal
```

Use ceiling-to-step only for exchange minimum quantity and floor-to-step for executable quantity. Recompute every invariant after quantization.

- [ ] **Step 4: Run GREEN**

Run: `pytest -q tests/unit/test_execution_sizing.py`

Expected: all dynamic sizing tests pass.

### Task 2: Persist Exact Account Capacity And Instrument Minimums

**Files:**
- Modify: `scripts/collect_strategy_group_live_facts_readonly.py`
- Modify: `src/application/action_time/account_safe_facts.py`
- Modify: `src/application/action_time/runtime_pg_fact_snapshots.py`
- Modify: `scripts/fetch_binance_usdm_public_facts.py`
- Modify: `src/application/action_time/pricing_sizing.py`
- Test: corresponding focused unit tests.

**Interfaces:**
- Produces numeric PG fact values `total_wallet_balance`, `available_balance`, `min_qty`, `qty_step`, `min_notional`, and source validity.

- [ ] **Step 1: Add failing producer-to-PG shape tests** proving numeric balances are retained and malformed/negative/stale values fail closed.
- [ ] **Step 2: Run focused tests and verify expected missing-key failures.**
- [ ] **Step 3: Persist exact Decimal-compatible strings without logging account secrets or adding files.**
- [ ] **Step 4: Run account/public fact tests and verify producer-consumer parity.**

### Task 3: Version The Owner Dynamic Risk Policy In PG

**Files:**
- Create: `migrations/versions/2026-07-12-115_add_dynamic_execution_risk_policy.py`
- Modify: `scripts/seed_runtime_control_state_foundation.py`
- Modify: current policy projector/readers found by `rg "max_notional|loss_unit|policy.get\(\"leverage\""`.
- Test: migration, seed, and repository tests.

**Interfaces:**
- Produces current PG policy columns `planned_stop_risk_fraction`, `max_initial_margin_utilization`, and `max_leverage`.
- Retires legacy `max_notional`, `leverage`, and `loss_unit` from runtime sizing decisions without reinterpreting historical rows.

- [ ] **Step 1: Write failing schema and seed tests** for exact values `0.03`, `0.90`, and `10`.
- [ ] **Step 2: Verify RED against migration 114.**
- [ ] **Step 3: Add migration constraints** requiring fractions in `(0, 1]` and integer max leverage in `[1, 125]`.
- [ ] **Step 4: Change seed provenance to an explicit Owner policy version and remove fixed sizing fields from new writes.**
- [ ] **Step 5: Run migration upgrade/downgrade and policy tests.**

### Task 4: Reuse One Decision Through Action-Time Ticket Lineage

**Files:**
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/budget_stop_risk.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `src/application/action_time/finalgate_preflight.py`
- Modify: `src/application/action_time/operation_layer_handoff.py`
- Modify: `src/application/action_time/protected_submit_attempt.py`
- Test: promotion, Ticket, safety, FinalGate, handoff, and submit tests.

**Interfaces:**
- Consumes one `ExecutionSizingDecision` and persists its lineage.
- Produces identical `intended_qty`, `selected_leverage`, `reserved_margin`, `planned_stop_risk_budget`, and `planned_stop_risk` downstream.

- [ ] **Step 1: Write failing parity and atomic rollback tests.**
- [ ] **Step 2: Verify existing code recomputes fixed-target quantity or fixed leverage.**
- [ ] **Step 3: Replace recomputation with typed reservation validation.**
- [ ] **Step 4: Verify that missing/stale account capacity, invalid Stop direction, minimum-quantity risk overflow, and lineage drift all fail before submit.**

- [x] **Step 5: Persist ENTRY-only `desired_leverage` in the durable command and set Binance leverage before order creation.** Protection and exit commands cannot mutate leverage; ambiguous dispatch freezes the netting domain.

### Task 5: Truthful Readiness And Conserved Blockers

**Files:**
- Modify: Candidate Pool/readiness projectors and existing monitor/Owner read models.
- Reuse: `brc_runtime_process_outcomes`; add no new packet or projection.
- Test: 22-scope, expiry, resolution, monitor transition, and dedupe tests.

**Interfaces:**
- Produces exact internal blockers and one Owner product state.

- [ ] **Step 1: Write failing tests** for risk-budget overflow, margin-capacity overflow, and old fixed-cap incident reclassification.
- [ ] **Step 2: Implement blocker conservation until a newer policy/account/rule certification or successful Ticket resolves it.**
- [ ] **Step 3: Map Owner wording to `当前止损与资金条件无法形成合规仓位，暂不可用`.**
- [ ] **Step 4: Verify no-signal state cannot erase a lane-scoped business blocker.**

### Task 6: Post-Trade Cost Truth And Legacy Sizing Removal

**Files:**
- Modify: `src/application/action_time/live_outcome_ledger.py`
- Delete or migrate: duplicate entry-sizing implementations.
- Test: actual fill VWAP, commission, funding, net PnL, and planned-R calculations.

**Interfaces:**
- Currently produces actual fill gross PnL, commission, signed entry slippage, fee-adjusted R, and a nullable funding field.
- Funding income and exit-reference slippage require ticket-bounded exchange income/reference facts; they remain unavailable rather than estimated until that collector exists.
- Does not feed these costs back into the current pre-submit hard gate.

- [ ] **Step 1: Write failing post-trade cost tests.**
- [ ] **Step 2: Complete ticket-bounded funding income ingestion without estimates.** Actual commission and entry slippage are implemented.
- [ ] **Step 3: Remove duplicate fixed-notional sizing authority and verify repository search is clean.**

### Task 7: Regression, Deploy, And Read-Only Acceptance

**Files:**
- Modify current roadmap/program/schema/contract documents with the final commit and migration evidence.

- [ ] **Step 1: Run focused risk, account, action-time, lifecycle, and six-event certification suites.**
- [ ] **Step 2: Run full regression only after focused suites are green.**
- [ ] **Step 3: Run docs, output-scope, runtime file-I/O, and diff validators.**
- [ ] **Step 4: Commit and push the reviewed checkpoint.**
- [ ] **Step 5: Deploy migration and code together through the bounded Tokyo git-export path.**
- [ ] **Step 6: Verify PG policy `0.03/0.90/10`, fresh numeric account facts, service health, no synthetic execution rows, and zero exchange writes during acceptance.**
- [ ] **Step 7: Leave the watcher active; the next natural signal becomes the live calibration interrupt without blocking remaining engineering.**

## Completion Audit

The task is complete only when current code and Tokyo runtime no longer consult fixed `20 USDT`, fixed `2x`, or fixed `10 USDT loss_unit` for new entry sizing; one typed dynamic decision reaches Ticket and submit validation; exact blockers survive signal expiry; all tests and validators pass; and only natural venue outcome calibration remains market-dependent.
