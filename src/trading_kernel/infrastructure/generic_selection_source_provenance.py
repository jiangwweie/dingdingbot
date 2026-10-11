"""Read-only 0007 Static comparison provenance preflight for a future upgrade.

No checkpoint, Episode or authority is written here. Insufficient source facts
must stop cutover rather than manufacture an arm or rebase a Static strategy.
"""

from __future__ import annotations

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.project_comparative_universe import (
    ComparativeUniverseProjection,
    build_comparative_universe_projection,
    comparative_member_set_digest,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import ExposureEpisodeState
from src.trading_kernel.domain.strategy_registry import strategy_contract_for


async def read_preserved_runtime_state(connection: AsyncConnection) -> dict[str, object]:
    """Deployment evidence only: persisted membership and historical cardinality."""
    rows = (await connection.execute(sa.text("""
        SELECT c.event_spec_id,c.universe_version_id,c.semantic_digest,
               c.lifecycle_state,c.activation_generation,c.activated_at_ms,
               u.source_kind,u.materialization_generation_id,
               array_agg(m.exchange_instrument_id ORDER BY m.exchange_instrument_id) AS member_ids
        FROM brc_strategy_universe_current c
        JOIN brc_strategy_universe_versions u USING(universe_version_id)
        JOIN brc_strategy_universe_members m USING(universe_version_id)
        GROUP BY c.event_spec_id,c.universe_version_id,c.semantic_digest,c.lifecycle_state,
                 c.activation_generation,c.activated_at_ms,u.source_kind,u.materialization_generation_id
        ORDER BY c.event_spec_id
    """))).mappings().all()
    counts = {}
    for key, table in (
        ("jobs", "brc_instrument_selection_jobs_current"),
        ("snapshots", "brc_instrument_selection_snapshots"),
        ("generations", "brc_strategy_universe_materialization_generations"),
        ("vacuums", "brc_strategy_entry_vacuums_current"),
        ("authorities", "brc_selection_session_authorities"),
        ("gap_audits", "brc_selection_authority_gap_audits_current"),
    ):
        counts[key] = int(await connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) or 0)
    return {
        "active_universe_manifest_digest": canonical_digest([dict(row) for row in rows]),
        "dynamic_selection_runtime_counts": counts,
    }


class SourceProvenanceInsufficient(RuntimeError):
    """The source cannot justify an unchanged Static comparison checkpoint."""


def count_nonquiescent_source_vacuums(connection: sa.Connection) -> int:
    """Keep a proved, drained standalone Owner pause as a negative fence.

    This never resolves a Vacuum or grants ENTRY. Generation-linked pauses,
    missing drain evidence, resumed controls and pending switches still block.
    Both advisory verification and the locked pre-DDL check use this predicate.
    """
    return int(connection.scalar(sa.text("""
        SELECT count(*) FROM brc_strategy_entry_vacuums_current v
        WHERE v.resolved_at_ms IS NULL AND NOT EXISTS (
          SELECT 1 FROM brc_strategy_entry_controls_current o
          JOIN brc_strategy_entry_control_events oe
            ON oe.strategy_entry_control_event_id=o.last_event_id
            AND oe.strategy_group_id=o.strategy_group_id
            AND oe.control_version=o.control_version
          JOIN brc_strategy_selection_control_current s
            ON s.strategy_group_id=o.strategy_group_id
            AND s.selection_spec_id=v.selection_spec_id
          WHERE o.strategy_group_id=v.strategy_group_id
            AND v.state='OWNER_PAUSED' AND v.first_blocker='OWNER_PAUSED'
            AND v.source_generation_id IS NULL
            AND v.drained_at_ms>=v.fenced_at_ms
            AND o.entry_state='paused' AND oe.operation='pause'
            AND oe.target_state='paused' AND oe.created_at_ms=o.updated_at_ms
            AND o.updated_at_ms<=v.fenced_at_ms
            AND s.pending_selection_mode IS NULL
            AND s.pending_authorization_id IS NULL
            AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events origin
              WHERE origin.entry_vacuum_id=v.entry_vacuum_id
                AND origin.event_sequence=1 AND origin.event_type='OPEN'
                AND origin.occurred_at_ms=v.fenced_at_ms
                AND origin.payload->>'intended_outcome'='OWNER_PAUSED')
            AND EXISTS (SELECT 1 FROM brc_strategy_entry_vacuum_events drained
              WHERE drained.entry_vacuum_id=v.entry_vacuum_id
                AND drained.event_sequence=v.projection_version
                AND drained.event_type='OWNER_PAUSED'
                AND drained.occurred_at_ms=v.drained_at_ms
                AND drained.payload->'entry_drain_complete'='true'::jsonb)
        )
    """)) or 0)


class StaticComparisonSourceEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    episode: ExposureEpisodeState
    current_universe_version_id: str
    current_universe_activated_at_ms: int
    current_member_ids: tuple[str, ...]
    current_universe_digest: str
    scope_universe_version_id: str
    scope_universe_digest: str
    scope_observed_close_ms: int
    comparison_projection: ComparativeUniverseProjection | None
    required_fact_observed_times: tuple[int, ...]
    required_fact_satisfied: tuple[bool, ...]


class StaticComparisonSourceProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    episode_domain_key: str
    episode_projection_version: int
    source_universe_version_id: str
    comparison_member_digest: str
    observed_close_ms: int
    source_evidence_digest: str


def certify_static_comparison_source(
    evidence: StaticComparisonSourceEvidence,
) -> StaticComparisonSourceProof:
    episode = evidence.episode
    contract = strategy_contract_for(episode.event_spec_id)
    if contract.strategy_group_id not in {"MPG-001", "MI-001"}:
        raise SourceProvenanceInsufficient(
            "SOURCE_PROVENANCE_INSUFFICIENT: unsupported comparison Event"
        )
    projection = evidence.comparison_projection
    if projection is None:
        raise SourceProvenanceInsufficient(
            "SOURCE_PROVENANCE_INSUFFICIENT: missing comparison projection"
        )
    members = evidence.current_member_ids
    expected_fact_count = len(contract.required_facts)
    if (
        episode.last_observed_at_ms is None
        or evidence.scope_universe_version_id != evidence.current_universe_version_id
        or evidence.current_universe_activated_at_ms >= episode.last_observed_at_ms
        or evidence.scope_universe_digest != evidence.current_universe_digest
        or evidence.current_universe_digest != canonical_digest({
            "event_spec_id": contract.event_spec_id,
            "strategy_group_id": contract.strategy_group_id,
            "exchange_instrument_ids": members,
        })
        or evidence.scope_observed_close_ms != episode.last_observed_at_ms
        or episode.exchange_instrument_id not in members
        or tuple(sorted(set(members))) != members
        or len(evidence.required_fact_observed_times) != expected_fact_count
        or len(evidence.required_fact_satisfied) != expected_fact_count
        or any(
            time != episode.last_observed_at_ms
            for time in evidence.required_fact_observed_times
        )
        or (all(evidence.required_fact_satisfied) != (episode.state == "triggered"))
        or projection.universe_version_id != evidence.current_universe_version_id
        or projection.event_spec_id != episode.event_spec_id
        or projection.closed_bar_time_ms != episode.last_observed_at_ms
        or projection.member_set_digest != comparative_member_set_digest(members)
        or projection.comparative_strength.lookback_bars
        != (8 if contract.strategy_group_id == "MPG-001" else 12)
    ):
        raise SourceProvenanceInsufficient(
            "SOURCE_PROVENANCE_INSUFFICIENT: source identity/time/episode mismatch"
        )
    reconstructed = build_comparative_universe_projection(
        event_spec_id=contract.event_spec_id,
        universe_version_id=evidence.current_universe_version_id,
        strategy_group_id=contract.strategy_group_id,
        exchange_instrument_ids=members,
        closed_bar_time_ms=episode.last_observed_at_ms,
        lookback_bars=projection.comparative_strength.lookback_bars,
        freshness_window_ms=contract.freshness_window_ms,
        member_windows=projection.member_windows,
    )
    if reconstructed.comparative_strength != projection.comparative_strength:
        raise SourceProvenanceInsufficient(
            "SOURCE_PROVENANCE_INSUFFICIENT: comparison numeric reconstruction mismatch"
        )
    return StaticComparisonSourceProof(
        episode_domain_key=episode.episode_domain_key,
        episode_projection_version=episode.projection_version,
        source_universe_version_id=evidence.current_universe_version_id,
        comparison_member_digest=projection.member_set_digest,
        observed_close_ms=episode.last_observed_at_ms,
        source_evidence_digest=canonical_digest(evidence.model_dump(mode="json")),
    )


async def certify_0007_static_comparison_sources(
    connection: AsyncConnection,
) -> tuple[StaticComparisonSourceProof, ...]:
    return await connection.run_sync(certify_0007_static_comparison_sources_sync)


def certify_0007_static_comparison_sources_sync(
    connection: sa.Connection,
) -> tuple[StaticComparisonSourceProof, ...]:
    """Certify all stored Static MPG/MI episodes in a caller-owned readonly tx.

    This is a one-off source certification scan, not a runtime cadence query.
    The caller must stop writers and repeat the proof before migration.
    """
    revision = connection.scalar(
        sa.text("SELECT version_num FROM alembic_version")
    )
    if revision != "0007_exit_profile_authority_v1":
        raise SourceProvenanceInsufficient(
            "SOURCE_PROVENANCE_INSUFFICIENT: source is not exact 0007"
        )
    events = ("event_spec:MPG-001:MPG-LONG:v3", "event_spec:MI-001:MI-LONG:v3")
    rows = (
        (
            connection.execute(
                sa.text(
                    "SELECT * FROM brc_exposure_episode_current WHERE event_spec_id IN (:mpg, :mi) ORDER BY episode_domain_key"
                ),
                {"mpg": events[0], "mi": events[1]},
            )
        )
        .mappings()
        .all()
    )
    proofs: list[StaticComparisonSourceProof] = []
    for row in rows:
        episode = ExposureEpisodeState.model_validate(row)
        contract = strategy_contract_for(episode.event_spec_id)
        current = (
            (
                connection.execute(
                    sa.text(
                        "SELECT c.universe_version_id, c.semantic_digest, c.activated_at_ms, s.runtime_scope_id, "
                        "s.universe_version_id AS scope_universe_version_id, s.universe_semantic_digest, "
                        "r.updated_at_ms AS observation_time "
                        "FROM brc_strategy_universe_current c "
                        "JOIN brc_runtime_scopes_current s ON s.event_spec_id=c.event_spec_id "
                        "AND s.universe_version_id=c.universe_version_id AND s.lifecycle_state='active' "
                        "LEFT JOIN brc_readiness_current r ON r.runtime_scope_id=s.runtime_scope_id "
                        "WHERE c.event_spec_id=:event AND s.exchange_instrument_id=:instrument"
                    ),
                    {
                        "event": episode.event_spec_id,
                        "instrument": episode.exchange_instrument_id,
                    },
                )
            )
            .mappings()
            .all()
        )
        if len(current) != 1:
            raise SourceProvenanceInsufficient(
                "SOURCE_PROVENANCE_INSUFFICIENT: missing or ambiguous current Static scope"
            )
        scope = current[0]
        members = tuple(
            (
                connection.execute(
                    sa.text(
                        "SELECT exchange_instrument_id FROM brc_strategy_universe_members "
                        "WHERE universe_version_id=:universe ORDER BY exchange_instrument_id"
                    ),
                    {"universe": scope["universe_version_id"]},
                )
            ).scalars()
        )
        projections = (
            (
                connection.execute(
                    sa.text(
                        "SELECT projection FROM brc_comparative_projection_current "
                        "WHERE event_spec_id=:event AND universe_version_id=:universe AND projection_status='ready'"
                    ),
                    {
                        "event": episode.event_spec_id,
                        "universe": scope["universe_version_id"],
                    },
                )
            )
            .scalars()
            .all()
        )
        facts = (
            (
                connection.execute(
                    sa.text(
                        "SELECT fact_definition_id, observed_at_ms, satisfied FROM brc_facts_current "
                        "WHERE runtime_scope_id=:scope"
                    ),
                    {"scope": scope["runtime_scope_id"]},
                )
            )
            .mappings()
            .all()
        )
        by_id = {fact["fact_definition_id"]: fact for fact in facts}
        required = [
            by_id.get(item.fact_definition_id) for item in contract.required_facts
        ]
        if any(fact is None for fact in required) or scope["observation_time"] is None:
            raise SourceProvenanceInsufficient(
                "SOURCE_PROVENANCE_INSUFFICIENT: missing contemporaneous Observation facts"
            )
        proof = certify_static_comparison_source(
            StaticComparisonSourceEvidence(
                episode=episode,
                current_universe_version_id=scope["universe_version_id"],
                current_universe_activated_at_ms=scope["activated_at_ms"],
                current_member_ids=members,
                current_universe_digest=scope["semantic_digest"],
                scope_universe_version_id=scope["scope_universe_version_id"],
                scope_universe_digest=scope["universe_semantic_digest"],
                scope_observed_close_ms=scope["observation_time"],
                comparison_projection=ComparativeUniverseProjection.model_validate(
                    projections[0]
                )
                if len(projections) == 1
                else None,
                required_fact_observed_times=tuple(
                    fact["observed_at_ms"] for fact in required if fact is not None
                ),
                required_fact_satisfied=tuple(
                    fact["satisfied"] for fact in required if fact is not None
                ),
            )
        )
        proofs.append(proof)
    return tuple(proofs)
