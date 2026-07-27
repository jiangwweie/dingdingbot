"""PostgreSQL authority for immutable universes and atomic activation."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Any, Literal, cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    UniverseActivationRecord,
    UniverseInstallCounts,
    UniverseLifecycle,
    UniverseMember,
    UniverseMemberRole,
)
from src.trading_kernel.domain.detectors.rsr_vcb import VCBArmedStructure
from src.trading_kernel.domain.universe_projection import (
    RSRProjectionMember,
    RSRUniverseProjection,
)
from src.trading_kernel.infrastructure.pg_models import (
    armed_structures,
    facts_current,
    instrument_product_current,
    instrument_rules_current,
    instruments,
    readiness_current,
    runtime_scopes_current,
    scope_warm_readiness,
    strategy_candidate_scopes,
    strategy_universe_activations,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    universe_projection_members,
    universe_projection_leases,
    universe_projection_runs,
)


class UniverseSeedConflict(RuntimeError):
    """Existing PostgreSQL membership differs from its immutable version."""


class PostgresStrategyUniverseRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def install_exact(
        self,
        universe: StrategyUniverseVersion,
        *,
        position_side: Literal["long", "short"],
        initial_lifecycle: UniverseLifecycle,
        installed_at_ms: int,
    ) -> UniverseInstallCounts:
        if installed_at_ms <= 0:
            raise ValueError("universe install time must be positive")
        inserted_instruments = 0
        for member in universe.members:
            inserted_instruments += await self._insert_exact(
                instruments,
                "exchange_instrument_id",
                {
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "venue_id": "binance-usdm",
                    "asset_class": universe.asset_class,
                    "venue_symbol": member.venue_symbol,
                    "contract_kind": "perpetual",
                    "status": "active",
                },
                compare_keys=(
                    "venue_id",
                    "asset_class",
                    "venue_symbol",
                    "contract_kind",
                    "status",
                ),
                conflict_name="instrument",
            )
        inserted_version = await self._insert_exact(
            strategy_universe_versions,
            "universe_version_id",
            {
                "universe_version_id": universe.universe_version_id,
                "universe_version": universe.universe_version,
                "strategy_group_id": universe.strategy_group_id,
                "event_spec_id": universe.event_spec_id,
                "asset_class": universe.asset_class,
                "semantic_digest": universe.semantic_digest(),
                "lifecycle_state": initial_lifecycle.value,
                "installed_at_ms": installed_at_ms,
                "activated_at_ms": (
                    installed_at_ms
                    if initial_lifecycle is UniverseLifecycle.ACTIVE
                    else None
                ),
            },
            compare_keys=(
                "universe_version",
                "strategy_group_id",
                "event_spec_id",
                "asset_class",
                "semantic_digest",
            ),
            conflict_name="universe version",
        )
        inserted_members = 0
        inserted_scopes = 0
        for member in universe.members:
            inserted_members += await self._insert_exact(
                strategy_universe_members,
                ("universe_version_id", "exchange_instrument_id"),
                {
                    "universe_version_id": universe.universe_version_id,
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "venue_symbol": member.venue_symbol,
                    "member_role": member.role.value,
                    "priority_rank": member.priority_rank,
                },
                compare_keys=("venue_symbol", "member_role", "priority_rank"),
                conflict_name="universe member",
            )
            if member.role is UniverseMemberRole.REFERENCE:
                continue
            inserted_scopes += await self._insert_exact(
                strategy_candidate_scopes,
                "candidate_scope_id",
                {
                    "candidate_scope_id": (
                        f"candidate:{universe.universe_version_id}:"
                        f"{member.exchange_instrument_id}"
                    ),
                    "strategy_group_id": universe.strategy_group_id,
                    "event_spec_id": universe.event_spec_id,
                    "universe_version_id": universe.universe_version_id,
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "position_side": position_side,
                    "priority_rank": member.priority_rank,
                    "status": "active",
                    "created_at_ms": installed_at_ms,
                },
                compare_keys=(
                    "strategy_group_id",
                    "event_spec_id",
                    "universe_version_id",
                    "exchange_instrument_id",
                    "position_side",
                    "priority_rank",
                    "status",
                ),
                conflict_name="candidate scope",
            )
        await self._assert_exact_members(universe)
        if initial_lifecycle is UniverseLifecycle.WARMING:
            await self._provision_replacement_runtime_scopes(
                universe,
                position_side=position_side,
                installed_at_ms=installed_at_ms,
            )

        inserted_current = 0
        inserted_activation = 0
        if initial_lifecycle is UniverseLifecycle.ACTIVE:
            existing_current = (
                await self._connection.execute(
                    sa.select(strategy_universe_current).where(
                        strategy_universe_current.c.event_spec_id
                        == universe.event_spec_id
                    )
                )
            ).mappings().one_or_none()
            if existing_current is None:
                inserted_current = await self._insert_exact(
                    strategy_universe_current,
                    "event_spec_id",
                    {
                        "event_spec_id": universe.event_spec_id,
                        "universe_version_id": universe.universe_version_id,
                        "activation_generation": 1,
                        "activated_at_ms": installed_at_ms,
                    },
                    compare_keys=(
                        "universe_version_id",
                        "activation_generation",
                    ),
                    conflict_name="universe current pointer",
                )
            activation = _activation_values(
                event_spec_id=universe.event_spec_id,
                old_universe_version_id=None,
                new_universe_version_id=universe.universe_version_id,
                activation_generation=1,
                activated_at_ms=installed_at_ms,
                operation="seed_initial_active",
            )
            inserted_activation = await self._insert_exact(
                strategy_universe_activations,
                "activation_id",
                activation,
                compare_keys=(
                    "event_spec_id",
                    "old_universe_version_id",
                    "new_universe_version_id",
                    "activation_generation",
                    "operation",
                ),
                conflict_name="universe activation",
            )

        return UniverseInstallCounts(
            inserted_universe_version_count=inserted_version,
            inserted_member_count=inserted_members,
            inserted_instrument_count=inserted_instruments,
            inserted_candidate_scope_count=inserted_scopes,
            inserted_current_pointer_count=inserted_current,
            inserted_activation_count=inserted_activation,
        )

    async def _provision_replacement_runtime_scopes(
        self,
        universe: StrategyUniverseVersion,
        *,
        position_side: Literal["long", "short"],
        installed_at_ms: int,
    ) -> None:
        """Copy current Event authority into deterministic warming replacement scopes."""

        authority_rows = (
            await self._connection.execute(
                sa.select(
                    runtime_scopes_current.c.strategy_version_id,
                    runtime_scopes_current.c.runtime_profile_id,
                    runtime_scopes_current.c.owner_policy_id,
                )
                .join(
                    strategy_universe_current,
                    sa.and_(
                        strategy_universe_current.c.event_spec_id
                        == runtime_scopes_current.c.event_spec_id,
                        strategy_universe_current.c.universe_version_id
                        == runtime_scopes_current.c.universe_version_id,
                    ),
                )
                .where(
                    runtime_scopes_current.c.event_spec_id
                    == universe.event_spec_id,
                    runtime_scopes_current.c.enabled.is_(True),
                )
                .distinct()
            )
        ).mappings().all()
        if not authority_rows:
            return
        if len(authority_rows) != 1:
            raise UniverseSeedConflict(
                "current Event scopes disagree on replacement authority"
            )
        authority = authority_rows[0]
        for member in universe.candidate_members:
            await self._insert_exact(
                runtime_scopes_current,
                "runtime_scope_id",
                {
                    "runtime_scope_id": (
                        f"scope:{universe.event_id}:"
                        f"v{universe.universe_version}:"
                        f"{member.venue_symbol}:{position_side}"
                    ),
                    "strategy_group_id": universe.strategy_group_id,
                    "strategy_version_id": str(
                        authority["strategy_version_id"]
                    ),
                    "event_spec_id": universe.event_spec_id,
                    "runtime_profile_id": str(
                        authority["runtime_profile_id"]
                    ),
                    "owner_policy_id": str(authority["owner_policy_id"]),
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "position_side": position_side,
                    "enabled": True,
                    "universe_version_id": universe.universe_version_id,
                    "observation_enabled": True,
                    "entry_enabled": False,
                    "scope_state": UniverseLifecycle.WARMING.value,
                    "warm_ready_at_ms": None,
                    "scope_version": 1,
                    "observation_due_at_ms": installed_at_ms,
                    "observation_lease_until_ms": None,
                    "observation_claim_owner": None,
                    "updated_at_ms": installed_at_ms,
                },
                compare_keys=(
                    "strategy_group_id",
                    "strategy_version_id",
                    "event_spec_id",
                    "runtime_profile_id",
                    "owner_policy_id",
                    "exchange_instrument_id",
                    "position_side",
                    "enabled",
                    "universe_version_id",
                    "observation_enabled",
                    "entry_enabled",
                    "scope_state",
                    "scope_version",
                ),
                conflict_name="replacement runtime scope",
            )

    async def get(
        self,
        universe_version_id: str,
        *,
        for_update: bool = False,
    ) -> tuple[StrategyUniverseVersion, UniverseLifecycle] | None:
        statement = sa.select(strategy_universe_versions).where(
            strategy_universe_versions.c.universe_version_id
            == universe_version_id
        )
        if for_update:
            statement = statement.with_for_update(of=strategy_universe_versions)
        row = (
            await self._connection.execute(statement)
        ).mappings().one_or_none()
        if row is None:
            return None
        members = (
            await self._connection.execute(
                sa.select(strategy_universe_members)
                .where(
                    strategy_universe_members.c.universe_version_id
                    == universe_version_id
                )
                .order_by(
                    strategy_universe_members.c.member_role,
                    strategy_universe_members.c.priority_rank,
                )
            )
        ).mappings().all()
        universe = StrategyUniverseVersion(
            universe_version_id=str(row["universe_version_id"]),
            universe_version=int(row["universe_version"]),
            strategy_group_id=str(row["strategy_group_id"]),
            event_spec_id=str(row["event_spec_id"]),
            event_id=_event_id(str(row["event_spec_id"])),
            asset_class=cast(
                Literal["crypto", "us_equity"],
                str(row["asset_class"]),
            ),
            members=tuple(_member_from_row(member) for member in members),
        )
        if universe.semantic_digest() != str(row["semantic_digest"]):
            raise UniverseSeedConflict("stored universe digest differs from members")
        return universe, UniverseLifecycle(str(row["lifecycle_state"]))

    async def mark_scope_warm_ready(
        self,
        *,
        runtime_scope_id: str,
        universe_version_id: str,
        observation_fact_digest: str,
        product_profile_id: str | None,
        product_profile_digest: str | None,
        projection_run_id: str | None,
        instrument_rules_projection_version: int | None,
        readiness_digest: str,
        ready_at_ms: int,
    ) -> None:
        if ready_at_ms <= 0:
            raise ValueError("scope warm-ready time must be positive")
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.universe_version_id
                == universe_version_id,
                runtime_scopes_current.c.observation_enabled.is_(True),
                runtime_scopes_current.c.scope_state == "warming",
            )
            .values(warm_ready_at_ms=ready_at_ms, updated_at_ms=ready_at_ms)
        )
        if result.rowcount != 1:
            raise ValueError("scope is not an observable warming universe member")
        await self._connection.execute(
            pg_insert(scope_warm_readiness)
            .values(
                runtime_scope_id=runtime_scope_id,
                universe_version_id=universe_version_id,
                observation_fact_digest=observation_fact_digest,
                product_profile_id=product_profile_id,
                product_profile_digest=product_profile_digest,
                projection_run_id=projection_run_id,
                instrument_rules_projection_version=(
                    instrument_rules_projection_version
                ),
                readiness_digest=readiness_digest,
                ready_at_ms=ready_at_ms,
            )
            .on_conflict_do_update(
                index_elements=[scope_warm_readiness.c.runtime_scope_id],
                set_={
                    "universe_version_id": universe_version_id,
                    "observation_fact_digest": observation_fact_digest,
                    "product_profile_id": product_profile_id,
                    "product_profile_digest": product_profile_digest,
                    "projection_run_id": projection_run_id,
                    "instrument_rules_projection_version": (
                        instrument_rules_projection_version
                    ),
                    "readiness_digest": readiness_digest,
                    "ready_at_ms": ready_at_ms,
                },
            )
        )

    async def freeze_for_corporate_action(
        self,
        *,
        exchange_instrument_id: str,
        required_at_ms: int,
    ) -> tuple[str, ...]:
        if required_at_ms <= 0:
            raise ValueError("corporate-action reprofile time must be positive")
        await self._connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtext(exchange_instrument_id)
                )
            )
        )
        rows = (
            await self._connection.execute(
                sa.select(runtime_scopes_current)
                .join(
                    strategy_universe_current,
                    sa.and_(
                        strategy_universe_current.c.event_spec_id
                        == runtime_scopes_current.c.event_spec_id,
                        strategy_universe_current.c.universe_version_id
                        == runtime_scopes_current.c.universe_version_id,
                    ),
                )
                .where(
                    runtime_scopes_current.c.exchange_instrument_id
                    == exchange_instrument_id,
                    runtime_scopes_current.c.enabled.is_(True),
                    runtime_scopes_current.c.scope_state == "active",
                )
                .with_for_update(of=runtime_scopes_current)
            )
        ).mappings().all()
        scope_ids = tuple(str(row["runtime_scope_id"]) for row in rows)
        if not scope_ids:
            return ()
        await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(runtime_scopes_current.c.runtime_scope_id.in_(scope_ids))
            .values(
                entry_enabled=False,
                scope_state="warming",
                warm_ready_at_ms=None,
                reprofile_required_at_ms=required_at_ms,
                scope_version=runtime_scopes_current.c.scope_version + 1,
                observation_due_at_ms=required_at_ms,
                observation_lease_until_ms=None,
                observation_claim_owner=None,
                updated_at_ms=required_at_ms,
            )
        )
        await self._connection.execute(
            sa.delete(scope_warm_readiness).where(
                scope_warm_readiness.c.runtime_scope_id.in_(scope_ids)
            )
        )
        await self._connection.execute(
            sa.delete(facts_current).where(
                facts_current.c.runtime_scope_id.in_(scope_ids)
            )
        )
        await self._connection.execute(
            sa.delete(readiness_current).where(
                readiness_current.c.runtime_scope_id.in_(scope_ids)
            )
        )
        await self._connection.execute(
            sa.update(armed_structures)
            .where(
                armed_structures.c.exchange_instrument_id
                == exchange_instrument_id,
                armed_structures.c.status == "active",
            )
            .values(status="invalidated_corporate_action")
        )
        return scope_ids

    async def reactivate_reprofiled_scope(
        self,
        *,
        runtime_scope_id: str,
        universe_version_id: str,
        reactivated_at_ms: int,
    ) -> None:
        if reactivated_at_ms <= 0:
            raise ValueError("reprofile activation time must be positive")
        row = (
            await self._connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id,
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id,
                )
                .with_for_update(of=runtime_scopes_current)
            )
        ).mappings().one_or_none()
        if row is None:
            raise ValueError("reprofiled runtime scope is missing")
        required_at_ms = row["reprofile_required_at_ms"]
        if (
            str(row["scope_state"]) != "warming"
            or bool(row["entry_enabled"])
            or row["warm_ready_at_ms"] is None
            or required_at_ms is None
        ):
            raise ValueError("scope is not ready for reprofile activation")
        current_universe = await self._connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == row["event_spec_id"]
            )
        )
        readiness = (
            await self._connection.execute(
                sa.select(scope_warm_readiness).where(
                    scope_warm_readiness.c.runtime_scope_id
                    == runtime_scope_id,
                    scope_warm_readiness.c.universe_version_id
                    == universe_version_id,
                )
            )
        ).mappings().one_or_none()
        current_profile = await self._connection.scalar(
            sa.select(instrument_product_current.c.product_profile_id).where(
                instrument_product_current.c.exchange_instrument_id
                == row["exchange_instrument_id"]
            )
        )
        current_rules_version = await self._connection.scalar(
            sa.select(instrument_rules_current.c.projection_version).where(
                instrument_rules_current.c.exchange_instrument_id
                == row["exchange_instrument_id"]
            )
        )
        if (
            str(current_universe or "") != universe_version_id
            or readiness is None
            or int(readiness["ready_at_ms"]) < int(required_at_ms)
            or str(readiness["product_profile_id"] or "")
            != str(current_profile or "")
            or readiness["instrument_rules_projection_version"] is None
            or int(readiness["instrument_rules_projection_version"])
            != int(current_rules_version or 0)
        ):
            raise ValueError("reprofile activation evidence is incomplete")
        await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == runtime_scope_id
            )
            .values(
                entry_enabled=True,
                scope_state="active",
                reprofile_required_at_ms=None,
                updated_at_ms=reactivated_at_ms,
            )
        )

    async def activate(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        expected_current_universe_version_id: str | None,
        activated_at_ms: int,
    ) -> UniverseActivationRecord:
        if activated_at_ms <= 0:
            raise ValueError("universe activation time must be positive")
        await self._connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtext(event_spec_id)
                )
            )
        )
        stored = await self.get(universe_version_id, for_update=True)
        if stored is None:
            raise ValueError("universe version does not exist")
        universe, lifecycle = stored
        if universe.event_spec_id != event_spec_id:
            raise ValueError("universe and Event identities differ")

        current = (
            await self._connection.execute(
                sa.select(strategy_universe_current)
                .where(
                    strategy_universe_current.c.event_spec_id == event_spec_id
                )
                .with_for_update(of=strategy_universe_current)
            )
        ).mappings().one_or_none()
        if (
            lifecycle is UniverseLifecycle.ACTIVE
            and current is not None
            and str(current["universe_version_id"]) == universe_version_id
        ):
            return await self._load_activation_record(
                event_spec_id=event_spec_id,
                universe_version_id=universe_version_id,
            )
        actual_current_universe_version_id = (
            None if current is None else str(current["universe_version_id"])
        )
        if (
            actual_current_universe_version_id
            != expected_current_universe_version_id
        ):
            raise ValueError("current Universe changed before activation")
        if lifecycle is not UniverseLifecycle.WARMING:
            raise ValueError("only a warming universe can be activated")

        scope_rows = (
            await self._connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.event_spec_id == event_spec_id,
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id,
                )
                .with_for_update(of=runtime_scopes_current)
            )
        ).mappings().all()
        readiness_scope_ids = set(
            (
                await self._connection.execute(
                    sa.select(scope_warm_readiness.c.runtime_scope_id).where(
                        scope_warm_readiness.c.universe_version_id
                        == universe_version_id
                    )
                )
            ).scalars()
        )
        if (
            len(scope_rows) != len(universe.candidate_members)
            or any(
                not bool(row["observation_enabled"])
                or row["warm_ready_at_ms"] is None
                or str(row["scope_state"]) != "warming"
                for row in scope_rows
            )
            or readiness_scope_ids
            != {str(row["runtime_scope_id"]) for row in scope_rows}
        ):
            raise ValueError("activation requires all candidate scopes to be warm")

        old_universe_version_id = actual_current_universe_version_id
        generation = (
            1 if current is None else int(current["activation_generation"]) + 1
        )
        if old_universe_version_id is not None:
            await self._connection.execute(
                sa.update(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.universe_version_id
                    == old_universe_version_id
                )
                .values(lifecycle_state=UniverseLifecycle.RETIRING.value)
            )
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == old_universe_version_id
                )
                .values(entry_enabled=False, scope_state="retiring")
            )
        await self._connection.execute(
            sa.update(strategy_universe_versions)
            .where(
                strategy_universe_versions.c.universe_version_id
                == universe_version_id
            )
            .values(
                lifecycle_state=UniverseLifecycle.ACTIVE.value,
                activated_at_ms=activated_at_ms,
            )
        )
        await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == universe_version_id
            )
            .values(
                entry_enabled=True,
                scope_state="active",
                updated_at_ms=activated_at_ms,
            )
        )
        await self._connection.execute(
            pg_insert(strategy_universe_current)
            .values(
                event_spec_id=event_spec_id,
                universe_version_id=universe_version_id,
                activation_generation=generation,
                activated_at_ms=activated_at_ms,
            )
            .on_conflict_do_update(
                index_elements=[strategy_universe_current.c.event_spec_id],
                set_={
                    "universe_version_id": universe_version_id,
                    "activation_generation": generation,
                    "activated_at_ms": activated_at_ms,
                },
            )
        )
        values = _activation_values(
            event_spec_id=event_spec_id,
            old_universe_version_id=old_universe_version_id,
            new_universe_version_id=universe_version_id,
            activation_generation=generation,
            activated_at_ms=activated_at_ms,
            operation="activate_warmed_universe",
        )
        await self._connection.execute(
            sa.insert(strategy_universe_activations).values(values)
        )
        return UniverseActivationRecord(
            activation_id=str(values["activation_id"]),
            event_spec_id=event_spec_id,
            old_universe_version_id=old_universe_version_id,
            new_universe_version_id=universe_version_id,
            activation_generation=generation,
            activated_scope_count=len(scope_rows),
            activated_at_ms=activated_at_ms,
            activation_digest=str(values["activation_digest"]),
        )

    async def claim_projection(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        as_of_close_time_ms: int,
        claim_owner: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> Literal["claimed", "completed", "busy"]:
        if (
            not event_spec_id.strip()
            or not universe_version_id.strip()
            or not claim_owner.strip()
            or now_ms <= 0
            or lease_until_ms <= now_ms
        ):
            raise ValueError("projection claim inputs are invalid")
        claim_id = _projection_claim_id(
            event_spec_id,
            universe_version_id,
            as_of_close_time_ms,
        )
        row = (
            await self._connection.execute(
                sa.select(universe_projection_leases)
                .where(
                    universe_projection_leases.c.projection_claim_id
                    == claim_id
                )
                .with_for_update()
            )
        ).mappings().one_or_none()
        if row is None:
            await self._connection.execute(
                sa.insert(universe_projection_leases).values(
                    projection_claim_id=claim_id,
                    event_spec_id=event_spec_id,
                    universe_version_id=universe_version_id,
                    as_of_close_time_ms=as_of_close_time_ms,
                    claim_status="running",
                    claim_owner=claim_owner,
                    lease_until_ms=lease_until_ms,
                    failure_reason=None,
                    updated_at_ms=now_ms,
                )
            )
            return "claimed"
        if str(row["claim_status"]) == "completed":
            return "completed"
        if (
            str(row["claim_status"]) == "running"
            and row["lease_until_ms"] is not None
            and int(row["lease_until_ms"]) > now_ms
            and str(row["claim_owner"]) != claim_owner
        ):
            return "busy"
        await self._connection.execute(
            sa.update(universe_projection_leases)
            .where(
                universe_projection_leases.c.projection_claim_id == claim_id
            )
            .values(
                claim_status="running",
                claim_owner=claim_owner,
                lease_until_ms=lease_until_ms,
                failure_reason=None,
                updated_at_ms=now_ms,
            )
        )
        return "claimed"

    async def complete_projection_claim(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        as_of_close_time_ms: int,
        claim_owner: str,
        completed_at_ms: int,
    ) -> None:
        updated = await self._connection.execute(
            sa.update(universe_projection_leases)
            .where(
                universe_projection_leases.c.projection_claim_id
                == _projection_claim_id(
                    event_spec_id,
                    universe_version_id,
                    as_of_close_time_ms,
                ),
                universe_projection_leases.c.claim_status == "running",
                universe_projection_leases.c.claim_owner == claim_owner,
            )
            .values(
                claim_status="completed",
                claim_owner=None,
                lease_until_ms=None,
                failure_reason=None,
                updated_at_ms=completed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise ValueError("projection claim ownership changed before completion")

    async def fail_projection_claim(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        as_of_close_time_ms: int,
        claim_owner: str,
        failure_reason: str,
        failed_at_ms: int,
    ) -> None:
        normalized = str(failure_reason or "").strip()[:512]
        if not normalized:
            raise ValueError("projection failure requires a reason")
        updated = await self._connection.execute(
            sa.update(universe_projection_leases)
            .where(
                universe_projection_leases.c.projection_claim_id
                == _projection_claim_id(
                    event_spec_id,
                    universe_version_id,
                    as_of_close_time_ms,
                ),
                universe_projection_leases.c.claim_status == "running",
                universe_projection_leases.c.claim_owner == claim_owner,
            )
            .values(
                claim_status="failed",
                claim_owner=None,
                lease_until_ms=None,
                failure_reason=normalized,
                updated_at_ms=failed_at_ms,
            )
        )
        if updated.rowcount != 1:
            raise ValueError("projection claim ownership changed before failure")

    async def save_projection(
        self,
        projection: RSRUniverseProjection,
        *,
        persisted_at_ms: int,
    ) -> bool:
        if persisted_at_ms < projection.as_of_close_time_ms:
            raise ValueError("projection cannot be persisted before its close")
        result = await self._connection.execute(
            pg_insert(universe_projection_runs)
            .values(
                projection_run_id=projection.projection_run_id,
                event_spec_id=projection.event_spec_id,
                universe_version_id=projection.universe_version_id,
                universe_digest=projection.universe_digest,
                as_of_close_time_ms=projection.as_of_close_time_ms,
                input_digest=projection.input_digest,
                reference_digest=projection.reference_digest,
                regime_eligible=projection.regime_eligible,
                projection_status="completed",
                failure_reason=None,
                created_at_ms=persisted_at_ms,
                completed_at_ms=persisted_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[universe_projection_runs.c.projection_run_id]
            )
        )
        if result.rowcount != 1:
            existing = await self.get_latest_projection(
                event_spec_id=projection.event_spec_id,
                universe_version_id=projection.universe_version_id,
                at_or_before_close_time_ms=projection.as_of_close_time_ms,
            )
            if existing != projection:
                raise UniverseSeedConflict("projection identity conflict")
            return False
        await self._connection.execute(
            sa.insert(universe_projection_members),
            [
                {
                    "projection_run_id": projection.projection_run_id,
                    "exchange_instrument_id": member.exchange_instrument_id,
                    "eligible": member.eligible,
                    "rank": member.rank,
                    "return_24h": member.return_24h,
                    "return_72h": member.return_72h,
                    "relative_strength_24h": member.relative_strength_24h,
                    "relative_strength_72h": member.relative_strength_72h,
                    "volume_ratio_24h": member.volume_ratio_24h,
                    "trend_eligible": member.trend_eligible,
                    "metrics_digest": _model_digest(member),
                }
                for member in projection.members
            ],
        )
        return True

    async def get_latest_projection(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        at_or_before_close_time_ms: int,
    ) -> RSRUniverseProjection | None:
        row = (
            await self._connection.execute(
                sa.select(universe_projection_runs)
                .where(
                    universe_projection_runs.c.event_spec_id == event_spec_id,
                    universe_projection_runs.c.universe_version_id
                    == universe_version_id,
                    universe_projection_runs.c.as_of_close_time_ms
                    <= at_or_before_close_time_ms,
                    universe_projection_runs.c.projection_status == "completed",
                )
                .order_by(
                    universe_projection_runs.c.as_of_close_time_ms.desc(),
                    universe_projection_runs.c.projection_run_id,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        member_rows = (
            await self._connection.execute(
                sa.select(universe_projection_members)
                .where(
                    universe_projection_members.c.projection_run_id
                    == row["projection_run_id"]
                )
                .order_by(
                    universe_projection_members.c.exchange_instrument_id
                )
            )
        ).mappings().all()
        members = tuple(_projection_member_from_row(member) for member in member_rows)
        if any(
            _model_digest(member) != str(member_row["metrics_digest"])
            for member, member_row in zip(members, member_rows, strict=True)
        ):
            raise UniverseSeedConflict("projection member digest conflict")
        return RSRUniverseProjection(
            projection_run_id=str(row["projection_run_id"]),
            event_spec_id=str(row["event_spec_id"]),
            universe_version_id=str(row["universe_version_id"]),
            universe_digest=str(row["universe_digest"]),
            as_of_close_time_ms=int(row["as_of_close_time_ms"]),
            regime_eligible=bool(row["regime_eligible"]),
            reference_digest=str(row["reference_digest"]),
            members=members,
            input_digest=str(row["input_digest"]),
        )

    async def save_armed_structure(
        self,
        armed: VCBArmedStructure,
    ) -> bool:
        generation = armed.armed_at_ms // 3_600_000
        result = await self._connection.execute(
            pg_insert(armed_structures)
            .values(
                armed_structure_id=armed.armed_structure_id,
                event_spec_id=armed.event_spec_id,
                universe_version_id=armed.universe_version_id,
                projection_run_id=armed.projection_run_id,
                exchange_instrument_id=armed.exchange_instrument_id,
                armed_generation=generation,
                breakout_boundary=armed.breakout_boundary,
                compression_ratio=armed.compression_ratio,
                input_digest=armed.input_digest,
                status="active",
                armed_at_ms=armed.armed_at_ms,
                expires_at_ms=armed.expires_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[armed_structures.c.armed_structure_id]
            )
        )
        return result.rowcount == 1

    async def get_active_armed_structure(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        projection_run_id: str,
        exchange_instrument_id: str,
        now_ms: int,
    ) -> VCBArmedStructure | None:
        row = (
            await self._connection.execute(
                sa.select(
                    armed_structures,
                    strategy_universe_versions.c.semantic_digest.label(
                        "universe_digest"
                    ),
                    universe_projection_members.c.rank,
                    universe_projection_members.c.relative_strength_24h,
                    universe_projection_members.c.relative_strength_72h,
                    universe_projection_members.c.volume_ratio_24h,
                )
                .join(
                    strategy_universe_versions,
                    strategy_universe_versions.c.universe_version_id
                    == armed_structures.c.universe_version_id,
                )
                .join(
                    universe_projection_members,
                    sa.and_(
                        universe_projection_members.c.projection_run_id
                        == armed_structures.c.projection_run_id,
                        universe_projection_members.c.exchange_instrument_id
                        == armed_structures.c.exchange_instrument_id,
                    ),
                )
                .where(
                    armed_structures.c.event_spec_id == event_spec_id,
                    armed_structures.c.universe_version_id
                    == universe_version_id,
                    armed_structures.c.projection_run_id == projection_run_id,
                    armed_structures.c.exchange_instrument_id
                    == exchange_instrument_id,
                    armed_structures.c.status == "active",
                    armed_structures.c.armed_at_ms < now_ms,
                    armed_structures.c.expires_at_ms >= now_ms,
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None or row["rank"] is None:
            return None
        return VCBArmedStructure(
            armed_structure_id=str(row["armed_structure_id"]),
            event_spec_id=str(row["event_spec_id"]),
            universe_version_id=str(row["universe_version_id"]),
            universe_digest=str(row["universe_digest"]),
            projection_run_id=str(row["projection_run_id"]),
            exchange_instrument_id=str(row["exchange_instrument_id"]),
            rsr_rank=int(row["rank"]),
            relative_strength_24h=cast(
                Any, row["relative_strength_24h"]
            ),
            relative_strength_72h=cast(
                Any, row["relative_strength_72h"]
            ),
            rsr_volume_ratio_24h=cast(Any, row["volume_ratio_24h"]),
            compression_ratio=cast(Any, row["compression_ratio"]),
            breakout_boundary=cast(Any, row["breakout_boundary"]),
            armed_at_ms=int(row["armed_at_ms"]),
            expires_at_ms=int(row["expires_at_ms"]),
            input_digest=str(row["input_digest"]),
        )

    async def _load_activation_record(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
    ) -> UniverseActivationRecord:
        row = (
            await self._connection.execute(
                sa.select(strategy_universe_activations)
                .where(
                    strategy_universe_activations.c.event_spec_id
                    == event_spec_id,
                    strategy_universe_activations.c.new_universe_version_id
                    == universe_version_id,
                )
                .order_by(
                    strategy_universe_activations.c.activation_generation.desc()
                )
                .limit(1)
            )
        ).mappings().one()
        scope_count = int(
            await self._connection.scalar(
                sa.select(sa.func.count())
                .select_from(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id,
                    runtime_scopes_current.c.scope_state == "active",
                )
            )
            or 0
        )
        return UniverseActivationRecord(
            activation_id=str(row["activation_id"]),
            event_spec_id=event_spec_id,
            old_universe_version_id=(
                None
                if row["old_universe_version_id"] is None
                else str(row["old_universe_version_id"])
            ),
            new_universe_version_id=universe_version_id,
            activation_generation=int(row["activation_generation"]),
            activated_scope_count=scope_count,
            activated_at_ms=int(row["activated_at_ms"]),
            activation_digest=str(row["activation_digest"]),
        )

    async def _assert_exact_members(
        self,
        universe: StrategyUniverseVersion,
    ) -> None:
        rows = (
            await self._connection.execute(
                sa.select(strategy_universe_members)
                .where(
                    strategy_universe_members.c.universe_version_id
                    == universe.universe_version_id
                )
                .order_by(
                    strategy_universe_members.c.member_role,
                    strategy_universe_members.c.priority_rank,
                )
            )
        ).mappings().all()
        actual = {
            (
                str(row["exchange_instrument_id"]),
                str(row["venue_symbol"]),
                str(row["member_role"]),
                int(row["priority_rank"]),
            )
            for row in rows
        }
        expected = {
            (
                member.exchange_instrument_id,
                member.venue_symbol,
                member.role.value,
                member.priority_rank,
            )
            for member in universe.members
        }
        if actual != expected:
            raise UniverseSeedConflict("universe member conflict")

    async def _insert_exact(
        self,
        table: sa.Table,
        identity_columns: str | tuple[str, ...],
        values: Mapping[str, Any],
        *,
        compare_keys: tuple[str, ...],
        conflict_name: str,
    ) -> int:
        identity_names = (
            (identity_columns,)
            if isinstance(identity_columns, str)
            else identity_columns
        )
        row = (
            await self._connection.execute(
                sa.select(table)
                .where(
                    *[
                        table.c[name] == values[name]
                        for name in identity_names
                    ]
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            await self._connection.execute(sa.insert(table).values(dict(values)))
            return 1
        if any(not _same_value(row[key], values[key]) for key in compare_keys):
            identity = ":".join(str(values[key]) for key in identity_names)
            raise UniverseSeedConflict(f"{conflict_name} conflict: {identity}")
        return 0


def _member_from_row(row: RowMapping) -> UniverseMember:
    return UniverseMember(
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        venue_symbol=str(row["venue_symbol"]),
        role=UniverseMemberRole(str(row["member_role"])),
        priority_rank=int(row["priority_rank"]),
    )


def _projection_member_from_row(row: RowMapping) -> RSRProjectionMember:
    return RSRProjectionMember(
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        return_24h=cast(Any, row["return_24h"]),
        return_72h=cast(Any, row["return_72h"]),
        relative_strength_24h=cast(Any, row["relative_strength_24h"]),
        relative_strength_72h=cast(Any, row["relative_strength_72h"]),
        volume_ratio_24h=cast(Any, row["volume_ratio_24h"]),
        trend_eligible=bool(row["trend_eligible"]),
        eligible=bool(row["eligible"]),
        rank=None if row["rank"] is None else int(row["rank"]),
    )


def _model_digest(model: RSRProjectionMember) -> str:
    encoded = json.dumps(
        model.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _projection_claim_id(
    event_spec_id: str,
    universe_version_id: str,
    as_of_close_time_ms: int,
) -> str:
    encoded = json.dumps(
        {
            "event_spec_id": event_spec_id,
            "universe_version_id": universe_version_id,
            "as_of_close_time_ms": as_of_close_time_ms,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"projection-claim:{sha256(encoded).hexdigest()}"


def _event_id(event_spec_id: str) -> str:
    parts = event_spec_id.split(":")
    if len(parts) != 4 or parts[0] != "event_spec":
        raise UniverseSeedConflict("stored Event Spec identity is malformed")
    return parts[2]


def _activation_values(
    *,
    event_spec_id: str,
    old_universe_version_id: str | None,
    new_universe_version_id: str,
    activation_generation: int,
    activated_at_ms: int,
    operation: str,
) -> dict[str, object]:
    payload = {
        "event_spec_id": event_spec_id,
        "old_universe_version_id": old_universe_version_id,
        "new_universe_version_id": new_universe_version_id,
        "activation_generation": activation_generation,
        "operation": operation,
        "activated_at_ms": activated_at_ms,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = f"sha256:{sha256(encoded).hexdigest()}"
    return {
        "activation_id": (
            f"universe-activation:{event_spec_id}:g{activation_generation}"
        ),
        **payload,
        "activation_digest": digest,
    }


def _same_value(actual: object, expected: object) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return actual == expected or str(actual) == str(expected)
