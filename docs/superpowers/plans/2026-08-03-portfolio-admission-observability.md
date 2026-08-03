# Portfolio Admission Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one forward-only Trading Kernel release that fixes Episode re-arm semantics, records immutable AdmissionDecision and bounded Shadow Outcome evidence, and enforces Policy v4 Family/directional/materialization limits without expanding exchange-write authority.

**Architecture:** Observation owns a typed rising-edge Episode projection and idle-only Shadow projection. Entry remains globally serialized; it freezes candidate-set and portfolio usage into one AdmissionDecision, then either atomically issues the existing Claim/Ticket/Command chain or atomically records a terminal rejection. Registry owns Episode policy and Exposure Family; Owner Policy owns limits.

**Tech Stack:** Python 3.12, Pydantic v2 frozen models, SQLAlchemy Core async, PostgreSQL/Alembic, pytest/pytest-asyncio, Decimal, Ruff, Mypy, systemd deployment scripts.

## Global Constraints

- Preserve the sole authoritative chain: Observation -> StrategySignal -> Readiness/Authority -> CapacityClaim -> immutable Ticket -> durable Exchange Command -> protected lifecycle -> reconciliation -> settlement -> review.
- One Exposure Episode owns at most one Ticket; adding to a position remains forbidden.
- Network I/O remains outside PostgreSQL transactions.
- Rejected AdmissionDecision and every Shadow Outcome create zero Ticket, Reservation, Netting Domain hold, or Exchange Command.
- Fixed exchange leverage remains `5x`; max leverage remains `10`; margin mode remains `cross`.
- Policy v4 is exactly `3` Tickets, `0.02` per Ticket stop risk, `0.06` gross stop risk, `0.30` per Ticket initial margin, `0.90` gross initial margin, `0.50` minimum materialization ratio, and `0.04` directional stop-risk limit.
- Family limits are exactly `long_continuation=1`, `opening_range=2`, `rally_failure_short=1`.
- Schema changes use exact flat `0002_sor_v3_strategy_group_capacity -> 0003_portfolio_admission_observability`; no downgrade, fallback, dual write, or active-position handover.
- Deployment and postflight keep Entry stopped, disabled, and write-fenced.

---

### Task 1: Pure Episode policy and Registry vNext

**Files:**
- Create: `src/trading_kernel/domain/exposure_episode.py`
- Modify: `src/trading_kernel/domain/strategy_registry.py`
- Modify: `src/trading_kernel/application/produce_strategy_signal.py`
- Test: `tests/trading_kernel/unit/test_exposure_episode.py`
- Test: `tests/trading_kernel/unit/test_strategy_registry.py`
- Test: `tests/trading_kernel/integration/test_live_replay_detector_parity.py`

**Interfaces:**
- Produces `EpisodePolicy = Literal["rising_edge", "session_reference"]` and `ExposureFamily = Literal["long_continuation", "opening_range", "rally_failure_short"]`.
- Produces frozen `ExposureEpisodeState` and `ExposureEpisodeTransition`.
- Produces `advance_exposure_episode(contract, current, detector_status, occurred_at_ms, exchange_instrument_id) -> ExposureEpisodeTransition`.
- Changes `produce_strategy_signal` to accept the keyword `exposure_episode_id: str | None = None`; rising-edge callers pass the resolved ID and session-reference callers continue using identity facts.

- [ ] **Step 1: Write RED unit tests for rising-edge transitions**

```python
def test_continuous_trigger_reuses_one_rising_edge_episode() -> None:
    first = advance_exposure_episode(contract, None, DetectorStatus.TRIGGERED, 1_000, ETH)
    second = advance_exposure_episode(contract, first.current, DetectorStatus.TRIGGERED, 2_000, ETH)
    assert second.exposure_episode_id == first.exposure_episode_id
    assert second.created_new_episode is False

def test_false_closed_bar_rearms_the_next_trigger() -> None:
    first = advance_exposure_episode(contract, None, DetectorStatus.TRIGGERED, 1_000, ETH)
    armed = advance_exposure_episode(contract, first.current, DetectorStatus.NOT_TRIGGERED, 2_000, ETH)
    second = advance_exposure_episode(contract, armed.current, DetectorStatus.TRIGGERED, 3_000, ETH)
    assert second.exposure_episode_id != first.exposure_episode_id
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/unit/test_exposure_episode.py -q`

Expected: collection/import failure because `exposure_episode.py` does not exist.

- [ ] **Step 3: Implement the pure reducer and canonical identities**

Use SHA-256 over canonical JSON containing exact Event version, instrument, side, and first rising-edge occurrence. Invalid detector status is not accepted by the reducer; NOT_TRIGGERED never creates an Episode.

- [ ] **Step 4: Verify episode unit GREEN**

Run: `pytest tests/trading_kernel/unit/test_exposure_episode.py -q`

Expected: all Episode tests pass.

- [ ] **Step 5: Write RED Registry tests**

Assert exact current contracts:

```python
assert contract_map["CPM-LONG"].strategy_version_id == "sgv:CPM-RO-001:v3"
assert contract_map["CPM-LONG"].episode_policy == "rising_edge"
assert contract_map["CPM-LONG"].exposure_family == "long_continuation"
assert contract_map["SOR-SHORT"].episode_policy == "session_reference"
assert contract_map["SOR-SHORT"].exposure_family == "opening_range"
```

- [ ] **Step 6: Verify Registry RED**

Run: `pytest tests/trading_kernel/unit/test_strategy_registry.py -q`

Expected: failures for missing Registry fields and old v1 identities.

- [ ] **Step 7: Implement Registry vNext and producer contract**

Add required non-default fields `episode_policy`, `exposure_family`, and `shadow_horizon_bars`. Bump CPM/MPG/MI/BRF2 from v2 to v3 and SOR from v3 to v4. Assign new ExitPolicy identities to every new Event version while keeping lifecycle calculations unchanged. `produce_strategy_signal` must reject a missing explicit Episode ID for `rising_edge` and reject an explicit ID for `session_reference`.

- [ ] **Step 8: Verify Registry and Live/Replay GREEN**

Run: `pytest tests/trading_kernel/unit/test_strategy_registry.py tests/trading_kernel/integration/test_live_replay_detector_parity.py -q`

Expected: all tests pass with unchanged detector truth and versioned identity.

- [ ] **Step 9: Commit Task 1**

```text
git add src/trading_kernel/domain/exposure_episode.py src/trading_kernel/domain/strategy_registry.py src/trading_kernel/application/produce_strategy_signal.py tests/trading_kernel/unit/test_exposure_episode.py tests/trading_kernel/unit/test_strategy_registry.py tests/trading_kernel/integration/test_live_replay_detector_parity.py
git commit -m "feat(kernel): version exposure episode semantics"
```

### Task 2: PostgreSQL Episode projection and Observation integration

**Files:**
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/observe_strategy_scope.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_signal_repository.py`
- Test: `tests/trading_kernel/integration/test_observation_to_signal.py`
- Test: `tests/trading_kernel/integration/test_live_replay_detector_parity.py`

**Interfaces:**
- Add `SignalRepository.lock_exposure_episode(episode_domain_key) -> ExposureEpisodeState | None`.
- Add `SignalRepository.save_exposure_episode(state, expected_version) -> None`.
- Observation calls the pure reducer only after current Facts persist and inside the same short transaction.

- [ ] **Step 1: Write RED integration tests EPI-001 through EPI-010**

Use disposable PostgreSQL. The continuous CPM test runs two observations with different closed-bar times and asserts one `brc_signal_events` row and one stable `exposure_episode_id`. The true→false→true test asserts two Signal rows and two Episode IDs.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/integration/test_observation_to_signal.py -q`

Expected: continuous CPM produces two Episode identities under current occurred-at fallback.

- [ ] **Step 3: Add current table metadata and repository locking**

Define `brc_exposure_episode_current` with exact PK, state-shape checks, monotonic projection version, and `SELECT ... FOR UPDATE`. Do not touch frozen `migrations/trading_kernel/v4_schema.py`.

- [ ] **Step 4: Integrate the reducer into Observation**

For active `rising_edge` scopes, apply state transition before Signal production. For NOT_TRIGGERED persist re-arm and `signal_absent` together. Warming and invalid observations perform zero Episode writes. Session-reference behavior remains unchanged.

- [ ] **Step 5: Verify GREEN and concurrency behavior**

Run: `pytest tests/trading_kernel/integration/test_observation_to_signal.py tests/trading_kernel/integration/test_live_replay_detector_parity.py -q`

Expected: all tests pass; the concurrency case creates one Episode.

- [ ] **Step 6: Commit Task 2**

```text
git add src/trading_kernel/application/ports.py src/trading_kernel/application/observe_strategy_scope.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_signal_repository.py tests/trading_kernel/integration/test_observation_to_signal.py tests/trading_kernel/integration/test_live_replay_detector_parity.py
git commit -m "feat(kernel): persist rising edge episodes"
```

### Task 3: Immutable AdmissionDecision and atomic Entry evidence

**Files:**
- Create: `src/trading_kernel/domain/admission_decision.py`
- Modify: `src/trading_kernel/domain/arbitration.py`
- Modify: `src/trading_kernel/application/select_entry_candidate.py`
- Modify: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `src/trading_kernel/interfaces/entry_worker.py`
- Test: `tests/trading_kernel/unit/test_arbitration.py`
- Test: `tests/trading_kernel/unit/test_admission_decision.py`
- Test: `tests/trading_kernel/integration/test_signal_to_ticket.py`
- Test: `tests/trading_kernel/integration/test_issue_ticket.py`

**Interfaces:**
- Add frozen `CandidateSetSnapshot` with `ranked_signal_event_ids`, `candidate_count`, and canonical digest.
- Add frozen `AdmissionDecision` and `AdmissionDecisionStatus`.
- Add `AdmissionDecisionRepository.add`, `get_for_signal`, and bounded list methods.
- Add `KernelUnitOfWork.admission_decisions`.

- [ ] **Step 1: Write RED candidate digest and Decision model tests**

```python
def test_candidate_digest_is_input_order_independent_after_ranking() -> None:
    left = freeze_candidate_set((candidate_b, candidate_a))
    right = freeze_candidate_set((candidate_a, candidate_b))
    assert left.digest == right.digest

def test_rejected_decision_forbids_ticket_identity() -> None:
    payload = _valid_rejected_decision_payload()
    with pytest.raises(ValueError):
        AdmissionDecision.model_validate({**payload, "ticket_id": "ticket:x"})
```

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/unit/test_admission_decision.py tests/trading_kernel/unit/test_arbitration.py -q`

Expected: missing Decision interfaces.

- [ ] **Step 3: Implement pure candidate and Decision models**

Use canonical JSON digests. Candidate summary contains only rank, Signal/Event/Strategy identity, instrument, side, and occurrence time. Do not include mutable account facts.

- [ ] **Step 4: Verify unit GREEN**

Run: `pytest tests/trading_kernel/unit/test_admission_decision.py tests/trading_kernel/unit/test_arbitration.py -q`

Expected: all unit tests pass.

- [ ] **Step 5: Write RED transaction tests ADM-001 through ADM-012**

Inject repository failure after `issue_ticket` writes and assert transaction rollback leaves zero Decision, Claim, Ticket, Reservation, and Command. Assert one rejected Decision and no trading authority for capacity refusal.

- [ ] **Step 6: Verify integration RED**

Run: `pytest tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_issue_ticket.py -q`

Expected: current issuance has no AdmissionDecision rows.

- [ ] **Step 7: Add PostgreSQL table and repository**

Define `brc_admission_decisions` with unique `signal_event_id`, admitted/rejected shape checks, SHA-256 candidate and decision digests, and query indexes on `decided_at_ms`, `first_blocker`, and Strategy/Event identity.

- [ ] **Step 8: Integrate atomic admitted/rejected persistence**

`issue_ready_signal` freezes the current candidate set after revalidation. Admitted Decision is added after `issue_ticket` inside the same UoW. `_refuse` builds and inserts rejected Decision before saving terminal Readiness. Entry action-facts timeout records a rejected infrastructure Decision with no Shadow eligibility.

- [ ] **Step 9: Verify integration GREEN**

Run: `pytest tests/trading_kernel/integration/test_signal_to_ticket.py tests/trading_kernel/integration/test_issue_ticket.py tests/trading_kernel/integration/test_global_runtime_workers.py -q`

Expected: all tests pass and rejected paths create no Exchange Command.

- [ ] **Step 10: Commit Task 3**

```text
git add src/trading_kernel/domain/admission_decision.py src/trading_kernel/domain/arbitration.py src/trading_kernel/application/select_entry_candidate.py src/trading_kernel/application/issue_ready_signal.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/infrastructure/pg_unit_of_work.py src/trading_kernel/interfaces/entry_worker.py tests/trading_kernel
git commit -m "feat(kernel): record immutable admission decisions"
```

### Task 4: Policy v4, Exposure Family, direction, and minimum materialization

**Files:**
- Modify: `src/trading_kernel/domain/capacity.py`
- Modify: `src/trading_kernel/domain/capacity_sizing.py`
- Modify: `src/trading_kernel/application/build_capacity_claim.py`
- Modify: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/application/revalidate_entry_dispatch.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `src/trading_kernel/domain/ticket.py`
- Test: `tests/trading_kernel/unit/test_capacity.py`
- Test: `tests/trading_kernel/unit/test_capacity_sizing.py`
- Test: `tests/trading_kernel/integration/test_capacity_claim_to_ticket.py`
- Test: `tests/trading_kernel/integration/test_runtime_authority_seed.py`

**Interfaces:**
- Replace current StrategyGroup capacity input with `active_family_ticket_count`, `family_ticket_limit`, and `directional_risk_at_stop`.
- Extend `CapacityPolicy` with typed `family_ticket_limits`, `directional_stop_risk_limit_fraction`, and `min_materialization_ratio`.
- Extend Claim/Ticket with exact Family and action-time limit lineage.

- [ ] **Step 1: Write RED pure Capacity tests CAP-001 through CAP-014**

Hand-check wallet `1000`: target risk `20`, gross limit `60`, directional limit `40`, minimum materialization `10`. Assert `9.99` rejects with `budget_exhausted + minimum_materialization_ratio`, while `10` proceeds.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py -q`

Expected: old Policy fields and 3%/45% assertions fail.

- [ ] **Step 3: Implement pure Policy v4 decisions**

Evaluate family and direction before sizing; include directional remaining risk in the planned stop-risk cap. Apply minimum materialization after all risk/margin/instrument rounding binds. Preserve exact first-blocker order from the design.

- [ ] **Step 4: Verify unit GREEN**

Run: `pytest tests/trading_kernel/unit/test_capacity.py tests/trading_kernel/unit/test_capacity_sizing.py -q`

Expected: all tests pass.

- [ ] **Step 5: Write RED PostgreSQL usage and lineage tests**

Insert at most three active Tickets with frozen Family and active reservations. Assert Family count and directional risk selectors use terminal/current predicates and no full-history aggregation.

- [ ] **Step 6: Verify integration RED**

Run: `pytest tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_runtime_authority_seed.py -q`

Expected: current schema/snapshots lack Family and Policy v4 fields.

- [ ] **Step 7: Implement repository selectors, seed v4, Claim/Ticket lineage, and dispatch revalidation**

Owner Policy current uses typed family-limit JSON. Remove `max_strategy_group_concurrent_tickets` from current admission code and current Policy projection; historical Claim columns remain readable. Dispatch revalidates exact Policy v4 fields frozen in Claim.

- [ ] **Step 8: Verify integration GREEN**

Run: `pytest tests/trading_kernel/integration/test_capacity_claim_to_ticket.py tests/trading_kernel/integration/test_runtime_authority_seed.py tests/trading_kernel/integration/test_entry_promotion_gate.py -q`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 4**

```text
git add src/trading_kernel/domain/capacity.py src/trading_kernel/domain/capacity_sizing.py src/trading_kernel/domain/ticket.py src/trading_kernel/application/build_capacity_claim.py src/trading_kernel/application/issue_ready_signal.py src/trading_kernel/application/ports.py src/trading_kernel/application/revalidate_entry_dispatch.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/infrastructure/runtime_authority_seed.py tests/trading_kernel
git commit -m "feat(kernel): enforce portfolio admission policy v4"
```

### Task 5: Bounded read-only Shadow Outcome

**Files:**
- Create: `src/trading_kernel/domain/shadow_outcome.py`
- Create: `src/trading_kernel/application/project_shadow_outcome.py`
- Modify: `src/trading_kernel/application/issue_ready_signal.py`
- Modify: `src/trading_kernel/application/ports.py`
- Modify: `src/trading_kernel/infrastructure/pg_models.py`
- Modify: `src/trading_kernel/infrastructure/pg_repositories.py`
- Modify: `src/trading_kernel/infrastructure/pg_unit_of_work.py`
- Modify: `src/trading_kernel/interfaces/observation_worker.py`
- Test: `tests/trading_kernel/unit/test_shadow_outcome.py`
- Test: `tests/trading_kernel/integration/test_shadow_outcome_projection.py`
- Test: `tests/trading_kernel/integration/test_global_runtime_workers.py`

**Interfaces:**
- Add frozen `ShadowOutcomeSpec`, `ShadowOutcomeProjection`, and `evaluate_fixed_horizon_excursion(spec, candles)`.
- Add `ShadowOutcomeRepository.add_pending`, `claim_one_due`, `complete`, `mark_unavailable`, and `release_expired_claim`.
- Observation worker processes at most one due Shadow only when no Strategy Scope is due.

- [ ] **Step 1: Write RED pure MFE/MAE tests SHD-005, SHD-006, SHD-007, SHD-014**

For long entry `100`, stop `95`, high `110`, low `97`, assert `mfe_r=2` and `mae_r=0.6`. For short entry `100`, stop `105`, low `90`, high `103`, assert the same literals.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/unit/test_shadow_outcome.py -q`

Expected: missing Shadow domain.

- [ ] **Step 3: Implement pure fixed-horizon evaluation**

Filter to closed candles whose close is within `(horizon_start_ms, horizon_end_ms]`. Use `Decimal`, require positive risk distance, and label every result `fixed_horizon_excursion_v1`.

- [ ] **Step 4: Verify unit GREEN**

Run: `pytest tests/trading_kernel/unit/test_shadow_outcome.py -q`

Expected: all tests pass.

- [ ] **Step 5: Write RED repository/worker tests SHD-001 through SHD-015**

Assert Strategy Scope work wins over due Shadow, source fetch happens after UoW exit, 1h limit is 24, 15m limit is at most 96, and terminal retry is idempotent.

- [ ] **Step 6: Verify integration RED**

Run: `pytest tests/trading_kernel/integration/test_shadow_outcome_projection.py tests/trading_kernel/integration/test_global_runtime_workers.py -q`

Expected: missing table/repository/worker status.

- [ ] **Step 7: Implement pending creation and idle-only projector**

Create pending Shadow only for valid portfolio/capacity rejection with entry and stop references. Do not import Ticket issuance, exchange command dispatch, or venue write adapters into Shadow modules.

- [ ] **Step 8: Verify integration GREEN**

Run: `pytest tests/trading_kernel/integration/test_shadow_outcome_projection.py tests/trading_kernel/integration/test_global_runtime_workers.py -q`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 5**

```text
git add src/trading_kernel/domain/shadow_outcome.py src/trading_kernel/application/project_shadow_outcome.py src/trading_kernel/application/issue_ready_signal.py src/trading_kernel/application/ports.py src/trading_kernel/infrastructure/pg_models.py src/trading_kernel/infrastructure/pg_repositories.py src/trading_kernel/infrastructure/pg_unit_of_work.py src/trading_kernel/interfaces/observation_worker.py tests/trading_kernel/unit/test_shadow_outcome.py tests/trading_kernel/integration/test_shadow_outcome_projection.py tests/trading_kernel/integration/test_global_runtime_workers.py
git commit -m "feat(kernel): project bounded shadow outcomes"
```

### Task 6: Forward-only 0003 migration and Registry/Universe transition

**Files:**
- Create: `migrations/trading_kernel/versions/0003_portfolio_admission_observability.py`
- Modify: `src/trading_kernel/infrastructure/runtime_identity.py`
- Modify: `src/trading_kernel/infrastructure/strategy_registry_seed.py`
- Modify: `src/trading_kernel/infrastructure/runtime_authority_seed.py`
- Modify: `src/trading_kernel/application/strategy_universe_batch_manifest.py`
- Modify: `scripts/trading_kernel/bootstrap_strategy_universes.py`
- Test: `tests/trading_kernel/integration/test_portfolio_admission_observability_migration.py`
- Test: `tests/trading_kernel/integration/test_clean_baseline_rebuild.py`
- Test: `tests/trading_kernel/integration/test_strategy_registry_seed.py`
- Test: `tests/trading_kernel/full_chain/test_strategy_universe_local_release_rehearsal.py`

**Interfaces:**
- Set `CURRENT_SCHEMA_REVISION = "0003_portfolio_admission_observability"`.
- Migration upgrades only from exact `0002_sor_v3_strategy_group_capacity` and raises on downgrade.
- Registry current contracts become CPM/MPG/MI/BRF2 v3 and SOR v4; existing non SOR v2 and SOR v3 remain historical lineage.

- [ ] **Step 1: Write RED migration tests MIG-001 through MIG-006**

Build a production-shaped `0002` database with terminal v1/v3 Signals, Claims, Tickets, Commands, Reservations, Settlement, and Review. Compute a literal source-column manifest before migration and assert exact equality after migration.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/integration/test_portfolio_admission_observability_migration.py -q`

Expected: Alembic cannot resolve revision `0003_portfolio_admission_observability`.

- [ ] **Step 3: Implement 0003 DDL/data migration**

Add new tables and columns, deterministically backfill Family, insert non SOR v3 and SOR v4 Registry/ExitPolicy lineage, retire old current pointers without deleting history, migrate Policy to v4 with Entry disabled, and define `downgrade()` to raise `RuntimeError`.

- [ ] **Step 4: Update seed and six-Universe batch identity**

Fresh head bootstrap installs exact current versions. Compatible source upgrade preserves old Registry rows needed by historical lineage and creates new Warming Universes only through the official batch path.

- [ ] **Step 5: Verify migration and clean rebuild GREEN**

Run: `pytest tests/trading_kernel/integration/test_portfolio_admission_observability_migration.py tests/trading_kernel/integration/test_clean_baseline_rebuild.py tests/trading_kernel/integration/test_strategy_registry_seed.py tests/trading_kernel/full_chain/test_strategy_universe_local_release_rehearsal.py -q`

Expected: all tests pass with one Alembic head.

- [ ] **Step 6: Commit Task 6**

```text
git add migrations/trading_kernel/versions/0003_portfolio_admission_observability.py src/trading_kernel/infrastructure/runtime_identity.py src/trading_kernel/infrastructure/strategy_registry_seed.py src/trading_kernel/infrastructure/runtime_authority_seed.py src/trading_kernel/application/strategy_universe_batch_manifest.py scripts/trading_kernel/bootstrap_strategy_universes.py tests/trading_kernel
git commit -m "feat(kernel): add portfolio admission schema revision"
```

### Task 7: Exact 0002 to 0003 deployment path

**Files:**
- Modify: `scripts/trading_kernel/deploy_tokyo_release.py`
- Modify: `scripts/trading_kernel/certify_readonly.py`
- Modify: `scripts/trading_kernel/verify_schema.py`
- Modify: `tests/trading_kernel/unit/test_deploy_tokyo_release.py`
- Create: `tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py`
- Modify: `tests/trading_kernel/architecture/test_flat_compatible_upgrade_architecture.py`

**Interfaces:**
- Set compatible source to exact `0002_sor_v3_strategy_group_capacity` and target to exact `0003_portfolio_admission_observability`.
- Preservation manifest covers every source `0002` table/column, excluding only Alembic version and `0003`-only objects.
- The release plan used for this RC has `enable_entry=False`.

- [ ] **Step 1: Write RED deployment tests MIG-007 through MIG-009 and DEP-001 through DEP-008**

Assert wrong source blocks before service stop, non-flat state blocks before migration, preservation mismatch leaves Entry fenced, and target safety workers start without Entry.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/unit/test_deploy_tokyo_release.py tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py -q`

Expected: existing deployment code accepts only 0001→0002.

- [ ] **Step 3: Implement exact current transition**

Replace obsolete compatible source constants and manifest assumptions; do not retain a generic multi-revision fallback. Postflight verifies exact Policy v4, Registry/Universe identity, Schema, Seed, safety services, Entry disabled, and write fence.

- [ ] **Step 4: Verify deployment GREEN**

Run: `pytest tests/trading_kernel/unit/test_deploy_tokyo_release.py tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py tests/trading_kernel/architecture/test_flat_compatible_upgrade_architecture.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 7**

```text
git add scripts/trading_kernel/deploy_tokyo_release.py scripts/trading_kernel/certify_readonly.py scripts/trading_kernel/verify_schema.py tests/trading_kernel/unit/test_deploy_tokyo_release.py tests/trading_kernel/integration/test_portfolio_admission_flat_compatible_deployment.py tests/trading_kernel/architecture/test_flat_compatible_upgrade_architecture.py
git commit -m "fix(deploy): certify exact portfolio admission upgrade"
```

### Task 8: Full-chain replay, architecture constraints, and current documentation

**Files:**
- Create: `tests/trading_kernel/full_chain/test_portfolio_admission_observability.py`
- Modify: `tests/trading_kernel/architecture/test_current_document_authority.py`
- Modify: `tests/trading_kernel/architecture/test_no_retired_execution.py`
- Modify: `tests/trading_kernel/architecture/test_runtime_file_io_audit.py`
- Modify: `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_DESIGN.md`
- Modify: `docs/current/P0_TRADING_KERNEL_REBUILD_IMPLEMENTATION_PLAN.md`
- Modify: `docs/current/RUNTIME_ORDER_CAPABLE_EXPERIMENT_PROFILE.md`
- Modify: `docs/current/TOKYO_RUNTIME_DEPLOYMENT_CONTRACT.md`
- Modify: `docs/current/STRATEGY_EXPERIMENT_EVALUATION_CONTRACT.md`
- Do not modify production identity/counts in `docs/current/MAIN_CONTROL_ROADMAP.md` before deployment.

**Interfaces:**
- Full-chain test reproduces the accepted overnight ordering and asserts BNB CPM admitted, DOGE CPM Family-rejected, BRF2 admitted, one SOR admitted, and exact Decision/Shadow evidence for rejections.
- Architecture tests forbid StrategyGroup capacity as current authority and forbid Shadow imports of exchange-write modules.

- [ ] **Step 1: Write RED full-chain and architecture tests**

Run the full producer boundary with real Registry contracts, PostgreSQL, recording public-market source, and recording venue. No downstream fixture may create Signals or Tickets directly for the principal replay assertion.

- [ ] **Step 2: Verify RED**

Run: `pytest tests/trading_kernel/full_chain/test_portfolio_admission_observability.py tests/trading_kernel/architecture -q`

Expected: current docs/schema markers and missing replay evidence fail.

- [ ] **Step 3: Update the smallest current authority set**

Record stable Policy v4, Episode, Decision, Shadow, Family, and `0003` migration semantics. Keep exact production SHA, tag, runtime counts, and deployment result solely in `MAIN_CONTROL_ROADMAP.md` after deployment.

- [ ] **Step 4: Verify full-chain and architecture GREEN**

Run: `pytest tests/trading_kernel/full_chain/test_portfolio_admission_observability.py tests/trading_kernel/architecture -q`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 8**

```text
git add tests/trading_kernel/full_chain/test_portfolio_admission_observability.py tests/trading_kernel/architecture docs/current
git commit -m "docs(kernel): converge portfolio admission authority"
```

### Task 9: Final verification, self-review, and release commit

**Files:**
- Review every file changed since `8ad18f40`.
- Modify only defects found by fresh evidence.

- [ ] **Step 1: Run focused suites in dependency order**

```text
pytest tests/trading_kernel/unit -q
pytest tests/trading_kernel/integration -q
pytest tests/trading_kernel/full_chain -q
pytest tests/trading_kernel/architecture -q
```

- [ ] **Step 2: Run the complete suite**

Run: `pytest tests/trading_kernel -q`

Expected: zero failures and zero errors.

- [ ] **Step 3: Run static and repository checks**

```text
ruff check src/trading_kernel scripts/trading_kernel tests/trading_kernel migrations/trading_kernel
mypy src/trading_kernel scripts/trading_kernel
git diff --check 8ad18f40..HEAD
git status --short
```

- [ ] **Step 4: Audit requirements against the two approved specs**

Create a local checklist mapping every EPI/ADM/CAP/SHD/PG/MIG/DEP requirement to a passing test. Fix any uncovered requirement through a fresh RED/GREEN cycle.

- [ ] **Step 5: Review safety boundaries**

Confirm no credential, withdrawal, transfer, leverage mutation, market expansion, manual close/cancel, active-position handover, dual write, old-schema reader, or `--enable-entry` deployment authorization entered the diff.

- [ ] **Step 6: Record the exact release candidate**

If verification creates no required edits, HEAD itself is the candidate. If self-review requires edits, add one focused fix commit and rerun Steps 1–5. Resolve the final exact 40-character SHA with `git rev-parse HEAD`.

### Task 10: Restore safe wait-for-deployment automation

**Files:**
- No repository file change until deployment completes.

- [ ] **Step 1: Update automation `p0` to the new exact SHA**

The automation prompt must name only the final Release Commit and exact branch, preserve the existing five-minute cadence, and prohibit `--enable-entry`.

- [ ] **Step 2: Preserve deployment gates**

The automation continues readonly PostgreSQL/systemd/Binance checks and deploys only after zero active Ticket/Position/order/Reservation/Netting Domain/unresolved Command/open Incident and complete Settlement/Review.

- [ ] **Step 3: Wait**

Do not manually close, cancel, alter stops/TP, or modify capital/Policy/market scope. The next action is natural flatness followed by the exact stopped compatible upgrade and Entry-off postflight.
