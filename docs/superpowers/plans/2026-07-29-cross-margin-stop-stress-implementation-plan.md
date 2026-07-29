# Cross-Margin Stop-Stress Authority Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace liquidation-price command authority with one typed Cross Margin Stop stress proof reused by CapacityClaim, ENTRY dispatch, and post-fill reconciliation, while preserving multi-position lifecycle, Settlement/Review fairness, and StrategyUniverse switching.

**Architecture:** Add one pure Domain evaluator and one canonical `AccountRiskSnapshot` read boundary. Application services compose account facts with certified instrument rules and persist exact evidence. Existing Entry, Lifecycle, Reconciliation, Command, Settlement, Review, Incident, Monitor, and StrategyUniverse chains remain the only runtime paths.

**Tech Stack:** Python 3.13, Pydantic v2, `decimal.Decimal`, SQLAlchemy async, PostgreSQL 16, Alembic, pytest/pytest-asyncio, Ruff, Mypy, Docker PostgreSQL.

## Global Constraints

- Local engineering only. Do not deploy, change Tokyo systemd, mutate Tokyo PostgreSQL, enable Entry, or write to the exchange.
- Follow RED/GREEN/REFACTOR for every production behavior. Preserve the failing assertion or command in the task log before production edits.
- Production code stays under `src/trading_kernel/**`; schema changes stay under `migrations/trading_kernel/**`.
- Keep Domain pure: no Application imports, SQLAlchemy, venue clients, filesystem, subprocess, web frameworks, `float`, or network I/O.
- Use frozen named Pydantic models and `Decimal` for every financial value.
- Persist exchange writes as durable Commands before dispatch. Unknown outcomes are never resent blindly.
- Do not add aliases, dual reads/writes, schema fallback, old Event readers, old-column compatibility, or DML-fabricated terminal state.
- The `0003` migration is forward-only and flat-only. There is no historical Ticket/Event translation.
- Reuse the existing Reconciliation worker, `get_next_reconciliation_work()`, due-at field, Incident/Monitor repositories, and closure-starvation priority. Do not add a worker, queue, timer, or selector.
- Preserve StrategyUniverse semantics: configuration order is eligibility only, target eight members, hard maximum ten, and final production members are not seeded until the Owner fixes the list.
- Existing STOP_MARKET Initial Stop/runner, LIMIT+GTX TP1, `actualOrderId -> trade.orderId`, BNB fee valuation, Settlement/Review, and closure-only handover behavior must remain green.

---

## Task 1: Build the Pure Cross-Margin Stop-Stress Domain

**Files:**

- Create: `src/trading_kernel/domain/cross_margin_stress.py`
- Create: `tests/trading_kernel/unit/test_cross_margin_stress.py`

- [ ] **Step 1: Write typed invariant tests**

Cover:

- canonical `AccountRiskPosition` and `AccountRiskSnapshot`;
- finite signed total margin balance and unrealized PnL;
- nonnegative maintenance margin;
- unique `instrument + position_side`;
- snapshot digest excludes raw venue liquidation observations;
- projected `StressPosition` uniqueness;
- Long/Short protective Stop direction;
- bracket uniqueness, ordering, contiguity, floor/cap validity;
- coefficient must be finite, positive, and explicitly certified.

- [ ] **Step 2: Run the new test module and preserve RED**

Run:

```bash
uv run pytest -q tests/trading_kernel/unit/test_cross_margin_stress.py
```

Expected: import/collection failure because the new Domain module and models do not exist.

- [ ] **Step 3: Implement the frozen Domain models**

Implement:

```python
AccountRiskPosition
AccountRiskSnapshot
StressPosition
CrossMarginStressRequest
CrossMarginStressPoint
CrossMarginStressProof
CrossMarginStressEvidence
CrossMarginStressStatus
evaluate_cross_margin_stress
```

Use `canonical_digest()` semantics compatible with existing Kernel SHA-256 identities, but keep the implementation local to the Domain module or move the existing generic canonical digest into one Domain utility only if both call sites can import it without a cycle.

- [ ] **Step 4: Write Long/Short pressure-boundary tests**

Parameterize:

- passed at every point;
- failed before Stop;
- failed only beyond Stop;
- zero surplus is failed;
- mark already beyond Stop is failed;
- Long stress clamps to zero;
- Short stress extends upward;
- same-instrument Long and Short remain separate;
- account totals subtract current exact-instrument UPNL/MM before projected evaluation.

- [ ] **Step 5: Write bracket-boundary tests**

Assert evaluation includes only:

- current mark;
- Initial Stop;
- final stress boundary;
- every floor/cap crossing inside the interval for each projected Side.

Assert deterministic deduplication, exact `Decimal` values, minimum surplus identity, and bounded point count.

- [ ] **Step 6: Implement the evaluator**

Use:

```text
base margin balance
  = total margin balance - exact-instrument current UPNL

base maintenance margin
  = total maintenance margin - exact-instrument current maintenance margin

projected UPNL
  = side-aware quantity * price movement

projected maintenance margin
  = notional * bracket rate - maintenance amount

surplus
  = projected account margin balance - projected account maintenance margin
```

Return `facts_contradictory` only for complete typed facts that contradict one another. External absence/timeouts do not enter the evaluator.

- [ ] **Step 7: Run Domain tests and targeted static checks**

Run:

```bash
uv run pytest -q tests/trading_kernel/unit/test_cross_margin_stress.py
uv run ruff check src/trading_kernel/domain/cross_margin_stress.py tests/trading_kernel/unit/test_cross_margin_stress.py
```

Expected: all new Domain tests pass with no lint errors.

- [ ] **Step 8: Commit the Domain slice**

```bash
git add src/trading_kernel/domain/cross_margin_stress.py tests/trading_kernel/unit/test_cross_margin_stress.py
git commit -m "feat(kernel): add cross-margin stop stress proof"
```

---

## Task 2: Establish One Canonical Account-Risk Fact Boundary

**Files:**

- Modify: `src/trading_kernel/domain/entry_admission_snapshot.py`
- Modify: `src/trading_kernel/domain/position.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify: `tests/trading_kernel/unit/test_entry_admission_snapshot.py`
- Modify: `tests/trading_kernel/unit/test_venue_adapter.py`
- Modify: `tests/trading_kernel/unit/test_instrument_certification.py`

- [ ] **Step 1: Add failing AccountRiskSnapshot port and composition tests**

Assert:

- `AccountRiskSnapshotRequest` has only venue/account/instrument/time identity;
- `AccountRiskSnapshotSource` returns the Domain snapshot;
- `EntryAdmissionSnapshot` composes `account_risk_snapshot + quote + open_orders`;
- admission no longer duplicates account balances, modes, mark, or positions;
- Kernel ownership remains separate PostgreSQL authority.

- [ ] **Step 2: Add failing Binance account parser tests**

Use sanitized payloads for:

- `/fapi/v2/account` with `multiAssetsMargin=false`;
- account totals and target Long/Short `unrealizedProfit`/`maintMargin`;
- exact symbol `positionRisk` identity, side, quantity, entry, mark, Cross, and fixed 5x;
- position-mode endpoint;
- cross-validation mismatch;
- missing account position values;
- one-way, isolated, leverage mismatch, multi-asset, and non-USDT rejection.

Run:

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_entry_admission_snapshot.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_instrument_certification.py
```

Expected: failures show the old duplicated snapshot and missing canonical parser.

- [ ] **Step 3: Implement the shared read port and single parser**

Implement exactly one infrastructure helper:

```python
_read_account_risk_snapshot(...)
```

Both `read_entry_admission_snapshot()` and `read_account_risk_snapshot()` call it. Do not create an Application copy adapter or a second account parser.

Use the existing action-time timeout boundary and keep every network call outside PostgreSQL transactions.

- [ ] **Step 4: Rename raw liquidation observation**

Replace:

```text
PositionSnapshot.liquidation_price
```

with:

```text
PositionSnapshot.venue_reported_liquidation_price
```

Preserve parseable `"0"` as `Decimal("0")`, preserve direction-inconsistent positive values, and distinguish missing from invalid through the existing Monitor boundary. The raw value must not enter `AccountRiskSnapshot` or its digest.

- [ ] **Step 5: Extend certified instrument rules**

Add `notional_coefficient` and coefficient certification state to:

- `InstrumentRulesFacts`;
- `CapacityInstrumentRules`;
- Binance leverage-bracket decoding;
- product/rules digest.

Use Binance `cum` as `maintenance_amount`. Reject gaps, overlaps, unsorted/duplicate brackets. Default coefficient `1` is accepted only when the payload explicitly represents the default schedule; non-default or semantically unverified coefficients produce `OWNER_ACTION_REQUIRED`, not an inferred transformation.

- [ ] **Step 6: Prove parser reuse and bounded calls**

Add spy/call assertions showing:

- Entry composite and post-fill narrow reads invoke the same parser;
- no new Multi-Assets endpoint call;
- exact-symbol reads are bounded;
- raw liquidation changes do not change account snapshot/rules digest.

- [ ] **Step 7: Run the focused fact-boundary suite**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_entry_admission_snapshot.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_instrument_certification.py \
  tests/trading_kernel/unit/test_production_runtime.py

uv run ruff check \
  src/trading_kernel/domain/entry_admission_snapshot.py \
  src/trading_kernel/domain/position.py \
  src/trading_kernel/application/runtime_facts.py \
  src/trading_kernel/infrastructure/venue_adapter.py \
  tests/trading_kernel/unit/test_entry_admission_snapshot.py \
  tests/trading_kernel/unit/test_venue_adapter.py
```

- [ ] **Step 8: Commit the canonical fact boundary**

```bash
git add \
  src/trading_kernel/domain/entry_admission_snapshot.py \
  src/trading_kernel/domain/position.py \
  src/trading_kernel/application/runtime_facts.py \
  src/trading_kernel/infrastructure/venue_adapter.py \
  tests/trading_kernel/unit/test_entry_admission_snapshot.py \
  tests/trading_kernel/unit/test_venue_adapter.py \
  tests/trading_kernel/unit/test_instrument_certification.py \
  tests/trading_kernel/unit/test_production_runtime.py
git commit -m "refactor(kernel): unify account risk facts"
```

---

## Task 3: Replace Claim and Dispatch Liquidation Formulas

**Files:**

- Modify: `src/trading_kernel/domain/capacity_sizing.py`
- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/domain/ticket.py`
- Modify: `src/trading_kernel/application/build_capacity_claim.py`
- Modify: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `tests/trading_kernel/unit/test_capacity_sizing.py`
- Modify: `tests/trading_kernel/unit/test_capacity.py`
- Modify: `tests/trading_kernel/unit/test_ticket.py`
- Modify: `tests/trading_kernel/unit/test_entry_dispatch_preflight.py`
- Modify: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- Modify: `tests/trading_kernel/integration/test_command_dispatch.py`

- [ ] **Step 1: Write RED tests for retirement and one evaluator**

Assert:

- `CapacitySizingRequest/Selection` contain sizing facts only;
- no projected liquidation root/distance/ratio fields or helper;
- Claim evaluates stress after selecting quantity;
- dispatch re-evaluates from fresh action-time account/rules facts;
- identical inputs yield identical evidence/proof digest;
- changed balance, position, mode, bracket, coefficient, or mark re-evaluates and fails closed;
- strategy and Universe identity cannot override a failed risk proof.

- [ ] **Step 2: Run the focused Claim/dispatch suite**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/unit/test_capacity.py \
  tests/trading_kernel/unit/test_ticket.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/integration/test_command_dispatch.py
```

Expected: old liquidation fields/formulas violate new assertions.

- [ ] **Step 3: Separate sizing from stress authority**

Retain slot, stop-risk, margin-utilization, leverage, exchange-minimum, TP1, and runner sizing in `select_capacity_candidate()`.

Remove:

- `_project_cross_margin_liquidation_price`;
- root/minimum-price constants;
- liquidation proof status/fields;
- maintenance-bracket calculations that exist only for the retired root.

Application builds the projected Side positions and calls `evaluate_cross_margin_stress()` once the candidate quantity is known.

- [ ] **Step 4: Replace policy and immutable identities**

Replace:

```text
min_liquidation_distance_to_stop_distance_ratio
```

with:

```text
post_stop_stress_multiple
```

`CapacityClaim` stores complete typed pre-entry `CrossMarginStressEvidence`.

`TradeTicket` stores only:

- model id;
- stress multiple;
- Claim proof digest.

Do not duplicate the full proof in the Ticket.

- [ ] **Step 5: Reuse the evaluator at dispatch**

Build action-time projected positions from:

- exact current opposite Side, if any;
- Ticket target Side quantity;
- fresh action-time entry reference.

Reject ENTRY terminally when action facts are stale, unavailable, contradictory, or proof status is not `passed`. Persist no ENTRY Command for a rejected proof.

- [ ] **Step 6: Verify claim-to-ticket round-trip**

Assert exact evidence serialization, proof digest identity, model id, Policy identity, Universe identity, and risk reservation remain frozen.

- [ ] **Step 7: Run tests and static checks**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/unit/test_capacity.py \
  tests/trading_kernel/unit/test_ticket.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/integration/test_command_dispatch.py

uv run ruff check \
  src/trading_kernel/domain/capacity_sizing.py \
  src/trading_kernel/domain/capacity.py \
  src/trading_kernel/domain/ticket.py \
  src/trading_kernel/application/build_capacity_claim.py \
  src/trading_kernel/application/revalidate_entry_dispatch.py
```

- [ ] **Step 8: Commit Claim and dispatch authority**

```bash
git add \
  src/trading_kernel/domain/capacity_sizing.py \
  src/trading_kernel/domain/capacity.py \
  src/trading_kernel/domain/ticket.py \
  src/trading_kernel/application/build_capacity_claim.py \
  src/trading_kernel/application/revalidate_entry_dispatch.py \
  src/trading_kernel/application/ports.py \
  tests/trading_kernel/unit/test_capacity_sizing.py \
  tests/trading_kernel/unit/test_capacity.py \
  tests/trading_kernel/unit/test_ticket.py \
  tests/trading_kernel/unit/test_entry_dispatch_preflight.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/integration/test_command_dispatch.py
git commit -m "refactor(kernel): use stop stress for entry authority"
```

---

## Task 4: Split Actual Stop Risk from Post-Fill Account Stress

**Files:**

- Modify: `src/trading_kernel/domain/post_fill_risk.py`
- Modify: `src/trading_kernel/domain/events.py`
- Modify: `src/trading_kernel/domain/aggregate.py`
- Modify: `src/trading_kernel/domain/reducer.py`
- Modify: `src/trading_kernel/domain/effects.py`
- Modify: `tests/trading_kernel/unit/test_post_fill_risk.py`
- Modify: `tests/trading_kernel/unit/test_reducer.py`
- Modify: `tests/trading_kernel/architecture/test_event_registry_parity.py`

- [ ] **Step 1: Add RED tests for Stop-first lifecycle**

Assert:

- `EntryFilled` contains fill quantity, average fill, actual Stop risk, raw venue liquidation observation, and observation time;
- `EntryFilled` contains no Cross Margin stress proof;
- wrong Stop direction flattens immediately without installing an invalid Stop;
- actual Stop risk over hard limit installs Initial Stop then flattens;
- acceptable Stop risk installs Initial Stop first;
- `InitialStopConfirmed` transitions to `post_fill_risk_pending`;
- Entry lane remains held and TP1 is absent while pending.

- [ ] **Step 2: Add RED tests for one result Event**

Add:

```python
PostFillStressAssessed(
    status="passed" | "failed",
    evidence=CrossMarginStressEvidence(...),
    policy_identity=...,
    fill_identity=...,
    stop_identity=...,
)
```

Assert:

- passed resolves retry Incident, releases Entry lane, and prepares one TP1;
- failed opens `post_fill_stress_failed`, keeps account/lane blocked, and prepares one durable Controlled Flatten;
- facts unavailable/contradictory are not Trade Events;
- repeated result application is rejected by expected version/sequence.

- [ ] **Step 3: Run RED tests**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_post_fill_risk.py \
  tests/trading_kernel/unit/test_reducer.py \
  tests/trading_kernel/architecture/test_event_registry_parity.py
```

- [ ] **Step 4: Simplify actual Stop-risk assessment**

Retain only:

- protective Stop direction;
- exact fill quantity and average price;
- actual risk at Stop;
- planned risk and post-fill hard limit;
- `protect_then_continue`, `protect_then_flatten`, or `flatten_immediately`.

Remove liquidation-price decision inputs and all `actual_liquidation_*` outputs.

- [ ] **Step 5: Add Aggregate state and one Event**

Add:

```text
AggregateStatus.POST_FILL_RISK_PENDING
PostFillStressAssessed
post_fill_stress_status
post_fill_stress_proof_digest
```

Do not add a separate Event for unavailable/contradictory reads.

- [ ] **Step 6: Refactor reducer effects**

Enforce:

```text
EntryFilled
-> Initial Stop request
-> InitialStopConfirmed
-> post_fill_risk_pending
-> assessed passed: TP1
-> assessed failed: Controlled Flatten
```

Lane/account block release occurs only at the specified safe boundary.

- [ ] **Step 7: Run focused tests and lint**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_post_fill_risk.py \
  tests/trading_kernel/unit/test_reducer.py \
  tests/trading_kernel/architecture/test_event_registry_parity.py

uv run ruff check \
  src/trading_kernel/domain/post_fill_risk.py \
  src/trading_kernel/domain/events.py \
  src/trading_kernel/domain/aggregate.py \
  src/trading_kernel/domain/reducer.py \
  src/trading_kernel/domain/effects.py
```

- [ ] **Step 8: Commit the lifecycle state machine**

```bash
git add \
  src/trading_kernel/domain/post_fill_risk.py \
  src/trading_kernel/domain/events.py \
  src/trading_kernel/domain/aggregate.py \
  src/trading_kernel/domain/reducer.py \
  src/trading_kernel/domain/effects.py \
  tests/trading_kernel/unit/test_post_fill_risk.py \
  tests/trading_kernel/unit/test_reducer.py \
  tests/trading_kernel/architecture/test_event_registry_parity.py
git commit -m "refactor(kernel): separate post-fill stress lifecycle"
```

---

## Task 5: Orchestrate Post-Fill Stress Through Existing Reconciliation

**Files:**

- Modify: `src/trading_kernel/application/reconcile_ticket.py`
- Modify: `src/trading_kernel/interfaces/reconciliation_worker.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `tests/trading_kernel/unit/test_reconciliation_worker_fairness.py`
- Modify: `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`
- Modify: `tests/trading_kernel/integration/test_pg_unit_of_work.py`

- [ ] **Step 1: Add RED orchestration tests**

Cover:

- pending Ticket reads account snapshot and instrument rules outside the transaction;
- exact Ticket is then locked and expected status/version is rechecked;
- unavailable read upserts one idempotent Incident, one Monitor state, and due-at without Event/Command/version movement;
- contradictory proof does the same with Owner-action semantics;
- recovery to passed atomically appends result Event, updates Aggregate, resolves retry Incident, and materializes TP1 Command;
- recovery to failed atomically appends result Event, opens failed Incident, and materializes Flatten Command;
- commit fault rolls everything back;
- command dispatch occurs only after commit.

- [ ] **Step 2: Add scheduler fairness RED tests**

Assert:

- `post_fill_risk_pending` belongs to existing `RECONCILIATION_POSITION_STATUSES`;
- multiple pending/protected Tickets are selected by existing due-at logic;
- overdue Settlement/Review retains closure-starvation priority;
- no early return prevents closure work;
- retry interval is not shorter than worker poll interval.

- [ ] **Step 3: Run RED suites**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_reconciliation_worker_fairness.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/integration/test_pg_unit_of_work.py
```

- [ ] **Step 4: Add the pending reconciliation branch**

Use existing worker and selector only. The branch:

1. reads canonical account risk facts and certified rules;
2. builds projected actual Long/Short positions;
3. calls `evaluate_cross_margin_stress()`;
4. commits either one assessed Event or one retry state;
5. dispatches a materialized Command after commit.

- [ ] **Step 5: Add idempotent Incident/Monitor retry persistence**

Use exact kinds:

```text
post_fill_risk_facts_unavailable
post_fill_risk_facts_contradictory
post_fill_stress_failed
```

Account-capacity incidents use the canonical account block key. Do not resolve `post_fill_stress_failed` when creating or accepting Flatten; resolve it only after external flat, no residual orders, and `ReconciliationMatched`.

- [ ] **Step 6: Preserve existing closure work**

Keep Settlement and Review work in `get_next_reconciliation_work()`. Extend the current selector status set and ordering instead of adding a post-fill-specific queue.

- [ ] **Step 7: Run integration and fairness tests**

```bash
uv run pytest -q \
  tests/trading_kernel/unit/test_reconciliation_worker_fairness.py \
  tests/trading_kernel/unit/test_reconciliation_worker_review.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/integration/test_pg_unit_of_work.py \
  tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py
```

- [ ] **Step 8: Commit the existing-worker orchestration**

```bash
git add \
  src/trading_kernel/application/reconcile_ticket.py \
  src/trading_kernel/interfaces/reconciliation_worker.py \
  src/trading_kernel/application/runtime_facts.py \
  src/trading_kernel/application/ports.py \
  src/trading_kernel/infrastructure/pg_unit_of_work.py \
  src/trading_kernel/infrastructure/pg_repositories.py \
  tests/trading_kernel/unit/test_reconciliation_worker_fairness.py \
  tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py \
  tests/trading_kernel/integration/test_pg_unit_of_work.py
git commit -m "feat(kernel): reconcile post-fill stop stress"
```

---

## Task 6: Replace the PostgreSQL Authority with Flat-Only Schema `0003`

**Files:**

- Create: `migrations/trading_kernel/versions/0003_cross_margin_stop_stress.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`
- Modify: `tests/trading_kernel/integration/test_schema_migration_postgres.py`
- Modify: `tests/trading_kernel/integration/test_runtime_authority_seed.py`
- Modify: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- Modify: `tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py`

- [ ] **Step 1: Write schema RED assertions**

Require:

- Alembic head `0003_cross_margin_stop_stress`;
- old liquidation root/ratio columns absent;
- Owner Policy has `post_stop_stress_multiple`;
- Instrument Rules has coefficient authority;
- CapacityClaim has complete typed stress evidence JSONB;
- Ticket has model id, multiple, and proof digest only;
- Aggregate has post-fill stress status/digest only;
- raw venue liquidation observation is audit-only;
- Event payload round-trips `PostFillStressAssessed`.

- [ ] **Step 2: Write flat-only migration refusal tests**

Parameterize every relevant runtime/trade table:

```text
Ticket, Aggregate, Event, Command, Position, Incident,
Budget, Exposure, Settlement/Review, Monitor, runtime authority
```

For each populated table, assert migration rejects before DDL and the transaction leaves the schema unchanged.

- [ ] **Step 3: Run schema RED tests against disposable PostgreSQL**

Start and health-check repository Docker PostgreSQL if needed, then run:

```bash
uv run pytest -q \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_runtime_authority_seed.py
```

- [ ] **Step 4: Implement forward-only migration**

The migration must:

1. lock all tables used in the flat preflight;
2. reject any nonempty runtime/trade authority;
3. drop old constraints and columns;
4. add the new columns/constraints;
5. declare no downgrade path.

No backfill and no historical Event decoder are allowed.

- [ ] **Step 5: Align SQLAlchemy metadata and repositories**

Use exact Pydantic `model_dump(mode="json")` and `model_validate()` for stress evidence. Do not persist untyped arbitrary dictionaries as authority.

- [ ] **Step 6: Seed only approved policy semantics**

Seed `post_stop_stress_multiple=Decimal("2.0")`. Do not seed a final production Universe member list. Keep target eight/hard maximum ten enforcement in existing Universe authority.

- [ ] **Step 7: Verify fresh schema, refusal, and round trips**

```bash
uv run pytest -q \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_runtime_authority_seed.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/integration/test_pg_unit_of_work.py \
  tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py
```

- [ ] **Step 8: Commit schema authority**

```bash
git add \
  migrations/trading_kernel/versions/0003_cross_margin_stop_stress.py \
  src/trading_kernel/infrastructure/pg_models.py \
  src/trading_kernel/infrastructure/pg_repositories.py \
  src/trading_kernel/infrastructure/pg_unit_of_work.py \
  src/trading_kernel/infrastructure/runtime_authority_seed.py \
  tests/trading_kernel/integration/test_schema_baseline.py \
  tests/trading_kernel/integration/test_schema_migration_postgres.py \
  tests/trading_kernel/integration/test_runtime_authority_seed.py \
  tests/trading_kernel/integration/test_capacity_claim_to_ticket.py \
  tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py
git commit -m "feat(kernel): migrate stop stress authority"
```

---

## Task 7: Close P0, Multi-Position, Lifecycle, and Universe Full Chains

**Files:**

- Create: `tests/trading_kernel/full_chain/test_cross_margin_post_fill_stress.py`
- Modify: `tests/trading_kernel/full_chain/lifecycle_support.py`
- Modify: `tests/trading_kernel/full_chain/test_multi_position_certification.py`
- Modify: `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`
- Modify: `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Modify: `tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py`
- Modify: `tests/trading_kernel/full_chain/test_binance_actual_order_review.py`
- Modify: `tests/trading_kernel/full_chain/test_crypto_universe_replacement.py`
- Modify: `tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py`

- [ ] **Step 1: Add ETH/AVAX accident RED fixtures**

Parameterize:

- ETH Long raw venue liquidation `0`;
- AVAX Long entry `6.60`, Stop `6.383`, raw venue liquidation `14.076`;
- identical canonical account/rules facts with only raw observation changed.

Assert raw observation never changes proof, Event, TP1, or Flatten decision.

- [ ] **Step 2: Add complete post-fill recovery paths**

Cover:

- unavailable then passed;
- unavailable then failed;
- repeated unavailable across worker restart;
- actual Stop-risk hard-limit branch;
- failed stress with exactly one durable Flatten;
- external flat/no residual orders before Incident/lane/budget/domain release.

- [ ] **Step 3: Add multi-position and dual-Side paths**

Cover:

- same symbol Long and Short;
- three different Netting Domains;
- one risk-pending Ticket while another protected/runner Ticket progresses;
- new Entry global serialization;
- no cross-Ticket Stop/TP1/Command identities.

- [ ] **Step 4: Preserve complete economic closure**

Every successful chain must continue through:

```text
Signal -> Claim -> Ticket -> ENTRY -> Fill -> Initial Stop
-> post-fill stress -> TP1 -> runner -> flat
-> Reconciliation -> Settlement -> Review
```

Assert:

- TP1 is LIMIT+GTX;
- Initial Stop and runner remain STOP_MARKET;
- conditional order `actualOrderId -> trade.orderId` attribution;
- BNB fee asset converts to USDT Review economics;
- closure work is not starved by protected/pending Tickets.

- [ ] **Step 5: Preserve StrategyUniverse switching**

Run a full switch with an eight-member independent strategy pool and assert:

- configuration order does not create trade priority;
- hard maximum ten remains enforced;
- certification, warm-up, and activation are atomic;
- active Universe controls new Signals only;
- no detector or order-chain code change is needed per symbol;
- no final production symbol list is introduced.

- [ ] **Step 6: Run full-chain RED/GREEN loop**

```bash
uv run pytest -q \
  tests/trading_kernel/full_chain/test_cross_margin_post_fill_stress.py \
  tests/trading_kernel/full_chain/test_multi_position_certification.py \
  tests/trading_kernel/full_chain/test_ticket_lifecycle.py \
  tests/trading_kernel/full_chain/test_fault_matrix.py \
  tests/trading_kernel/full_chain/test_multi_ticket_closure_fairness.py \
  tests/trading_kernel/full_chain/test_binance_actual_order_review.py \
  tests/trading_kernel/full_chain/test_crypto_universe_replacement.py \
  tests/trading_kernel/full_chain/test_crypto_universe_failure_recovery.py
```

- [ ] **Step 7: Commit full-chain coverage**

```bash
git add tests/trading_kernel/full_chain
git commit -m "test(kernel): certify stop stress full chain"
```

---

## Task 8: Enforce Architecture and Remove Retired Authority

**Files:**

- Create: `tests/trading_kernel/architecture/test_cross_margin_risk_authority.py`
- Modify: `tests/trading_kernel/architecture/test_no_retired_execution.py`
- Modify: `tests/trading_kernel/architecture/test_runtime_file_io_audit.py`
- Modify: affected unit/integration/full-chain fixtures that still construct retired fields
- Delete: tests/helpers that encode liquidation-price command authority

- [ ] **Step 1: Add architecture RED scans**

Assert:

- only `cross_margin_stress.py` contains the stress financial formula;
- no root solver, binary search, projected liquidation field, old ratio, safe-liquidation helper, or liquidation-based reducer branch remains;
- Domain does not import Application/infrastructure or forbidden libraries;
- one `AccountRiskSnapshot` type and one infrastructure parser exist;
- no new worker, timer, queue, selector, runtime file output, compatibility adapter, alias, or dual read/write exists.

- [ ] **Step 2: Remove retired tests and fixtures**

Delete tests that require old liquidation authority. Rewrite fixtures to provide canonical account/rules facts and stress evidence. Do not keep old names as aliases.

- [ ] **Step 3: Run architecture and source scans**

```bash
uv run pytest -q tests/trading_kernel/architecture

rg -n \
  'projected_liquidation|actual_liquidation|min_liquidation_distance|safe_liquidation|_project_cross_margin_liquidation' \
  src/trading_kernel tests/trading_kernel migrations/trading_kernel scripts/trading_kernel
```

Expected: `rg` returns no production/test/schema matches except explicit forbidden-token assertions inside the architecture test.

- [ ] **Step 4: Run performance-bound tests**

Assert:

- account/position/rules calls stay within the designed bounded count;
- stress point count is bounded by bracket schedule size and projected Side count;
- repository queries use exact Ticket/current-state indexes;
- retries update due-at and cannot busy-loop;
- production no-signal cadence writes zero files.

- [ ] **Step 5: Commit architecture enforcement**

```bash
git add \
  tests/trading_kernel/architecture/test_cross_margin_risk_authority.py \
  tests/trading_kernel/architecture/test_no_retired_execution.py \
  tests/trading_kernel/architecture/test_runtime_file_io_audit.py \
  src/trading_kernel tests/trading_kernel migrations/trading_kernel scripts/trading_kernel
git commit -m "test(kernel): enforce single stress authority"
```

---

## Task 9: Run Local Certification and Stop at the Deployment Gate

**Files:**

- Modify only if evidence requires: implementation/test files from Tasks 1-8
- Do not update volatile Tokyo facts in `docs/current/MAIN_CONTROL_ROADMAP.md` without a fresh readonly production refresh

- [ ] **Step 1: Ensure disposable PostgreSQL is healthy**

Use the repository test dependency only. Never substitute Tokyo.

- [ ] **Step 2: Run the complete test matrix**

```bash
uv run pytest -q \
  tests/trading_kernel/unit \
  tests/trading_kernel/integration \
  tests/trading_kernel/full_chain \
  tests/trading_kernel/architecture
```

- [ ] **Step 3: Run static and runtime-file gates**

```bash
uv run ruff check \
  src/trading_kernel \
  tests/trading_kernel \
  scripts/trading_kernel

uv run --with mypy mypy \
  --config-file mypy.ini \
  src/trading_kernel \
  scripts/trading_kernel

uv run python scripts/audit_production_runtime_file_io.py
git diff --check
```

- [ ] **Step 4: Review the final diff**

Verify:

- no unrelated user changes;
- no credentials or runtime output;
- no compatibility glue;
- no duplicated financial formulas;
- no hidden exchange-write path;
- no weakening of Entry fences, Unknown-outcome handling, STOP_MARKET protection, GTX TP1, order attribution, fee valuation, Settlement/Review fairness, or Universe activation.

- [ ] **Step 5: Record final local evidence**

Capture:

- commit SHA and clean/intentional worktree status;
- exact test totals;
- PostgreSQL migration head;
- Ruff/Mypy/file-I/O results;
- explicit statement that Tokyo Entry and deployment were untouched.

- [ ] **Step 6: Commit any evidence-driven final cleanup**

If verification required no edits, do not create an empty commit. If it required
edits, inspect `git diff --name-only`, stage only the exact implementation or
test files changed by the verified cleanup, and commit:

```bash
git commit -m "chore(kernel): complete local stop stress certification"
```

- [ ] **Step 7: Stop before deployment**

Do not:

- run `deploy_tokyo_release.py`;
- run remote migrations/reset;
- change Tokyo systemd;
- enable Entry;
- submit exchange mode/leverage/order commands.

The next state is:

```text
LOCAL_IMPLEMENTATION_CERTIFIED
-> WAITING_FOR_OWNER_DEPLOYMENT_CONFIRMATION
```
