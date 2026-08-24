"""PostgreSQL ownership for Dynamic Selection facts and current Authority."""

from __future__ import annotations

from typing import ClassVar, Literal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
)
from src.trading_kernel.infrastructure.pg_models import (
    selection_authority_current,
    selection_session_authorities,
)

LeaseKind = Literal["selection", "materialization", "observation"]


class SelectionAuthorityVersionConflict(RuntimeError):
    """The current Authority pointer differs from the caller's locked view."""


class PostgresInstrumentSelectionRepository:
    """Persist immutable Selection facts behind exact, bounded projections."""

    _LEASE_NAMESPACES: ClassVar[dict[LeaseKind, str]] = {
        "selection": "selection_job",
        "materialization": "materialization_generation",
        "observation": "runtime_scope_observation",
    }

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    @classmethod
    def lease_namespace(cls, lease_kind: LeaseKind) -> str:
        return cls._LEASE_NAMESPACES[lease_kind]

    async def add_authority_and_set_current(
        self,
        authority: SelectionSessionAuthority,
        *,
        expected_current_version: int | None,
    ) -> None:
        """Append one Authority and atomically advance its current pointer."""

        await self._connection.execute(
            sa.insert(selection_session_authorities).values(
                _authority_values(authority)
            )
        )
        if expected_current_version is None:
            result = await self._connection.execute(
                pg_insert(selection_authority_current)
                .values(
                    selection_spec_id=authority.selection_spec_id,
                    selection_authority_id=authority.selection_authority_id,
                    projection_version=1,
                    updated_at_ms=authority.created_at_ms,
                )
                .on_conflict_do_nothing(
                    index_elements=[selection_authority_current.c.selection_spec_id]
                )
            )
        else:
            result = await self._connection.execute(
                sa.update(selection_authority_current)
                .where(
                    selection_authority_current.c.selection_spec_id
                    == authority.selection_spec_id,
                    selection_authority_current.c.projection_version
                    == expected_current_version,
                )
                .values(
                    selection_authority_id=authority.selection_authority_id,
                    projection_version=expected_current_version + 1,
                    updated_at_ms=authority.created_at_ms,
                )
            )
        if result.rowcount != 1:
            raise SelectionAuthorityVersionConflict(
                "Selection Authority current pointer version changed"
            )

    async def get_current_authority(
        self,
        selection_spec_id: str,
    ) -> SelectionSessionAuthority | None:
        row = (
            await self._connection.execute(
                sa.select(selection_session_authorities)
                .join(
                    selection_authority_current,
                    selection_authority_current.c.selection_authority_id
                    == selection_session_authorities.c.selection_authority_id,
                )
                .where(
                    selection_authority_current.c.selection_spec_id
                    == selection_spec_id
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return None if row is None else _authority_from_row(row)


def _authority_values(authority: SelectionSessionAuthority) -> dict[str, object]:
    pair = authority.authorized_pair
    proof = authority.grant_proof
    return {
        "selection_authority_id": authority.selection_authority_id,
        "selection_spec_id": authority.selection_spec_id,
        "session_start_ms": authority.session_start_ms,
        "decision_boundary_ms": authority.decision_boundary_ms,
        "authority_sequence": authority.authority_sequence,
        "selection_mode": authority.selection_mode.value,
        "selection_job_id": None,
        "selection_attempt_id": None,
        "selection_snapshot_id": authority.selection_snapshot_id,
        "continued_from_selection_authority_id": (
            authority.continued_from_selection_authority_id
        ),
        "continuity_source_kind": authority.continuity_source_kind.value,
        "authority_gap_audit_id": authority.authority_gap_audit_id,
        "materialization_generation_id": authority.materialization_generation_id,
        "owner_control_version": authority.owner_control_version,
        "authority_outcome": authority.authority_outcome.value,
        "authorized_long_universe_version_id": (
            None if pair is None else pair.long_universe_version_id
        ),
        "authorized_short_universe_version_id": (
            None if pair is None else pair.short_universe_version_id
        ),
        "grant_proof_kind": None if proof is None else proof.kind.value,
        "grant_predecessor_authority_id": (
            None if proof is None else proof.predecessor_authority_id
        ),
        "effective_from_ms": authority.effective_from_ms,
        "first_eligible_close_time_ms": authority.first_eligible_close_time_ms,
        "expires_at_ms": authority.expires_at_ms,
        "reason_code": authority.reason_code,
        "semantic_digest": authority.semantic_digest,
        "created_at_ms": authority.created_at_ms,
    }


def _authority_from_row(row: RowMapping) -> SelectionSessionAuthority:
    long_id = row["authorized_long_universe_version_id"]
    short_id = row["authorized_short_universe_version_id"]
    pair = (
        None
        if long_id is None or short_id is None
        else UniverseAuthorityPair(
            long_universe_version_id=str(long_id),
            short_universe_version_id=str(short_id),
        )
    )
    proof_kind = row["grant_proof_kind"]
    proof = (
        None
        if proof_kind is None
        else AuthorityGrantProof(
            kind=AuthorityGrantProofKind(str(proof_kind)),
            predecessor_authority_id=row["grant_predecessor_authority_id"],
            authority_gap_audit_id=row["authority_gap_audit_id"],
        )
    )
    return SelectionSessionAuthority(
        selection_authority_id=str(row["selection_authority_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["session_start_ms"]),
        decision_boundary_ms=int(row["decision_boundary_ms"]),
        authority_sequence=int(row["authority_sequence"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        selection_snapshot_id=row["selection_snapshot_id"],
        continued_from_selection_authority_id=row[
            "continued_from_selection_authority_id"
        ],
        continuity_source_kind=ContinuitySourceKind(
            str(row["continuity_source_kind"])
        ),
        authority_gap_audit_id=row["authority_gap_audit_id"],
        materialization_generation_id=row["materialization_generation_id"],
        owner_control_version=int(row["owner_control_version"]),
        authority_outcome=AuthorityOutcome(str(row["authority_outcome"])),
        authorized_pair=pair,
        grant_proof=proof,
        effective_from_ms=int(row["effective_from_ms"]),
        first_eligible_close_time_ms=(
            None
            if row["first_eligible_close_time_ms"] is None
            else int(row["first_eligible_close_time_ms"])
        ),
        expires_at_ms=int(row["expires_at_ms"]),
        reason_code=str(row["reason_code"]),
        created_at_ms=int(row["created_at_ms"]),
    )
