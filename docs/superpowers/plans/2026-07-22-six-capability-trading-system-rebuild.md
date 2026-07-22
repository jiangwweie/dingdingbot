# Six-Capability Trading System Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the six registered StrategyGroup Event capabilities into the single `src/trading_kernel/**` production chain, certify the complete input-to-review lifecycle locally, and stop before Tokyo deployment for Owner confirmation.

**Architecture:** Closed market snapshots feed six pure deterministic detectors that emit immutable `StrategySignal` records and exact fact lineage. A bounded candidate selector chooses one fresh signal, action-time facts produce an immutable `CapacityClaim`, and the existing globally serialized Ticket issuer atomically creates the Ticket, budget reservation, Netting Domain hold, lifecycle aggregate, and durable ENTRY command. Venue truth, exit policy, protection, reconciliation, settlement, and Owner projection remain one kernel authority with no compatibility path.

**Tech Stack:** Python 3.11+, Pydantic v2 frozen models, `decimal.Decimal`, SQLAlchemy 2, PostgreSQL/Alembic, pytest, Ruff, Mypy, CCXT-compatible Binance USD-M adapter.

## Global Constraints

- Production execution code belongs only under `src/trading_kernel/**`.
- One Exposure Episode owns exactly one immutable Ticket.
- Adding to an existing position is forbidden.
- One Ticket has one ENTRY command generation.
- New ENTRY admission is globally serialized; protected Ticket lifecycle work is concurrent.
- Long and short are independent Netting Domains.
- Strategy detection cannot assign quantity, notional, leverage, account budget, or exchange-write authority.
- Authoritative ENTRY rejection is terminal and is not retried.
- Unknown venue outcome is never blindly resent.
- Partial ENTRY fill is an incident: cancel the exact remainder, confirm cancellation, flatten the filled quantity, then release the lane.
- PostgreSQL is the only runtime authority; no JSON/Markdown runtime input or recurring report output is allowed.
- No dual writes, compatibility readers, retired tables, retired imports, or old-runtime fallback.
- No Tokyo mutation or exchange write occurs during Tasks 1-8.
- Tokyo deployment remains blocked after Task 9 until explicit Owner confirmation.

---

### Task 1: Freeze the six registered Event contracts and deterministic seed

**Files:**
- Create: `src/trading_kernel/domain/strategy_registry.py`
- Create: `src/trading_kernel/infrastructure/strategy_registry_seed.py`
- Create: `scripts/trading_kernel/seed_strategy_registry.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/unit/test_strategy_registry.py`
- Test: `tests/trading_kernel/integration/test_strategy_registry_seed.py`

**Interfaces:**
- Produces: `registered_strategy_contracts() -> tuple[RegisteredStrategyContract, ...]`
- Produces: `seed_strategy_registry(uow, *, seeded_at_ms: int) -> RegistrySeedResult`
- Produces exactly six Event contracts: `CPM-LONG`, `MPG-LONG`, `MI-LONG`, `SOR-LONG`, `SOR-SHORT`, `BRF2-SHORT`.

- [x] **Step 1: Write the failing registry contract test**

```python
def test_registry_contains_only_the_six_owner_accepted_events() -> None:
    contracts = registered_strategy_contracts()

    assert {(item.strategy_group_id, item.event_id, item.position_side) for item in contracts} == {
        ("CPM-RO-001", "CPM-LONG", "long"),
        ("MPG-001", "MPG-LONG", "long"),
        ("MI-001", "MI-LONG", "long"),
        ("SOR-001", "SOR-LONG", "long"),
        ("SOR-001", "SOR-SHORT", "short"),
        ("BRF2-001", "BRF2-SHORT", "short"),
    }
```

- [x] **Step 2: Run the unit test and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_strategy_registry.py`

Expected: collection fails because `src.trading_kernel.domain.strategy_registry` does not exist.

- [x] **Step 3: Implement frozen registry models and exact accepted semantics**

```python
class RegisteredStrategyContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    event_id: str
    position_side: Literal["long", "short"]
    timeframe: Literal["15m", "1h"]
    candidate_instruments: tuple[str, ...]
    required_facts: tuple[RegisteredFactRequirement, ...]
    disable_facts: tuple[RegisteredFactRequirement, ...] = ()
    entry_order_type: EntryOrderType = EntryOrderType.MARKET
    exit_policy_id: str
    priority_by_instrument: tuple[InstrumentPriority, ...]
```

Populate identities, timeframes, fact keys, directions, candidate instruments, and priority ranks from the committed pre-deletion sources at `d570018a^`; do not read the strategy research repository.

- [x] **Step 4: Run the unit test and verify GREEN**

Run: `pytest -q tests/trading_kernel/unit/test_strategy_registry.py`

Expected: all registry contract tests pass.

- [x] **Step 5: Write the failing PostgreSQL seed test**

```python
async def test_strategy_seed_is_exact_and_idempotent(pg_uow) -> None:
    first = await seed_strategy_registry(pg_uow, seeded_at_ms=1_800_000_000_000)
    second = await seed_strategy_registry(pg_uow, seeded_at_ms=1_800_000_000_001)

    assert first.inserted_event_count == 6
    assert second.inserted_event_count == 0
    assert await pg_uow.strategy_registry.list_current_event_ids() == (
        "CPM-LONG",
        "MPG-LONG",
        "MI-LONG",
        "SOR-LONG",
        "SOR-SHORT",
        "BRF2-SHORT",
    )
```

- [x] **Step 6: Run the integration test and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_strategy_registry_seed.py`

Expected: failure because the seed service and repository port do not exist.

- [x] **Step 7: Implement one idempotent PG seed transaction**

The service inserts exact registry rows, fact requirements, exit-policy bindings, runtime scopes, and candidate priorities. Existing rows must either match the canonical semantic hash exactly or fail with `RegistrySeedConflict`; silent updates are forbidden.

- [x] **Step 8: Run focused registry and schema tests**

Run: `pytest -q tests/trading_kernel/unit/test_strategy_registry.py tests/trading_kernel/integration/test_strategy_registry_seed.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/trading_kernel/domain/strategy_registry.py src/trading_kernel/infrastructure/strategy_registry_seed.py scripts/trading_kernel/seed_strategy_registry.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/application/ports.py migrations/trading_kernel/versions/0001_initial.py tests/trading_kernel/unit/test_strategy_registry.py tests/trading_kernel/integration/test_strategy_registry_seed.py
git commit -m "feat(kernel): seed six registered strategy events"
```

---

### Task 2: Replace capital-bearing ActionableSignal with immutable StrategySignal and fact lineage

**Files:**
- Replace: `src/trading_kernel/domain/signal.py`
- Modify: `src/trading_kernel/application/ingest_signal.py`
- Modify: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/unit/test_signal.py`
- Test: `tests/trading_kernel/integration/test_signal_to_ticket.py`

**Interfaces:**
- Replaces: `ActionableSignal` and `SignalTicketTerms`.
- Produces: `StrategySignal` with identity, occurrence, expiry, and exact immutable fact snapshots only.
- Produces: `brc_signal_fact_snapshots` append-only rows keyed by `signal_event_id + fact_definition_id`.

- [ ] **Step 1: Write failing tests proving strategy signals cannot assign capital**

```python
def test_strategy_signal_rejects_ticket_terms() -> None:
    with pytest.raises(ValidationError):
        StrategySignal.model_validate({**valid_signal_payload(), "quantity": "1"})


def test_signal_digest_covers_the_exact_immutable_fact_bundle() -> None:
    signal = StrategySignal.model_validate(valid_signal_payload())
    assert signal.fact_digest == build_signal_fact_digest(signal.facts)
```

- [ ] **Step 2: Run the unit test and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_signal.py`

Expected: failure because `StrategySignal` does not exist and current signals require `SignalTicketTerms`.

- [ ] **Step 3: Implement the narrow signal model**

```python
class StrategySignal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_event_id: str
    runtime_scope_id: str
    runtime_scope_version: int
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]
    occurred_at_ms: int
    expires_at_ms: int
    facts: tuple[SignalFactSnapshot, ...]
    fact_digest: str
```

The model validator requires a unique fact definition set and an exact digest match. Quantity, notional, leverage, entry price, stop price, and take-profit terms are forbidden extras.

- [ ] **Step 4: Run the unit test and verify GREEN**

Run: `pytest -q tests/trading_kernel/unit/test_signal.py`

Expected: all signal model tests pass.

- [ ] **Step 5: Write failing integration tests for immutable fact persistence**

```python
async def test_ingest_persists_signal_and_fact_lineage_without_ticket_terms(pg_uow) -> None:
    result = await ingest_signal(pg_uow, valid_ingest_request())

    assert result.status is IngestSignalStatus.CANDIDATE_READY
    stored = await pg_uow.signals.get(valid_signal().signal_event_id)
    assert stored == valid_signal()
    assert await pg_uow.signals.get_fact_snapshots(stored.signal_event_id) == stored.facts
```

- [ ] **Step 6: Run the integration test and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_signal_to_ticket.py`

Expected: failure because current persistence columns and issuer still read signal ticket terms.

- [ ] **Step 7: Change persistence and ingestion semantics**

Remove financial columns from `brc_signal_events`; add `brc_signal_fact_snapshots`; rename readiness state from `ticket_ready` to `candidate_ready`; keep duplicate signal identity idempotent. Ticket issuance must temporarily return `CAPACITY_CLAIM_MISSING` until Task 5 provides the claim.

- [ ] **Step 8: Run focused tests**

Run: `pytest -q tests/trading_kernel/unit/test_signal.py tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_schema_baseline.py`

Expected: all updated tests pass and no signal producer can assign capital.

- [ ] **Step 9: Commit**

```bash
git add src/trading_kernel/domain/signal.py src/trading_kernel/application/ingest_signal.py src/trading_kernel/application/issue_ready_signal.py src/trading_kernel/infrastructure/pg_signal_repository.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py tests/trading_kernel/unit/test_signal.py tests/trading_kernel/integration/test_signal_to_ticket.py
git commit -m "refactor(kernel): separate strategy signals from ticket capital"
```

---

### Task 3: Extract six pure deterministic Event detectors

**Files:**
- Create: `src/trading_kernel/domain/market.py`
- Create: `src/trading_kernel/domain/detector.py`
- Create: `src/trading_kernel/domain/detectors/cpm.py`
- Create: `src/trading_kernel/domain/detectors/mpg.py`
- Create: `src/trading_kernel/domain/detectors/mi.py`
- Create: `src/trading_kernel/domain/detectors/sor.py`
- Create: `src/trading_kernel/domain/detectors/brf2.py`
- Create: `src/trading_kernel/domain/detectors/__init__.py`
- Test: `tests/trading_kernel/unit/detectors/test_registered_detectors.py`
- Test: `tests/trading_kernel/unit/detectors/test_detector_negative_matrix.py`

**Interfaces:**
- Consumes: `RegisteredStrategyContract`, `MarketSnapshot`.
- Produces: `DetectorResult` containing exact computed facts and optional occurrence time.
- Produces: `detector_for(event_spec_id: str) -> StrategyDetector`.

- [ ] **Step 1: Write failing detector routing and purity tests**

```python
@pytest.mark.parametrize("event_id", [
    "CPM-LONG", "MPG-LONG", "MI-LONG", "SOR-LONG", "SOR-SHORT", "BRF2-SHORT",
])
def test_every_registered_event_has_one_detector(event_id: str) -> None:
    contract = contract_by_event_id(event_id)
    assert detector_for(contract.event_spec_id).event_spec_id == contract.event_spec_id


def test_detector_returns_equal_results_for_equal_snapshots() -> None:
    detector = detector_for(contract_by_event_id("SOR-LONG").event_spec_id)
    snapshot = opening_range_breakout_snapshot()
    assert detector.evaluate(snapshot) == detector.evaluate(snapshot)
```

- [ ] **Step 2: Run detector tests and verify RED**

Run: `pytest -q tests/trading_kernel/unit/detectors`

Expected: collection fails because the market and detector modules do not exist.

- [ ] **Step 3: Implement immutable market inputs and detector protocol**

```python
class ClosedCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class StrategyDetector(Protocol):
    event_spec_id: str
    def evaluate(self, snapshot: MarketSnapshot) -> DetectorResult: ...
```

- [ ] **Step 4: Port evaluator behavior from committed old production sources**

Port only pure calculations from:

```text
d570018a^:src/domain/cpm_historical_evaluator.py
d570018a^:src/domain/mpg_momentum_persistence_evaluator.py
d570018a^:src/application/runtime_strategy_signal_evaluation_service.py
d570018a^:src/domain/sor_session_range_evaluator.py
d570018a^:src/domain/brf_price_action_evaluator.py
```

Do not port packet, DB, artifact, readiness, invocation, or exchange dependencies.

- [ ] **Step 5: Add negative tests for missing, stale, insufficient, and disable facts**

```python
def test_brf2_strong_uptrend_disable_prevents_short_signal() -> None:
    result = detector_for(brf2_event_spec_id()).evaluate(brf2_strong_uptrend_snapshot())
    assert result.triggered is False
    assert result.facts_by_name["strong_uptrend_disable"].satisfied is True
```

- [ ] **Step 6: Run detector tests and verify GREEN**

Run: `pytest -q tests/trading_kernel/unit/detectors`

Expected: all six positive vectors and the full negative matrix pass.

- [ ] **Step 7: Commit**

```bash
git add src/trading_kernel/domain/market.py src/trading_kernel/domain/detector.py src/trading_kernel/domain/detectors tests/trading_kernel/unit/detectors
git commit -m "feat(kernel): add six pure strategy event detectors"
```

---

### Task 4: Build event-time observation and Live/Replay-identical signal production

**Files:**
- Create: `src/trading_kernel/application/observe_strategy_scope.py`
- Create: `src/trading_kernel/application/produce_strategy_signal.py`
- Create: `src/trading_kernel/application/market_ports.py`
- Create: `src/trading_kernel/infrastructure/binance_public_market_source.py`
- Create: `src/trading_kernel/interfaces/observation_worker.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/integration/test_observation_to_signal.py`
- Test: `tests/trading_kernel/integration/test_live_replay_detector_parity.py`

**Interfaces:**
- Produces: `observe_strategy_scope(uow, market_source, request) -> ObservationResult`.
- Produces: stable signal identity from Event Spec, instrument, side, occurrence time, and fact digest.
- Live and replay call the same detector function with the same `MarketSnapshot` type.

- [ ] **Step 1: Write failing closed-candle and no-signal cadence tests**

```python
async def test_observer_ignores_open_candle_and_creates_no_signal(pg_uow, market_source) -> None:
    market_source.return_snapshot(snapshot_with_open_tail_candle())
    result = await observe_strategy_scope(pg_uow, market_source, request_for("SOR-LONG"))

    assert result.signal_event_id is None
    assert await pg_uow.signals.count() == 0
```

- [ ] **Step 2: Run observation tests and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_observation_to_signal.py`

Expected: failure because no observation service or market source port exists.

- [ ] **Step 3: Implement bounded observation**

Fetch only required 15m/1h/4h closed candles, compute a `MarketSnapshot`, evaluate exactly one scope, upsert changed current facts, and append a signal plus fact snapshots only when triggered. A no-signal evaluation writes no files and appends no signal history.

- [ ] **Step 4: Write failing Live/Replay parity test**

```python
def test_live_and_replay_use_the_same_detector_result() -> None:
    snapshot = cpm_reclaim_snapshot()
    assert evaluate_live_snapshot(cpm_contract(), snapshot) == evaluate_replay_snapshot(cpm_contract(), snapshot)
```

- [ ] **Step 5: Run parity test and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_live_replay_detector_parity.py`

Expected: failure because the shared evaluation boundary is missing.

- [ ] **Step 6: Implement one shared evaluation boundary and worker cadence**

The worker schedules by closed-bar event time, not a two-second heavy recomputation loop. Network calls have explicit timeout seconds. Current fact rows are bounded upserts; signal and fact-history rows grow only on actual signals.

- [ ] **Step 7: Run focused observation tests**

Run: `pytest -q tests/trading_kernel/unit/detectors tests/trading_kernel/integration/test_observation_to_signal.py tests/trading_kernel/integration/test_live_replay_detector_parity.py`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/trading_kernel/application/observe_strategy_scope.py src/trading_kernel/application/produce_strategy_signal.py src/trading_kernel/application/market_ports.py src/trading_kernel/infrastructure/binance_public_market_source.py src/trading_kernel/interfaces/observation_worker.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py migrations/trading_kernel/versions/0001_initial.py tests/trading_kernel/integration/test_observation_to_signal.py tests/trading_kernel/integration/test_live_replay_detector_parity.py
git commit -m "feat(kernel): produce live strategy signals from closed market data"
```

---

### Task 5: Add deterministic candidate arbitration, action-time facts, and immutable CapacityClaim

**Files:**
- Create: `src/trading_kernel/domain/arbitration.py`
- Create: `src/trading_kernel/domain/capacity.py`
- Create: `src/trading_kernel/application/select_entry_candidate.py`
- Create: `src/trading_kernel/application/build_capacity_claim.py`
- Modify: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/unit/test_arbitration.py`
- Test: `tests/trading_kernel/unit/test_capacity.py`
- Test: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`

**Interfaces:**
- Produces: `rank_candidates(candidates) -> tuple[CandidateRank, ...]`.
- Produces: `build_capacity_claim(policy, action_facts, signal_facts) -> CapacityClaimDecision`.
- Produces: immutable `brc_capacity_claims` rows and atomic Claim-to-Ticket issuance.

- [ ] **Step 1: Write failing deterministic arbitration tests**

```python
def test_arbitration_orders_priority_then_event_time_then_identity() -> None:
    ranked = rank_candidates(candidate_matrix())
    assert [item.signal_event_id for item in ranked] == ["signal:b", "signal:a", "signal:c"]
```

- [ ] **Step 2: Run arbitration test and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_arbitration.py`

Expected: failure because the new arbitration module does not exist.

- [ ] **Step 3: Implement the accepted ordering and bounded batch size**

Use Owner Policy Priority, Candidate Scope Priority, Event Time, Observed Time, and Signal Event ID. Accept at most 64 fresh candidates per selector call.

- [ ] **Step 4: Write failing CapacityClaim tests**

```python
def test_capacity_claim_computes_quantity_from_stop_risk_and_instrument_steps() -> None:
    decision = build_capacity_claim(policy(), action_facts(), signal_facts())
    assert decision.status is CapacityClaimStatus.CLAIMED
    assert decision.claim.quantity % action_facts().quantity_step == 0
    assert decision.claim.risk_at_stop <= policy().max_ticket_open_risk
```

- [ ] **Step 5: Run Capacity tests and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_capacity.py`

Expected: failure because CapacityClaim and action-time models do not exist.

- [ ] **Step 6: Implement action-time pricing and capacity mathematics**

Use fresh bid/ask, account balance, margin, open positions, current reservations, quantity step, price tick, minimum quantity, minimum notional, strategy stop reference, Owner capacity limits, and Netting Domain occupancy. All arithmetic uses `Decimal`. The claim contains a canonical SHA-256 decision digest.

- [ ] **Step 7: Write failing atomic Claim-to-Ticket integration test**

```python
async def test_claim_ticket_budget_domain_and_entry_command_commit_atomically(pg_uow) -> None:
    result = await issue_ready_signal(pg_uow, issue_request())
    assert result.status is IssueTicketStatus.ISSUED
    assert await pg_uow.capacity_claims.get_for_ticket(result.ticket_id) is not None
    assert await pg_uow.commands.get_entry_for_ticket(result.ticket_id) is not None
```

- [ ] **Step 8: Run integration test and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`

Expected: failure because the issuer does not yet build or persist Capacity Claims.

- [ ] **Step 9: Implement one atomic issuance transaction**

Revalidate signal expiry, scope, account mode, instrument rules, capacity, same-domain occupancy, and schema identity inside the global ENTRY lane transaction. Persist Capacity Claim, Ticket, budget reservation, active Netting Domain key, aggregate, creation event, and durable ENTRY command together.

- [ ] **Step 10: Run focused tests**

Run: `pytest -q tests/trading_kernel/unit/test_arbitration.py tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_issue_ticket.py`

Expected: all tests pass.

- [ ] **Step 11: Commit**

```bash
git add src/trading_kernel/domain/arbitration.py src/trading_kernel/domain/capacity.py src/trading_kernel/application/select_entry_candidate.py src/trading_kernel/application/build_capacity_claim.py src/trading_kernel/application/issue_ready_signal.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_repositories.py migrations/trading_kernel/versions/0001_initial.py tests/trading_kernel/unit/test_arbitration.py tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/integration/test_capacity_claim_to_ticket.py
git commit -m "feat(kernel): issue tickets from deterministic capacity claims"
```

---

### Task 6: Resolve unknown venue outcomes through one VenueTruthPort

**Files:**
- Create: `src/trading_kernel/application/recover_unknown_command.py`
- Create: `src/trading_kernel/domain/venue_truth.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/dispatch_exchange_command.py`
- Modify: `src/trading_kernel/infrastructure/venue_adapter.py`
- Modify: `src/trading_kernel/application/runtime.py`
- Test: `tests/trading_kernel/unit/test_unknown_command_recovery.py`
- Test: `tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

**Interfaces:**
- Extends venue access with `find_order_by_client_id`, position snapshot, fills, regular open orders, and conditional open orders.
- Produces: `recover_unknown_command(uow, venue, request) -> UnknownRecoveryResult`.

- [ ] **Step 1: Write failing decision tests**

```python
def test_visible_matching_order_resolves_unknown_as_submitted() -> None:
    result = decide_unknown_recovery(command(), matching_order_truth())
    assert result.status is UnknownRecoveryStatus.RECONCILED_SUBMITTED


def test_identity_contradiction_opens_hard_incident() -> None:
    result = decide_unknown_recovery(command(), contradictory_order_truth())
    assert result.status is UnknownRecoveryStatus.IDENTITY_CONTRADICTION
```

- [ ] **Step 2: Run unit tests and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_unknown_command_recovery.py`

Expected: failure because venue-truth models and recovery decisions do not exist.

- [ ] **Step 3: Implement pure lookup decisions**

States are `pending_visibility`, `reconciled_submitted`, `reconciled_absent`, `identity_contradiction`, and `lookup_failed`. `reconciled_absent` never authorizes a second ENTRY generation.

- [ ] **Step 4: Write failing integration tests for visibility and restart**

```python
async def test_unknown_entry_survives_restart_and_is_never_redispatched(pg_uow, venue) -> None:
    await persist_unknown_entry(pg_uow)
    venue.return_no_match()
    result = await recover_unknown_command(pg_uow, venue, recovery_request())
    assert result.status is UnknownRecoveryStatus.PENDING_VISIBILITY
    assert venue.create_order_calls == 0
```

- [ ] **Step 5: Run integration test and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py`

Expected: failure because the current runtime records unknown outcomes but cannot resolve them through venue lookup.

- [ ] **Step 6: Implement the VenueTruthPort and runtime recovery selector**

All venue calls are timeout-bounded and occur outside DB transactions. Identity contradiction creates a runtime incident and hard stop. A proven submitted ENTRY proceeds to protection recovery; a proven absent authoritative outcome closes pre-exposure terminally without retry.

- [ ] **Step 7: Run focused command and recovery tests**

Run: `pytest -q tests/trading_kernel/unit/test_unknown_command_recovery.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py tests/trading_kernel/integration/test_command_dispatch.py`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/trading_kernel/application/recover_unknown_command.py src/trading_kernel/domain/venue_truth.py src/trading_kernel/application/ports.py src/trading_kernel/application/dispatch_exchange_command.py src/trading_kernel/infrastructure/venue_adapter.py src/trading_kernel/application/runtime.py tests/trading_kernel/unit/test_unknown_command_recovery.py tests/trading_kernel/integration/test_unknown_outcome_reconciliation.py
git commit -m "feat(kernel): reconcile unknown exchange command outcomes"
```

---

### Task 7: Add versioned exit policies and concurrent protected lifecycle maintenance

**Files:**
- Create: `src/trading_kernel/domain/exit_policy.py`
- Create: `src/trading_kernel/application/maintain_ticket_lifecycle.py`
- Modify: `src/trading_kernel/domain/reducer.py`
- Modify: `src/trading_kernel/domain/events.py`
- Modify: `src/trading_kernel/domain/effects.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `migrations/trading_kernel/versions/0001_initial.py`
- Test: `tests/trading_kernel/unit/test_exit_policy.py`
- Test: `tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py`

**Interfaces:**
- Produces six exact versioned Exit Policy bindings.
- Produces lifecycle decisions for Initial Stop, TP1, break-even floor, runner replacement, final exit, orphan cleanup, and terminal flatness.

- [ ] **Step 1: Write failing policy contract tests**

```python
@pytest.mark.parametrize("event_id", [
    "CPM-LONG", "MPG-LONG", "MI-LONG", "SOR-LONG", "SOR-SHORT", "BRF2-SHORT",
])
def test_each_registered_event_has_one_current_exit_policy(event_id: str) -> None:
    policy = exit_policy_for(contract_by_event_id(event_id).event_spec_id)
    assert policy.tp1.reward_multiple == Decimal("1")
    assert policy.tp1.quantity_fraction == Decimal("0.5")
    assert policy.runner.kind is RunnerKind.STRUCTURAL_ATR
```

- [ ] **Step 2: Run policy tests and verify RED**

Run: `pytest -q tests/trading_kernel/unit/test_exit_policy.py`

Expected: failure because no exit-policy domain exists in the rebuilt kernel.

- [ ] **Step 3: Implement the accepted policy family**

SOR-LONG retains its exact committed policy: 1R TP1 at 50%, cost-adjusted break-even floor, 15m structural ATR runner, ATR period 14, structure window 4, buffer 0.5 ATR, two-tick minimum improvement, and 96-bar time stop. The other five use the accepted 1R/50% plus structural ATR runner family on their registered timeframe and registered structural invalidation fact; no unregistered time stop is invented.

- [ ] **Step 4: Write failing lifecycle branch tests**

```python
def test_tp1_fill_replaces_full_stop_with_runner_quantity() -> None:
    next_state, effects = reduce_ticket(active_ticket_state(), tp1_filled_event())
    assert next_state.position_qty == Decimal("0.5")
    assert any(effect.kind is EffectKind.REPLACE_RUNNER_STOP for effect in effects)
```

- [ ] **Step 5: Run lifecycle tests and verify RED**

Run: `pytest -q tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py`

Expected: failure because the current reducer does not bind all six strategy exit policies.

- [ ] **Step 6: Implement concurrent lifecycle maintenance**

Lifecycle workers claim exact active Tickets independently; they never hold the global ENTRY lane. Stop/TP/runner cancel-replace uses durable commands and exact lineage. Position-flat with live protection creates cleanup commands before settlement completes.

- [ ] **Step 7: Run focused lifecycle tests**

Run: `pytest -q tests/trading_kernel/unit/test_exit_policy.py tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py tests/trading_kernel/full_chain/test_ticket_lifecycle.py tests/trading_kernel/full_chain/test_fault_matrix.py`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/trading_kernel/domain/exit_policy.py src/trading_kernel/application/maintain_ticket_lifecycle.py src/trading_kernel/domain/reducer.py src/trading_kernel/domain/events.py src/trading_kernel/domain/effects.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_repositories.py migrations/trading_kernel/versions/0001_initial.py tests/trading_kernel/unit/test_exit_policy.py tests/trading_kernel/full_chain/test_registered_strategy_exit_matrix.py
git commit -m "feat(kernel): bind six strategy exit policies to ticket lifecycle"
```

---

### Task 8: Split global runtime workers and produce one Owner supervision projection

**Files:**
- Create: `src/trading_kernel/application/project_owner_state.py`
- Create: `src/trading_kernel/interfaces/reconciliation_worker.py`
- Create: `src/trading_kernel/interfaces/lifecycle_worker.py`
- Modify: `src/trading_kernel/interfaces/observation_worker.py`
- Modify: `src/trading_kernel/interfaces/worker.py`
- Modify: `src/trading_kernel/interfaces/readonly_api.py`
- Modify: `src/trading_kernel/application/runtime.py`
- Test: `tests/trading_kernel/integration/test_global_runtime_workers.py`
- Test: `tests/trading_kernel/integration/test_owner_projection.py`

**Interfaces:**
- Observation Worker owns market snapshots, facts, and signals.
- Entry Worker owns arbitration, Capacity Claim, Ticket issuance, and command dispatch.
- Lifecycle Worker owns protection and exit progression for active Tickets.
- Reconciliation Worker owns venue truth, unknown outcomes, settlement, and review closure.
- Owner projection returns only documented product states.

- [ ] **Step 1: Write failing ownership tests**

```python
def test_each_runtime_transition_has_one_worker_owner() -> None:
    assert worker_ownership_map() == {
        "observation": "observation_worker",
        "entry": "entry_worker",
        "lifecycle": "lifecycle_worker",
        "reconciliation": "reconciliation_worker",
    }
```

- [ ] **Step 2: Run runtime tests and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_global_runtime_workers.py`

Expected: failure because the current worker combines multiple selectors and the new workers do not exist.

- [ ] **Step 3: Implement bounded independent worker selectors**

Each tick claims at most one bounded unit of work, uses exact indexed selectors, and records state only when it changes. External calls are timeout-bounded. A no-signal observation tick creates zero files and no append-only event row.

- [ ] **Step 4: Write failing Owner projection tests**

```python
@pytest.mark.parametrize((fixture_name, expected), [
    ("healthy_no_signal", "waiting_for_opportunity"),
    ("signal_or_ticket_active", "processing"),
    ("unknown_outcome", "needs_intervention"),
    ("observation_down", "temporarily_unavailable"),
    ("terminal_reviewed", "completed"),
])
def test_owner_projection_uses_product_states(fixture_name: str, expected: str) -> None:
    assert project_owner_state(owner_projection_fixture(fixture_name)).state == expected
```

- [ ] **Step 5: Run projection tests and verify RED**

Run: `pytest -q tests/trading_kernel/integration/test_owner_projection.py`

Expected: failure because current projection does not include strategy observation and candidate state.

- [ ] **Step 6: Implement one current Owner projection**

Internal blocker identities remain diagnostic fields; the primary state is one of `not_enabled`, `running`, `waiting_for_opportunity`, `processing`, `temporarily_unavailable`, `needs_intervention`, `paused`, or `completed`.

- [ ] **Step 7: Run focused runtime tests**

Run: `pytest -q tests/trading_kernel/integration/test_global_runtime_workers.py tests/trading_kernel/integration/test_owner_projection.py tests/trading_kernel/integration/test_runtime_worker.py`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/trading_kernel/application/project_owner_state.py src/trading_kernel/interfaces/reconciliation_worker.py src/trading_kernel/interfaces/lifecycle_worker.py src/trading_kernel/interfaces/observation_worker.py src/trading_kernel/interfaces/worker.py src/trading_kernel/interfaces/readonly_api.py src/trading_kernel/application/runtime.py tests/trading_kernel/integration/test_global_runtime_workers.py tests/trading_kernel/integration/test_owner_projection.py
git commit -m "feat(kernel): split runtime ownership and owner projection"
```

---

### Task 9: Certify the full six-capability chain and stop before Tokyo

**Files:**
- Create: `tests/trading_kernel/full_chain/test_six_event_system_certification.py`
- Modify: `tests/trading_kernel/full_chain/test_multi_position_certification.py`
- Modify: `tests/trading_kernel/full_chain/test_fault_matrix.py`
- Modify: `tests/trading_kernel/architecture/test_no_retired_execution.py`
- Modify: `tests/trading_kernel/architecture/test_runtime_file_io_audit.py`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`

**Interfaces:**
- Proves all six Events can progress from closed market input to deterministic signal and through the shared Ticket chain.
- Proves Tokyo and exchange-write capability remain disabled.

- [ ] **Step 1: Write failing requirement-by-requirement certification tests**

```python
@pytest.mark.parametrize("event_id", [
    "CPM-LONG", "MPG-LONG", "MI-LONG", "SOR-LONG", "SOR-SHORT", "BRF2-SHORT",
])
async def test_registered_event_reaches_terminal_review(event_id: str, certified_runtime) -> None:
    result = await certified_runtime.run_complete_fixture(event_id)
    assert result.ticket_status == "reviewed"
    assert result.position_qty == Decimal("0")
    assert result.open_order_count == 0
    assert result.open_incident_count == 0
```

- [ ] **Step 2: Run certification test and verify RED**

Run: `pytest -q tests/trading_kernel/full_chain/test_six_event_system_certification.py`

Expected: at least one Event or fault branch remains unimplemented before the final integration work.

- [ ] **Step 3: Close only failures proven by the certification matrix**

Do not add compatibility behavior. Fix shared abstractions when a failure affects a problem class; add per-Event code only when the registered strategy semantics are genuinely different.

- [ ] **Step 4: Run complete local certification**

Run:

```bash
pytest -q tests/trading_kernel
ruff check src/trading_kernel tests/trading_kernel scripts/trading_kernel migrations/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
python3 scripts/audit_production_runtime_file_io.py
python3 scripts/trading_kernel/bootstrap_schema.py --verify-rebuild
```

Expected: full test suite passes, Ruff passes, Mypy reports zero errors, file-I/O audit reports zero production readers/writers, and an empty PostgreSQL database rebuilds from `0001_initial` plus the deterministic seed.

- [ ] **Step 5: Verify destructive cutover remains refusal-safe without applying Tokyo**

Run: `pytest -q tests/trading_kernel/integration/test_cutover_state_machine.py`

Expected: all flatness, order, protection, unknown-outcome, writer-fence, identity, interruption, and resume tests pass. Do not execute `cutover_tokyo.py --apply`.

- [ ] **Step 6: Update current authority and mark the Tokyo stop**

Current documents must state that local six-capability certification is complete while Tokyo deployment, production Capacity values, initial live scope, and real-funds enablement remain blocked for Owner confirmation.

- [ ] **Step 7: Commit**

```bash
git add tests/trading_kernel docs/current
git commit -m "test(kernel): certify six-event complete trading system"
```

## Plan Self-Review

- **Spec coverage:** Tasks 1-9 cover Registry, six detectors, observation, Signal production, arbitration, Capacity, Ticket issuance, venue truth, unknown recovery, exit policy, lifecycle, settlement, review, Owner projection, schema, performance, and the Tokyo stop boundary.
- **Authority coverage:** All production code remains under `src/trading_kernel/**`; scripts are thin entrypoints and do not own business logic.
- **Deletion coverage:** No task reintroduces readiness packets, evidence packets, promotion packets, shadow candidates, action-time invocations, file-backed authority, old tables, dual writes, or compatibility imports.
- **Performance coverage:** Observation runs at closed-bar event time; facts are bounded upserts; append-only growth occurs only for real signals and lifecycle transitions; exact active-ticket selectors bound reconciliation; external calls are timeout-bounded; no-signal ticks create zero files.
- **Safety coverage:** Unknown outcomes never resend, partial fills flatten, same-domain occupancy blocks, account mode is validated, and deployment stays disabled.
- **Execution mode:** The active Owner goal already authorizes inline implementation. No subagent dispatch or separate execution-choice prompt is required.
