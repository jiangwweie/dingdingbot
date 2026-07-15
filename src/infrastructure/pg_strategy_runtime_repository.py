"""PG repository for StrategyRuntimeInstance shadow governance."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String, and_, column, func, or_, select, values
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeEvent,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
    StrategyRuntimePolicySnapshot,
    StrategyRuntimeReviewRequirement,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGStrategyRuntimeEventORM,
    PGStrategyRuntimeInstanceORM,
)
from src.application.readmodels.strategy_runtime_watcher_identity import (
    StrategyRuntimeWatcherIdentity,
    StrategyRuntimeWatcherIdentityPage,
    WatcherCandidateLaneKey,
)


class PgStrategyRuntimeRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def create(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        async with self._session_maker() as session:
            async with session.begin():
                row = self._to_orm(runtime)
                session.add(row)
                await session.flush()
                return self._to_domain(row)

    async def get(self, runtime_instance_id: str) -> Optional[StrategyRuntimeInstance]:
        async with self._session_maker() as session:
            row = await session.get(PGStrategyRuntimeInstanceORM, runtime_instance_id)
            return self._to_domain(row) if row is not None else None

    async def list(
        self,
        *,
        status: Optional[StrategyRuntimeInstanceStatus] = None,
        limit: int = 100,
    ) -> list[StrategyRuntimeInstance]:
        async with self._session_maker() as session:
            stmt = select(PGStrategyRuntimeInstanceORM)
            if status is not None:
                stmt = stmt.where(PGStrategyRuntimeInstanceORM.status == status.value)
            stmt = stmt.order_by(PGStrategyRuntimeInstanceORM.updated_at_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            return [self._to_domain(row) for row in result.scalars().all()]

    async def list_watcher_candidate_identity_page(
        self,
        *,
        candidate_lane_keys: tuple[WatcherCandidateLaneKey, ...],
        after_runtime_instance_id: str | None,
        limit: int = 16,
    ) -> StrategyRuntimeWatcherIdentityPage:
        if not 1 <= limit <= 100:
            raise ValueError("watcher_candidate_page_limit_invalid")
        if not candidate_lane_keys or len(candidate_lane_keys) > 256:
            raise ValueError("watcher_candidate_lane_keys_invalid")
        normalized_symbol = func.replace(
            func.replace(PGStrategyRuntimeInstanceORM.symbol, "/", ""),
            ":USDT",
            "",
        )
        lane_predicate = or_(
            *(
                and_(
                    PGStrategyRuntimeInstanceORM.strategy_family_id
                    == lane.strategy_group_id,
                    normalized_symbol
                    == lane.symbol.replace("/", "").replace(":USDT", ""),
                    PGStrategyRuntimeInstanceORM.side == lane.side,
                )
                for lane in candidate_lane_keys
            )
        )
        active_predicate = PGStrategyRuntimeInstanceORM.status == "active"
        columns = (
            PGStrategyRuntimeInstanceORM.runtime_instance_id,
            PGStrategyRuntimeInstanceORM.strategy_family_id,
            PGStrategyRuntimeInstanceORM.strategy_family_version_id,
            PGStrategyRuntimeInstanceORM.symbol,
            PGStrategyRuntimeInstanceORM.side,
            PGStrategyRuntimeInstanceORM.carrier_id,
            PGStrategyRuntimeInstanceORM.status,
        )
        async with self._session_maker() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                candidate_lanes = values(
                    column("strategy_group_id", String),
                    column("symbol", String),
                    column("side", String),
                    name="candidate_lanes",
                ).data(
                    [
                        (
                            lane.strategy_group_id,
                            lane.symbol.replace("/", "").replace(":USDT", ""),
                            lane.side,
                        )
                        for lane in candidate_lane_keys
                    ]
                )
                stmt = select(*columns).select_from(
                    PGStrategyRuntimeInstanceORM.__table__.join(
                        candidate_lanes,
                        and_(
                            PGStrategyRuntimeInstanceORM.strategy_family_id
                            == candidate_lanes.c.strategy_group_id,
                            normalized_symbol == candidate_lanes.c.symbol,
                            PGStrategyRuntimeInstanceORM.side
                            == candidate_lanes.c.side,
                        ),
                    )
                ).where(active_predicate)
            else:
                # SQLite is retained only for local deterministic unit tests;
                # production PostgreSQL always uses the bounded VALUES join.
                stmt = select(*columns).where(active_predicate, lane_predicate)
            if after_runtime_instance_id:
                stmt = stmt.where(
                    PGStrategyRuntimeInstanceORM.runtime_instance_id
                    > after_runtime_instance_id
                )
            stmt = stmt.order_by(
                PGStrategyRuntimeInstanceORM.runtime_instance_id.asc()
            ).limit(limit + 1)
            rows = (await session.execute(stmt)).mappings().all()
            excluded_count = int(
                await session.scalar(
                    select(func.count())
                    .select_from(PGStrategyRuntimeInstanceORM)
                    .where(active_predicate, ~lane_predicate)
                )
                or 0
            )
            excluded_rows = (
                await session.execute(
                    select(PGStrategyRuntimeInstanceORM.runtime_instance_id)
                    .where(active_predicate, ~lane_predicate)
                    .order_by(PGStrategyRuntimeInstanceORM.runtime_instance_id.asc())
                    .limit(32)
                )
            ).scalars().all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = tuple(
            StrategyRuntimeWatcherIdentity(
                runtime_instance_id=str(row["runtime_instance_id"]),
                strategy_group_id=str(row["strategy_family_id"]),
                strategy_group_version_id=str(row["strategy_family_version_id"]),
                symbol=str(row["symbol"]),
                side=str(row["side"]),
                carrier_id=(
                    str(row["carrier_id"])
                    if row["carrier_id"] is not None
                    else None
                ),
                status="active",
            )
            for row in page_rows
        )
        return StrategyRuntimeWatcherIdentityPage(
            items=items,
            next_cursor=(items[-1].runtime_instance_id if has_more else None),
            has_more=has_more,
            excluded_active_count=excluded_count,
            excluded_active_sample_ids=tuple(str(value) for value in excluded_rows),
        )

    async def update_status(self, runtime: StrategyRuntimeInstance) -> StrategyRuntimeInstance:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(
                    PGStrategyRuntimeInstanceORM,
                    runtime.runtime_instance_id,
                )
                if row is None:
                    raise ValueError(f"strategy runtime not found: {runtime.runtime_instance_id}")
                updated = self._to_orm(runtime)
                for key in [
                    "runtime_instance_id",
                    "trial_binding_id",
                    "admission_decision_id",
                    "strategy_family_id",
                    "strategy_family_version_id",
                    "owner_risk_acceptance_id",
                    "carrier_id",
                    "symbol",
                    "side",
                    "status",
                    "boundary_json",
                    "policy_snapshot_json",
                    "review_requirement",
                    "execution_enabled",
                    "shadow_mode",
                    "created_at_ms",
                    "updated_at_ms",
                    "activated_at_ms",
                    "expires_at_ms",
                    "revoked_at_ms",
                    "closed_at_ms",
                    "metadata_json",
                ]:
                    value = getattr(updated, key)
                    setattr(row, key, value)
                await session.flush()
                return self._to_domain(row)

    async def record_event(self, event: StrategyRuntimeEvent) -> StrategyRuntimeEvent:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGStrategyRuntimeEventORM(
                    event_id=event.event_id,
                    runtime_instance_id=event.runtime_instance_id,
                    event_type=event.event_type,
                    previous_status=(
                        event.previous_status.value
                        if event.previous_status is not None
                        else None
                    ),
                    next_status=event.next_status.value,
                    actor=event.actor,
                    reason=event.reason,
                    metadata_json=dict(event.metadata),
                    created_at_ms=event.created_at_ms,
                )
                session.add(row)
                await session.flush()
                return self._event_to_domain(row)

    async def find_by_trial_binding_id(
        self,
        trial_binding_id: str,
    ) -> Optional[StrategyRuntimeInstance]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGStrategyRuntimeInstanceORM)
                .where(PGStrategyRuntimeInstanceORM.trial_binding_id == trial_binding_id)
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._to_domain(row) if row is not None else None

    @staticmethod
    def _to_orm(runtime: StrategyRuntimeInstance) -> PGStrategyRuntimeInstanceORM:
        payload = runtime.model_dump(mode="json")
        return PGStrategyRuntimeInstanceORM(
            runtime_instance_id=payload["runtime_instance_id"],
            trial_binding_id=payload["trial_binding_id"],
            admission_decision_id=payload["admission_decision_id"],
            strategy_family_id=payload["strategy_family_id"],
            strategy_family_version_id=payload["strategy_family_version_id"],
            owner_risk_acceptance_id=payload.get("owner_risk_acceptance_id"),
            carrier_id=payload.get("carrier_id"),
            symbol=payload["symbol"],
            side=payload["side"],
            status=payload["status"],
            boundary_json=dict(payload["boundary"]),
            policy_snapshot_json=dict(payload["policy_snapshot"]),
            review_requirement=payload["review_requirement"],
            execution_enabled=payload["execution_enabled"],
            shadow_mode=payload["shadow_mode"],
            created_at_ms=payload["created_at_ms"],
            updated_at_ms=payload["updated_at_ms"],
            activated_at_ms=payload.get("activated_at_ms"),
            expires_at_ms=payload.get("expires_at_ms"),
            revoked_at_ms=payload.get("revoked_at_ms"),
            closed_at_ms=payload.get("closed_at_ms"),
            metadata_json=dict(payload["metadata"]),
        )

    @staticmethod
    def _to_domain(row: PGStrategyRuntimeInstanceORM) -> StrategyRuntimeInstance:
        return StrategyRuntimeInstance(
            runtime_instance_id=row.runtime_instance_id,
            trial_binding_id=row.trial_binding_id,
            admission_decision_id=row.admission_decision_id,
            strategy_family_id=row.strategy_family_id,
            strategy_family_version_id=row.strategy_family_version_id,
            owner_risk_acceptance_id=row.owner_risk_acceptance_id,
            carrier_id=row.carrier_id,
            symbol=row.symbol,
            side=row.side,
            status=StrategyRuntimeInstanceStatus(row.status),
            boundary=StrategyRuntimeBoundary.model_validate(row.boundary_json),
            policy_snapshot=StrategyRuntimePolicySnapshot.model_validate(
                row.policy_snapshot_json
            ),
            review_requirement=StrategyRuntimeReviewRequirement(row.review_requirement),
            execution_enabled=row.execution_enabled,
            shadow_mode=row.shadow_mode,
            created_at_ms=row.created_at_ms,
            updated_at_ms=row.updated_at_ms,
            activated_at_ms=row.activated_at_ms,
            expires_at_ms=row.expires_at_ms,
            revoked_at_ms=row.revoked_at_ms,
            closed_at_ms=row.closed_at_ms,
            metadata=row.metadata_json,
        )

    @staticmethod
    def _event_to_domain(row: PGStrategyRuntimeEventORM) -> StrategyRuntimeEvent:
        return StrategyRuntimeEvent(
            event_id=row.event_id,
            runtime_instance_id=row.runtime_instance_id,
            event_type=row.event_type,
            previous_status=(
                StrategyRuntimeInstanceStatus(row.previous_status)
                if row.previous_status is not None
                else None
            ),
            next_status=StrategyRuntimeInstanceStatus(row.next_status),
            actor=row.actor,
            reason=row.reason,
            metadata=row.metadata_json,
            created_at_ms=row.created_at_ms,
        )
