"""Production-shaped Dynamic Selection Authority fixtures for PostgreSQL tests."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.domain.instrument_selection import (
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
)
from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
    PostgresInstrumentSelectionRepository,
)
from src.trading_kernel.infrastructure.pg_models import (
    facts_current,
    instrument_certification_current,
    instrument_rules_current,
    instrument_selection_specs,
    selection_authority_gap_audits_current,
    strategy_selection_control_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
)
from tests.trading_kernel.support.signal_ingest import signal

DAY_MS = 86_400_000
INTERVAL_MS = 900_000
SESSION_START_MS = DAY_MS
DECISION_BOUNDARY_MS = SESSION_START_MS + 3_600_000
FIRST_ELIGIBLE_CLOSE_MS = SESSION_START_MS + 5 * INTERVAL_MS
SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
SELECTION_AUTHORITY_ID = "authority:dynamic-test:1"
SHORT_UNIVERSE_ID = "universe:sor-short:4"


async def install_dynamic_pre_fence_authority(
    engine: AsyncEngine,
    *,
    long_universe_id: str = "universe:sor-long:4",
    short_universe_id: str = SHORT_UNIVERSE_ID,
    universe_semantic_digest: str = "sha256:" + "a" * 64,
    exchange_instrument_id: str = "binance-usdm:BTCUSDT:perpetual",
    owner_control_version: int = 1,
) -> SelectionSessionAuthority:
    """Install one exact Dynamic continuity grant over the current SOR pair."""

    gap_audit_id = "gap-audit:dynamic-test:1"
    async with engine.begin() as connection:
        await connection.execute(
            pg_insert(instrument_selection_specs)
            .values(
                selection_spec_id=SELECTION_SPEC_ID,
                strategy_group_id="SOR-001",
                strategy_version_id="sgv:SOR-001:v4",
                selection_version=1,
                selection_kind="sor_dynamic_v0",
                algorithm_semantic_digest="sha256:" + "d" * 64,
                status="active",
                installed_at_ms=DECISION_BOUNDARY_MS,
            )
            .on_conflict_do_nothing(
                index_elements=[instrument_selection_specs.c.selection_spec_id]
            )
        )
        await connection.execute(
            pg_insert(strategy_selection_control_current)
            .values(
                strategy_group_id="SOR-001",
                selection_spec_id=SELECTION_SPEC_ID,
                selection_mode="dynamic_selection",
                pending_selection_mode=None,
                pending_effective_session_start_ms=None,
                pending_authorization_id=None,
                control_version=1,
                rollback_baseline_id=None,
                updated_at_ms=DECISION_BOUNDARY_MS,
            )
            .on_conflict_do_update(
                index_elements=[
                    strategy_selection_control_current.c.strategy_group_id
                ],
                set_={
                    "selection_spec_id": SELECTION_SPEC_ID,
                    "selection_mode": "dynamic_selection",
                    "pending_selection_mode": None,
                    "pending_effective_session_start_ms": None,
                    "pending_authorization_id": None,
                    "control_version": 1,
                    "rollback_baseline_id": None,
                    "updated_at_ms": DECISION_BOUNDARY_MS,
                },
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_versions)
            .values(
                universe_version_id=short_universe_id,
                strategy_group_id="SOR-001",
                event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                universe_version=4,
                semantic_digest=universe_semantic_digest,
                lifecycle_state="active",
                source_kind="manual",
                installed_at_ms=DECISION_BOUNDARY_MS,
                activated_at_ms=DECISION_BOUNDARY_MS + 1,
            )
            .on_conflict_do_nothing(
                index_elements=[strategy_universe_versions.c.universe_version_id]
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_members)
            .values(
                universe_version_id=short_universe_id,
                exchange_instrument_id=exchange_instrument_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    strategy_universe_members.c.universe_version_id,
                    strategy_universe_members.c.exchange_instrument_id,
                ]
            )
        )
        await connection.execute(
            pg_insert(strategy_universe_current)
            .values(
                event_spec_id=SOR_SHORT_EVENT_SPEC_ID,
                universe_version_id=short_universe_id,
                semantic_digest=universe_semantic_digest,
                lifecycle_state="active",
                activation_generation=1,
                activated_at_ms=DECISION_BOUNDARY_MS + 1,
            )
            .on_conflict_do_update(
                index_elements=[strategy_universe_current.c.event_spec_id],
                set_={
                    "universe_version_id": short_universe_id,
                    "semantic_digest": universe_semantic_digest,
                    "lifecycle_state": "active",
                    "activation_generation": 1,
                    "activated_at_ms": DECISION_BOUNDARY_MS + 1,
                },
            )
        )
        await connection.execute(
            sa.insert(selection_authority_gap_audits_current).values(
                authority_gap_audit_id=gap_audit_id,
                selection_spec_id=SELECTION_SPEC_ID,
                session_start_ms=SESSION_START_MS,
                gap_kind="LATE_PRE_FENCE_CONTINUITY",
                source_entry_vacuum_id=None,
                source_generation_id=None,
                proposed_authority_outcome="PRE_FENCE_CONTINUITY",
                unauthorized_from_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
                audited_through_close_time_ms=(
                    FIRST_ELIGIBLE_CLOSE_MS - INTERVAL_MS
                ),
                first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
                audit_scope_digest="sha256:" + "1" * 64,
                audit_result_digest="sha256:" + "2" * 64,
                detector_semantic_digest="sha256:" + "3" * 64,
                state="COMPLETE",
                first_blocker=None,
                projection_version=1,
            )
        )
        authority = SelectionSessionAuthority(
            selection_authority_id=SELECTION_AUTHORITY_ID,
            selection_spec_id=SELECTION_SPEC_ID,
            session_start_ms=SESSION_START_MS,
            decision_boundary_ms=DECISION_BOUNDARY_MS,
            authority_sequence=1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            selection_snapshot_id=None,
            continued_from_selection_authority_id=None,
            continuity_source_kind=ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
            authority_gap_audit_id=gap_audit_id,
            materialization_generation_id=None,
            owner_control_version=owner_control_version,
            authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
            authorized_pair=UniverseAuthorityPair(
                long_universe_version_id=long_universe_id,
                short_universe_version_id=short_universe_id,
            ),
            grant_proof=AuthorityGrantProof(
                kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
                predecessor_authority_id=None,
                authority_gap_audit_id=gap_audit_id,
            ),
            effective_from_ms=DECISION_BOUNDARY_MS,
            first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
            expires_at_ms=SESSION_START_MS + DAY_MS + 3_600_000,
            reason_code="TEST_PRE_FENCE_CONTINUITY",
            created_at_ms=DECISION_BOUNDARY_MS + 1,
        )
        await PostgresInstrumentSelectionRepository(
            connection
        ).add_authority_and_set_current(
            authority,
            expected_current_version=None,
        )
    return authority


async def move_seeded_runtime_to_dynamic_period(engine: AsyncEngine) -> None:
    """Move the shared Signal fixture's volatile facts into the Authority period."""

    valid_until_ms = FIRST_ELIGIBLE_CLOSE_MS + 9_000
    dynamic_signal = signal(occurred_at_ms=FIRST_ELIGIBLE_CLOSE_MS)
    async with engine.begin() as connection:
        await connection.execute(
            sa.update(instrument_rules_current).values(
                observed_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
                valid_until_ms=valid_until_ms,
            )
        )
        await connection.execute(
            sa.update(instrument_certification_current).values(
                observed_at_ms=FIRST_ELIGIBLE_CLOSE_MS,
                valid_until_ms=valid_until_ms,
                next_check_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 5_000,
            )
        )
        await connection.execute(sa.delete(facts_current))
        await connection.execute(
            sa.insert(facts_current),
            [
                {
                    "fact_current_id": (
                        "fact-current:scope-sor-btc-long:"
                        f"{fact.fact_definition_id}"
                    ),
                    "runtime_scope_id": "scope-sor-btc-long",
                    "fact_definition_id": fact.fact_definition_id,
                    "value": fact.value,
                    "satisfied": fact.satisfied,
                    "observed_at_ms": fact.observed_at_ms,
                    "valid_until_ms": fact.valid_until_ms,
                    "projection_version": fact.projection_version,
                }
                for fact in dynamic_signal.facts
            ],
        )


def continuity_successor(
    predecessor: SelectionSessionAuthority,
    *,
    authority_id: str,
    created_at_ms: int = FIRST_ELIGIBLE_CLOSE_MS - 1,
) -> SelectionSessionAuthority:
    """Build the next exact PRE_FENCE continuity revision for one period."""

    return SelectionSessionAuthority(
        selection_authority_id=authority_id,
        selection_spec_id=predecessor.selection_spec_id,
        session_start_ms=predecessor.session_start_ms,
        decision_boundary_ms=predecessor.decision_boundary_ms,
        authority_sequence=predecessor.authority_sequence + 1,
        selection_mode=predecessor.selection_mode,
        selection_snapshot_id=None,
        continued_from_selection_authority_id=predecessor.selection_authority_id,
        continuity_source_kind=ContinuitySourceKind.SELECTION_AUTHORITY,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=predecessor.owner_control_version,
        authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        authorized_pair=predecessor.authorized_pair,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=predecessor.selection_authority_id,
            authority_gap_audit_id=None,
        ),
        effective_from_ms=predecessor.effective_from_ms,
        first_eligible_close_time_ms=predecessor.first_eligible_close_time_ms,
        expires_at_ms=predecessor.expires_at_ms,
        reason_code="TEST_PRE_FENCE_CONTINUITY_REFRESH",
        created_at_ms=created_at_ms,
    )
