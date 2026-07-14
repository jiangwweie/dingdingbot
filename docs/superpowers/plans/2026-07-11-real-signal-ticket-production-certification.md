# P0-RT Real-Signal Ticket Closure Implementation Plan

> Execute inline with strict red-green TDD. Synthetic inputs remain test-only,
> and no test or deploy step may call a real exchange write.

**Goal:** Repair the shared production price/sizing/risk boundary, preserve its
first blocker in PG current truth, and certify all five current StrategyGroups
through Ticket, FinalGate, Operation Layer handoff, Runtime Safety State, and
disabled-smoke protected submit.

**Architecture:** Normalize the existing nested PG public-fact shape into one
typed Action-Time pricing reference, compute one persisted Decimal sizing/risk
decision before promotion, and make every downstream consumer validate and
reuse that decision.

**Tech stack:** Python 3, Pydantic, `decimal.Decimal`, SQLAlchemy,
PostgreSQL/SQLite test fixtures, pytest, Alembic 112.

## File Map

### New files

- `src/application/action_time/pricing_sizing.py`: typed pricing and one
  quantity/stop-risk decision.
- `src/application/action_time/ticket_materialization_sequence.py`: one
  rollback-capable PG unit for facts, projection, promotion/lane, reservation,
  and Ticket.
- `scripts/materialize_action_time_ticket_sequence.py`: thin PG CLI wrapper for
  the atomic application sequence.
- `docs/superpowers/specs/2026-07-11-real-signal-ticket-production-certification-design.md`:
  approved architecture record.
- `docs/superpowers/plans/2026-07-11-real-signal-ticket-production-certification.md`:
  execution plan.

### Expected modified files

- `src/application/action_time/fact_snapshots.py`: normalize nested production
  public facts into typed execution pricing values.
- `src/application/action_time/promotion_action_time_lane.py`: fail before lane
  creation and persist the selected sizing/risk reservation.
- `src/application/action_time/action_time_ticket.py`: validate and consume the
  persisted reservation rather than recomputing it.
- `src/application/action_time/protected_submit_attempt.py`: use the persisted
  intended quantity for all order legs.
- `scripts/run_server_product_state_refresh_sequence.py`: replace four
  Action-Time subprocess steps with the bounded atomic sequence.
- `src/application/runtime_process_outcome.py` or the current projection owner:
  preserve unresolved engineering first blocker across later no-signal ticks.
- `tests/unit/test_pg_promotion_action_time_lane_materialization.py`: producer-
  shaped pricing and early-blocker tests.
- `tests/unit/test_action_time_ticket_materialization.py`: reservation
  consumption and mismatch tests.
- `tests/unit/test_action_time_full_chain_impact.py`: six-Event-Spec production-
  shaped certification matrix.
- `tests/unit/test_ticket_bound_protected_submit_attempt.py`: reserved quantity
  lineage tests, if not already covered in the full-chain suite.
- `docs/current/MAIN_CONTROL_ROADMAP.md` and
  `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`: current P0-RT/P0-PC
  route and release gate.

The exact projection owner will be selected after its current writer and
replacement semantics are verified. No new table or file-backed truth is
allowed.

## Task 1: Lock the production-shape defect with failing tests

### Step 1: Add a focused normalization test

Create a public-fact snapshot with this producer shape and no top-level price:

```python
{
    "facts": {
        "mark_price": "100.0",
        "bid_price": "99.9",
        "ask_price": "100.1",
        "qty_step": "0.001",
        "min_notional": "5",
    }
}
```

Assert long uses best ask, short uses best bid, source lineage is retained, and
all numeric values are Decimal-safe/canonically serialized.

Run:

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  -k "production_public_fact_shape or side_specific_entry_reference"
```

Expected before implementation: pricing reference is absent and promotion can
open a lane with zero risk.

### Step 2: Add fail-closed input tests

Cover missing side quote, mark-only data, invalid `qty_step`, quantity rounded
to zero, below-minimum notional, wrong-side stop, and zero stop distance.
Assert no Action-Time lane or active budget reservation is created.

## Task 2: Implement typed pricing and one sizing/risk decision

### Step 1: Add typed domain-adjacent application models

Implement Decimal-backed Pydantic models or frozen dataclasses in
`pricing_sizing.py`:

- `ActionTimePricingReference`;
- `TicketSizingRiskDecision`;
- structured blocker/result type.

Reject non-finite, malformed, zero, negative, stale, or incomplete values.

### Step 2: Normalize nested public facts

In `fact_snapshots.py`, consume `source_values["facts"]` and materialize the
side-specific pricing reference plus quantity rules into the Action-Time fact
snapshot. Do not add loose alias fallback and do not derive market facts from
strategy semantics.

### Step 3: Compute and persist the decision before lane creation

In `promotion_action_time_lane.py`:

1. compute target notional, step-rounded intended quantity, notional, stop
   distance, and risk at stop;
2. append exact blockers when the decision is invalid;
3. include the decision in capital arbitration;
4. persist it into the existing budget reservation columns;
5. open a lane only when the persisted decision is valid and within loss-unit
   scope.

Run:

```bash
pytest -q tests/unit/test_pg_promotion_action_time_lane_materialization.py
```

## Task 3: Make the Action-Time Ticket unit atomic and TTL-bounded

### Step 1: Add atomicity red tests

Exercise the sequence through one SQLAlchemy connection and assert:

- success commits action-time fact, promotion, budget, lane, and Ticket;
- a Ticket blocker after promotion leaves none of those partial action rows;
- the exact blocker is persisted in `brc_runtime_process_outcomes` for every
  affected `StrategyGroup + symbol + side`, not only the first failed lane;
- completion at or after the shortest source/Ticket TTL rolls back the action
  rows and persists `action_time_sequence_ttl_expired_before_ticket_commit`;
- no-signal and fact-blocked outcomes create no lane or Ticket.

### Step 2: Implement the application sequence

Add `ticket_materialization_sequence.py` with one outer transaction-compatible
function and one nested action savepoint. Reuse the existing fact, lightweight
readiness projector, promotion, and Ticket functions; do not duplicate their
business rules. The function returns a typed/structured result and writes one
sequence-level process outcome per affected lane. A fresh signal may re-certify
and clear an older lane blocker; a global no-signal outcome may not erase it.

### Step 3: Replace the subprocess gap

Add the thin CLI wrapper and update
`run_server_product_state_refresh_sequence.py` so action-time mode invokes one
required `materialize_action_time_ticket_sequence` step instead of four
separate commands. Keep FinalGate, Operation Layer handoff, Runtime Safety
State, and after-action projection as downstream required steps. Add a bounded
subprocess timeout and classify timeout as a required-step failure. The
in-transaction projector refreshes only PG pretrade readiness; Candidate Pool,
Daily Table, Goal Status, and Owner snapshots remain after the critical path.
Business blockers exit successfully after their PG outcome is persisted, while
process/database failures still fail the watcher service.

Run:

```bash
pytest -q \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_server_product_state_refresh_sequence.py
```

## Task 4: Make Ticket and submit consume the same decision

### Step 1: Add Ticket red tests

Assert Ticket creation succeeds when the active budget reservation already
contains the valid decision. Assert missing, expired, invalid, or mismatched
reservation fields block without recomputation.

### Step 2: Remove Ticket recomputation

Change `action_time_ticket.py` to validate the reservation with the shared
model/helper and bind the Ticket to it. Ticket creation may mark the
reservation consumed and attach `ticket_id`, but it must not change pricing,
quantity, stop, or risk values.

### Step 3: Add protected-submit quantity lineage tests

Assert entry and stop use the exact budget reservation `intended_qty`; TP1
retains the current one-half target but floors it to the same `qty_step`.
Assert a target-notional recalculation or quantity mismatch cannot pass.

Run:

```bash
pytest -q \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py
```

## Task 5: Add six-Event-Spec production-shaped certification

### Step 1: Replace downstream-complete fixture inputs

Extend the full-chain harness so public facts use the production nested
`facts` shape and strategy evaluator observations provide only event semantics
and protection references. Do not inject top-level `last_price`, intended
quantity, risk, or Ticket-ready values.

### Step 2: Parametrize all current executable Event Specs

Certify:

```text
CPM-LONG
MPG-LONG
MI-LONG
SOR-LONG
SOR-SHORT
BRF2-SHORT
```

For each case assert positive step-normalized quantity/risk, matching
reservation lineage, Ticket creation, FinalGate pass, Operation Layer handoff,
Runtime Safety State `submit_allowed=true`, and disabled-smoke protected submit
without exchange write.

### Step 3: Add a release-gate negative matrix

For at least one long and one short case, corrupt each production boundary in
turn and prove the first blocker is exact and occurs before the lane.

Run:

```bash
pytest -q tests/unit/test_action_time_full_chain_impact.py \
  -k "production_shaped or five_strategygroup"
```

## Task 6: Preserve engineering blocker truth in PG

### Step 1: Find the single current projection owner

Trace the writer for Goal Status, Candidate Pool, Daily Live Enablement, and
runtime process outcome replacement semantics. Select the narrowest existing
PG projection that owns the first blocker; do not duplicate ownership.

### Step 2: Add an overwrite-regression red test

Write an engineering failure from an eligible chain, then run a later no-
signal tick. Assert the current first blocker remains the unresolved
engineering blocker until a successful certification/live chain supersedes it.

### Step 3: Implement explicit blocker precedence

Make current projection replacement distinguish market absence from unresolved
pipeline failure. Preserve append-only historical outcomes and keep Owner-
facing state at `temporarily_unavailable` or equivalent abnormal product state,
not normal `waiting_for_opportunity`, while the defect is unresolved.

Run the exact affected repository/read-model tests plus:

```bash
pytest -q tests/unit/test_server_product_state_refresh_sequence.py
```

## Task 7: Repository verification

### Step 1: Run the focused regression set

```bash
pytest -q \
  tests/unit/test_action_time_ticket_materialization.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_action_time_full_chain_impact.py \
  tests/unit/test_runtime_control_state_repository.py \
  tests/unit/test_ticket_bound_protected_submit_attempt.py \
  tests/unit/test_server_product_state_refresh_sequence.py
```

### Step 2: Run source, file-I/O, and document audits

```bash
python3 scripts/audit_production_runtime_file_io.py --json
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/validate_current_docs_authority.py
git diff --check
```

Require `performance_risk.status=clear`, zero frequent report writers, no new
runtime JSON/MD authority, and valid current-doc authority.

### Step 3: Run the full suite

```bash
pytest -q
```

Inspect the complete diff and worktree status before commit.

## Task 8: Commit, push, deploy, and accept Tokyo

### Step 1: Commit and push the focused branch

Commit only the approved design, plan, roadmap changes, implementation, and
tests. Push `codex/p0-real-signal-ticket-closure` and verify remote head equals
local head.

### Step 2: Run git-based deployment preflight

Use the current deployment planner/executor with:

- deployed baseline `12feb47e2cd777a93c314c781dbafdcd69930cfc` unless live
  verification proves a newer authorized release;
- exact pushed target commit;
- remote and target migration count `112` unless the committed diff adds an
  explicitly reviewed migration;
- active release path `/home/ubuntu/brc-deploy/app/current`.

Stop on release drift, migration drift, unpushed head, audit regression,
service-health failure, or any exchange-write-capable acceptance path.

### Step 3: Apply and verify

Verify manifest commit, `alembic current`, backend HTTP health, watcher timer,
runtime monitor timer, Ticket lifecycle timer, and one bounded watcher tick.

### Step 4: Prove five-StrategyGroup trading-door readiness

Use PG/current projections to prove:

- five current enabled StrategyGroups;
- six current executable Event Specs;
- twenty-two current candidate scopes and watcher coverage;
- production-shaped certification passed for all six Event Specs;
- current execution-input blocker is absent;
- a new eligible production signal can progress to Ticket, FinalGate,
  Operation Layer handoff, and Runtime Safety State without manual repair;
- no exchange write, real order, profile expansion, sizing expansion,
  credential mutation, withdrawal, or transfer occurred during acceptance.

## Done When

The exact deployed commit consumes the real nested production price shape,
persists one valid quantity/stop-risk decision before lane creation, reuses it
through Ticket and submit request, prevents later market-wait ticks from hiding
an unresolved engineering defect, and carries all five StrategyGroups through
the non-executing trading door under the six-Event-Spec certification matrix.

## Hard Stop

Do not deploy if any focused or full test fails, if quantity can be recomputed
differently downstream, if a missing quote silently falls back to mark price,
if synthetic certification can grant exchange-write authority, if PG ceases to
be runtime truth, if scope or capital policy expands, or if the exact pushed
release cannot be proven.
