---
title: DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_IMPLEMENTATION_PLAN
status: LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED
authority: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_IMPLEMENTATION_PLAN.md
implements: docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md
last_verified: 2026-07-17
deployment_state: LOCAL_ONLY_NO_DEPLOY
checkpoint_d2_commit: abe8d300
integration_state: LOCAL_MERGE_CERTIFIED_NOT_DEPLOYED
production_state: UNCHANGED
policy_activation: NOT_PERFORMED
exchange_write: 0
migration_head: 133_LOCAL_ONLY
---

# Dual-Position Account Risk V0 Asset-Neutral Identity Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:executing-plans` and execute inline in this isolated worktree.
> Repository policy and the current task prohibit subagent implementation.
> Every production change follows failing test -> minimal implementation ->
> focused regression -> local commit.

**Goal:** Extend the existing Dual-Position Account Risk V0 mainline so exact
instrument identity, versioned rules, immutable capacity claim, exposure episode,
cluster membership and FinalGate revalidation remain valid for known future asset
classes without creating another risk engine or enabling new live scope.

**Architecture:** Candidate Scope directly owns exact `exchange_instrument_id`.
Stable instrument identity and versioned rule facts feed the existing account-capacity
decision. The existing `brc_budget_reservations` row is the physical capacity claim;
one ActionTimeInvocation creates at most one Reservation, Ticket and ExposureEpisode
inside one short PG transaction. A typed current repository keeps historical PG rows out
of Action-Time, while streaming HTTP parsing preserves complete active account facts
without retaining full raw bodies. Ticket remains the sole business lifecycle owner.

**Tech Stack:** Python 3, Pydantic v2, `decimal.Decimal`, SQLAlchemy, Alembic,
PostgreSQL, `ijson>=3.5.1,<4.0.0`, pytest.

## Local Completion Evidence

| Gate | Result | Evidence meaning |
| --- | ---: | --- |
| Focused account-risk regression | **105 passed** | Domain, policy, sizing, reservation, ownership, exposure, budget, FinalGate and Ticket sequence |
| Conflict-adjacent regression | **352 passed** | Release Ticket/lifecycle and account-risk identity/capacity behavior remain compatible |
| PostgreSQL RCI | **14 passed** | Causal-integrity invariants pass at local migration head `133` |
| PostgreSQL integration | **9 passed, 0 skipped** | Concurrent claim, exact lane identity, cross-asset claim/release, 100000-row migrations and hot path |
| Migration paths | **fresh, 125→133, 133→125→133 passed** | Release rows preserve count and hash across the reversible path |
| Authority and file I/O gates | **all exit 0** | Current docs valid, output scope valid, suspicious authority 0, frequent writes 0, performance clear |
| Complete suite | **3564 passed / 1 skipped / 0 failed in 816.02s** | Sole skip records intentional removal of the legacy Trading Console proxy |

The integrated release/account-risk run additionally found and fixed certification defects at
the shared boundaries:

1. fresh revision-086 test schemas could not persist the exact instrument now required by
   current seed and repository validation;
2. legacy simulation fixtures reached Exchange Command without an explicit
   `exposure_episode_id`;
3. release Ticket, FinalGate, runtime outcome and Canary fixtures needed the exact episode and
   instrument fields now enforced by migrations 131–133;
4. fresh revision-086 schemas needed a nullable exact-instrument expansion point so both fresh
   installs and deployed databases can reach the enforced head through the same authority model.

No deployment, production migration apply, policy activation or exchange write occurred.

## Global Constraints

- Risk policy remains exactly **2.5% per Ticket, 2 positions, 6% portfolio risk,
  4% primary-cluster risk, 90% initial-margin cap, 10x leverage ceiling**.
- Current production remains the deployed single-position / 3% baseline; this plan
  does not deploy or activate the local V0 policy.
- `exchange_instrument_id` is opaque. Code must not parse ID prefixes or construct
  IDs from `exchange_id + symbol`.
- `asset_class`, `instrument_type`, `settlement_asset`, and `margin_asset` are
  independent typed fields.
- Financial calculations use `Decimal`; no float conversion is allowed.
- PG/current remains the only runtime authority. No JSON/MD/YAML/JSONL reader,
  writer, fallback, evidence directory or dynamic-path sidecar may be added.
- Candidate Scope, rule snapshots and cluster membership changes are admin/policy
  cadence only; no-signal ticks create zero new files, zero claim/Ticket rows and
  zero exposure-episode identities.
- Budget Action-Time reads use a dedicated typed current repository. Production
  budget code must not call `read_control_state()`, use `SELECT *`, reflect tables
  with `autoload_with`, or load terminal history for Python filtering.
- Budget current rows are bounded by exact keys and
  `max_concurrent_positions + 1`; the extra row proves overflow and stops further
  materialization.
- Full-account HTTP success bodies use endpoint-schema incremental parsing with a
  configurable **65536-byte transport chunk** default and consumer backpressure.
  There is no **512 KiB/endpoint**, **2.5 MiB/five-endpoint**, response-total or
  typed-row rejection threshold. All required account scalars, nonzero positions
  and open orders remain functionally complete.
- HTTP error diagnostics retain at most **65536 bytes** of masked body. Budget code
  must not impose a low `max_positions`, `max_orders`, or total typed-row cap.
- Historical migration classification uses set-based SQL or stable-key keyset
  batches of at most **1000 rows**, with **5-second lock timeout** and **60-second
  statement timeout** defaults. The batch and timeout bound one attempt; they do not
  skip rows or cap total migration size.
- PostgreSQL scale certification seeds **100000 terminal reservations**, **100000
  terminal commands** and **100000 historical rule/membership rows**. Large-history
  hot-path peak Python allocation may exceed the small fixture by at most **16 MiB**.
- Capacity transactions perform zero network calls and zero subprocess calls.
- Action-Time stays inside the existing **30-second** refresh budget and may not
  extend source freshness windows.
- Ticket remains the sole business lifecycle owner. ExposureEpisode is identity
  and derived fact lineage only.
- Existing positions, protection, exits, reconciliation and settlement continue
  after entry policy invalidation; only new risk is stopped.
- No FinalGate bypass, Operation Layer bypass, exchange write, live-profile change,
  sizing-default expansion, withdrawal, transfer, credential change or StrategyGroup
  scope expansion is authorized.
- A different-identity natural fresh signal or active production safety incident is
  a P0 interrupt. Finish the current local transaction/commit boundary, preserve the
  worktree, and handle the deployed production acceptance path separately.
- Do not run the approximately 11-minute full suite until all focused and PostgreSQL
  gates are green; announce that final long-running gate before starting it.

## Design Review Closure

| Finding | Resolution in reviewed design | Execution owner |
| --- | --- | --- |
| Old table design still made symbol mapping authoritative | New design explicitly supersedes Candidate Scope, instrument and reservation sections | Tasks 2-3 |
| Reservation/Ticket circular dependency and lineage drift | Ticket owns one composite FK to the Reservation's reservation/Ticket/episode tuple; pre-generated IDs commit in one transaction | Tasks 2 and 5 |
| Mutable identity in idempotency key could create a second claim | Idempotency anchors only to account + runtime profile + ActionTimeInvocation; lane/instrument/side/policy stay in payload/hash | Tasks 1 and 5 |
| FinalGate could double-count the claim being checked | Revalidate as `aggregate - own claim + own claim` | Task 7 |
| Candidate uniqueness omitted timeframe | Active uniqueness becomes group + exact instrument + side + timeframe | Tasks 2-3 |
| Terminal consumed history could be mis-backfilled | Migration 123-equivalent cleanup and audit precede strict backfill | Task 2 |
| Performance/cadence contract was missing | Zero file growth, bounded PG rows, indexed hot path and 30-second budget are explicit | Task 8 |
| Budget projector loaded all account Reservation history | Dedicated current repository applies account/profile/status predicates and bounded overflow reads in SQL | Task 6 |
| Full-account snapshot transport had timeout but no memory ceiling | Core streaming HTTP/JSON transport bounds resident raw buffers while preserving all active account facts | Task 6 |
| Migration 127 could materialize all history in Python | Set-based SQL or 1000-row keyset batches with lock/statement timeouts are mandatory | Task 2 |
| Small fixtures could make O(n) reads look green | 100000-row PostgreSQL scale, EXPLAIN, SQL-shape and tracemalloc gates are mandatory | Task 8 |

## Chain Position And State Transition

```text
chain_position:
Candidate Scope
-> ActionTimeInvocation
-> Account Capacity Claim
-> Action-Time Ticket
-> FinalGate

local_state_before:
dual-position risk remediation implemented
+ symbol-derived instrument paths still exist
+ capacity claim lacks asset-neutral identity and episode lineage
+ Budget projector materializes account history before Python filtering
+ full-account HTTP collector retains unbounded raw responses

local_state_after:
exact-instrument asset-neutral claim is locally certified
+ two-position risk calculations unchanged
+ Budget hot path cost follows current active facts, not terminal history
+ full valid account facts remain complete through streaming normalization
+ no production deploy or policy activation

production_state_after:
unchanged until a separately authorized deploy and shadow certification
```

**Blocker removed or reclassified:** local `schema_invalid`,
`action_time_boundary_not_reproduced` and production-performance risks caused by
symbol-derived identity, historical hot-path materialization and unbounded raw HTTP
responses are removed. The production legacy second-position blocker remains until a
later deploy/shadow/activation stage.

## File Responsibility Map

| File or family | Responsibility in this plan |
| --- | --- |
| `src/domain/instrument_risk_identity.py` | Pure stable identity, rule-snapshot and cluster-snapshot references |
| `src/domain/account_capacity_claim.py` | Pure immutable claim payload, canonical hash and idempotency key |
| `src/domain/runtime_lane_identity.py` | Carry exact instrument through the existing lane identity |
| migrations 126-128 | Expand, historical-time backfill, validate and enforce target schema |
| `src/application/runtime_lane_identity_service.py` | Resolve Candidate Scope exact instrument from PG |
| `src/application/action_time/instrument_risk_facts.py` | Load one current typed identity/rule/cluster bundle without network I/O |
| `src/application/action_time/account_capacity_reservation.py` | Capacity decision inputs and immutable claim result |
| `src/application/action_time/account_capacity_claim.py` | Persist/verify one claim and enforce immutable-column updates |
| `src/application/action_time/account_capacity_materialization.py` | Lock-first account capacity orchestration |
| `src/application/action_time/promotion_action_time_lane.py` | Pre-generate and conserve reservation/Ticket/episode IDs |
| `src/application/action_time/action_time_ticket.py` | Materialize Ticket from exact claim lineage |
| `src/application/action_time/account_exposure_current.py` | Netting-domain current projection plus episode lineage |
| `src/infrastructure/account_capacity_hot_path_repository.py` | Exact current/active Budget reads with typed overflow evidence; replaces generic `_rows()` |
| `src/infrastructure/streaming_http_json.py` | Backpressured, endpoint-schema success parsing and bounded error diagnostics for Budget snapshots |
| `src/infrastructure/binance_usdm_streaming_signed_reader.py` | Signed Binance request opening plus streaming endpoint normalization |
| `src/infrastructure/binance_usdm_account_risk_snapshot.py` | Functionally complete, streaming and resident-memory-bounded full-account snapshot |
| `requirements.txt` | Add `ijson>=3.5.1,<4.0.0` for maintained nested event-stream parsing |
| `src/application/action_time/finalgate_preflight.py` | Latest semantic claim revalidation before exchange write |
| `src/infrastructure/runtime_control_state_repository.py` | PG/current read shape and negative schema validation |

---

### Task 1: Pure Asset-Neutral Identity And Claim Contracts

**Task ID:** `DAR-AI-01`

**Files:**

- Create: `src/domain/instrument_risk_identity.py`
- Create: `src/domain/account_capacity_claim.py`
- Modify: `src/domain/runtime_lane_identity.py`
- Create: `tests/unit/test_instrument_risk_identity.py`
- Create: `tests/unit/test_account_capacity_claim.py`
- Modify: `tests/unit/test_runtime_lane_identity.py`

**Interfaces:**

- Produces `InstrumentRiskIdentity`, `InstrumentRuleSnapshotRef`,
  `RiskClusterMembershipSnapshotRef`, `AccountCapacityClaimPayload`,
  `capacity_claim_hash()` and `reservation_idempotency_key()`.
- `RuntimeLaneIdentity` gains required `exchange_instrument_id` without inferring
  it from symbol or exchange.

- [ ] **Step 1: Write failing identity tests**

```python
def test_instrument_identity_is_explicit_and_opaque() -> None:
    identity = InstrumentRiskIdentity(
        exchange_instrument_id="instrument-opaque-1",
        exchange_id="binance-usdm",
        exchange_symbol="SOLUSDT",
        asset_class="crypto",
        instrument_type="perpetual",
        settlement_asset="USDT",
        margin_asset="USDT",
        instrument_identity_schema_version="v1",
    )
    assert identity.exchange_instrument_id == "instrument-opaque-1"
    assert identity.instrument_type == "perpetual"
```

```python
def test_runtime_lane_identity_requires_exact_instrument() -> None:
    with pytest.raises(ValidationError):
        RuntimeLaneIdentity(**lane_values_without_exchange_instrument_id())
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m pytest -q \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_runtime_lane_identity.py
```

Expected: collection or validation failure because the new types/field do not exist.

- [ ] **Step 3: Implement the frozen identity contracts**

```python
class InstrumentRiskIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    exchange_id: str = Field(min_length=1, max_length=96)
    exchange_symbol: str = Field(min_length=1, max_length=128)
    asset_class: str = Field(min_length=1, max_length=64)
    instrument_type: str = Field(min_length=1, max_length=64)
    settlement_asset: str = Field(min_length=1, max_length=64)
    margin_asset: str = Field(min_length=1, max_length=64)
    instrument_identity_schema_version: str = Field(min_length=1, max_length=32)


class InstrumentRuleSnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    instrument_rule_snapshot_id: str
    rule_schema_version: str
    price_tick: Decimal
    quantity_step: Decimal
    min_qty: Decimal
    min_notional: Decimal
    contract_multiplier: Decimal
    exchange_max_leverage_for_claim_notional: int
    source_fact_snapshot_id: str
    valid_until_ms: int


class RiskClusterMembershipSnapshotRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cluster_membership_snapshot_id: str
    primary_risk_cluster_id: str
    semantic_hash: str


class AccountCapacityClaimPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    capacity_claim_schema_version: str
    reservation_id: str
    ticket_id: str
    exposure_episode_id: str
    action_time_invocation_id: str
    action_time_lane_input_id: str
    promotion_candidate_id: str
    signal_event_id: str
    account_id: str
    runtime_profile_id: str
    strategy_group_id: str
    side: Literal["long", "short"]
    instrument: InstrumentRiskIdentity
    rule_snapshot: InstrumentRuleSnapshotRef
    cluster_snapshot: RiskClusterMembershipSnapshotRef
    pricing_source_fact_snapshot_id: str
    account_source_fact_snapshot_id: str
    account_fact_schema_version: str
    account_risk_policy_version: str
    account_risk_policy_event_id: str
    claimed_budget_projection_version: int
    entry_reference_price: Decimal
    stop_price: Decimal
    intended_qty: Decimal
    target_notional: Decimal
    allowed_risk_budget: Decimal
    planned_stop_risk: Decimal
    reserved_margin: Decimal
    selected_leverage: int
    reserved_at_ms: int
    expires_at_ms: int
```

- [ ] **Step 4: Write failing deterministic claim tests**

```python
def test_policy_event_changes_hash_but_not_idempotency_key() -> None:
    first = claim_payload(policy_event_id="policy-event-1")
    second = claim_payload(policy_event_id="policy-event-2")
    assert reservation_idempotency_key(first) == reservation_idempotency_key(second)
    assert capacity_claim_hash(first) != capacity_claim_hash(second)


def test_instrument_or_lane_drift_cannot_change_invocation_key() -> None:
    first = claim_payload(
        exchange_instrument_id="instrument-1",
        action_time_lane_input_id="lane-1",
    )
    drifted = claim_payload(
        exchange_instrument_id="instrument-2",
        action_time_lane_input_id="lane-2",
    )
    assert reservation_idempotency_key(first) == reservation_idempotency_key(drifted)
    assert capacity_claim_hash(first) != capacity_claim_hash(drifted)


def test_mutable_state_is_not_part_of_claim_payload() -> None:
    fields = AccountCapacityClaimPayload.model_fields
    assert "status" not in fields
    assert "margin_accounting_state" not in fields
```

- [ ] **Step 5: Implement canonical claim serialization**

```python
def _canonical(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def capacity_claim_hash(payload: AccountCapacityClaimPayload) -> str:
    encoded = json.dumps(
        _canonical(payload.model_dump(mode="python")),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def reservation_idempotency_key(payload: AccountCapacityClaimPayload) -> str:
    parts = (
        payload.account_id,
        payload.runtime_profile_id,
        payload.action_time_invocation_id,
    )
    return "account_capacity:" + sha256("|".join(parts).encode()).hexdigest()
```

- [ ] **Step 6: Run focused tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_runtime_lane_identity.py
```

Expected: all tests pass; no I/O imports appear under `src/domain/`.

- [ ] **Step 7: Commit checkpoint A1**

```bash
git add \
  src/domain/instrument_risk_identity.py \
  src/domain/account_capacity_claim.py \
  src/domain/runtime_lane_identity.py \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_runtime_lane_identity.py
git commit -m "feat: define asset-neutral account risk identities"
```

### Task 2: Expand, Historical-Time Backfill, Validate And Enforce Schema

**Task ID:** `DAR-AI-02`

**Files:**

- Create: `migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py`
- Create: `migrations/versions/2026-07-17-132_backfill_asset_neutral_account_risk_identity.py`
- Create: `migrations/versions/2026-07-17-133_enforce_asset_neutral_account_risk_identity.py`
- Create: `tests/unit/test_asset_neutral_account_risk_migrations.py`
- Create: `tests/integration/test_asset_neutral_account_risk_migration_scale.py`
- Modify: `tests/unit/test_account_risk_policy_migration.py`
- Modify: `tests/unit/test_account_risk_current_migration.py`

**Interfaces:**

- Migration 126 only expands nullable structure and creates new snapshot tables.
- Migration 127 performs terminal cleanup audit and historical-time backfill.
- Migration 128 rejects incomplete active/current/live-eligible rows, adds unique/FK
  constraints and removes old active unique indexes.
- Migration 127 uses set-based SQL or `budget_reservation_id` keyset batches of at
  most 1000 rows; no Python operation may materialize the complete history.

- [ ] **Step 1: Write failing migration-shape tests**

Assert exact target columns:

```python
assert {
    "exchange_instrument_id",
    "instrument_type",
    "settlement_asset",
    "margin_asset",
}.issubset(columns(conn, "brc_strategy_group_candidate_scope") | columns(conn, "brc_exchange_instruments"))

assert {
    "exposure_episode_id",
    "action_time_invocation_id",
    "instrument_rule_snapshot_id",
    "pricing_source_fact_snapshot_id",
    "account_source_fact_snapshot_id",
    "primary_risk_cluster_id",
    "cluster_membership_snapshot_id",
    "capacity_claim_hash",
    "reservation_idempotency_key",
}.issubset(columns(conn, "brc_budget_reservations"))
```

- [ ] **Step 2: Run migration tests RED**

```bash
python3 -m pytest -q tests/unit/test_asset_neutral_account_risk_migrations.py
```

Expected: missing migration modules/tables/columns.

- [ ] **Step 3: Implement migration 126 expand structure**

Create:

```text
brc_instrument_rule_snapshots
brc_risk_cluster_membership_snapshots
```

Extend:

```text
brc_exchange_instruments:
  instrument_type, settlement_asset, margin_asset,
  instrument_identity_schema_version

brc_strategy_group_candidate_scope:
  exchange_instrument_id

brc_risk_cluster_memberships:
  cluster_membership_snapshot_id, membership_role, status

brc_budget_reservations:
  exposure_episode_id, action_time_invocation_id,
  asset_class, instrument_type, settlement_asset, margin_asset,
  instrument_rule_snapshot_id, instrument_rule_schema_version,
  pricing_source_fact_snapshot_id, account_source_fact_snapshot_id,
  account_fact_schema_version, primary_risk_cluster_id,
  cluster_membership_snapshot_id, capacity_claim_schema_version,
  capacity_claim_hash, reservation_idempotency_key,
  reconciliation_state, released_at_ms, invalidated_at_ms,
  current_first_blocker

brc_action_time_tickets:
  exposure_episode_id, asset_class, instrument_type,
  capacity_claim_hash

brc_account_exposure_current:
  asset_class, instrument_type, current_exposure_episode_id,
  primary_risk_cluster_id, cluster_membership_snapshot_id,
  account_source_fact_snapshot_id, account_fact_schema_version

brc_ticket_bound_exchange_commands:
  exposure_episode_id
```

- [ ] **Step 4: Implement migration 127 historical-time backfill**

Backfill order:

```text
1. apply migration-123-equivalent terminal reservation cleanup;
2. candidate scopes use the one mapping valid at valid_from_ms;
3. tickets keep their already persisted exchange_instrument_id;
4. reservations prefer bound ticket identity, else mapping valid at reserved_at_ms;
5. signals resolve only through candidate scope valid at event_time_ms;
6. current exposure uses classified exchange identity only;
7. unresolved terminal history becomes legacy audit-only;
8. unresolved active/current rows abort migration.
```

Map legacy `asset_class=crypto_perpetual` to:

```text
asset_class=crypto
instrument_type=perpetual
```

- [ ] **Step 5: Add backfill negative tests**

Cover:

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_backfill_uses_mapping_valid_at_reservation_time` | Old mapping valid at reservation time and different mapping current now | Reservation receives the historical instrument ID |
| `test_current_mapping_cannot_rewrite_historical_ticket` | Ticket already carries instrument A while current alias points to B | Ticket remains instrument A |
| `test_unresolved_active_claim_aborts_constraint_phase` | Active reservation has no unique historical mapping | Migration 128 raises and adds no constraints |
| `test_terminal_released_history_may_remain_audit_only` | Released terminal reservation has no mapping | Migration succeeds while row remains non-current audit history |
| `test_backfill_does_not_fetchall_terminal_history` | 100001 terminal rows plus one active row | No `.all()`/`fetchall()` path; each Python batch is at most 1000 rows |
| `test_backfill_timeout_aborts_before_constraint_phase` | Backfill statement exceeds 60 seconds or lock waits over 5 seconds | Migration fails and migration 128 constraints are absent |

Migration implementation is fixed to:

```text
SET LOCAL lock_timeout = '5s'
SET LOCAL statement_timeout = '60s'
preflight -> SELECT count(*), min(primary_key), max(primary_key)
normal rows -> set-based UPDATE ... FROM
exception rows -> WHERE primary_key > :cursor ORDER BY primary_key LIMIT 1000
```

`5s/60s` are defaults exposed as migration session parameters. A maintenance run may
raise them after preflight without changing migration semantics; lowering or raising a
timeout never skips a row, changes a fact, or advances the constraint phase after failure.

The exception classifier consumes one batch iterator and discards it before the next
query. It must not use `.all()`, `.fetchall()`, `list(result)` or a dictionary keyed by
every historical row.

- [ ] **Step 6: Implement migration 128 constraints**

Required constraints/indexes:

```text
active Candidate Scope unique:
  strategy_group_id + exchange_instrument_id + side + timeframe

current rule snapshot unique:
  exchange_instrument_id WHERE status='current'

active exposure hot path:
  account_id + exposure_state
  WHERE exposure_state NOT IN ('flat','closed') OR first_blocker IS NOT NULL

membership primary unique:
  cluster_membership_snapshot_id WHERE membership_role='primary' AND status='active'

reservation idempotency unique:
  reservation_idempotency_key

effective reservation hot path:
  account_id + runtime_profile_id + status
  WHERE status IN ('active','consumed')

nonterminal command evidence hot path:
  ticket_id + command_state
  WHERE command_state NOT IN ('confirmed_rejected','reconciled_absent')

one claim per Invocation unique:
  action_time_invocation_id

active/consumed claim:
  all immutable identity/snapshot/hash columns non-null

Ticket:
  (budget_reservation_id, ticket_id, exposure_episode_id) composite FK
  -> brc_budget_reservations same three-column unique lineage
```

Do not add a non-deferrable reverse Reservation -> Ticket FK.

- [ ] **Step 7: Run migration tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_asset_neutral_account_risk_migrations.py \
  tests/unit/test_account_risk_policy_migration.py \
  tests/unit/test_account_risk_current_migration.py
```

Run the PostgreSQL scale gate without skips:

```bash
test -n "$BRC_LOCAL_TEST_POSTGRES_DSN"
BRC_LOCAL_TEST_POSTGRES_DSN="$BRC_LOCAL_TEST_POSTGRES_DSN" \
python3 -m pytest -q \
  tests/integration/test_asset_neutral_account_risk_migration_scale.py
```

Expected: 100001 historical rows are fully classified through set-based/keyset work;
observed Python batch size never exceeds 1000 and no constraint phase follows timeout.

- [ ] **Step 8: Commit checkpoint A2**

```bash
git add \
  migrations/versions/2026-07-17-131_expand_asset_neutral_account_risk_identity.py \
  migrations/versions/2026-07-17-132_backfill_asset_neutral_account_risk_identity.py \
  migrations/versions/2026-07-17-133_enforce_asset_neutral_account_risk_identity.py \
  tests/unit/test_asset_neutral_account_risk_migrations.py \
  tests/integration/test_asset_neutral_account_risk_migration_scale.py \
  tests/unit/test_account_risk_policy_migration.py \
  tests/unit/test_account_risk_current_migration.py
git commit -m "feat: add asset-neutral account risk schema"
```

### Task 3: Cut Runtime Lane And Candidate Scope To Exact Instrument

**Task ID:** `DAR-AI-03`

**Files:**

- Modify: `src/application/runtime_lane_identity_service.py`
- Modify: `src/application/readmodels/runtime_strategy_signal_input.py`
- Modify: `src/application/readmodels/strategy_live_candidate_pool.py`
- Modify: `src/application/strategy_semantic_admission.py`
- Modify: `src/infrastructure/runtime_control_state_repository.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/application/action_time/exchange_scope.py`
- Modify: `tests/unit/test_runtime_lane_identity_service.py`
- Modify: `tests/integration/test_runtime_lane_identity_certification.py`
- Modify: `tests/unit/test_strategy_live_candidate_pool.py`
- Modify: `tests/unit/test_pg_promotion_action_time_lane_materialization.py`
- Modify: `tests/unit/test_ticket_bound_exchange_scope.py`

**Interfaces:**

- Candidate Scope produces exact `exchange_instrument_id`.
- RuntimeLaneIdentity conserves it through signal, promotion, lane and Ticket.
- Symbol mapping is no longer consulted to upgrade Action-Time identity.

- [ ] **Step 1: Write failing exact-instrument certification tests**

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_same_symbol_two_instruments_do_not_cross_candidate_scope` | Two active scopes share display symbol but have different exact instruments/timeframes | Lookup without exact scope is ambiguous; exact scope resolves one row |
| `test_runtime_lane_identity_copies_candidate_exchange_instrument_id` | Candidate carries opaque instrument ID | Identity and identity hash contain that exact ID |
| `test_action_time_ticket_rejects_symbol_derived_instrument` | Lane exact ID differs from a value constructible from exchange + symbol | Ticket uses lane ID and rejects the fabricated value |
| `test_current_mapping_change_does_not_rewrite_existing_ticket` | Alias mapping changes after Ticket creation | Current Ticket scope remains valid when its Candidate Scope/instrument registry remain active |
| `test_candidate_hot_path_never_calls_read_control_state` | Spy makes generic full-state reader raise | Exact Candidate Scope still resolves through bounded SQL |
| `test_display_key_ambiguity_reads_at_most_two_rows` | 100 Candidate history rows share the display key | Repository reads only two active candidates and fails `candidate_scope_ambiguous` |

- [ ] **Step 2: Run focused tests RED**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/unit/test_ticket_bound_exchange_scope.py
```

Expected: Candidate Scope query does not select the new field and Ticket still uses mapping.

- [ ] **Step 3: Change RuntimeLaneIdentity resolution**

The production candidate query must consume `candidate_scope_id` or the already-bound
`exchange_instrument_id + timeframe` and select only required columns:

```sql
SELECT candidate_scope_id, strategy_group_id, symbol,
       exchange_instrument_id, asset_class, side, timeframe,
       policy_current_id
FROM brc_strategy_group_candidate_scope
WHERE candidate_scope_id = :candidate_scope_id
  AND status = 'active'
LIMIT 1
```

The display-key compatibility lookup is diagnostic-only and adds
`ORDER BY candidate_scope_id LIMIT 2`. Zero rows mean missing; one row may be returned;
two rows are sufficient to prove `candidate_scope_ambiguous`. It must never load every
matching timeframe/instrument row.

- [ ] **Step 4: Propagate exact identity through readmodels and repository validation**

Require `exchange_instrument_id` in current Candidate Scope, runtime coverage,
signal input and hot-path repository rows. Reject blank/mismatched values as
`schema_invalid`; do not fall back to symbol mapping. The production path must use the
`action_time_hot_path_current` profile or its exact typed selector and must not call
`read_control_state()`.

- [ ] **Step 5: Delete Action-Time identity construction**

Remove:

```python
f"{snapshot.exchange_id}:{symbol}"
```

and delete `_exchange_instrument_id()` mapping resolution from Ticket materialization.
Use only:

```python
exchange_instrument_id=bundle.lane_identity.exchange_instrument_id
```

- [ ] **Step 6: Replace exchange-scope current mapping check**

Validate Ticket against its bound Candidate Scope, instrument registry status and
runtime scope. Historical mapping remains diagnostic only and cannot block a valid
already-bound Ticket merely because the current alias changed.

- [ ] **Step 7: Run all exact-identity tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_ticket_bound_exchange_scope.py
```

- [ ] **Step 8: Commit checkpoint B1**

```bash
git add \
  src/application/runtime_lane_identity_service.py \
  src/application/readmodels/runtime_strategy_signal_input.py \
  src/application/readmodels/strategy_live_candidate_pool.py \
  src/application/strategy_semantic_admission.py \
  src/infrastructure/runtime_control_state_repository.py \
  src/application/action_time/promotion_action_time_lane.py \
  src/application/action_time/action_time_ticket.py \
  src/application/action_time/exchange_scope.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/unit/test_strategy_live_candidate_pool.py \
  tests/unit/test_pg_promotion_action_time_lane_materialization.py \
  tests/unit/test_ticket_bound_exchange_scope.py
git commit -m "refactor: conserve exact instrument through runtime lane"
```

### Task 4: Versioned Instrument Rules And Primary Cluster Snapshot

**Task ID:** `DAR-AI-04`

**Files:**

- Create: `src/application/action_time/instrument_risk_facts.py`
- Modify: `src/application/action_time/account_risk_policy.py`
- Modify: `src/application/action_time/account_capacity_reservation.py`
- Modify: `src/domain/account_risk.py`
- Create: `tests/unit/test_instrument_risk_facts.py`
- Modify: `tests/unit/test_account_risk_policy.py`
- Modify: `tests/unit/test_account_capacity_reservation.py`

**Interfaces:**

- Produces `InstrumentRiskFacts(identity, rule_snapshot, cluster_snapshot)` from
  exact indexed PG rows.
- Capacity consumes rule and primary cluster snapshots, not symbol defaults.

- [ ] **Step 1: Write failing rule/membership tests**

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_loader_requires_one_current_rule_snapshot` | Zero or two current rule rows | Loader fails closed instead of picking one |
| `test_loader_rejects_expired_rule_snapshot` | One row with `valid_until_ms <= now_ms` | `instrument_rule_snapshot_stale` |
| `test_membership_requires_exactly_one_primary` | Membership snapshot has zero or two primary rows | `primary_risk_cluster_membership_invalid` |
| `test_secondary_membership_does_not_reduce_v0_capacity` | Primary and two secondary memberships exist | Capacity uses only primary held-risk cap |
| `test_loader_ignores_large_rule_and_membership_history` | 100000 old snapshots plus one current snapshot | Exact current result; materialized rows remain constant |
| `test_identical_membership_semantics_reuse_current_snapshot` | Admin repeats the same membership set | No new header/member history rows |

- [ ] **Step 2: Run tests RED**

```bash
python3 -m pytest -q \
  tests/unit/test_instrument_risk_facts.py \
  tests/unit/test_account_risk_policy.py
```

- [ ] **Step 3: Implement the no-network PG loader**

```python
class InstrumentRiskFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    identity: InstrumentRiskIdentity
    rule_snapshot: InstrumentRuleSnapshotRef
    cluster_snapshot: RiskClusterMembershipSnapshotRef


def load_instrument_risk_facts(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    risk_policy_version: str,
    planned_notional: Decimal,
    now_ms: int,
) -> InstrumentRiskFacts:
    identity = _load_exact_instrument_identity(conn, exchange_instrument_id)
    rule = _load_one_current_rule_snapshot(
        conn,
        exchange_instrument_id=exchange_instrument_id,
        planned_notional=planned_notional,
        now_ms=now_ms,
    )
    cluster = _load_one_primary_cluster_snapshot(
        conn,
        exchange_instrument_id=exchange_instrument_id,
        risk_policy_version=risk_policy_version,
    )
    return InstrumentRiskFacts(
        identity=identity,
        rule_snapshot=rule,
        cluster_snapshot=cluster,
    )
```

The loader performs bounded primary-key/current-index reads only. Every query selects
named columns and uses `LIMIT 2`: one row is valid, two rows prove an identity conflict.
It must not call exchange APIs, parse `exchange_instrument_id`, reflect tables at runtime,
or scan historical rule/membership rows.

Private helper contracts in the same file are fixed as:

```python
def _load_exact_instrument_identity(
    conn: sa.Connection,
    exchange_instrument_id: str,
) -> InstrumentRiskIdentity:
    """Return one active registry row or raise instrument_identity_missing."""


def _load_one_current_rule_snapshot(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    planned_notional: Decimal,
    now_ms: int,
) -> InstrumentRuleSnapshotRef:
    """Return one unexpired current rule applicable to planned_notional."""


def _load_one_primary_cluster_snapshot(
    conn: sa.Connection,
    *,
    exchange_instrument_id: str,
    risk_policy_version: str,
) -> RiskClusterMembershipSnapshotRef:
    """Return the versioned snapshot with exactly one active primary member."""
```

- [ ] **Step 4: Version cluster membership replacement**

`replace_risk_cluster_memberships()` appends a snapshot header and member rows;
it no longer deletes history. Before append it computes the canonical semantic hash and
reuses the current snapshot when the hash is unchanged. It requires exactly one primary
membership per instrument/policy snapshot. Secondary rows remain non-enforcing in V0.

- [ ] **Step 5: Adapt capacity candidate**

Replace scalar `risk_cluster_id`, `min_qty`, `qty_step`, `min_notional` and
`exchange_max_leverage` inputs with typed `InstrumentRiskFacts`. Pass only the
normalized values into the pure `decide_account_capacity()` function.

- [ ] **Step 6: Run focused tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_instrument_risk_facts.py \
  tests/unit/test_account_risk_policy.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_account_risk.py
```

- [ ] **Step 7: Commit checkpoint B2**

```bash
git add src/application/action_time/instrument_risk_facts.py \
  src/application/action_time/account_risk_policy.py \
  src/application/action_time/account_capacity_reservation.py \
  src/domain/account_risk.py \
  tests/unit/test_instrument_risk_facts.py \
  tests/unit/test_account_risk_policy.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_account_risk.py
git commit -m "feat: version instrument rules and cluster membership"
```

### Task 5: Atomic Immutable Claim, Ticket And Exposure Episode

**Task ID:** `DAR-AI-05`

**Files:**

- Create: `src/application/action_time/account_capacity_claim.py`
- Modify: `src/application/action_time/account_capacity_materialization.py`
- Modify: `src/application/action_time/account_capacity_reservation.py`
- Modify: `src/application/action_time/promotion_action_time_lane.py`
- Modify: `src/application/action_time/action_time_ticket.py`
- Modify: `src/application/action_time/budget_reservation_transition.py`
- Create: `tests/unit/test_account_capacity_claim_persistence.py`
- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Modify: `tests/integration/test_account_capacity_postgres.py`

**Interfaces:**

- One `action_time_invocation_id` creates one deterministic idempotency key.
- The transaction pre-generates `reservation_id`, `ticket_id`,
  `exposure_episode_id`, persists a sealed claim and commits Ticket/claim together.
- Reservation transitions may update only mutable columns.

- [ ] **Step 1: Write failing idempotency and atomicity tests**

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_same_invocation_returns_same_claim` | Retry identical payload | Same reservation, Ticket and episode IDs return |
| `test_same_key_different_hash_hard_stops` | Retry same Invocation with changed lane/instrument/side or other immutable payload | `account_capacity_claim_idempotency_conflict` and row count remains one |
| `test_policy_change_does_not_create_second_claim_for_invocation` | Change policy event after first claim | Old claim invalidates; no second reservation is inserted |
| `test_ticket_insert_failure_rolls_back_claim_and_lineage` | Force Ticket composite-lineage constraint failure | Transaction leaves zero Reservation/Ticket rows and no durable episode identity |
| `test_transition_cannot_mutate_claim_payload` | Transition attempts to change instrument or risk | Update is rejected and hash remains unchanged |

- [ ] **Step 2: Run unit tests RED**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_claim_persistence.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py
```

- [ ] **Step 3: Implement claim persistence API**

```python
class PersistedAccountCapacityClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    payload: AccountCapacityClaimPayload
    capacity_claim_hash: str
    reservation_idempotency_key: str


def insert_or_get_account_capacity_claim(
    conn: sa.Connection,
    *,
    payload: AccountCapacityClaimPayload,
) -> PersistedAccountCapacityClaim:
    claim_hash = capacity_claim_hash(payload)
    idempotency_key = reservation_idempotency_key(payload)
    existing = _claim_by_invocation_id(conn, payload.action_time_invocation_id)
    if existing is not None:
        if existing.reservation_idempotency_key != idempotency_key:
            raise AccountCapacityClaimConflict(
                "account_capacity_claim_invocation_identity_conflict"
            )
        if existing.capacity_claim_hash != claim_hash:
            raise AccountCapacityClaimConflict(
                "account_capacity_claim_idempotency_conflict"
            )
        return existing
    _insert_claim_row(
        conn,
        payload=payload,
        capacity_claim_hash=claim_hash,
        reservation_idempotency_key=idempotency_key,
    )
    return PersistedAccountCapacityClaim(
        payload=payload,
        capacity_claim_hash=claim_hash,
        reservation_idempotency_key=idempotency_key,
    )
```

On duplicate idempotency key:

```text
same hash -> return existing claim
different hash -> account_capacity_claim_idempotency_conflict
```

Private persistence helpers in the same file are fixed as:

```python
def _claim_by_invocation_id(
    conn: sa.Connection,
    action_time_invocation_id: str,
) -> PersistedAccountCapacityClaim | None:
    """Load the one reservation row and reconstruct its immutable payload."""


def _insert_claim_row(
    conn: sa.Connection,
    *,
    payload: AccountCapacityClaimPayload,
    capacity_claim_hash: str,
    reservation_idempotency_key: str,
) -> None:
    """Insert every immutable claim field plus initial mutable current state."""
```

- [ ] **Step 4: Pre-generate and conserve the three identities**

Generate all IDs after the account budget row is locked and before inserts. The lane ID
must be deterministic for the Invocation. Insert Reservation first using the pre-generated
Ticket and episode IDs, then insert Ticket through the composite Reservation/Ticket/episode
FK, update lane/invocation references, and commit once. Any retry that supplies a different
lane ID, instrument or side for the same Invocation must hit the existing Invocation row and
fail with an identity/hash conflict.

- [ ] **Step 5: Enforce mutable-column allowlist**

`budget_reservation_transition.py` may update only:

```python
MUTABLE_RESERVATION_COLUMNS = {
    "status",
    "margin_accounting_state",
    "reconciliation_state",
    "release_reason",
    "released_at_ms",
    "invalidated_at_ms",
    "current_first_blocker",
}
```

Every transition recomputes and verifies `capacity_claim_hash` before update.

- [ ] **Step 6: Add PostgreSQL concurrency certification**

Two concurrent transactions for the same Invocation must serialize on the budget
row/idempotency unique key. Exactly one claim/Ticket row pair and episode identity commit; the
other returns the existing claim or a deterministic capacity blocker.

- [ ] **Step 7: Run PostgreSQL gate GREEN**

```bash
test -n "$BRC_LOCAL_TEST_POSTGRES_DSN"
test -n "$BRC_LOCAL_TEST_POSTGRES_SCHEMA"
BRC_LOCAL_TEST_POSTGRES_DSN="$BRC_LOCAL_TEST_POSTGRES_DSN" \
BRC_LOCAL_TEST_POSTGRES_SCHEMA="$BRC_LOCAL_TEST_POSTGRES_SCHEMA" \
python3 -m pytest -q tests/integration/test_account_capacity_postgres.py
```

Expected: no skip; concurrency, rollback and lifecycle-release cases pass.

- [ ] **Step 8: Commit checkpoint C1**

```bash
git add \
  src/application/action_time/account_capacity_claim.py \
  src/application/action_time/account_capacity_materialization.py \
  src/application/action_time/account_capacity_reservation.py \
  src/application/action_time/promotion_action_time_lane.py \
  src/application/action_time/action_time_ticket.py \
  src/application/action_time/budget_reservation_transition.py \
  tests/unit/test_account_capacity_claim_persistence.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/integration/test_account_capacity_postgres.py
git commit -m "feat: seal atomic account capacity claims"
```

### Task 6: Bounded Account Truth, Exposure Projection And Episode Conservation

**Task ID:** `DAR-AI-06`

**Files:**

- Create: `src/infrastructure/account_capacity_hot_path_repository.py`
- Create: `src/infrastructure/streaming_http_json.py`
- Create: `src/infrastructure/binance_usdm_streaming_signed_reader.py`
- Modify: `src/infrastructure/binance_usdm_account_risk_snapshot.py`
- Modify: `requirements.txt`
- Modify: `src/application/action_time/account_exchange_ownership.py`
- Modify: `src/application/action_time/account_exposure_current.py`
- Modify: `src/application/action_time/account_budget_current.py`
- Modify: `src/domain/ticket_bound_exchange_command.py`
- Modify: `src/application/action_time/exchange_command.py`
- Modify: `src/application/action_time/post_submit_reconciliation_tick.py`
- Modify: `src/application/action_time/live_outcome_ledger.py`
- Modify: `scripts/materialize_action_time_ticket_sequence.py`
- Modify: `scripts/run_ticket_bound_lifecycle_maintenance_once.py`
- Create: `tests/unit/test_account_capacity_hot_path_repository.py`
- Create: `tests/unit/test_streaming_http_json.py`
- Modify: `tests/unit/test_binance_usdm_account_risk_snapshot.py`
- Modify: `tests/unit/test_account_exchange_ownership.py`
- Modify: `tests/unit/test_account_exposure_current.py`
- Modify: `tests/unit/test_account_budget_current.py`
- Modify: `tests/unit/test_ticket_bound_exchange_command_materialization.py`

**Interfaces:**

- Current netting-domain rows carry nullable `current_exposure_episode_id`.
- System-owned commands/outcomes conserve episode lineage.
- Unowned or unresolved exchange truth creates a global new-entry hold without
  fabricating an instrument or episode.
- Budget aggregation consumes only exact current/active typed rows; terminal history
  never enters Python merely to be filtered.
- Full-account collection remains complete but streams success payloads and stores
  only normalized nonzero positions plus all open orders.

- [ ] **Step 1: Write failing episode/external tests**

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_reservation_only_row_uses_persisted_instrument_and_episode` | Active claim, no exchange position | Current row copies claim instrument and episode |
| `test_flat_current_row_clears_current_episode_id` | Previously owned position becomes flat | Current episode is null and slot is released |
| `test_external_known_instrument_has_null_episode_and_global_hold` | Exchange position maps to registry but no Ticket owns it | `external_unowned`, null episode, new entry false |
| `test_unresolved_instrument_creates_budget_blocker_without_fake_exposure` | Exchange symbol has no unique instrument | No fabricated exposure row; budget blocker is identity missing |
| `test_exchange_command_conserves_exposure_episode_id` | Ticket and command use same episode | Command persists exact episode; mismatch rejects |
| `test_budget_hot_path_filters_terminal_history_in_sql` | 100 terminal claims plus one active claim | Repository returns one active row; no Python terminal filter |
| `test_budget_hot_path_overflow_reads_only_policy_limit_plus_one` | Policy limit 2 and 100 corrupt active claims | Three rows materialize, overflow blocker returns, remaining rows are not loaded |
| `test_command_evidence_is_scoped_to_current_account_tickets` | Other-account and terminal command history exists | Only current account's nonterminal Ticket commands return |
| `test_hot_path_uses_no_select_star_or_runtime_reflection` | SQL recorder wraps the connection | No `SELECT *`, `information_schema`, `autoload_with` or `read_control_state` |
| `test_large_account_object_streams_required_scalars_without_tree` | Valid `/account` object contains large nested assets/positions arrays | Required top-level budget scalars complete; ignored nested rows are not retained |
| `test_large_position_and_order_arrays_stream_without_truncation` | Each valid response is several MiB and contains many items | All nonzero positions and all open orders retained; no total-byte or typed-row cap |
| `test_malformed_or_interrupted_stream_fails_closed` | JSON ends mid-item after prior valid items | `account_risk_snapshot_fetch_failed`; no partial snapshot published |
| `test_transport_never_calls_unbounded_read` | Response spy rejects `read()` without positive size | Every success read is positive and at most the configured chunk size |
| `test_error_body_keeps_only_masked_64k_excerpt` | HTTP error body exceeds 64 KiB and contains secret-like text | Diagnostic is bounded/masked; snapshot fails closed |

- [ ] **Step 2: Run focused tests RED**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py
```

- [ ] **Step 3: Implement exact bounded PG readers**

`account_capacity_hot_path_repository.py` owns explicit-column SQL only and exposes:

```python
T = TypeVar("T")


@dataclass(frozen=True)
class AccountExposureCurrentRecord:
    account_exposure_current_id: str
    owner_ticket_id: str | None
    exposure_state: str
    actual_directional_risk: Decimal
    held_risk: Decimal
    unreflected_pending_margin: Decimal
    reconciliation_state: str
    position_slot_claimed: bool
    first_blocker: str | None


@dataclass(frozen=True)
class AccountCapacityClaimRecord:
    budget_reservation_id: str
    ticket_id: str | None
    exchange_instrument_id: str
    exposure_episode_id: str
    status: str
    risk_at_stop: Decimal
    reserved_margin: Decimal
    margin_accounting_state: str


@dataclass(frozen=True)
class AccountCommandEvidenceRecord:
    ticket_id: str
    exchange_instrument_id: str
    exchange_order_id: str | None
    client_order_id: str | None
    parent_order_id: str | None
    order_role: str
    command_state: str


@dataclass(frozen=True)
class BoundedCurrentRows(Generic[T]):
    rows: tuple[T, ...]
    overflow: bool


def load_live_exposure_rows(
    conn: sa.Connection,
    *,
    account_id: str,
    max_concurrent_positions: int,
) -> BoundedCurrentRows[AccountExposureCurrentRecord]:
    """Read at most policy limit plus one non-flat/current exposure rows."""


def load_effective_reservation_rows(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
    max_concurrent_positions: int,
) -> BoundedCurrentRows[AccountCapacityClaimRecord]:
    """Read active/consumed claims only, bounded by policy limit plus one."""


def load_current_command_identity_evidence(
    conn: sa.Connection,
    *,
    account_id: str,
    ticket_ids: tuple[str, ...],
) -> tuple[AccountCommandEvidenceRecord, ...]:
    """Read nonterminal commands for the already-bounded current Ticket set."""
```

The SQL must use named columns, exact account/profile predicates, current status
predicates, stable `ORDER BY`, and `LIMIT max_concurrent_positions + 1`. Overflow is a
typed fail-closed result; no caller issues a second query to load the remainder.

The three query shapes are fixed as:

```sql
SELECT account_exposure_current_id, owner_ticket_id, exposure_state,
       actual_directional_risk, held_risk, unreflected_pending_margin,
       reconciliation_state, position_slot_claimed, first_blocker
FROM brc_account_exposure_current
WHERE account_id = :account_id
  AND (exposure_state NOT IN ('flat', 'closed') OR first_blocker IS NOT NULL)
ORDER BY account_exposure_current_id
LIMIT :policy_limit_plus_one;

SELECT budget_reservation_id, ticket_id, exchange_instrument_id,
       exposure_episode_id, status, risk_at_stop, reserved_margin,
       margin_accounting_state
FROM brc_budget_reservations
WHERE account_id = :account_id
  AND runtime_profile_id = :runtime_profile_id
  AND status IN ('active', 'consumed')
ORDER BY budget_reservation_id
LIMIT :policy_limit_plus_one;

SELECT c.ticket_id, c.exchange_instrument_id, c.exchange_order_id,
       c.client_order_id, c.parent_order_id, c.order_role, c.command_state
FROM brc_ticket_bound_exchange_commands AS c
WHERE c.ticket_id = ANY(:current_ticket_ids)
  AND c.command_state NOT IN ('confirmed_rejected', 'reconciled_absent')
ORDER BY c.ticket_id, c.operation_submit_command_id;
```

Delete `account_budget_current._rows()`. Replace ownership's broad command statement
with `load_current_command_identity_evidence()`. Table metadata is not reflected inside
Action-Time; the repository uses fixed `sa.text()` statements matching migrations 126-128.

- [ ] **Step 4: Implement streaming, function-preserving HTTP reads**

Add `ijson>=3.5.1,<4.0.0` to `requirements.txt`. `streaming_http_json.py` wraps
`ijson.parse()` and `ijson.items()` so nested objects and arrays are consumed without
first materializing the root document. Do not implement a home-grown parser with
`json.JSONDecoder.raw_decode`, because a large top-level object would still require the
entire object in memory. The transport default is a configurable 64 KiB positive-size
read and must never invoke unbounded `read()`.

```python
def iter_json_events(
    response: BinaryIO,
    *,
    chunk_bytes: int = 65_536,
) -> Iterator[tuple[str, str, object]]:
    """Yield nested JSON events with transport backpressure."""


def read_masked_error_excerpt(
    response: BinaryIO, *, max_bytes: int = 65_536
) -> str:
    """Retain diagnostic text only; never publish it as account truth."""
```

`binance_usdm_streaming_signed_reader.py` owns signing and response opening. Success arrays
are mapped item-by-item: PositionRisk drops zero-position rows immediately; regular and
Algo order readers retain every open order. The Account and Position Mode object readers
consume only the required top-level scalar events and skip nested collections without
building a general-purpose object tree. Error bodies retain at most 64 KiB after masking.
The two Budget runtime scripts stop importing script-local `_request_json()` and construct
this infrastructure reader instead.

The account snapshot provider returns `snapshot_ready=False` on streaming/parser failure.
It must not truncate a valid list, impose a response-byte/typed-row business cap, reject a
large valid item merely because of size, or turn a partial list into a complete snapshot.

- [ ] **Step 5: Remove all exposure identity fabrication**

Delete both position and reservation fallbacks shaped as:

```python
f"{snapshot.exchange_id}:{symbol}"
```

Reservation-only rows require persisted claim identity. Unresolved raw exchange rows
remain in the account fact snapshot and set
`account_exchange_instrument_identity_missing` on Account Budget Current.

- [ ] **Step 6: Project episode-aware current state**

Owned working/open exposure copies the Ticket episode. External/unowned exposure uses
`current_exposure_episode_id=None`. Flat rows clear the episode ID but retain normal
Ticket/claim/lifecycle history outside the current projection. Budget aggregation calls
the bounded repository and never reloads flat rows merely to discard them.

- [ ] **Step 7: Propagate lineage after Ticket**

Require matching `exposure_episode_id` on entry/protection command materialization,
post-submit reconciliation and Live Outcome. A mismatch is a hard identity blocker;
recovery may not invent a new episode.

- [ ] **Step 8: Run focused tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py
```

- [ ] **Step 9: Commit checkpoint C2**

```bash
git add \
  src/infrastructure/account_capacity_hot_path_repository.py \
  src/infrastructure/streaming_http_json.py \
  src/infrastructure/binance_usdm_streaming_signed_reader.py \
  src/infrastructure/binance_usdm_account_risk_snapshot.py \
  requirements.txt \
  src/application/action_time/account_exchange_ownership.py \
  src/application/action_time/account_exposure_current.py \
  src/application/action_time/account_budget_current.py \
  src/domain/ticket_bound_exchange_command.py \
  src/application/action_time/exchange_command.py \
  src/application/action_time/post_submit_reconciliation_tick.py \
  src/application/action_time/live_outcome_ledger.py \
  scripts/materialize_action_time_ticket_sequence.py \
  scripts/run_ticket_bound_lifecycle_maintenance_once.py \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_ticket_bound_exchange_command_materialization.py \
  tests/unit/test_ticket_bound_exchange_command.py \
  tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py
git commit -m "feat: bound account truth and conserve exposure identity"
```

### Task 7: FinalGate Semantic Claim Revalidation

**Task ID:** `DAR-AI-07`

**Files:**

- Modify: `src/domain/account_capacity_claim.py`
- Modify: `src/application/action_time/finalgate_preflight.py`
- Modify: `src/application/action_time/runtime_safety_state.py`
- Modify: `tests/unit/test_account_capacity_finalgate_guard.py`
- Modify: `tests/unit/test_action_time_finalgate_preflight_materialization.py`
- Modify: `tests/unit/test_dual_position_account_risk_release_acceptance.py`

**Interfaces:**

- FinalGate still consumes `ticket_id` only.
- Claim revalidation preserves original snapshot IDs for audit but uses latest
  PG/current semantic capacity.
- Same Invocation claim is validated or invalidated; it is never rewritten or regenerated.

- [ ] **Step 1: Replace the old projection-version test matrix**

| Test name | Arrange | Required assertion |
| --- | --- | --- |
| `test_new_snapshot_id_with_same_semantic_capacity_passes` | New snapshot ID, equal safe totals | No blocker |
| `test_claim_hash_mismatch_blocks` | Mutate immutable stored quantity | `account_capacity_claim_hash_mismatch` |
| `test_claim_counted_zero_or_twice_blocks` | Budget lineage count is zero, then two | Both cases fail closed with distinct count blocker |
| `test_own_claim_is_excluded_before_capacity_recheck` | Aggregate already contains this claim exactly once | Claim is not double-counted and passes |
| `test_new_external_position_blocks` | Latest account projection adds external exposure | Global new-entry hold blocker |
| `test_rule_change_that_keeps_order_legal_passes` | Rule snapshot changes but exact prepared order remains legal | No rule blocker |
| `test_rule_change_that_invalidates_qty_blocks` | New quantity step makes prepared quantity illegal | Claim/Ticket invalidates before dispatch |
| `test_policy_or_primary_cluster_change_invalidates` | Policy event or primary membership differs | Entry blocked; original claim remains auditable |
| `test_entry_invalidation_does_not_block_protection_or_exit` | Command already dispatched | Recovery/protection path does not invoke new-entry gate |
| `test_finalgate_never_loads_terminal_history` | 100000 terminal claims/commands plus one current Ticket | Same result and bounded query rows as empty history |
| `test_finalgate_rejects_generic_control_state_reader` | `read_control_state()` spy raises | FinalGate succeeds through exact Ticket/current selectors only |

- [ ] **Step 2: Run tests RED**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py
```

Expected: current code blocks on projection-version change alone and lacks claim hash/rule checks.

- [ ] **Step 3: Implement pure own-claim exclusion arithmetic**

```python
def revalidate_capacity_totals(
    *,
    current_portfolio_held_risk: Decimal,
    current_primary_cluster_held_risk: Decimal,
    current_pending_margin: Decimal,
    current_claimed_position_slots: int,
    available_balance: Decimal,
    claim_risk: Decimal,
    claim_margin: Decimal,
    portfolio_limit: Decimal,
    cluster_limit: Decimal,
    margin_limit: Decimal,
    max_concurrent_positions: int,
) -> Sequence[str]:
    other_risk = max(Decimal("0"), current_portfolio_held_risk - claim_risk)
    other_cluster = max(
        Decimal("0"), current_primary_cluster_held_risk - claim_risk
    )
    other_margin = max(Decimal("0"), current_pending_margin - claim_margin)
    blockers: list[str] = []
    if other_risk + claim_risk > portfolio_limit:
        blockers.append("portfolio_open_risk_capacity_exhausted")
    if other_cluster + claim_risk > cluster_limit:
        blockers.append("risk_cluster_open_risk_capacity_exhausted")
    if other_margin + claim_margin > margin_limit:
        blockers.append("portfolio_initial_margin_capacity_exhausted")
    if other_margin + claim_margin > available_balance:
        blockers.append("available_balance_capacity_exhausted")
    if current_claimed_position_slots > max_concurrent_positions:
        blockers.append("max_concurrent_positions_reached")
    return tuple(blockers)
```

The PG query must independently prove the claim is counted exactly once before this
arithmetic, including exactly one claimed position slot. Do not use subtraction to hide
a missing or duplicate claim. `current_claimed_position_slots` already contains this
claim, so the valid boundary is `<= max_concurrent_positions`; it is not incremented again.

- [ ] **Step 4: Replace physical snapshot equality with semantic checks**

Retain original snapshot IDs in the claim. Remove
`account_budget_projection_version_changed` as a blocker when the latest projection
is fresh and semantically contains the exact claim once. Keep policy event, scope,
account, instrument, rule legality, capacity and external/unknown blockers fail-closed.
All reads consume the typed hot-path repository from Task 6: one exact Ticket/claim,
one Account Budget Current row, at most policy-limit-plus-one exposure/reservation rows,
and exact current rule/cluster rows. No FinalGate code may call `read_control_state()`,
reflect tables, select terminal history or build an Owner readmodel.

- [ ] **Step 5: Preserve lifecycle recovery authority**

Run the new entry-only claim gate before dispatch. After dispatch/unknown/fill, recovery,
protection, TP, Runner, exit, reconciliation and settlement consume frozen lineage and
must not call the new-entry capacity gate.

- [ ] **Step 6: Run focused tests GREEN**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
```

- [ ] **Step 7: Commit checkpoint D1**

```bash
git add \
  src/domain/account_capacity_claim.py \
  src/application/action_time/finalgate_preflight.py \
  src/application/action_time/runtime_safety_state.py \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_action_time_finalgate_preflight_materialization.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
git commit -m "fix: revalidate account capacity by current semantics"
```

### Task 8: Delete Fallbacks And Run Production-Shaped Certification

**Task ID:** `DAR-AI-08`

**Files:**

- Modify: `tests/unit/test_action_time_ticket_materialization_sequence.py`
- Modify: `tests/unit/test_dual_position_account_risk_release_acceptance.py`
- Modify: `tests/integration/test_account_capacity_postgres.py`
- Create: `tests/integration/test_asset_neutral_account_risk_full_chain.py`
- Create: `tests/integration/test_account_capacity_hot_path_scale.py`
- Modify: `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md`
- Modify: `docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_IMPLEMENTATION_PLAN.md`

**Interfaces:**

- One production-shaped test starts before Candidate Scope resolution and reaches
  Ticket + non-executing FinalGate preparation without exchange write.
- Old symbol/prefix/mapping fallback paths are absent from Action-Time/account-risk code.
- A PostgreSQL scale test proves that terminal history changes neither hot-path result
  cardinality nor Python memory complexity.

- [x] **Step 1: Write the full-chain test before final cleanup**

The test must start from PG Candidate Scope + exact instrument + current rule/account/
cluster snapshots, then exercise:

```text
RuntimeLaneIdentity
-> ActionTimeInvocation
-> lock Account Budget Current
-> capacity decision
-> immutable claim
-> Ticket + exposure episode
-> FinalGate semantic revalidation
-> lifecycle release
-> second different-instrument capacity claim
```

It must assert:

```python
assert gateway.exchange_write_called is False
assert first_claim.instrument.exchange_instrument_id != second_claim.instrument.exchange_instrument_id
assert first_ticket.exposure_episode_id == first_claim.exposure_episode_id
assert released_budget.claimed_position_slots == 0
```

- [x] **Step 2: Add negative production-shaped matrix**

Cover all six current Event Specs plus:

```text
same symbol / different instrument
missing exact instrument
stale rule snapshot
wrong asset class
wrong primary cluster snapshot
duplicate Invocation claim
external unowned position
unknown exchange outcome
claim hash mutation
terminal released history
100000 terminal reservations/commands/rule-membership rows
multi-MiB valid account/position/order responses
```

`test_account_capacity_hot_path_scale.py` seeds history with PostgreSQL
`generate_series()` so the test does not create 300000 Python objects. After warming the
typed repository, it runs the same current read against the small and large fixtures under
`tracemalloc` and asserts:

```python
assert large.rows == small.rows
assert large.sql_statement_count == small.sql_statement_count
assert large.materialized_row_count == small.materialized_row_count
assert large.peak_bytes - small.peak_bytes <= 16 * 1024 * 1024
assert "read_control_state" not in large.call_names
assert "SELECT *" not in large.normalized_sql
assert "information_schema" not in large.normalized_sql
assert large.history_seq_scan_count == 0
```

The 16 MiB assertion measures additional Python allocation caused by historical data;
it is not an OS/process memory limit and does not cap legitimate active account facts.

- [x] **Step 3: Delete obsolete fallback code**

Run:

```bash
rg -n 'f"\{snapshot\.exchange_id\}:\{.*symbol|LIKE .binance_usdm:%|_exchange_instrument_id\(' \
  src/application src/domain src/infrastructure migrations
```

Expected after cleanup: no active Action-Time/account-risk consumer constructs or
parses instrument identity. Historical migrations may retain literal provenance only
when no runtime consumer imports it.

Run the Budget hot-path static guard:

```bash
rg -n 'read_control_state\(|SELECT \*|autoload_with=|def _rows\(' \
  src/application/action_time/account_budget_current.py \
  src/application/action_time/account_exchange_ownership.py \
  src/application/action_time/finalgate_preflight.py \
  src/infrastructure/account_capacity_hot_path_repository.py
```

Expected: no matches. Audit/forensics readers outside these production Budget files are
not deleted by this task and remain outside Action-Time cadence.

- [x] **Step 4: Run focused unit regression**

```bash
python3 -m pytest -q \
  tests/unit/test_account_capacity_hot_path_repository.py \
  tests/unit/test_streaming_http_json.py \
  tests/unit/test_binance_usdm_account_risk_snapshot.py \
  tests/unit/test_instrument_risk_identity.py \
  tests/unit/test_account_capacity_claim.py \
  tests/unit/test_runtime_lane_identity.py \
  tests/unit/test_runtime_lane_identity_service.py \
  tests/unit/test_account_risk.py \
  tests/unit/test_account_risk_policy.py \
  tests/unit/test_account_capacity_reservation.py \
  tests/unit/test_account_capacity_materialization.py \
  tests/unit/test_account_exchange_ownership.py \
  tests/unit/test_account_exposure_current.py \
  tests/unit/test_account_budget_current.py \
  tests/unit/test_account_capacity_finalgate_guard.py \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py
```

- [x] **Step 5: Run PostgreSQL integration without skips**

```bash
test -n "$BRC_LOCAL_TEST_POSTGRES_DSN"
test -n "$BRC_LOCAL_TEST_POSTGRES_SCHEMA"
BRC_LOCAL_TEST_POSTGRES_DSN="$BRC_LOCAL_TEST_POSTGRES_DSN" \
BRC_LOCAL_TEST_POSTGRES_SCHEMA="$BRC_LOCAL_TEST_POSTGRES_SCHEMA" \
python3 -m pytest -q \
  tests/integration/test_account_capacity_postgres.py \
  tests/integration/test_runtime_lane_identity_certification.py \
  tests/integration/test_asset_neutral_account_risk_full_chain.py \
  tests/integration/test_asset_neutral_account_risk_migration_scale.py \
  tests/integration/test_account_capacity_hot_path_scale.py
```

Expected: all selected tests pass and pytest reports zero skipped tests. The scale test
must report 100000 rows in each history family while the typed current result remains
bounded by policy-limit-plus-one.

- [x] **Step 6: Run authority, output and performance gates**

```bash
git diff --check
python3 scripts/validate_current_docs_authority.py
python3 scripts/validate_output_artifact_scope.py --git-status --git-tracked
python3 scripts/audit_production_runtime_file_io.py
```

Required results:

```text
current_docs_authority_valid
output_artifact_scope_valid
suspicious_runtime_file_authority=0
frequent_report_write=0
performance_risk.status=clear
```

- [x] **Step 7: Measure Action-Time cadence**

Use the existing refresh timing telemetry to assert:

```text
no-signal new JSON/MD files = 0
no-signal new claim/Ticket rows = 0/0
no-signal new exposure_episode_id values = 0
one Invocation claim/Ticket rows = 1/1
one Invocation distinct exposure_episode_id values across claim/Ticket = 1
terminal history rows materialized by hot path = 0
current exposure/reservation rows <= max_concurrent_positions + 1
Action-Time SELECT * / table reflection / read_control_state calls = 0
stream read chunk bytes = 65536 (configurable default)
unbounded response.read calls = 0
response-total / typed-row rejection caps = 0
all nonzero positions and all open orders conserved = true
capacity transaction network calls = 0
capacity transaction subprocess calls = 0
Action-Time refresh elapsed <= 30 seconds
```

- [x] **Step 8: Announce and run the full suite once**

After notifying the Owner that the approximately 11-minute gate is starting:

```bash
python3 -m pytest -q
```

Expected: exit code 0. Any unrelated pre-existing failure is recorded separately;
do not weaken or skip account-risk gates to make the suite green.

- [x] **Step 9: Update documents with observed evidence only**

Change design/plan status to local implementation complete only after all required
commands actually pass. Record exact commit, test counts, PostgreSQL non-skip proof,
file-I/O audit and Action-Time timing. Do not claim deployed or live-enabled.

- [x] **Step 10: Commit checkpoint D2**

```bash
git add \
  tests/unit/test_action_time_ticket_materialization_sequence.py \
  tests/unit/test_dual_position_account_risk_release_acceptance.py \
  tests/integration/test_account_capacity_postgres.py \
  tests/integration/test_asset_neutral_account_risk_full_chain.py \
  tests/integration/test_account_capacity_hot_path_scale.py \
  docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md \
  docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_DESIGN.md \
  docs/current/DUAL_POSITION_ACCOUNT_RISK_V0_ASSET_NEUTRAL_IDENTITY_EXTENSION_IMPLEMENTATION_PLAN.md
git commit -m "test: certify asset-neutral account risk chain"
```

## Phase Acceptance Gates

| Checkpoint | Included tasks | Reviewer may approve when |
| --- | --- | --- |
| **A — Contract and schema** | 1-2 | Types are pure; migrations preserve history and reject incomplete active rows |
| **B — Exact identity and rules** | 3-4 | Symbol/prefix inference is absent from Action-Time and primary cluster semantics are versioned |
| **C — Claim and bounded account truth** | 5-6 | One Invocation produces one atomic claim/Ticket pair; account facts remain complete while hot-path rows and raw buffers stay bounded |
| **D — FinalGate and certification** | 7-8 | Semantic revalidation, PostgreSQL concurrency, 100000-row history scale, full-chain negative matrix and performance gates pass |

Each checkpoint is an independently reviewable local commit range. A failed checkpoint
does not authorize continuing into later tasks by adding compatibility fallbacks.

## Stop Conditions

Stop the local execution and report the exact blocker when any of these occurs:

- an active/current row cannot be historically mapped to one exact instrument;
- terminal reservation cleanup finds exchange write, unknown command or slot claim;
- migration would need destructive production cleanup;
- the same Invocation can commit two reservation IDs;
- immutable claim payload can be changed without hash failure;
- an external/unowned position is treated as system-owned;
- FinalGate requires loose symbol/side parameters instead of `ticket_id`;
- Operation Layer or gateway exchange write is reached by a test in this plan;
- PostgreSQL integration is skipped or unavailable;
- file-I/O audit reports runtime file authority or frequent report writes;
- any Budget Action-Time path calls `read_control_state()`, uses `SELECT *`, reflects
  tables at runtime or filters terminal history in Python;
- a valid account response is truncated by bytes, item count, symbol count or typed-row cap;
- large terminal history changes materialized current row count or adds more than 16 MiB
  of Python allocation relative to the small fixture;
- Action-Time exceeds 30 seconds because of the new indexed PG work;
- implementation requires changing Owner risk parameters, live profile, StrategyGroup
  scope or production stage.

## Capability Unlocked

After local completion, the system will have a **single asset-neutral account-capacity
identity contract** across Candidate Scope, Reservation, Ticket, Exposure Current,
FinalGate and lifecycle lineage. This makes future equity-linked and precious-metals
adapters possible without copying the crypto budget engine, while leaving their actual
live scope, session, expiry, settlement and risk policy for future Owner authorization.
The same completion also proves that Budget Action-Time cost follows current active facts,
not accumulated Ticket history, while complete account responses are streamed rather than
functionally truncated.

## Next Engineering Bottleneck

The next bottleneck after this plan is not more schema work. It is a separately scoped
**shadow certification and deployment decision** for the reviewed Dual-Position V0,
followed by production observation of whether a protected first position can coexist
with a valid second different-instrument opportunity without identity, capacity,
protection or reconciliation drift.
