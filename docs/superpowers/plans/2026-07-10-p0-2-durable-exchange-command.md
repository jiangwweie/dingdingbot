# P0-2 Durable Exchange Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every ticket-bound exchange order command before dispatch, classify ambiguous network outcomes as unknown, reconcile by deterministic exchange identity, and prevent duplicate submit.

**Architecture:** `brc_ticket_bound_protected_submit_attempts` remains the aggregate attempt while normalized `brc_ticket_bound_exchange_commands` rows own current per-order command truth. The API commits prepared commands, marks each command dispatching in a short transaction, calls the gateway outside transactions, and commits a confirmed or unknown outcome. Unknown commands freeze the exact scope and are reconciled read-only before any later ticket can submit.

**Tech Stack:** Python 3.14-compatible code, Pydantic v2, `decimal.Decimal`, SQLAlchemy, Alembic migration 105, PostgreSQL/SQLite migration tests, pytest.

## Global Constraints

- No exchange call may occur inside a DB transaction.
- No runtime authority may depend on JSON/Markdown or aggregate submit-result JSON.
- `client_order_id` and request fingerprint are deterministic and immutable.
- Network error, timeout, incomplete response, or process interruption becomes `outcome_unknown`, never generic confirmed failure.
- An unknown command blocks new submit for the exact account, StrategyGroup, instrument, and side scope.
- No automatic resubmit after `reconciled_absent`; a new current ticket and official gates are required.
- No live-profile, sizing-default, credential, withdrawal, transfer, instrument, side, or capital-scope expansion.
- No-signal ticks create zero exchange-command rows and zero report files.
- Current runtime state remains PG-only.

---

### Task 1: Exchange Command Domain And Migration 105

**Files:**
- Create: `src/domain/ticket_bound_exchange_command.py`
- Create: `migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py`
- Create: `tests/unit/test_ticket_bound_exchange_command.py`
- Modify: `tests/unit/test_pg_migration_identifier_names.py`

**Interfaces:**
- Produces: `ExchangeCommandState`, `ExchangeCommandOutcomeClass`, `TicketBoundExchangeCommand`, `command_transition_blockers(current, target, outcome_class)`, and `deterministic_client_order_id(ticket_id, operation_submit_command_id, order_role, command_generation)`.
- Produces: PG table `brc_ticket_bound_exchange_commands` with one row per ticket/order role/generation.

- [ ] **Step 1: Write failing domain and migration tests**

```python
def test_network_timeout_transitions_dispatching_to_outcome_unknown():
    blockers = command_transition_blockers(
        current=ExchangeCommandState.DISPATCHING,
        target=ExchangeCommandState.OUTCOME_UNKNOWN,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
    )
    assert blockers == []


def test_confirmed_rejected_requires_authoritative_rejection():
    blockers = command_transition_blockers(
        current=ExchangeCommandState.DISPATCHING,
        target=ExchangeCommandState.CONFIRMED_REJECTED,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
    )
    assert "confirmed_rejected_requires_authoritative_rejection" in blockers


def test_client_order_id_is_stable_per_ticket_role_generation():
    first = deterministic_client_order_id("ticket-1", "submit-1", "ENTRY", 1)
    second = deterministic_client_order_id("ticket-1", "submit-1", "ENTRY", 1)
    assert first == second
    assert len(first) <= 36
```

Migration test creates foundation migrations through 104, applies 105, and asserts:

```python
columns = {column["name"] for column in inspector.get_columns("brc_ticket_bound_exchange_commands")}
assert {"exchange_command_id", "client_order_id", "exchange_instrument_id", "command_state", "request_fingerprint"} <= columns
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command.py tests/unit/test_pg_migration_identifier_names.py`

Expected: FAIL because the domain module and migration 105 do not exist and the migration head remains 104.

- [ ] **Step 3: Implement the domain model and migration**

The domain states are exactly:

```python
class ExchangeCommandState(str, Enum):
    PREPARED = "prepared"
    DISPATCHING = "dispatching"
    CONFIRMED_SUBMITTED = "confirmed_submitted"
    CONFIRMED_REJECTED = "confirmed_rejected"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILED_SUBMITTED = "reconciled_submitted"
    RECONCILED_ABSENT = "reconciled_absent"
    HARD_STOPPED = "hard_stopped"
```

Migration constraints enforce unique `client_order_id`, unique `(ticket_id, order_role, command_generation)`, positive amounts, immutable identity columns by application update discipline, valid state values, and `exchange_order_id` presence for confirmed/reconciled submitted states.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command.py tests/unit/test_pg_migration_identifier_names.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/ticket_bound_exchange_command.py migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py tests/unit/test_ticket_bound_exchange_command.py tests/unit/test_pg_migration_identifier_names.py
git commit -m "feat(runtime): add durable exchange command state"
```

### Task 2: Materialize Commands With Protected Submit Attempt

**Files:**
- Create: `src/application/action_time/exchange_command.py`
- Modify: `src/application/action_time/protected_submit_attempt.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `tests/unit/test_ticket_bound_protected_submit_attempt.py`
- Create: `tests/unit/test_ticket_bound_exchange_command_materialization.py`

**Interfaces:**
- Consumes: protected-submit `submit_request.orders` and the domain command model.
- Produces: `materialize_ticket_bound_exchange_commands(conn, attempt, now_ms) -> list[dict[str, Any]]`.
- Produces: `mark_exchange_command_dispatching(conn, exchange_command_id, now_ms) -> dict[str, Any]`.
- Produces: `record_exchange_command_outcome(conn, exchange_command_id, target_state, outcome_class, exchange_result, now_ms) -> dict[str, Any]`.

- [ ] **Step 1: Write failing materialization tests**

```python
def test_real_submit_prepare_commits_entry_sl_tp1_commands(pg_control_connection):
    ids = _create_handoff_ready(pg_control_connection)
    _materialize_real_submit_mode(pg_control_connection, ids)
    prepared = prepare_ticket_bound_protected_submit_attempt(
        pg_control_connection,
        ticket_id=ids["ticket_id"],
        operation_submit_command_id=ids["operation_submit_command_id"],
        submit_mode="real_gateway_action",
        now_ms=NOW_MS,
    )
    commands = _exchange_command_rows(pg_control_connection)
    assert prepared["status"] == "submit_prepared"
    assert [row["order_role"] for row in commands] == ["ENTRY", "SL", "TP1"]
    assert {row["command_state"] for row in commands} == {"prepared"}
    assert len({row["client_order_id"] for row in commands}) == 3
```

Add a negative test proving a repeated prepare reuses the same rows and cannot mutate the request fingerprint.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py -k 'exchange_command or submit_prepared'`

Expected: FAIL because prepare does not materialize normalized command rows.

- [ ] **Step 3: Implement command materialization**

For each request order, build typed numeric values and deterministic identity:

```python
command = TicketBoundExchangeCommand(
    exchange_command_id=stable_command_id(
        attempt["ticket_id"],
        order_request["order_role"],
        1,
    ),
    protected_submit_attempt_id=attempt["protected_submit_attempt_id"],
    ticket_id=attempt["ticket_id"],
    operation_submit_command_id=attempt["operation_submit_command_id"],
    account_id=submit_request["account_id"],
    strategy_group_id=attempt["strategy_group_id"],
    runtime_profile_id=attempt["runtime_profile_id"],
    order_role=order_request["order_role"],
    local_order_id=order_request["local_order_id"],
    client_order_id=deterministic_client_order_id(
        attempt["ticket_id"],
        attempt["operation_submit_command_id"],
        order_request["order_role"],
        1,
    ),
    command_generation=1,
    exchange_instrument_id=submit_request["exchange_symbol"],
    side=attempt["side"],
    request_fingerprint=command_request_fingerprint(order_request),
    command_state=ExchangeCommandState.PREPARED,
    gateway_order_type=order_request["gateway_order_type"],
    gateway_side=order_request["gateway_side"],
    amount=Decimal(str(order_request["amount"])),
    price=optional_decimal(order_request.get("price")),
    trigger_price=optional_decimal(order_request.get("trigger_price")),
    reduce_only=order_request["reduce_only"] is True,
    prepared_at_ms=now_ms,
    updated_at_ms=now_ms,
    authority_source_ref=attempt["authority_source_ref"],
)
```

`prepare_ticket_bound_protected_submit_attempt` persists the aggregate attempt first and then all commands in the same transaction. Existing rows must match exactly or the prepare becomes blocked.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py -k 'exchange_command or submit_prepared'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/application/action_time/exchange_command.py src/application/action_time/protected_submit_attempt.py src/infrastructure/runtime_control_state_repository.py tests/unit/test_ticket_bound_protected_submit_attempt.py tests/unit/test_ticket_bound_exchange_command_materialization.py
git commit -m "feat(runtime): persist ticket bound exchange commands"
```

### Task 3: Dispatch Outside Transactions And Classify Unknown Outcomes

**Files:**
- Modify: `src/interfaces/api_trading_console.py`
- Modify: `src/infrastructure/exchange_gateway.py`
- Modify: `tests/unit/test_ticket_bound_protected_submit_api.py`
- Modify: `tests/unit/test_ticket_bound_protected_submit_attempt.py`

**Interfaces:**
- Consumes: persisted prepared exchange commands.
- Produces: `_execute_one_ticket_bound_exchange_command(engine, command_id, gateway, order_lifecycle_service, now_ms)` that never receives an open DB connection.
- Produces: short transaction helpers around dispatch-state and result-state writes.

- [ ] **Step 1: Write failing API transaction and timeout tests**

```python
@pytest.mark.asyncio
async def test_network_timeout_records_outcome_unknown_without_retry(
    pg_control_engine,
    fake_gateway,
    fake_order_lifecycle_service,
):
    fake_gateway.place_order.side_effect = ConnectionLostError("timeout", "C-001")
    result = await _run_ticket_bound_protected_submit(
        ticket_id="ticket-1",
        operation_submit_command_id="submit-1",
        submit_mode="real_gateway_action",
    )
    commands = read_commands(pg_control_engine)
    assert result["status"] == "submit_outcome_unknown"
    assert commands[0]["command_state"] == "outcome_unknown"
    assert fake_gateway.place_order.await_count == 1


@pytest.mark.asyncio
async def test_gateway_call_has_no_open_command_transaction(
    pg_control_engine,
    fake_gateway,
    fake_order_lifecycle_service,
):
    gateway.place_order.side_effect = assert_no_checked_out_command_transaction
    await _execute_one_ticket_bound_exchange_command(
        pg_control_engine,
        "exchange-command-1",
        fake_gateway,
        fake_order_lifecycle_service,
        NOW_MS,
    )
```

Also test explicit invalid-order rejection becomes `confirmed_rejected` and a missing exchange order ID becomes `outcome_unknown`.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_ticket_bound_protected_submit_api.py -k 'outcome_unknown or transaction or confirmed_rejected'`

Expected: FAIL because the API compresses ambiguous gateway errors into `exchange_submit_failed` and does not persist per-command dispatch state.

- [ ] **Step 3: Implement the command executor**

Execution sequence per command:

```python
with engine.begin() as conn:
    command = mark_exchange_command_dispatching(conn, command_id, now_ms)

try:
    placement = await gateway.place_order(
        symbol=command.exchange_instrument_id,
        order_type=command.gateway_order_type,
        side=command.gateway_side,
        amount=command.amount,
        price=command.price,
        trigger_price=command.trigger_price,
        reduce_only=command.reduce_only,
        client_order_id=command.client_order_id,
    )
except (ConnectionLostError, TimeoutError, asyncio.TimeoutError) as exc:
    with engine.begin() as conn:
        record_exchange_command_outcome(
            conn,
            command_id,
            ExchangeCommandState.OUTCOME_UNKNOWN,
            ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
            sanitized_error(exc),
            now_ms,
        )
```

Explicit exchange validation/rejection maps to `confirmed_rejected`; any ambiguous exception or incomplete success response maps to `outcome_unknown`. Aggregate submit state is derived from command rows and never overwrites unknown with generic failure.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/unit/test_ticket_bound_protected_submit_api.py tests/unit/test_ticket_bound_protected_submit_attempt.py -k 'outcome_unknown or transaction or confirmed_rejected or submitted'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/interfaces/api_trading_console.py src/infrastructure/exchange_gateway.py tests/unit/test_ticket_bound_protected_submit_api.py tests/unit/test_ticket_bound_protected_submit_attempt.py
git commit -m "fix(runtime): persist ambiguous exchange outcomes"
```

### Task 4: Unknown-Outcome Reconciliation And Scope Freeze

**Files:**
- Create: `src/application/action_time/exchange_command_reconciliation.py`
- Modify: `src/application/action_time/capital_safety_guard.py`
- Modify: `src/application/action_time/lifecycle_maintenance_service.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Create: `tests/unit/test_ticket_bound_exchange_command_reconciliation.py`
- Modify: `tests/unit/test_capital_safety_scope_freeze_gate.py`

**Interfaces:**
- Produces: `reconcile_unknown_exchange_commands(conn, gateway, now_ms, max_commands) -> dict[str, Any]`.
- Produces: exact-scope blocker `exchange_command_outcome_unknown` consumed by `current_scope_blockers(control_state, strategy_group_id, symbol, side)`.

- [ ] **Step 1: Write failing reconciliation tests**

```python
@pytest.mark.asyncio
async def test_unknown_command_reconciles_submitted_by_client_order_id(
    pg_control_connection,
    fake_gateway,
):
    gateway.find_order_by_client_id.return_value = exchange_order("123")
    report = await reconcile_unknown_exchange_commands(
        pg_control_connection,
        fake_gateway,
        now_ms=NOW_MS,
        max_commands=10,
    )
    assert report["reconciled_submitted"] == 1
    assert command_row()["command_state"] == "reconciled_submitted"


def test_unknown_command_freezes_exact_scope_only(control_state_with_unknown_command):
    control_state = control_state_with_unknown_command
    blockers = current_scope_blockers(
        control_state,
        strategy_group_id="SOR-001",
        symbol="ETHUSDT",
        side="long",
    )
    assert "exchange_command_outcome_unknown" in blockers
    assert current_scope_blockers(control_state, strategy_group_id="MPG-001", symbol="OPUSDT", side="long") == []
```

Add tests for reconciled absence after the bounded window, contradictory evidence hard stop, and no automatic resubmit.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command_reconciliation.py tests/unit/test_capital_safety_scope_freeze_gate.py -k exchange_command`

Expected: FAIL because unknown commands are not queried or included in scope blockers.

- [ ] **Step 3: Implement bounded read-only reconciliation**

Use the persisted `exchange_instrument_id`, `exchange_order_id`, and `client_order_id`. Reconciliation calls exchange read methods only and records one allowed transition. It never cancels, adopts, or resubmits an unknown order. The lifecycle maintenance runner invokes this only when unresolved commands exist and enforces existing timeout bounds.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest -q tests/unit/test_ticket_bound_exchange_command_reconciliation.py tests/unit/test_capital_safety_scope_freeze_gate.py tests/unit/test_ticket_bound_lifecycle_maintenance_service.py -k 'exchange_command or scope_freeze'`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/application/action_time/exchange_command_reconciliation.py src/application/action_time/capital_safety_guard.py src/application/action_time/lifecycle_maintenance_service.py scripts/run_ticket_bound_lifecycle_maintenance_once.py tests/unit/test_ticket_bound_exchange_command_reconciliation.py tests/unit/test_capital_safety_scope_freeze_gate.py
git commit -m "fix(runtime): reconcile unknown exchange commands"
```

### Task 5: Tokyo Monitor Coverage And P0-2 Verification

**Files:**
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Modify: `tests/unit/test_tokyo_runtime_server_monitor.py`
- Modify: `scripts/validate_current_projection_ownership.py`

**Interfaces:**
- Consumes: PG exchange-command rows.
- Produces: quiet `processing` for fresh dispatch work and notify/needs-intervention for overdue unknown or hard-stopped commands.

- [ ] **Step 1: Write failing monitor tests**

```python
def test_recent_dispatching_command_is_processing_quiet(pg_control_state):
    pg_control_state["ticket_bound_exchange_commands"] = [
        exchange_command_row(command_state="dispatching", updated_at_ms=NOW_MS - 1_000)
    ]
    artifact = _recent_pg_chain_event(pg_control_state)
    assert artifact["decision"]["status"] == "processing"
    assert artifact["decision"]["notify"] is False


def test_overdue_unknown_command_notifies_owner(pg_control_state):
    pg_control_state["ticket_bound_exchange_commands"] = [
        exchange_command_row(command_state="outcome_unknown", updated_at_ms=NOW_MS - 120_000)
    ]
    artifact = _recent_pg_chain_event(pg_control_state)
    assert artifact["decision"]["status"] == "needs_intervention"
    assert artifact["decision"]["notify"] is True
```

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/unit/test_tokyo_runtime_server_monitor.py -k exchange_command`

Expected: FAIL because monitor does not inspect durable command state.

- [ ] **Step 3: Implement monitor classification and run bounded verification**

Run:

```bash
pytest -q tests/unit/test_ticket_bound_exchange_command.py tests/unit/test_ticket_bound_exchange_command_materialization.py tests/unit/test_ticket_bound_protected_submit_attempt.py tests/unit/test_ticket_bound_protected_submit_api.py tests/unit/test_ticket_bound_exchange_command_reconciliation.py tests/unit/test_capital_safety_scope_freeze_gate.py tests/unit/test_ticket_bound_lifecycle_maintenance_service.py tests/unit/test_tokyo_runtime_server_monitor.py
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 -m compileall -q src scripts migrations/versions
```

Expected: all tests pass, `suspicious_runtime_file_authority=0`, `frequent_report_write=0`, output scope valid, and compile exits 0.

- [ ] **Step 4: Stop condition**

P0-2 stops when every persisted command is confirmed, reconciled, or hard-stopped; no unknown outcome can create a duplicate submit; and the existing Tokyo monitor exposes overdue unknown state without adding report files.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_tokyo_runtime_server_monitor.py tests/unit/test_tokyo_runtime_server_monitor.py scripts/validate_current_projection_ownership.py
git commit -m "feat(monitor): surface exchange command outcomes"
```
