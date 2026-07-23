# Multi-Position Dynamic Budget And Leverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-USDT, fixed-leverage admission envelope with one PostgreSQL-authoritative, balance-relative model that supports at most three concurrent capital-owning Tickets, chooses the lowest safe slot-fitting leverage up to 10x, and preserves one readable end-to-end Trading Kernel chain.

**Architecture:** One fresh `EntryAdmissionSnapshot` supplies the account and instrument truth for a pure slot-aware capacity decision. The resulting immutable `CapacityClaim` and `TradeTicket` freeze budget, leverage, liquidation, and protection evidence; optional leverage mutation and ENTRY submission use separate durable commands. Existing Lifecycle and Reconciliation workers remain the only recovery path, and `ReconciliationMatched` atomically releases budget, account capacity, and Netting Domain before Settlement and Review finish.

**Tech Stack:** Python 3.11+, Pydantic v2 frozen models, `decimal.Decimal`, SQLAlchemy 2, PostgreSQL 16/Alembic, pytest, Ruff, Mypy, CCXT-compatible Binance USD-M adapter, persistent systemd workers.

## Execution Status At Plan Publication

| Work | Status | Evidence / next boundary |
| --- | --- | --- |
| Tasks 1-5 | Complete and committed | `edad2c70`, `89c4e64a`, `6a6c14b6`, `7b2cb127`; dynamic policy, one admission snapshot, slot-aware sizing, frozen Claim/Ticket/reservation evidence, and scoped admission ownership exist |
| Task 6 | Next implementation boundary | Add the separate durable `SET_LEVERAGE` command and prohibit same-transaction leverage mutation plus ENTRY creation |
| Tasks 7-14 | Pending | Must follow the ordered mutation, safety, release, production-contract, certification, and retirement gates below |
| Task 15 | Separately gated | No Tokyo rebuild or exchange write occurs until Tasks 1-14 have direct local certification |

The checklists below are the original test-first task recipes. This status table,
not an unchecked historical RED/GREEN sub-step, is the current execution
position.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-07-23-multi-position-dynamic-budget-and-leverage-design.md`, revision 4.
- Production execution remains exclusively under `src/trading_kernel/**`; the only schema baseline remains `migrations/trading_kernel/versions/0001_initial.py`.
- Owner Policy values are exactly: `max_concurrent_tickets=3`, `planned_stop_risk_fraction=0.03`, `max_initial_margin_utilization=0.90`, `max_leverage=10`, `supported_margin_mode=cross`, `min_liquidation_distance_to_stop_distance_ratio=2.0`, and `max_post_fill_stop_risk_overrun_fraction=0.10`.
- `new_entry_submit_enabled` controls only new ENTRY authority; it never suppresses Initial Stop, protection repair, exit, cancellation, controlled flatten, reconciliation, Settlement, or Review for existing exposure.
- One Exposure Episode owns exactly one immutable Ticket; adding to an existing position is forbidden.
- New ENTRY admission is globally serialized; existing protected Ticket lifecycle work is concurrent.
- One active Ticket is allowed per `venue_id + account_id + exchange_instrument_id + position_side` Netting Domain.
- Long and short may coexist only when the account exposes independent sides and the shared exact-instrument leverage remains valid.
- Account capacity keys use `venue_id + account_id`; instrument rules and leverage keys use `venue_id + account_id + exchange_instrument_id`.
- Every exchange mutation has one durable Exchange Command. `SET_LEVERAGE` generation 1 must resolve before `ENTRY` generation 1 is created.
- An authoritative ENTRY or SET_LEVERAGE rejection is terminal; unknown outcomes are reconciled and never blindly resent.
- Financial arithmetic uses `Decimal`; leverage and counts use validated integers; booleans and fractional leverage are rejected.
- Domain modules remain pure: no SQLAlchemy, venue client, filesystem, subprocess, web framework, clock, or logging dependency.
- Network I/O occurs outside PostgreSQL transactions and is timeout-bounded.
- The implementation modifies the clean `0001_initial` baseline directly; no compatibility migration, old-column reader, dual write, or fallback path is permitted.
- The business-table count remains exactly 33; this program adds columns, constraints, command kinds, and typed payloads, not a new business table.
- Tokyo exchange writes remain disabled throughout local implementation and certification.
- The unrelated untracked reset artifacts `scripts/trading_kernel/reset_flat_runtime.sql` and `tests/trading_kernel/architecture/test_flat_runtime_reset_sql.py` are outside this plan and must not be staged by any task.

## File Structure

| File | Responsibility |
| --- | --- |
| `src/trading_kernel/domain/entry_admission_snapshot.py` | One immutable account observation cycle and canonical digest |
| `src/trading_kernel/domain/account_entry_health.py` | Pure account-wide Cross-margin ownership classification |
| `src/trading_kernel/domain/instrument_entry_health.py` | Pure exact-instrument ownership, direction, and leverage classification |
| `src/trading_kernel/domain/incident_blocking.py` | Typed Incident blocking scope and canonical key |
| `src/trading_kernel/domain/capacity.py` | Policy, immutable Claim, statuses, and frozen decision identity |
| `src/trading_kernel/domain/capacity_sizing.py` | Pure slot allocation, candidate leverage evaluation, and deterministic selection |
| `src/trading_kernel/domain/post_fill_risk.py` | Pure actual fill-risk and liquidation disposition |
| `src/trading_kernel/domain/commands.py` | Separate SET_LEVERAGE and order command payloads/results |
| `src/trading_kernel/application/build_capacity_claim.py` | Compose typed inputs and invoke pure admission sizing |
| `src/trading_kernel/application/revalidate_entry_dispatch.py` | Fresh pre-mutation policy, ownership, margin, quote, and leverage checks |
| `src/trading_kernel/application/reconcile_leverage_command.py` | Resolve unknown leverage mutation by exact read-back |
| `src/trading_kernel/application/issue_ticket.py` | Atomic Ticket, reservation, count, domain, event, and initial command issue |
| `src/trading_kernel/application/reconcile_ticket.py` | Exact external truth and ReconciliationMatched release trigger |
| `src/trading_kernel/infrastructure/venue_adapter.py` | One admission snapshot, leverage set/read-back, and order mutations |
| `src/trading_kernel/infrastructure/pg_models.py` | SQLAlchemy declaration of the revised single baseline |
| `src/trading_kernel/infrastructure/pg_repositories.py` | Exact typed persistence and bounded selectors |
| `src/trading_kernel/infrastructure/runtime_authority_seed.py` | Deterministic versioned dynamic budget policy seed |

---

### Task 1: Replace the fixed policy envelope in the clean schema and runtime seed

**Files:**
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `scripts/trading_kernel/seed_runtime_authority.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`
- Modify: `tests/trading_kernel/integration/test_schema_migration_postgres.py`
- Modify: `tests/trading_kernel/integration/test_runtime_authority_seed.py`

**Interfaces:**
- Replaces: `real_submit_enabled`, `max_gross_notional`, `max_gross_risk_at_stop`, `max_ticket_risk_at_stop`, and `target_leverage` as admission authority.
- Produces: `OwnerPolicySnapshot(new_entry_submit_enabled: bool, max_concurrent_tickets: int, planned_stop_risk_fraction: Decimal, max_initial_margin_utilization: Decimal, max_leverage: int, supported_margin_mode: Literal["cross"], min_liquidation_distance_to_stop_distance_ratio: Decimal, max_post_fill_stop_risk_overrun_fraction: Decimal)`.
- Produces: `AccountExposureSnapshot(venue_id: str, account_id: str, active_ticket_count: int, gross_notional: Decimal, gross_risk_at_stop: Decimal, projection_version: int, updated_at_ms: int)`.

- [ ] **Step 1: Write failing schema and seed assertions**

```python
def test_owner_policy_uses_only_dynamic_budget_columns(metadata) -> None:
    columns = set(metadata.tables["brc_owner_policy_current"].columns.keys())
    assert {
        "new_entry_submit_enabled",
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "max_leverage",
        "supported_margin_mode",
        "min_liquidation_distance_to_stop_distance_ratio",
        "max_post_fill_stop_risk_overrun_fraction",
    } <= columns
    assert {
        "real_submit_enabled",
        "max_gross_notional",
        "max_gross_risk_at_stop",
        "max_ticket_risk_at_stop",
        "target_leverage",
    }.isdisjoint(columns)


async def test_seed_installs_owner_approved_dynamic_policy(pg_uow) -> None:
    result = await seed_runtime_authority(pg_uow, seed_request())
    assert result.new_entry_submit_enabled is False
    assert result.max_concurrent_tickets == 3
    assert result.planned_stop_risk_fraction == Decimal("0.03")
    assert result.max_initial_margin_utilization == Decimal("0.90")
    assert result.max_leverage == 10
    assert result.supported_margin_mode == "cross"
    assert result.min_liquidation_distance_to_stop_distance_ratio == Decimal("2.0")
    assert result.max_post_fill_stop_risk_overrun_fraction == Decimal("0.10")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_schema_baseline.py tests/trading_kernel/integration/test_runtime_authority_seed.py`

Expected: FAIL because the current baseline and seed still expose fixed Envelope columns and 1/2 Ticket policy transitions.

- [ ] **Step 3: Implement the revised baseline and deterministic policy state**

```python
class OwnerPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    owner_policy_id: str
    policy_version: int
    enabled: bool
    new_entry_submit_enabled: bool
    priority_rank: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    max_leverage: int
    supported_margin_mode: Literal["cross"]
    min_liquidation_distance_to_stop_distance_ratio: Decimal
    max_post_fill_stop_risk_overrun_fraction: Decimal
```

Use SQL constraints `0 < planned_stop_risk_fraction AND planned_stop_risk_fraction < 1`, `0 < max_initial_margin_utilization AND max_initial_margin_utilization <= 1`, `max_leverage BETWEEN 1 AND 10`, positive liquidation ratio, and `0 <= max_post_fill_stop_risk_overrun_fraction < 1`. Make `venue_id + account_id` the account-exposure primary key. Replace acceptance/full envelopes with one three-Ticket policy whose seed and arm transitions change only `new_entry_submit_enabled`; preserve monotonic policy versions and exact semantic hashes.

- [ ] **Step 4: Run focused schema and seed tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_schema_baseline.py tests/trading_kernel/integration/test_schema_migration_postgres.py tests/trading_kernel/integration/test_runtime_authority_seed.py`

Expected: PASS; the empty database still creates exactly 33 business tables and contains no retired fixed-policy columns.

- [ ] **Step 5: Commit**

```bash
git add migrations/trading_kernel/versions/0001_initial.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/runtime_authority_seed.py scripts/trading_kernel/seed_runtime_authority.py tests/trading_kernel/integration/test_schema_baseline.py tests/trading_kernel/integration/test_schema_migration_postgres.py tests/trading_kernel/integration/test_runtime_authority_seed.py
git commit -m "refactor(kernel): replace fixed capacity policy baseline"
```

---

### Task 2: Introduce one immutable EntryAdmissionSnapshot and typed health decisions

**Files:**
- Create: `src/trading_kernel/domain/entry_admission_snapshot.py`
- Create: `src/trading_kernel/domain/account_entry_health.py`
- Create: `src/trading_kernel/domain/instrument_entry_health.py`
- Create: `src/trading_kernel/domain/incident_blocking.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Create: `tests/trading_kernel/unit/test_entry_admission_snapshot.py`
- Create: `tests/trading_kernel/unit/test_entry_health.py`
- Modify: `tests/trading_kernel/unit/test_venue_adapter.py`

**Interfaces:**
- Produces: `EntryAdmissionSnapshot.digest() -> str`.
- Produces: `classify_account_entry_health(snapshot: EntryAdmissionSnapshot, ownership: AdmissionOwnership) -> AccountEntryHealth`.
- Produces: `classify_instrument_entry_health(snapshot: EntryAdmissionSnapshot, ownership: AdmissionOwnership, exchange_instrument_id: str) -> InstrumentEntryHealth`.
- Replaces: separately timed `read_action_time_facts` and raw exact-domain open-count authority for new admission.

- [ ] **Step 1: Write failing snapshot and classification tests**

```python
def test_account_and_instrument_health_share_one_parent_digest() -> None:
    snapshot = admission_snapshot()
    account = classify_account_entry_health(snapshot, owned_rows())
    instrument = classify_instrument_entry_health(snapshot, owned_rows(), "SOLUSDT")
    assert account.entry_admission_snapshot_digest == snapshot.digest()
    assert instrument.entry_admission_snapshot_digest == snapshot.digest()


def test_unowned_order_anywhere_blocks_cross_account() -> None:
    snapshot = admission_snapshot(open_orders=(unowned_order("BTCUSDT"),))
    health = classify_account_entry_health(snapshot, owned_rows())
    assert health.status is AccountEntryHealthStatus.UNOWNED_ORDER
    assert health.entry_block_scope is EntryBlockScope.ACCOUNT_CAPACITY
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_entry_admission_snapshot.py tests/trading_kernel/unit/test_entry_health.py`

Expected: FAIL because the snapshot and classifier modules do not exist.

- [ ] **Step 3: Implement frozen snapshot, canonical digest, and pure classifiers**

```python
class AdmissionPosition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    quantity: Decimal
    average_entry_price: Decimal | None


class AdmissionOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_order_id: str
    venue_client_order_id: str | None
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    reduce_only: bool


class EntryAdmissionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_mode: Literal["independent_sides", "one_way"]
    margin_mode: Literal["cross", "isolated"]
    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    total_maintenance_margin: Decimal
    available_margin: Decimal
    best_bid_price: Decimal
    best_ask_price: Decimal
    mark_price: Decimal
    configured_leverage: int
    positions: tuple[AdmissionPosition, ...]
    open_orders: tuple[AdmissionOrder, ...]
    observed_at_ms: int
    valid_until_ms: int

    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="python"))
```

`canonical_digest` uses the existing sorted JSON/Decimal canonicalization pattern from `domain/capacity.py`. `AdmissionOwnership` contains exact BRC Ticket, command, and expected-order identities loaded before classification. `EntryBlockScope` is a `StrEnum` with `RUNTIME`, `ACCOUNT_CAPACITY`, `LEVERAGE_DOMAIN`, and `NONE`; `canonical_entry_block_key(scope, *, venue_id, account_id, exchange_instrument_id)` returns `global`, `venue_id:account_id`, `venue_id:account_id:exchange_instrument_id`, or `None`. Reject mismatched venue/account identity, stale windows, duplicate rows, non-finite values, negative account facts, fractional leverage, and any classifier result whose parent digest differs.

- [ ] **Step 4: Replace the venue read with one bounded observation cycle**

```python
class EntryAdmissionSnapshotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    observed_at_ms: int
    valid_for_ms: int


class EntryAdmissionFactsSource(Protocol):
    async def read_entry_admission_snapshot(
        self,
        request: EntryAdmissionSnapshotRequest,
    ) -> EntryAdmissionSnapshot:
        raise NotImplementedError
```

`CcxtVenueAdapter.read_entry_admission_snapshot` must gather order book, balance, position mode, both-side positions, all current regular/conditional open orders, mark/leverage facts, and one observed time using one `asyncio.gather`. It returns one typed snapshot; it does not call a repository or classify ownership.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_entry_admission_snapshot.py tests/trading_kernel/unit/test_entry_health.py tests/trading_kernel/unit/test_venue_adapter.py`

Expected: PASS; the venue adapter performs one bounded fact cycle and both health decisions freeze its exact digest.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/entry_admission_snapshot.py src/trading_kernel/domain/account_entry_health.py src/trading_kernel/domain/instrument_entry_health.py src/trading_kernel/domain/incident_blocking.py src/trading_kernel/application/runtime_facts.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/venue_adapter.py tests/trading_kernel/unit/test_entry_admission_snapshot.py tests/trading_kernel/unit/test_entry_health.py tests/trading_kernel/unit/test_venue_adapter.py
git commit -m "feat(kernel): add unified entry admission snapshot"
```

---

### Task 3: Implement pure slot-aware capacity, leverage, and liquidation selection

**Files:**
- Create: `src/trading_kernel/domain/capacity_sizing.py`
- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/application/build_capacity_claim.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `tests/trading_kernel/unit/test_capacity.py`
- Create: `tests/trading_kernel/unit/test_capacity_sizing.py`
- Modify: `tests/trading_kernel/integration/test_runtime_fact_workers.py`
- Modify: `tests/trading_kernel/integration/test_schema_baseline.py`

**Interfaces:**
- Produces: `select_capacity_candidate(request: CapacitySizingRequest) -> CapacitySizingDecision`.
- Produces: `CapacitySizingStatus` values `selected`, `count_exhausted`, `margin_exhausted`, `venue_minimum_unmet`, `exit_plan_unexecutable`, `liquidation_proof_failed`, and `invalid_facts`.
- Consumes: one `EntryAdmissionSnapshot`, one `CapacityPolicy`, one `CapacityInstrumentRules`, one Initial Stop, current capital-owning Ticket count, and the frozen TP1 policy.

- [ ] **Step 1: Write failing arithmetic and boundary tests**

```python
@pytest.mark.parametrize(("active_count", "remaining_slots"), [(0, 3), (1, 2), (2, 1)])
def test_slot_budget_uses_remaining_ticket_capacity(active_count: int, remaining_slots: int) -> None:
    decision = select_capacity_candidate(sizing_request(active_ticket_count=active_count))
    assert decision.selected is not None
    assert decision.selected.remaining_slots == remaining_slots
    assert decision.selected.ticket_margin_budget == (
        decision.selected.remaining_executable_margin / Decimal(remaining_slots)
    )


def test_selects_lowest_safe_leverage_that_fits_full_risk_target() -> None:
    decision = select_capacity_candidate(sizing_request(full_target_first_fits_at=4))
    assert decision.selected.selected_leverage == 4


def test_shrunk_candidate_maximizes_stop_risk_then_uses_lower_leverage() -> None:
    decision = select_capacity_candidate(sizing_request(no_full_target=True))
    assert decision.selected == expected_largest_safe_shrunk_candidate()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_capacity_sizing.py`

Expected: FAIL because `capacity_sizing.py` does not exist.

- [ ] **Step 3: Implement deterministic Decimal sizing**

```python
class MaintenanceMarginBracket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    notional_floor: Decimal
    notional_cap: Decimal | None
    maintenance_margin_rate: Decimal
    maintenance_amount: Decimal


class CapacitySizingRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_wallet_balance: Decimal
    total_margin_balance: Decimal
    total_initial_margin: Decimal
    available_margin: Decimal
    active_ticket_count: int
    max_concurrent_tickets: int
    planned_stop_risk_fraction: Decimal
    max_initial_margin_utilization: Decimal
    permitted_max_leverage: int
    configured_leverage: int
    instrument_has_open_position: bool
    entry_reference_price: Decimal
    initial_stop_price: Decimal
    quantity_step: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    tp1_quantity_fraction: Decimal
    maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...]
    position_side: Literal["long", "short"]
    mark_price: Decimal
    min_liquidation_distance_to_stop_distance_ratio: Decimal
```

Calculate `planned_stop_risk_budget`, `remaining_policy_margin`, `remaining_executable_margin`, `ticket_margin_budget`, risk quantity, integer leverage candidates, rounded final quantity, reserved margin, planned stop risk, TP1/runner executability, and conservative bracket-derived liquidation proof. When the instrument already has either-side exposure, evaluate only `configured_leverage` and set `leverage_change_required=False`. Sort eligible full-target candidates by leverage ascending; otherwise sort by planned stop risk descending then leverage ascending.

Extend `brc_instrument_rules_current` and its typed repository model with exact `venue_id + exchange_instrument_id` identity, `exchange_max_leverage`, a versioned maintenance-margin bracket payload, payload digest, observed time, and expiry. Decode the JSON payload into `tuple[MaintenanceMarginBracket, ...]` before invoking the domain; loose dictionaries never cross the application/domain boundary.

- [ ] **Step 4: Integrate the pure decision into Claim construction**

`build_capacity_claim` validates signal identity, scope, snapshot freshness, Cross margin, independent sides, account health, instrument health, and instrument rules, then delegates all financial selection to `select_capacity_candidate`. It maps each refusal status without collapsing ownership, margin mode, stale fact, liquidation, and venue-minimum failures into one generic reason.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: PASS for 0/1/2/3 active Ticket counts, exact 90% account margin ceiling, lowest sufficient leverage, shrunk capacity, venue minimums, TP1/runner split, Cross-only mode, and the exact 2.0 liquidation boundary.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/capacity_sizing.py src/trading_kernel/domain/capacity.py src/trading_kernel/application/build_capacity_claim.py src/trading_kernel/application/runtime_facts.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py src/trading_kernel/infrastructure/pg_repositories.py tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/integration/test_schema_baseline.py
git commit -m "feat(kernel): add slot-aware leverage sizing"
```

---

### Task 4: Freeze the new CapacityClaim, Ticket, and reservation audit model

**Files:**
- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/domain/ticket.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `tests/trading_kernel/unit/test_capacity.py`
- Modify: `tests/trading_kernel/unit/test_ticket.py`
- Modify: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- Modify: `tests/trading_kernel/integration/test_pg_unit_of_work.py`

**Interfaces:**
- Produces: `CapacityClaim.to_ticket() -> TradeTicket` with exact frozen policy, slot, leverage, margin, liquidation, and tolerance evidence.
- Produces: `BudgetReservationRecord(budget_reservation_id: str, ticket_id: str, owner_policy_id: str, venue_id: str, account_id: str, reserved_notional: Decimal, reserved_risk: Decimal, reserved_margin: Decimal, planned_stop_risk_budget: Decimal, risk_reservation_basis: str, status: str, created_at_ms: int, released_at_ms: int | None = None)`.
- Replaces: generic Decimal `leverage` with validated integer `selected_leverage`.

- [ ] **Step 1: Write failing round-trip tests**

```python
def test_claim_to_ticket_preserves_dynamic_budget_evidence() -> None:
    claim = valid_dynamic_capacity_claim()
    ticket = claim.to_ticket()
    assert ticket.capacity_claim_id == claim.capacity_claim_id
    assert ticket.selected_leverage == claim.selected_leverage
    assert ticket.leverage_change_required == claim.leverage_change_required
    assert ticket.reserved_margin == claim.reserved_margin
    assert ticket.post_fill_stop_risk_limit == claim.post_fill_stop_risk_limit
    assert ticket.projected_liquidation_price == claim.projected_liquidation_price


async def test_pg_round_trip_preserves_integer_leverage_and_decimal_budget(pg_uow) -> None:
    await pg_uow.capacity_claims.add(valid_dynamic_capacity_claim())
    stored = await pg_uow.capacity_claims.get(CLAIM_ID)
    assert stored == valid_dynamic_capacity_claim()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_ticket.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_pg_unit_of_work.py`

Expected: FAIL because the current Claim, Ticket, schema, and repository mappings contain the fixed-policy shape.

- [ ] **Step 3: Implement immutable model and digest changes**

Add the complete revision-3 Claim fields, including `account_capacity_domain_key`, `leverage_domain_key`, `entry_admission_snapshot_digest`, both health digests, wallet/margin facts, active count, remaining slots, risk fraction and budget, hard post-fill limit, margin utilization, slot margin, integer required/selected/configured leverage, `leverage_change_required`, reserved margin, maintenance bracket identity, projected liquidation values, and decision digest. Add the Ticket subset required after Claim expiry. Digest every field except the generated identity and digest itself.

- [ ] **Step 4: Implement exact persistence mappings and constraints**

Store integer leverage in integer columns, all financial values in `NUMERIC(38, 18)`, canonical digests in text columns, and exact venue/account identities on reservations. Constraints require nonnegative/positive values, `selected_leverage <= max_leverage`, `risk_at_stop <= planned_stop_risk_budget`, and `post_fill_stop_risk_limit >= planned_stop_risk_budget`.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_ticket.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: PASS with exact Decimal and integer round trips and no legacy Claim/Ticket field fallback.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/capacity.py src/trading_kernel/domain/ticket.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/infrastructure/pg_unit_of_work.py tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_ticket.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/integration/test_schema_baseline.py
git commit -m "refactor(kernel): freeze dynamic budget ticket evidence"
```

---

### Task 5: Persist typed Incident blocking scope and bounded admission ownership

**Files:**
- Modify: `src/trading_kernel/domain/incident.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/application/build_capacity_claim.py`
- Create: `tests/trading_kernel/unit/test_incident_blocking.py`
- Modify: `tests/trading_kernel/integration/test_pg_unit_of_work.py`
- Modify: `tests/trading_kernel/integration/test_signal_to_ticket.py`

**Interfaces:**
- Produces: `RuntimeIncidentRecord(incident_id: str, ticket_id: str | None, incident_kind: str, status: str, first_blocker: str, entry_block_scope: EntryBlockScope, entry_block_key: str | None, details: dict[str, JsonValue], opened_at_ms: int, resolved_at_ms: int | None = None)`.
- Produces: `IncidentRepository.list_open_entry_blocks(*, venue_id: str, account_id: str, exchange_instrument_id: str) -> tuple[RuntimeIncidentRecord, ...]`.
- Produces: `EntryAdmissionRepository.read_admission_ownership(*, venue_id: str, account_id: str, exchange_instrument_id: str) -> AdmissionOwnership` using bounded current Ticket, position, order, and unknown-command queries.

- [ ] **Step 1: Write failing scope and repository tests**

```python
@pytest.mark.parametrize(
    ("scope", "key"),
    [
        (EntryBlockScope.RUNTIME, "global"),
        (EntryBlockScope.ACCOUNT_CAPACITY, "binance-usdm:acct"),
        (EntryBlockScope.LEVERAGE_DOMAIN, "binance-usdm:acct:SOLUSDT"),
        (EntryBlockScope.NONE, None),
    ],
)
def test_incident_scope_requires_canonical_key(scope, key) -> None:
    assert runtime_incident(entry_block_scope=scope, entry_block_key=key)


async def test_open_account_incident_blocks_only_exact_account(pg_uow) -> None:
    await pg_uow.incidents.open(account_incident("binance-usdm", "acct-a"))
    assert await pg_uow.incidents.list_open_entry_blocks(
        venue_id="binance-usdm", account_id="acct-a", exchange_instrument_id="SOLUSDT"
    )
    assert not await pg_uow.incidents.list_open_entry_blocks(
        venue_id="binance-usdm", account_id="acct-b", exchange_instrument_id="SOLUSDT"
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_incident_blocking.py tests/trading_kernel/integration/test_pg_unit_of_work.py -k incident`

Expected: FAIL because Incident rows have only free-form details and no typed entry-block scope.

- [ ] **Step 3: Implement typed scope, SQL constraints, and bounded selectors**

The database permits only `runtime`, `account_capacity`, `leverage_domain`, and `none`. A check constraint binds `runtime` to `global`, `account_capacity` to a two-part key, `leverage_domain` to a three-part key, and `none` to NULL. Repository queries select only open rows matching runtime, exact account, or exact instrument scope and never infer scope from `first_blocker` or JSON details.

- [ ] **Step 4: Feed ownership and Incident truth into Claim construction**

`build_capacity_claim` accepts typed `AccountEntryHealth`, `InstrumentEntryHealth`, and applicable open Incident blocks. Normal same-domain occupancy remains a terminal admission refusal, not an Incident. Unowned Cross-account exposure blocks the account; owned flat residue blocks only the leverage domain.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_incident_blocking.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/integration/test_signal_to_ticket.py`

Expected: PASS with deterministic scope behavior and no free-form blocker inference.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/incident.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/application/build_capacity_claim.py tests/trading_kernel/unit/test_incident_blocking.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/integration/test_signal_to_ticket.py
git commit -m "feat(kernel): type incident entry blocking scope"
```

---

### Task 6: Add SET_LEVERAGE as a separate durable command and initial Ticket state

**Files:**
- Modify: `src/trading_kernel/domain/commands.py`
- Modify: `src/trading_kernel/domain/effects.py`
- Modify: `src/trading_kernel/domain/events.py`
- Modify: `src/trading_kernel/domain/aggregate.py`
- Modify: `src/trading_kernel/domain/reducer.py`
- Modify: `src/trading_kernel/application/issue_ticket.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `tests/trading_kernel/unit/test_commands.py`
- Modify: `tests/trading_kernel/unit/test_reducer.py`
- Modify: `tests/trading_kernel/integration/test_issue_ticket.py`

**Interfaces:**
- Produces: `ExchangeCommandKind.SET_LEVERAGE`.
- Produces: `SetLeverageCommandPayload(desired_leverage: int, owner_policy_version: int, entry_admission_snapshot_digest: str, leverage_fact_digest: str)`.
- Produces: `SetLeverageCommandResult(exchange_configured_leverage: int, leverage_verified_at_ms: int, leverage_verification_digest: str)`.
- Produces at Ticket issue: either SET_LEVERAGE generation 1 or ENTRY generation 1, never both.

- [ ] **Step 1: Write failing command and reducer tests**

```python
def test_set_leverage_generation_is_exactly_one() -> None:
    command = set_leverage_command(generation=1)
    assert command.kind is ExchangeCommandKind.SET_LEVERAGE
    with pytest.raises(ValueError, match="SET_LEVERAGE command cannot have a retry generation"):
        set_leverage_command(generation=2)


def test_ticket_issue_prepares_only_set_leverage_when_change_is_required() -> None:
    reduction = reduce_event(None, ticket_issued(leverage_change_required=True))
    assert [type(effect) for effect in reduction.effects] == [PrepareSetLeverageCommand]


def test_ticket_issue_prepares_entry_when_leverage_already_matches() -> None:
    reduction = reduce_event(None, ticket_issued(leverage_change_required=False))
    assert [type(effect) for effect in reduction.effects] == [PrepareEntryCommand]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_commands.py tests/trading_kernel/unit/test_reducer.py -k leverage`

Expected: FAIL because SET_LEVERAGE types, effects, events, and aggregate states do not exist.

- [ ] **Step 3: Implement separate command payload/result validation**

Extend `CommandPayload` with `SetLeverageCommandPayload`. SET_LEVERAGE forbids `venue_client_order_id` and order payloads; order commands continue to require deterministic client order identity. ENTRY payload adds `required_configured_leverage: int` and `leverage_verification_digest: str`. Both SET_LEVERAGE and ENTRY enforce generation 1.

- [ ] **Step 4: Implement reducer states and atomic issue selection**

Add `LEVERAGE_PENDING`, `LEVERAGE_CONFIRMED`, `LEVERAGE_REJECTED`, and `LEVERAGE_OUTCOME_UNKNOWN` aggregate states and typed leverage events. `issue_ticket` revalidates `new_entry_submit_enabled`, exact policy version, count, domain, Incident scope, and Claim digest while holding the global lane and exact venue/account exposure row. The same transaction persists Claim, Ticket, reservation, count, domain, aggregate, first event, and only the applicable first command.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_commands.py tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_issue_ticket.py`

Expected: PASS; each Ticket has at most one SET_LEVERAGE generation and at most one ENTRY generation, and no issue transaction persists both initial mutations.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/commands.py src/trading_kernel/domain/effects.py src/trading_kernel/domain/events.py src/trading_kernel/domain/aggregate.py src/trading_kernel/domain/reducer.py src/trading_kernel/application/issue_ticket.py src/trading_kernel/infrastructure/pg_repositories.py tests/trading_kernel/unit/test_commands.py tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_issue_ticket.py
git commit -m "feat(kernel): separate leverage and entry commands"
```

---

### Task 7: Dispatch and reconcile SET_LEVERAGE without blind resend

**Files:**
- Create: `src/trading_kernel/application/reconcile_leverage_command.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/dispatch_exchange_command.py`
- Modify: `src/trading_kernel/application/recover_unknown_command.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Modify: `tests/trading_kernel/unit/test_venue_adapter.py`
- Modify: `tests/trading_kernel/unit/test_unknown_command_recovery.py`
- Modify: `tests/trading_kernel/integration/test_command_dispatch.py`
- Modify: `tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

**Interfaces:**
- Produces: `VenuePort.set_leverage(request: VenueSetLeverageRequest) -> SetLeverageCommandResult`.
- Produces: `VenueTruthPort.read_configured_leverage(request: LeverageTruthRequest) -> LeverageTruthSnapshot`.
- Produces: `reconcile_leverage_command(uow, truth_port, request) -> ReconcileLeverageCommandResult`.

- [ ] **Step 1: Write failing dispatch and unknown-outcome tests**

```python
async def test_confirmed_leverage_creates_first_entry_command_in_later_transaction() -> None:
    result = await dispatch_exchange_command(uow_factory, venue, prepared_set_leverage())
    assert result.status is DispatchStatus.ACCEPTED
    commands = await list_commands(TICKET_ID)
    assert [(item.kind, item.generation) for item in commands] == [
        (ExchangeCommandKind.SET_LEVERAGE, 1),
        (ExchangeCommandKind.ENTRY, 1),
    ]


async def test_unknown_leverage_readback_mismatch_releases_without_resend() -> None:
    result = await reconcile_leverage_command(uow, truth_port(leverage=3), request(desired=4))
    assert result.status is ReconcileLeverageStatus.REJECTED_MISMATCH
    assert await count_commands(TICKET_ID, ExchangeCommandKind.SET_LEVERAGE) == 1
    assert await count_commands(TICKET_ID, ExchangeCommandKind.ENTRY) == 0
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py -k leverage`

Expected: FAIL because venue, dispatch, and recovery paths understand only order commands.

- [ ] **Step 3: Implement signed set/read-back at the venue boundary**

Add `set_leverage(symbol, desired_leverage)` to the CCXT exchange protocol and translate the signed response into a typed result. Immediately read exact current leverage after the mutation. A timeout after invoking `set_leverage` returns `OUTCOME_UNKNOWN`; an authoritative venue rejection returns `REJECTED`; exact read-back returns `ACCEPTED`. Never call `create_order` from the SET_LEVERAGE branch.

- [ ] **Step 4: Implement exact recovery progression**

`reconcile_leverage_command` reads exact instrument leverage, both-side positions, and open orders. Desired leverage plus flat/order-free truth records reconciled acceptance and persists ENTRY generation 1 in a new short transaction. Different leverage plus flat/order-free truth records terminal mismatch and releases the unexposed Ticket without another leverage command. Any position/order contradiction retains an account or leverage-domain Incident and blocks release.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_venue_adapter.py tests/trading_kernel/unit/test_unknown_command_recovery.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

Expected: PASS with zero blind leverage resend and one later ENTRY generation only after exact confirmation.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/application/reconcile_leverage_command.py src/trading_kernel/application/ports.py src/trading_kernel/application/dispatch_exchange_command.py src/trading_kernel/application/recover_unknown_command.py src/trading_kernel/infrastructure/venue_adapter.py src/trading_kernel/interfaces/entry_worker.py tests/trading_kernel/unit/test_venue_adapter.py tests/trading_kernel/unit/test_unknown_command_recovery.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py
git commit -m "feat(kernel): reconcile durable leverage mutation"
```

---

### Task 8: Add fresh pre-mutation dispatch revalidation for SET_LEVERAGE and ENTRY

**Files:**
- Create: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/dispatch_exchange_command.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Create: `tests/trading_kernel/unit/test_entry_dispatch_preflight.py`
- Modify: `tests/trading_kernel/integration/test_command_dispatch.py`
- Modify: `tests/trading_kernel/integration/test_runtime_fact_workers.py`

**Interfaces:**
- Produces: `revalidate_entry_dispatch(request: EntryDispatchPreflightRequest) -> EntryDispatchPreflightDecision`.
- Produces typed statuses for policy/scope drift, write disable, runtime fence, stale snapshot, ownership conflict, wallet-risk drift, margin drift, quote risk, liquidation failure, and leverage mismatch.
- Consumes: immutable Ticket/Claim, current policy/scope/runtime identity, one fresh admission snapshot, health decisions, and applicable Incident blocks.

- [ ] **Step 1: Write failing pure and integration tests**

```python
def test_entry_preflight_refuses_when_frozen_margin_no_longer_fits() -> None:
    decision = revalidate_entry_dispatch(preflight_request(available_margin=Decimal("4"), reserved_margin=Decimal("5")))
    assert decision.status is EntryDispatchPreflightStatus.MARGIN_DRIFT


async def test_policy_disable_before_entry_causes_zero_venue_mutations() -> None:
    await disable_new_entry_policy()
    result = await dispatch_exchange_command(uow_factory, recording_venue(), prepared_entry())
    assert result.status is DispatchStatus.SUPERSEDED
    assert recording_venue().mutations == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_entry_dispatch_preflight.py tests/trading_kernel/integration/test_command_dispatch.py -k preflight`

Expected: FAIL because dispatch currently claims a command and executes it without the revision-3 typed preflight.

- [ ] **Step 3: Implement the pure preflight decision**

Validate exact Ticket/command generation, Claim and command deadlines, current policy and scope versions, `new_entry_submit_enabled`, exact runtime commit/schema identity, independent sides, Cross margin, applicable Incident fences, Netting Domain flatness, opposite-side ownership health, frozen wallet-relative stop risk, `reserved_margin <= min(available_margin, max(total_margin_balance * 0.90 - total_initial_margin, 0))`, fresh quote protection direction, 110% hard stop-risk ceiling, bracket-derived liquidation ratio, and configured leverage branch.

- [ ] **Step 4: Integrate separate preflights before each mutation**

SET_LEVERAGE additionally requires both exact-instrument sides flat and all exact-instrument orders absent. ENTRY requires exact configured leverage equality and emits only `create_order`. A failed preflight records a typed authoritative refusal and releases an unexposed Ticket through the reducer; it never resizes, reprices, retries, or mutates the venue.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_entry_dispatch_preflight.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_runtime_fact_workers.py`

Expected: PASS for policy/scope drift, external ownership, Incident fences, margin and wallet drift, unsafe quotes, liquidation failure, and leverage mismatch with zero venue effects.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/application/revalidate_entry_dispatch.py src/trading_kernel/application/runtime_facts.py src/trading_kernel/application/ports.py src/trading_kernel/application/dispatch_exchange_command.py src/trading_kernel/interfaces/entry_worker.py tests/trading_kernel/unit/test_entry_dispatch_preflight.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_runtime_fact_workers.py
git commit -m "feat(kernel): revalidate entry mutations at dispatch"
```

---

### Task 9: Add typed post-fill stop-risk and liquidation disposition

**Files:**
- Create: `src/trading_kernel/domain/post_fill_risk.py`
- Modify: `src/trading_kernel/domain/events.py`
- Modify: `src/trading_kernel/domain/effects.py`
- Modify: `src/trading_kernel/domain/aggregate.py`
- Modify: `src/trading_kernel/domain/reducer.py`
- Modify: `src/trading_kernel/application/reconcile_ticket.py`
- Modify: `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- Modify: `src/trading_kernel/application/runtime_facts.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Create: `tests/trading_kernel/unit/test_post_fill_risk.py`
- Modify: `tests/trading_kernel/unit/test_reducer.py`
- Modify: `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`

**Interfaces:**
- Produces: `assess_post_fill_risk(request: PostFillRiskRequest) -> PostFillRiskDecision`.
- Produces statuses `within_budget`, `tolerated_overrun`, `hard_overrun`, `liquidation_safety_degraded`, and `protection_direction_invalid`.
- Produces aggregate fields for actual stop risk, actual liquidation evidence, and frozen lifecycle disposition without mutating the Ticket.

- [ ] **Step 1: Write failing boundary tests**

```python
@pytest.mark.parametrize(
    ("actual_risk", "expected"),
    [
        (Decimal("3.00"), PostFillRiskStatus.WITHIN_BUDGET),
        (Decimal("3.30"), PostFillRiskStatus.TOLERATED_OVERRUN),
        (Decimal("3.300000000000000001"), PostFillRiskStatus.HARD_OVERRUN),
    ],
)
def test_post_fill_risk_uses_exact_frozen_limit(actual_risk, expected) -> None:
    assert assess_post_fill_risk(post_fill_request(actual_stop_risk=actual_risk)).status is expected


def test_wrong_side_stop_requests_immediate_flatten() -> None:
    decision = assess_post_fill_risk(post_fill_request(position_side="long", fill_price="100", stop_price="101"))
    assert decision.status is PostFillRiskStatus.PROTECTION_DIRECTION_INVALID
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_post_fill_risk.py`

Expected: FAIL because post-fill risk is not a typed domain decision.

- [ ] **Step 3: Implement pure actual-risk and liquidation assessment**

Calculate `quantity * abs(average_fill_price - initial_stop_price)`, validate directional protection, consume signed current liquidation evidence, and compare the actual ratio with the frozen 2.0 policy. Tolerated overrun continues normally; hard overrun or degraded/unprovable liquidation sets `flatten_after_protection`; invalid protection direction sets `flatten_immediately`.

- [ ] **Step 4: Integrate lifecycle effects and persistence**

`EntryFilled` carries the assessment evidence. Normal/tolerated paths prepare Initial Stop then TP1. Protect-then-flatten prepares Initial Stop, records an account-scoped Incident, then `InitialStopConfirmed` prepares controlled flatten and never TP1. Invalid direction prepares controlled flatten immediately. Persist actual evidence on the mutable aggregate and append-only event only.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_post_fill_risk.py tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: PASS for exact tolerance boundaries, missing/contradictory liquidation evidence, protect-then-flatten, immediate flatten, and absence of TP1 in recovery paths.

- [ ] **Step 6: Commit**

```bash
git add src/trading_kernel/domain/post_fill_risk.py src/trading_kernel/domain/events.py src/trading_kernel/domain/effects.py src/trading_kernel/domain/aggregate.py src/trading_kernel/domain/reducer.py src/trading_kernel/application/reconcile_ticket.py src/trading_kernel/application/maintain_ticket_lifecycle.py src/trading_kernel/application/runtime_facts.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py src/trading_kernel/infrastructure/pg_repositories.py tests/trading_kernel/unit/test_post_fill_risk.py tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/integration/test_schema_baseline.py
git commit -m "feat(kernel): enforce post-fill risk disposition"
```

---

### Task 10: Release budget, account count, and Netting Domain on ReconciliationMatched

**Files:**
- Modify: `src/trading_kernel/domain/effects.py`
- Modify: `src/trading_kernel/domain/reducer.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/reconcile_ticket.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `tests/trading_kernel/unit/test_reducer.py`
- Modify: `tests/trading_kernel/integration/test_pg_unit_of_work.py`
- Modify: `tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

**Interfaces:**
- Produces: one `ReleaseCapitalAuthorities` effect containing `ticket_id`, Account Capacity Domain key, Netting Domain key, notional, risk, margin, and release time.
- Guarantees: `ReconciliationMatched` records the event and releases reservation, active Ticket count, and Netting Domain exactly once in the same transaction.
- Preserves: Settlement and Review remain mandatory but no longer consume a position slot after matched flatness.

- [ ] **Step 1: Write failing release tests**

```python
async def test_reconciliation_matched_atomically_releases_all_capital_authorities(pg_uow) -> None:
    await seed_reconciliation_pending_ticket(pg_uow)
    await reconcile_ticket(pg_uow, flat_order_free_snapshot_request())
    assert (await pg_uow.budgets.get(TICKET_ID)).status == "released"
    assert (await pg_uow.entry_admission.get_account_exposure("binance-usdm", "acct")).active_ticket_count == 0
    assert not await pg_uow.entry_admission.has_active_ticket_in_domain(NETTING_DOMAIN_KEY)
    assert (await pg_uow.aggregates.get(TICKET_ID)).status is AggregateStatus.SETTLEMENT_PENDING


async def test_repeated_matched_reconciliation_does_not_double_release(pg_uow) -> None:
    await reconcile_ticket(pg_uow, flat_order_free_snapshot_request())
    await reconcile_ticket(pg_uow, flat_order_free_snapshot_request())
    assert await release_event_count(pg_uow, TICKET_ID) == 1
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/full_chain/test_ticket_lifecycle.py -k release`

Expected: FAIL because current release and Settlement sequencing do not prove all three authorities are atomically and idempotently released at ReconciliationMatched.

- [ ] **Step 3: Implement one exact release effect and transaction**

`reduce_event(current_aggregate, reconciliation_matched_event)` emits one release effect. `PostgresKernelUnitOfWork.commit_reduction` handles it under the aggregate version lock: update active reservation to released, decrement the exact venue/account active count with a nonnegative guard, release the exact Netting Domain hold, append the event, and advance the aggregate. A missing or already released authority is accepted only when all three are already in the exact released state; partial release is an invariant error.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/full_chain/test_ticket_lifecycle.py`

Expected: PASS; a fourth Ticket may be admitted after one matched flat Ticket even while the old Ticket is Settlement/Review pending.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/domain/effects.py src/trading_kernel/domain/reducer.py src/trading_kernel/application/ports.py src/trading_kernel/application/reconcile_ticket.py src/trading_kernel/infrastructure/pg_unit_of_work.py src/trading_kernel/infrastructure/pg_repositories.py tests/trading_kernel/unit/test_reducer.py tests/trading_kernel/integration/test_pg_unit_of_work.py tests/trading_kernel/full_chain/test_ticket_lifecycle.py
git commit -m "feat(kernel): release capacity on reconciliation match"
```

---

### Task 11: Enforce policy, scope, strategy, and runtime-fence lifecycle boundaries

**Files:**
- Modify: `src/trading_kernel/application/issue_ticket.py`
- Modify: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- Modify: `src/trading_kernel/application/reconcile_ticket.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Modify: `src/trading_kernel/interfaces/lifecycle_worker.py`
- Modify: `src/trading_kernel/interfaces/reconciliation_worker.py`
- Modify: `tests/trading_kernel/integration/test_runtime_fact_workers.py`
- Modify: `tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py`
- Modify: `tests/trading_kernel/full_chain/test_fault_matrix.py`

**Interfaces:**
- New ENTRY consumes current enabled policy/scope/strategy authority and exact runtime identity.
- Existing exposure consumes frozen Ticket authority plus one currently certified exact writer.
- Runtime-scoped Incidents fence suspect writers; readonly probes and reconciliation observations remain permitted.

- [ ] **Step 1: Write failing lifecycle-boundary tests**

```python
async def test_new_entry_disable_releases_unmutated_ticket_but_does_not_block_stop() -> None:
    entry = await dispatch_prepared_entry_after_policy_disable()
    stop = await dispatch_prepared_initial_stop_after_policy_disable()
    assert entry.status is DispatchStatus.SUPERSEDED
    assert stop.status is DispatchStatus.ACCEPTED


async def test_mismatched_writer_performs_no_exchange_mutation() -> None:
    result = await run_lifecycle_worker_once(factory, venue, facts, runtime_identity="wrong")
    assert result.status is LifecycleWorkerStatus.RUNTIME_FENCED
    assert venue.mutations == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/full_chain/test_fault_matrix.py -k 'disable or fence'`

Expected: FAIL because the current write flag name and runtime-fence recovery ownership are not explicit enough.

- [ ] **Step 3: Implement exact boundary rules**

Before any new-entry mutation, a current policy/scope/strategy version mismatch or disable supersedes and releases the unexposed Ticket. After a mutation may have reached the venue, exact command reconciliation owns progression. After fill, frozen Ticket terms retain protection, repair, exit, cancel, flatten, reconciliation, Settlement, and Review authority. A worker with wrong commit/schema performs no mutation; after all competing writers are fenced, only the exact certified writer may resume durable safety commands while the runtime Incident remains open.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/full_chain/test_fault_matrix.py`

Expected: PASS for pre-mutation release, post-fill safety continuation, strategy kill after flat terminal closure, duplicate-writer fencing, and readonly observation under mismatch.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/application/issue_ticket.py src/trading_kernel/application/revalidate_entry_dispatch.py src/trading_kernel/application/maintain_ticket_lifecycle.py src/trading_kernel/application/reconcile_ticket.py src/trading_kernel/interfaces/entry_worker.py src/trading_kernel/interfaces/lifecycle_worker.py src/trading_kernel/interfaces/reconciliation_worker.py tests/trading_kernel/integration/test_runtime_fact_workers.py tests/trading_kernel/integration/test_ticket_lifecycle_maintenance.py tests/trading_kernel/full_chain/test_fault_matrix.py
git commit -m "fix(kernel): separate entry fence from exposure recovery"
```

---

### Task 12: Update production seed, probes, cutover, and certification for the dynamic model

**Files:**
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `src/trading_kernel/infrastructure/tokyo_cutover_adapter.py`
- Modify: `scripts/trading_kernel/seed_runtime_authority.py`
- Modify: `scripts/trading_kernel/probe_production_runtime.py`
- Modify: `scripts/trading_kernel/certify_readonly.py`
- Modify: `scripts/trading_kernel/cutover_tokyo.py`
- Modify: `scripts/trading_kernel/verify_schema.py`
- Modify: `tests/trading_kernel/integration/test_runtime_authority_seed.py`
- Modify: `tests/trading_kernel/integration/test_production_cutover_adapter.py`
- Modify: `tests/trading_kernel/integration/test_cutover_state_machine.py`

**Interfaces:**
- Seed installs the approved policy with `new_entry_submit_enabled=false`.
- Readonly probe reports exact policy values, account/position/margin modes, leverage, ownership classification, Incident fences, release counts, commit, schema, and seed identity.
- Controlled arm enables new ENTRY without changing any sizing limit; full authority enables the same three-Ticket policy only after one new-model terminal certification Ticket.

- [ ] **Step 1: Write failing production-contract tests**

```python
async def test_arm_changes_only_entry_submit_authority(pg_uow) -> None:
    before = await current_policy(pg_uow)
    after = await arm_acceptance_policy(pg_uow, ArmAcceptancePolicyRequest(armed_at_ms=NOW))
    assert after.new_entry_submit_enabled is True
    assert after.model_dump(exclude={"policy_version", "new_entry_submit_enabled"}) == before.model_dump(
        exclude={"policy_version", "new_entry_submit_enabled"}
    )


def test_readonly_certification_accepts_exchange_commands_when_live_policy_is_controlled() -> None:
    report = certify_readonly(certification_fixture(exchange_commands=True, new_entry_submit_enabled=False))
    assert report.status == "pass"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_production_cutover_adapter.py tests/trading_kernel/integration/test_cutover_state_machine.py`

Expected: FAIL because scripts still encode acceptance=1, full=2, fixed 20/40 USDT, fixed 2x, and the old write flag semantics.

- [ ] **Step 3: Replace retired operational semantics**

Update CLI help, JSON result models, seed hashes, cutover phase checks, schema probe, and readonly certification. `promote-full` no longer raises a 1/2 Ticket fixed envelope; it proves a terminal new-model Ticket and enables normal three-Ticket authority. Readonly certification checks capability truth rather than hard-coding `exchange_commands=false` as the only valid state.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_production_cutover_adapter.py tests/trading_kernel/integration/test_cutover_state_machine.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: PASS with exact dynamic policy identities and no retired operational copy or field name.

- [ ] **Step 5: Commit**

```bash
git add src/trading_kernel/infrastructure/runtime_authority_seed.py src/trading_kernel/infrastructure/tokyo_cutover_adapter.py scripts/trading_kernel/seed_runtime_authority.py scripts/trading_kernel/probe_production_runtime.py scripts/trading_kernel/certify_readonly.py scripts/trading_kernel/cutover_tokyo.py scripts/trading_kernel/verify_schema.py tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_production_cutover_adapter.py tests/trading_kernel/integration/test_cutover_state_machine.py tests/trading_kernel/integration/test_schema_baseline.py
git commit -m "refactor(cutover): certify dynamic entry authority"
```

---

### Task 13: Certify three Tickets, same-instrument dual sides, and scoped failures end to end

**Files:**
- Modify: `tests/trading_kernel/full_chain/test_multi_position_certification.py`
- Modify: `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Modify: `tests/trading_kernel/full_chain/test_six_event_system_certification.py`
- Modify: `tests/trading_kernel/integration/test_signal_to_ticket.py`
- Modify: `tests/trading_kernel/integration/test_command_dispatch.py`
- Modify: `tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

**Interfaces:**
- Certifies the unchanged public chain: StrategySignal -> Readiness -> CapacityClaim -> Ticket -> optional SET_LEVERAGE -> ENTRY -> protection -> lifecycle -> reconciliation -> release -> Settlement -> Review.
- Certifies three capital-owning Tickets across distinct Netting Domains with serial admission and concurrent protected lifecycle.

- [ ] **Step 1: Write the failing full-chain scenario**

```python
async def test_three_serial_tickets_progress_concurrently() -> None:
    sol_long = await run_natural_signal_to_protected("SOR-LONG", "SOLUSDT")
    sol_short = await run_natural_signal_to_protected("SOR-SHORT", "SOLUSDT")
    btc_long = await run_natural_signal_to_protected("CPM-LONG", "BTCUSDT")
    assert {sol_long.netting_domain.position_side, sol_short.netting_domain.position_side} == {"long", "short"}
    assert await active_capital_ticket_count("binance-usdm", ACCOUNT_ID) == 3
    assert await all_entry_commands_are_generation_one()
    assert await global_lane_is_idle()


async def test_same_direction_cross_strategy_and_fourth_ticket_have_zero_exchange_effects() -> None:
    assert await attempt_same_direction_second_strategy().status is IssueTicketStatus.ACTIVE_NETTING_DOMAIN
    assert await attempt_fourth_ticket().status is IssueTicketStatus.BUDGET_EXHAUSTED
    assert recording_venue().new_mutations == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/full_chain/test_multi_position_certification.py tests/trading_kernel/full_chain/test_fault_matrix.py`

Expected: FAIL until Tasks 1-12 close the new policy, leverage, conflict, release, and recovery semantics.

- [ ] **Step 3: Complete exact full-chain fixtures and assertions**

Use the six committed strategy contracts and typed natural StrategySignals. The scenario must include a flat-instrument SET_LEVERAGE path, an already-open opposite-side no-leverage-mutation path, a third-instrument path, same-direction refusal across strategies, fourth-Ticket refusal, account-scoped unknown outcome, leverage-domain owned residue, unowned account order, post-fill hard overrun recovery, and one matched release that permits a new market event while old Settlement/Review remains pending.

Also assert the deterministic arbitration order remains `owner_policy_priority -> candidate_scope_priority -> occurred_at_ms -> observed_at_ms -> signal_event_id`, and that a blocked or superseded Signal is never revived after capacity or domain state changes. Later admission requires a new market event and a new StrategySignal identity.

- [ ] **Step 4: Run the certification matrix and verify GREEN**

Run: `python3 -m pytest -q tests/trading_kernel/full_chain tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

Expected: PASS; no test injects quantity, notional, leverage, or Ticket identity at the StrategySignal boundary.

- [ ] **Step 5: Commit**

```bash
git add tests/trading_kernel/full_chain/test_multi_position_certification.py tests/trading_kernel/full_chain/test_fault_matrix.py tests/trading_kernel/full_chain/test_six_event_system_certification.py tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_command_dispatch.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py
git commit -m "test(kernel): certify dynamic three-ticket chain"
```

---

### Task 14: Retire old semantics, update current authority documents, and run complete local certification

**Files:**
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md`
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Modify: `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `tests/trading_kernel/architecture/test_current_document_authority.py`
- Modify: `tests/trading_kernel/architecture/test_no_retired_execution.py`
- Modify: `tests/trading_kernel/architecture/test_project_skill_authority.py`

**Interfaces:**
- Documents one current policy, one command chain, one release boundary, and one deployment posture.
- Scans production code, schema, seed, scripts, tests, and current documents for retired fixed-Envelope semantics.

- [ ] **Step 1: Add failing retired-semantics scans**

```python
@pytest.mark.parametrize(
    "retired",
    [
        "real_submit" + "_enabled",
        "max_gross" + "_notional",
        "max_gross" + "_risk_at_stop",
        "max_ticket" + "_risk_at_stop",
        "target" + "_leverage",
        "Acceptance=" + "1 Ticket",
        "Full=" + "2 Tickets",
        "20" + " USDT",
        "40" + " USDT",
    ],
)
def test_retired_capacity_semantics_are_absent(retired: str) -> None:
    assert retired not in current_authority_and_execution_text(
        excluded_paths={Path(__file__)},
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python3 -m pytest -q tests/trading_kernel/architecture/test_current_document_authority.py tests/trading_kernel/architecture/test_no_retired_execution.py tests/trading_kernel/architecture/test_project_skill_authority.py`

Expected: FAIL while old current documents, scripts, tests, or production identifiers remain.

- [ ] **Step 3: Update current authority and delete old semantic tests**

Document the exact approved policy values, slot-aware sizing, Account Capacity and Leverage Domains, same-instrument dual-side behavior, separate SET_LEVERAGE/ENTRY commands, `new_entry_submit_enabled`, post-fill disposition, Runtime Fence, and ReconciliationMatched release. Delete tests that require the fixed Envelope; do not preserve aliases or compatibility fields to satisfy them.

- [ ] **Step 4: Run complete local certification**

Run: `python3 -m pytest -q tests/trading_kernel`

Expected: all Trading Kernel tests pass.

Run: `python3 -m ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel migrations/trading_kernel`

Expected: no Ruff findings.

Run: `python3 -m mypy src/trading_kernel scripts/trading_kernel`

Expected: no Mypy findings.

Run: `python3 scripts/trading_kernel/verify_schema.py`

Expected: `status=pass`, schema revision `0001_initial`, exactly 33 tables, and the approved dynamic policy column contract.

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md CLAUDE.md docs/current tests/trading_kernel/architecture
git commit -m "docs(kernel): publish dynamic multi-position authority"
```

---

### Task 15: Perform the separately gated Tokyo rebuild and natural-signal real-funds certification

**Files:**
- Deployment input: exact reviewed implementation commit from Tasks 1-14
- Deployment tooling: `scripts/trading_kernel/cutover_tokyo.py`
- Schema tooling: `scripts/trading_kernel/bootstrap_schema.py`
- Seed tooling: `scripts/trading_kernel/seed_runtime_authority.py`
- Readonly checks: `scripts/trading_kernel/verify_flat_cutover.py`
- Readonly checks: `scripts/trading_kernel/probe_production_runtime.py`
- Readonly checks: `scripts/trading_kernel/certify_readonly.py`
- Durable evidence: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Durable evidence: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`

**Interfaces:**
- Consumes: one reviewed commit, exact `0001_initial`, exact runtime seed identity, exchange-flat/account-order-free proof, and the BRC-only Tokyo mutation allowlist.
- Produces: one terminal Ticket from a naturally observed registered StrategySignal under the new budget model, zero residual order, released capacity, Settlement, Review, zero open Incident, and normal three-Ticket authority.

- [ ] **Step 1: Run predeployment certification and verify the expected production RED**

Run on Tokyo from the currently deployed release:

```bash
python3 scripts/trading_kernel/certify_readonly.py --require-flat
python3 scripts/trading_kernel/probe_production_runtime.py
```

Expected: exchange flatness and ownership checks pass, but release/schema/seed policy identity does not match the reviewed dynamic-budget target, so deployment certification remains blocked and performs zero exchange mutation.

- [ ] **Step 2: Establish hard preconditions with read-only cutover evidence**

Run the committed `verify_flat_cutover.py` and `cutover_tokyo.py --plan` with `src.trading_kernel.infrastructure.tokyo_cutover_adapter:build_tokyo_cutover_adapter`, the exact reviewed target commit, computed seed identity, `0001_initial`, runtime profile `tiny-live-v1`, venue `binance-usdm`, and the configured production account identity. Required result: exchange quantity zero on both sides for every supported instrument; zero open BRC or unknown orders; zero unknown command outcome; all old BRC writers stopped and fenced; exact `brc_trading_kernel` database target identified; non-quantitative services excluded.

- [ ] **Step 3: Keep exchange writes disabled and rebuild only the isolated BRC database**

Stop the four BRC workers, deploy the exact reviewed release, destroy and recreate only the approved BRC PostgreSQL database, apply `0001_initial`, seed the six-strategy Registry and dynamic Owner Policy with `new_entry_submit_enabled=false`, and verify exact commit/schema/seed identity. Do not modify nginx, unrelated containers, unrelated PostgreSQL databases, or non-quantitative program data.

- [ ] **Step 4: Start persistent workers in read-only/new-entry-disabled mode**

Start Observation, Entry, Lifecycle, and Reconciliation persistent services. Verify zero BRC timers, stable idle CPU/memory on the 2c4g host, no recurring JSON/Markdown output, no warning/error loop, and correct Runtime Fence behavior. Entry may observe and classify but must perform zero mutation while the policy flag is false.

- [ ] **Step 5: Enable natural-signal acceptance only**

Use the monotonic policy transition to set only `new_entry_submit_enabled=true` under controlled acceptance authority. Wait for a newly observed registered StrategySignal; do not construct, replay-as-live, or manually inject a Signal. Certify the exact Admission Snapshot, Claim sizing, selected leverage, optional SET_LEVERAGE command, ENTRY, full fill, Initial Stop, lifecycle exit, exchange flatness, residue cleanup, ReconciliationMatched release, Settlement, Review, and zero Incident. Do not bypass the kernel.

- [ ] **Step 6: Enable normal three-Ticket authority only after terminal proof**

Run `promote-full` only after the naturally triggered Ticket is terminal, exchange-flat, order-free, reconciliation-matched, released, settled, reviewed, and Incident-free. Re-run readonly production certification and verify that the current policy remains exactly `3 / 0.03 / 0.90 / 10 / cross / 2.0 / 0.10` with no fixed notional or gross-risk cap.

- [ ] **Step 7: Re-run production certification and verify GREEN**

```bash
python3 scripts/trading_kernel/certify_readonly.py --require-flat
python3 scripts/trading_kernel/probe_production_runtime.py
```

Expected: exact target commit, `0001_initial`, dynamic seed identity, approved policy values, four persistent workers, zero unknown outcomes, zero residual orders, zero active Incident, and terminal controlled-Ticket evidence all pass.

- [ ] **Step 8: Record the production anchor and final evidence**

Update the production commit, immutable tag, schema identity, seed digest, worker health, naturally triggered Ticket identity, terminal economics, release evidence, and final requirement audit in current documents. Commit only those durable current-state documents; do not commit generated runtime output.

```bash
git add docs/current/MAIN_CONTROL_ROADMAP.md docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md
git commit -m "docs(production): certify dynamic multi-position runtime"
```

## Execution Order And Review Gates

| Gate | Tasks | Required proof before continuing |
| --- | --- | --- |
| Data authority | 1 | Empty baseline and exact seed tests pass |
| Pure domain | 2-3 | Snapshot, health, sizing, leverage, and liquidation tests pass |
| Immutable audit | 4-5 | Claim/Ticket/reservation/Incident round trips pass |
| Mutation identity | 6-8 | SET_LEVERAGE and ENTRY separation, unknown recovery, and preflight pass |
| Exposure safety | 9-11 | Post-fill recovery, atomic release, and runtime fence pass |
| Production contract | 12 | Seed, cutover, probe, and certification tests pass |
| End-to-end | 13 | Three-Ticket and scoped-failure certification passes |
| Local completion | 14 | Full pytest, Ruff, Mypy, schema, document, and diff checks pass |
| Production completion | 15 | One terminal natural Ticket and exact Tokyo evidence pass |

## Fix-Forward And Stop Conditions

- Tasks 1-14 are local implementation work. They do not authorize exchange mutation or Tokyo database changes.
- Task 15 uses the standing BRC-only deployment authorization but must stop before any write if account identity, position mode, margin mode, flatness, order ownership, runtime commit, schema, seed, writer uniqueness, or credential boundary is not exact.
- A failed local task is fixed forward on its focused commit sequence; no compatibility layer is introduced.
- A failed Tokyo precondition leaves workers stopped or new ENTRY disabled, preserves read-only evidence, and does not improvise a bypass writer.
- A SET_LEVERAGE or ENTRY unknown outcome blocks progression until exact external truth resolves that command.
- Existing exposure safety commands remain available only to the one certified exact writer; suspect writers never mutate the exchange.
