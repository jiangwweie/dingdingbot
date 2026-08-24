"""PostgreSQL persistence for typed signals and readiness authority."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import (
    ActiveStrategyUniverseMembershipSnapshot,
    ActiveStrategyUniverseSnapshot,
    EventSpecSnapshot,
    InstrumentRulesSnapshot,
    InstrumentSnapshot,
    ObservationScopeClaim,
    ObservationUniverseMembershipSnapshot,
    ReadinessSnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeProfileSnapshot,
    RuntimeScopeSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
    WarmReadiness,
)
from src.trading_kernel.domain.arbitration import EntryCandidate
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.exposure_episode import ExposureEpisodeState
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductSessionSnapshot,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
)
from src.trading_kernel.domain.strategy_universe import StrategyUniverseVersion
from src.trading_kernel.infrastructure.pg_models import (
    event_required_facts,
    event_specs,
    exposure_episode_current,
    facts_current,
    instrument_certification_current,
    instrument_product_current,
    instrument_product_profiles,
    instrument_rules_current,
    instruments,
    owner_policy_current,
    readiness_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    signal_events,
    signal_fact_snapshots,
    strategy_groups,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_product_current import (
    PostgresProductCurrentRepository,
)


class PostgresSignalRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, signal: StrategySignal) -> bool:
        result = await self._connection.execute(
            pg_insert(signal_events)
            .values(_signal_values(signal))
            .on_conflict_do_nothing()
        )
        if result.rowcount != 1:
            return False
        await self._connection.execute(
            sa.insert(signal_fact_snapshots),
            [_fact_snapshot_values(signal.signal_event_id, fact) for fact in signal.facts],
        )
        return True

    async def get(self, signal_event_id: str) -> StrategySignal | None:
        result = await self._connection.execute(
            sa.select(signal_events).where(
                signal_events.c.signal_event_id == signal_event_id
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        facts = await self.get_fact_snapshots(signal_event_id)
        return _signal_from_row(row, facts)

    async def get_fact_snapshots(
        self,
        signal_event_id: str,
    ) -> tuple[SignalFactSnapshot, ...]:
        result = await self._connection.execute(
            sa.select(signal_fact_snapshots)
            .where(signal_fact_snapshots.c.signal_event_id == signal_event_id)
            .order_by(signal_fact_snapshots.c.fact_definition_id)
        )
        return tuple(
            SignalFactSnapshot.model_validate(row, extra="ignore")
            for row in result.mappings()
        )

    async def upsert_current_facts(
        self,
        *,
        runtime_scope_id: str,
        facts: tuple[SignalFactSnapshot, ...],
    ) -> tuple[SignalFactSnapshot, ...]:
        persisted: list[SignalFactSnapshot] = []
        for fact in sorted(facts, key=lambda item: item.fact_definition_id):
            result = await self._connection.execute(
                sa.select(facts_current)
                .where(
                    facts_current.c.runtime_scope_id == runtime_scope_id,
                    facts_current.c.fact_definition_id
                    == fact.fact_definition_id,
                )
                .with_for_update()
            )
            row = result.mappings().one_or_none()
            if row is None:
                projection_version = 1
                await self._connection.execute(
                    sa.insert(facts_current).values(
                        fact_current_id=(
                            f"fact-current:{runtime_scope_id}:"
                            f"{fact.fact_definition_id}"
                        ),
                        runtime_scope_id=runtime_scope_id,
                        fact_definition_id=fact.fact_definition_id,
                        value=fact.value,
                        satisfied=fact.satisfied,
                        observed_at_ms=fact.observed_at_ms,
                        valid_until_ms=fact.valid_until_ms,
                        projection_version=projection_version,
                    )
                )
            elif _current_fact_matches(row, fact):
                projection_version = int(row["projection_version"])
            else:
                projection_version = int(row["projection_version"]) + 1
                await self._connection.execute(
                    sa.update(facts_current)
                    .where(
                        facts_current.c.runtime_scope_id == runtime_scope_id,
                        facts_current.c.fact_definition_id
                        == fact.fact_definition_id,
                    )
                    .values(
                        value=fact.value,
                        satisfied=fact.satisfied,
                        observed_at_ms=fact.observed_at_ms,
                        valid_until_ms=fact.valid_until_ms,
                        projection_version=projection_version,
                    )
                )
            persisted.append(
                fact.model_copy(
                    update={"projection_version": projection_version}
                )
            )
        return tuple(persisted)

    async def lock_exposure_episode(
        self,
        episode_domain_key: str,
    ) -> ExposureEpisodeState | None:
        normalized_key = str(episode_domain_key or "").strip()
        if not normalized_key:
            raise ValueError("Episode domain key must be non-blank")
        await self._connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtextextended(normalized_key, 0)
                )
            )
        )
        row = (
            await self._connection.execute(
                sa.select(exposure_episode_current)
                .where(
                    exposure_episode_current.c.episode_domain_key
                    == normalized_key
                )
                .with_for_update()
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else ExposureEpisodeState.model_validate(row, extra="ignore")
        )

    async def save_exposure_episode(
        self,
        state: ExposureEpisodeState,
        *,
        expected_version: int,
    ) -> None:
        if expected_version < 0:
            raise ValueError("Episode expected version cannot be negative")
        if state.projection_version != expected_version + 1:
            raise ValueError("Episode projection version is not monotonic")
        values = state.model_dump(mode="python")
        if expected_version == 0:
            result = await self._connection.execute(
                pg_insert(exposure_episode_current)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        exposure_episode_current.c.episode_domain_key
                    ]
                )
            )
        else:
            result = await self._connection.execute(
                sa.update(exposure_episode_current)
                .where(
                    exposure_episode_current.c.episode_domain_key
                    == state.episode_domain_key,
                    exposure_episode_current.c.projection_version
                    == expected_version,
                )
                .values(**values)
            )
        if result.rowcount != 1:
            raise RuntimeError("Exposure Episode authority changed")

    async def get_next_ready(self, *, now_ms: int) -> StrategySignal | None:
        return await self._get_next_candidate_ready(
            expiry_predicate=signal_events.c.expires_at_ms > now_ms
        )

    async def get_next_stale_ready(self, *, now_ms: int) -> StrategySignal | None:
        return await self._get_next_candidate_ready(
            expiry_predicate=signal_events.c.expires_at_ms <= now_ms
        )

    async def list_ready_candidates(
        self,
        *,
        now_ms: int,
        limit: int,
    ) -> tuple[EntryCandidate, ...]:
        if limit <= 0 or limit > 64:
            raise ValueError("ready candidate limit must be between 1 and 64")
        already_ticketed = sa.exists(
            sa.select(trade_tickets.c.ticket_id).where(
                trade_tickets.c.signal_event_id == signal_events.c.signal_event_id
            )
        )
        result = await self._connection.execute(
            sa.select(
                signal_events,
                owner_policy_current.c.priority_rank.label("owner_priority"),
            )
            .join(
                readiness_current,
                readiness_current.c.signal_event_id
                == signal_events.c.signal_event_id,
            )
            .join(
                runtime_scopes_current,
                runtime_scopes_current.c.runtime_scope_id
                == signal_events.c.runtime_scope_id,
            )
            .join(
                owner_policy_current,
                owner_policy_current.c.owner_policy_id
                == runtime_scopes_current.c.owner_policy_id,
            )
            .join(
                instrument_certification_current,
                sa.and_(
                    instrument_certification_current.c.runtime_profile_id
                    == runtime_scopes_current.c.runtime_profile_id,
                    instrument_certification_current.c.exchange_instrument_id
                    == signal_events.c.exchange_instrument_id,
                ),
            )
            .join(
                strategy_universe_current,
                sa.and_(
                    strategy_universe_current.c.event_spec_id
                    == signal_events.c.event_spec_id,
                    strategy_universe_current.c.universe_version_id
                    == signal_events.c.universe_version_id,
                    strategy_universe_current.c.semantic_digest
                    == signal_events.c.universe_semantic_digest,
                ),
            )
            .join(
                strategy_universe_members,
                sa.and_(
                    strategy_universe_members.c.universe_version_id
                    == signal_events.c.universe_version_id,
                    strategy_universe_members.c.exchange_instrument_id
                    == signal_events.c.exchange_instrument_id,
                ),
            )
            .where(
                readiness_current.c.readiness_state == "candidate_ready",
                signal_events.c.expires_at_ms > now_ms,
                runtime_scopes_current.c.entry_enabled.is_(True),
                runtime_scopes_current.c.lifecycle_state == "active",
                runtime_scopes_current.c.scope_version
                == signal_events.c.runtime_scope_version,
                runtime_scopes_current.c.universe_version_id
                == signal_events.c.universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == signal_events.c.universe_semantic_digest,
                owner_policy_current.c.enabled.is_(True),
                owner_policy_current.c.new_entry_submit_enabled.is_(True),
                instrument_certification_current.c.status == "eligible",
                instrument_certification_current.c.blocker_code.is_(None),
                instrument_certification_current.c.valid_until_ms > now_ms,
                ~already_ticketed,
            )
            .order_by(
                owner_policy_current.c.priority_rank,
                signal_events.c.occurred_at_ms,
                signal_events.c.observed_at_ms,
                signal_events.c.signal_event_id,
            )
            .limit(limit)
        )
        candidates: list[EntryCandidate] = []
        for row in result.mappings():
            signal_event_id = str(row["signal_event_id"])
            facts = await self.get_fact_snapshots(signal_event_id)
            candidates.append(
                EntryCandidate(
                    signal=_signal_from_row(row, facts),
                    owner_policy_priority=int(row["owner_priority"]),
                )
            )
        return tuple(candidates)

    async def claim_next_observation_scope(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ObservationScopeClaim | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("observation worker identity must be non-blank")
        if now_ms <= 0 or lease_until_ms <= now_ms:
            raise ValueError("observation lease must end after its claim time")
        result = await self._connection.execute(
            sa.select(
                runtime_scopes_current.c.runtime_scope_id,
                event_specs.c.timeframe,
            )
            .join(
                event_specs,
                event_specs.c.event_spec_id
                == runtime_scopes_current.c.event_spec_id,
            )
            .where(
                runtime_scopes_current.c.observation_enabled.is_(True),
                runtime_scopes_current.c.lifecycle_state.in_(
                    ("warming", "active")
                ),
                event_specs.c.status == "active",
                sa.or_(
                    runtime_scopes_current.c.next_observation_due_at_ms.is_(None),
                    runtime_scopes_current.c.next_observation_due_at_ms <= now_ms,
                ),
                sa.or_(
                    runtime_scopes_current.c.lease_expires_at_ms.is_(None),
                    runtime_scopes_current.c.lease_expires_at_ms <= now_ms,
                ),
            )
            .order_by(
                sa.func.coalesce(
                    runtime_scopes_current.c.next_observation_due_at_ms,
                    0,
                ),
                runtime_scopes_current.c.runtime_scope_id,
            )
            .limit(1)
            .with_for_update(of=runtime_scopes_current, skip_locked=True)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        runtime_scope_id = str(row["runtime_scope_id"])
        timeframe = cast(Literal["15m", "1h"], str(row["timeframe"]))
        interval_ms = 900_000 if timeframe == "15m" else 3_600_000
        trigger_candle_close_time_ms = now_ms - (now_ms % interval_ms)
        generation = (
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
                .values(
                    lease_owner=normalized_worker_id,
                    lease_expires_at_ms=lease_until_ms,
                    observation_generation=(
                        runtime_scopes_current.c.observation_generation + 1
                    ),
                )
                .returning(
                    runtime_scopes_current.c.observation_generation
                )
            )
        ).scalar_one()
        return ObservationScopeClaim(
            runtime_scope_id=runtime_scope_id,
            timeframe=timeframe,
            trigger_candle_close_time_ms=trigger_candle_close_time_ms,
            observation_generation=int(generation),
        )

    async def claim_observation_generation(
        self,
        runtime_scope_id: str,
    ) -> RuntimeScopeSnapshot | None:
        row = (
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
                .values(
                    observation_generation=(
                        runtime_scopes_current.c.observation_generation + 1
                    )
                )
                .returning(runtime_scopes_current)
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeScopeSnapshot.model_validate(row, extra="ignore")
        )

    async def schedule_observation_scope(
        self,
        *,
        runtime_scope_id: str,
        worker_id: str,
        observation_generation: int,
        due_at_ms: int,
    ) -> None:
        if due_at_ms <= 0:
            raise ValueError("observation due time must be positive")
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.lease_owner == worker_id,
                runtime_scopes_current.c.observation_generation
                == observation_generation,
            )
            .values(
                next_observation_due_at_ms=due_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("observation scope lease is not owned by worker")

    async def _get_next_candidate_ready(
        self,
        *,
        expiry_predicate: sa.ColumnElement[bool],
    ) -> StrategySignal | None:
        already_ticketed = sa.exists(
            sa.select(trade_tickets.c.ticket_id).where(
                trade_tickets.c.signal_event_id == signal_events.c.signal_event_id
            )
        )
        statement = (
            sa.select(signal_events)
            .join(
                readiness_current,
                readiness_current.c.signal_event_id
                == signal_events.c.signal_event_id,
            )
            .where(
                readiness_current.c.readiness_state == "candidate_ready",
                expiry_predicate,
                ~already_ticketed,
            )
            .order_by(
                signal_events.c.occurred_at_ms,
                signal_events.c.signal_event_id,
            )
            .limit(1)
            .with_for_update(of=readiness_current, skip_locked=True)
        )
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        signal_event_id = str(row["signal_event_id"])
        facts = await self.get_fact_snapshots(signal_event_id)
        return _signal_from_row(row, facts)

    async def get_readiness(
        self,
        runtime_scope_id: str,
    ) -> ReadinessSnapshot | None:
        result = await self._connection.execute(
            sa.select(readiness_current).where(
                readiness_current.c.runtime_scope_id == runtime_scope_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else ReadinessSnapshot.model_validate(row)

    async def save_readiness(
        self,
        *,
        runtime_scope_id: str,
        readiness_state: str,
        first_blocker: str | None,
        signal_event_id: str | None,
        fact_summary: dict[str, JsonValue],
        updated_at_ms: int,
    ) -> ReadinessSnapshot:
        await self._connection.execute(
            pg_insert(readiness_current)
            .values(
                runtime_scope_id=runtime_scope_id,
                readiness_state=readiness_state,
                first_blocker=first_blocker,
                signal_event_id=signal_event_id,
                fact_summary=fact_summary,
                updated_at_ms=updated_at_ms,
                projection_version=1,
            )
            .on_conflict_do_update(
                index_elements=[readiness_current.c.runtime_scope_id],
                set_={
                    "readiness_state": readiness_state,
                    "first_blocker": first_blocker,
                    "signal_event_id": signal_event_id,
                    "fact_summary": fact_summary,
                    "updated_at_ms": updated_at_ms,
                    "projection_version": (
                        readiness_current.c.projection_version + 1
                    ),
                },
            )
        )
        persisted = await self.get_readiness(runtime_scope_id)
        if persisted is None:
            raise RuntimeError("readiness upsert did not persist current state")
        return persisted

    async def save_warm_readiness(
        self,
        readiness: WarmReadiness,
    ) -> None:
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == readiness.runtime_scope_id,
                runtime_scopes_current.c.scope_version
                == readiness.scope_version,
                runtime_scopes_current.c.observation_generation
                == readiness.observation_generation,
                runtime_scopes_current.c.event_spec_id
                == readiness.event_spec_id,
                runtime_scopes_current.c.exchange_instrument_id
                == readiness.exchange_instrument_id,
                runtime_scopes_current.c.universe_version_id
                == readiness.universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == readiness.universe_semantic_digest,
                runtime_scopes_current.c.lifecycle_state == "warming",
                runtime_scopes_current.c.observation_enabled.is_(True),
                runtime_scopes_current.c.entry_enabled.is_(False),
                runtime_scopes_current.c.updated_at_ms
                <= readiness.warm_completed_at_ms,
            )
            .values(
                warm_closed_bar_time_ms=readiness.warm_closed_bar_time_ms,
                warm_completed_at_ms=readiness.warm_completed_at_ms,
                warm_readiness_digest=readiness.readiness_digest,
                warm_valid_until_ms=readiness.warm_valid_until_ms,
                updated_at_ms=readiness.warm_completed_at_ms,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("warm readiness authority changed")
        await self.save_readiness(
            runtime_scope_id=readiness.runtime_scope_id,
            readiness_state="warm_ready",
            first_blocker=None,
            signal_event_id=None,
            fact_summary={
                "fact_digest": readiness.fact_digest,
                "universe_version_id": readiness.universe_version_id,
                "universe_semantic_digest": (
                    readiness.universe_semantic_digest
                ),
                "warm_readiness_digest": readiness.readiness_digest,
                "warm_closed_bar_time_ms": readiness.warm_closed_bar_time_ms,
                "warm_completed_at_ms": readiness.warm_completed_at_ms,
                "warm_valid_until_ms": readiness.warm_valid_until_ms,
            },
            updated_at_ms=readiness.warm_completed_at_ms,
        )

    async def clear_warm_readiness(
        self,
        *,
        runtime_scope_id: str,
        scope_version: int,
        observation_generation: int,
        event_spec_id: str,
        exchange_instrument_id: str,
        universe_version_id: str,
        universe_semantic_digest: str,
        blocker: str,
        updated_at_ms: int,
    ) -> None:
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.scope_version == scope_version,
                runtime_scopes_current.c.observation_generation
                == observation_generation,
                runtime_scopes_current.c.event_spec_id == event_spec_id,
                runtime_scopes_current.c.exchange_instrument_id
                == exchange_instrument_id,
                runtime_scopes_current.c.universe_version_id
                == universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == universe_semantic_digest,
                runtime_scopes_current.c.lifecycle_state == "warming",
                runtime_scopes_current.c.updated_at_ms <= updated_at_ms,
            )
            .values(
                warm_closed_bar_time_ms=None,
                warm_completed_at_ms=None,
                warm_readiness_digest=None,
                warm_valid_until_ms=None,
                updated_at_ms=updated_at_ms,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("warm readiness authority changed")
        await self.save_readiness(
            runtime_scope_id=runtime_scope_id,
            readiness_state="blocked",
            first_blocker=blocker,
            signal_event_id=None,
            fact_summary={
                "universe_version_id": universe_version_id,
                "universe_semantic_digest": universe_semantic_digest,
            },
            updated_at_ms=updated_at_ms,
        )

    async def get_strategy_group(
        self,
        strategy_group_id: str,
    ) -> StrategyGroupSnapshot | None:
        result = await self._connection.execute(
            sa.select(strategy_groups).where(
                strategy_groups.c.strategy_group_id == strategy_group_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else StrategyGroupSnapshot.model_validate(row, extra="ignore")
        )

    async def get_strategy_version(
        self,
        strategy_version_id: str,
    ) -> StrategyVersionSnapshot | None:
        result = await self._connection.execute(
            sa.select(strategy_versions).where(
                strategy_versions.c.strategy_version_id == strategy_version_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else StrategyVersionSnapshot.model_validate(row, extra="ignore")
        )

    async def get_event_spec(
        self,
        event_spec_id: str,
    ) -> EventSpecSnapshot | None:
        result = await self._connection.execute(
            sa.select(event_specs).where(event_specs.c.event_spec_id == event_spec_id)
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else EventSpecSnapshot.model_validate(row, extra="ignore")
        )

    async def get_runtime_scope(
        self,
        runtime_scope_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeScopeSnapshot | None:
        statement = sa.select(runtime_scopes_current).where(
            runtime_scopes_current.c.runtime_scope_id == runtime_scope_id
        )
        if for_update:
            statement = statement.with_for_update(of=runtime_scopes_current)
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeScopeSnapshot.model_validate(row, extra="ignore")
        )

    async def get_active_universe_member(
        self,
        *,
        event_spec_id: str,
        exchange_instrument_id: str,
        for_update: bool = False,
    ) -> ActiveStrategyUniverseSnapshot | None:
        statement = (
            sa.select(
                strategy_universe_current.c.event_spec_id,
                strategy_universe_current.c.universe_version_id,
                strategy_universe_current.c.semantic_digest,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_current.c.universe_version_id,
            )
            .join(
                instruments,
                instruments.c.exchange_instrument_id
                == strategy_universe_members.c.exchange_instrument_id,
            )
            .where(
                strategy_universe_current.c.event_spec_id == event_spec_id,
                strategy_universe_current.c.lifecycle_state == "active",
                strategy_universe_members.c.exchange_instrument_id
                == exchange_instrument_id,
                instruments.c.status == "active",
            )
        )
        if for_update:
            statement = statement.with_for_update(
                of=(
                    strategy_universe_current,
                    strategy_universe_members,
                    instruments,
                )
            )
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else ActiveStrategyUniverseSnapshot.model_validate(row)
        )

    async def get_active_universe_members(
        self,
        *,
        event_spec_id: str,
    ) -> ActiveStrategyUniverseMembershipSnapshot | None:
        result = await self._connection.execute(
            sa.select(
                strategy_universe_current.c.event_spec_id,
                strategy_universe_current.c.universe_version_id,
                strategy_universe_current.c.semantic_digest,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_current.c.universe_version_id,
            )
            .where(
                strategy_universe_current.c.event_spec_id == event_spec_id,
                strategy_universe_current.c.lifecycle_state == "active",
            )
            .order_by(strategy_universe_members.c.exchange_instrument_id)
        )
        rows = result.mappings().all()
        if not rows:
            return None
        first = rows[0]
        return ActiveStrategyUniverseMembershipSnapshot(
            event_spec_id=str(first["event_spec_id"]),
            universe_version_id=str(first["universe_version_id"]),
            semantic_digest=str(first["semantic_digest"]),
            exchange_instrument_ids=tuple(
                str(row["exchange_instrument_id"]) for row in rows
            ),
        )

    async def get_observation_universe_members(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
    ) -> ObservationUniverseMembershipSnapshot | None:
        result = await self._connection.execute(
            sa.select(
                strategy_universe_versions.c.event_spec_id,
                strategy_universe_versions.c.universe_version_id,
                strategy_universe_versions.c.strategy_group_id,
                strategy_universe_versions.c.universe_version,
                strategy_universe_versions.c.semantic_digest,
                strategy_universe_versions.c.lifecycle_state,
                strategy_universe_versions.c.installed_at_ms,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_versions.c.universe_version_id,
            )
            .outerjoin(
                strategy_universe_current,
                sa.and_(
                    strategy_universe_current.c.event_spec_id
                    == strategy_universe_versions.c.event_spec_id,
                    strategy_universe_current.c.universe_version_id
                    == strategy_universe_versions.c.universe_version_id,
                    strategy_universe_current.c.semantic_digest
                    == strategy_universe_versions.c.semantic_digest,
                    strategy_universe_current.c.lifecycle_state == "active",
                ),
            )
            .where(
                strategy_universe_versions.c.event_spec_id == event_spec_id,
                strategy_universe_versions.c.universe_version_id
                == universe_version_id,
                strategy_universe_versions.c.lifecycle_state.in_(
                    ("warming", "active")
                ),
                sa.or_(
                    strategy_universe_versions.c.lifecycle_state == "warming",
                    strategy_universe_current.c.universe_version_id.is_not(None),
                ),
            )
            .order_by(strategy_universe_members.c.exchange_instrument_id)
            .limit(11)
        )
        rows = result.mappings().all()
        if not rows:
            return None
        if len(rows) > 10:
            raise RuntimeError("observation Universe exceeds ten members")
        first = rows[0]
        if any(
            row["event_spec_id"] != first["event_spec_id"]
            or row["universe_version_id"] != first["universe_version_id"]
            or row["semantic_digest"] != first["semantic_digest"]
            or row["lifecycle_state"] != first["lifecycle_state"]
            for row in rows
        ):
            raise RuntimeError("observation Universe identity is inconsistent")
        universe = StrategyUniverseVersion(
            universe_version_id=str(first["universe_version_id"]),
            strategy_group_id=str(first["strategy_group_id"]),
            event_spec_id=str(first["event_spec_id"]),
            universe_version=int(first["universe_version"]),
            exchange_instrument_ids=tuple(
                str(row["exchange_instrument_id"]) for row in rows
            ),
            semantic_digest=str(first["semantic_digest"]),
            installed_at_ms=int(first["installed_at_ms"]),
        )
        return ObservationUniverseMembershipSnapshot(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            semantic_digest=universe.semantic_digest,
            lifecycle_state=cast(
                Literal["warming", "active"],
                str(first["lifecycle_state"]),
            ),
            exchange_instrument_ids=universe.exchange_instrument_ids,
        )

    async def get_runtime_profile(
        self,
        runtime_profile_id: str,
    ) -> RuntimeProfileSnapshot | None:
        result = await self._connection.execute(
            sa.select(runtime_profiles).where(
                runtime_profiles.c.runtime_profile_id == runtime_profile_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeProfileSnapshot.model_validate(row, extra="ignore")
        )

    async def get_instrument(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentSnapshot | None:
        result = await self._connection.execute(
            sa.select(instruments).where(
                instruments.c.exchange_instrument_id == exchange_instrument_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentSnapshot.model_validate(row, extra="ignore")
        )

    async def get_product_session(
        self,
        exchange_instrument_id: str,
    ) -> ProductSessionSnapshot | None:
        row = (
            await self._connection.execute(
                sa.select(
                    instrument_product_current,
                    instrument_product_profiles.c.product_family,
                )
                .join(
                    instrument_product_profiles,
                    instrument_product_profiles.c.exchange_instrument_id
                    == instrument_product_current.c.exchange_instrument_id,
                )
                .where(
                    instrument_product_current.c.exchange_instrument_id
                    == exchange_instrument_id
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else ProductSessionSnapshot.model_validate(row, extra="ignore")
        )

    async def get_product_profile(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentProductProfile | None:
        row = (
            await self._connection.execute(
                sa.select(instrument_product_profiles).where(
                    instrument_product_profiles.c.exchange_instrument_id
                    == exchange_instrument_id
                )
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentProductProfile.model_validate(row, extra="ignore")
        )

    async def upsert_product_sessions(
        self,
        snapshots: tuple[ProductSessionSnapshot, ...],
    ) -> int:
        return await PostgresProductCurrentRepository(
            self._connection
        ).upsert_snapshots(snapshots)

    async def get_instrument_rules(
        self,
        venue_id: str,
        exchange_instrument_id: str,
    ) -> InstrumentRulesSnapshot | None:
        result = await self._connection.execute(
            sa.select(instrument_rules_current).where(
                instrument_rules_current.c.venue_id == venue_id,
                instrument_rules_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentRulesSnapshot.model_validate(row, extra="ignore")
        )

    async def upsert_instrument_rules(
        self,
        *,
        venue_id: str,
        exchange_instrument_id: str,
        quantity_step: Decimal,
        price_tick: Decimal,
        min_quantity: Decimal,
        min_notional: Decimal,
        exchange_max_leverage: int,
        maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...],
        maintenance_margin_brackets_digest: str,
        notional_coefficient: Decimal,
        notional_coefficient_certified: bool,
        observed_at_ms: int,
        valid_until_ms: int,
    ) -> InstrumentRulesSnapshot:
        result = await self._connection.execute(
            sa.select(instrument_rules_current)
            .where(
                instrument_rules_current.c.venue_id == venue_id,
                instrument_rules_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
            .with_for_update()
        )
        row = result.mappings().one_or_none()
        projection_version = 1 if row is None else int(row["projection_version"]) + 1
        values = {
            "venue_id": venue_id,
            "exchange_instrument_id": exchange_instrument_id,
            "quantity_step": quantity_step,
            "price_tick": price_tick,
            "min_quantity": min_quantity,
            "min_notional": min_notional,
            "exchange_max_leverage": exchange_max_leverage,
            "maintenance_margin_brackets": [
                item.model_dump(mode="json")
                for item in maintenance_margin_brackets
            ],
            "maintenance_margin_brackets_digest": maintenance_margin_brackets_digest,
            "notional_coefficient": notional_coefficient,
            "notional_coefficient_certified": notional_coefficient_certified,
            "session_and_settlement": {},
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
            "projection_version": projection_version,
        }
        if row is None:
            await self._connection.execute(
                sa.insert(instrument_rules_current).values(values)
            )
        else:
            await self._connection.execute(
                sa.update(instrument_rules_current)
                .where(
                    instrument_rules_current.c.venue_id == venue_id,
                    instrument_rules_current.c.exchange_instrument_id
                    == exchange_instrument_id
                )
                .values(values)
            )
        return InstrumentRulesSnapshot.model_validate(values, extra="ignore")

    async def get_runtime_capability(
        self,
        capability_key: str,
    ) -> RuntimeCapabilitySnapshot | None:
        result = await self._connection.execute(
            sa.select(runtime_capabilities_current).where(
                runtime_capabilities_current.c.capability_key == capability_key
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeCapabilitySnapshot.model_validate(row, extra="ignore")
        )

    async def get_required_facts(
        self,
        *,
        runtime_scope_id: str,
        event_spec_id: str,
    ) -> tuple[SignalFactSnapshot, ...] | None:
        required_result = await self._connection.execute(
            sa.select(
                event_required_facts.c.fact_definition_id,
                event_required_facts.c.role,
            )
            .where(
                event_required_facts.c.event_spec_id == event_spec_id,
                event_required_facts.c.required.is_(True),
            )
            .order_by(event_required_facts.c.fact_definition_id)
        )
        requirements = {
            str(row["fact_definition_id"]): str(row["role"])
            for row in required_result.mappings()
        }
        required_ids = tuple(requirements)
        if not required_ids:
            return ()

        facts_result = await self._connection.execute(
            sa.select(facts_current)
            .where(
                facts_current.c.runtime_scope_id == runtime_scope_id,
                facts_current.c.fact_definition_id.in_(required_ids),
            )
            .order_by(facts_current.c.fact_definition_id)
        )
        rows = tuple(facts_result.mappings())
        if len(rows) != len(required_ids):
            return None
        return tuple(
            SignalFactSnapshot(
                fact_definition_id=str(row["fact_definition_id"]),
                role=cast(
                    Literal["condition", "protection_reference", "disable"],
                    requirements[str(row["fact_definition_id"])],
                ),
                value=row["value"],
                satisfied=bool(row["satisfied"]),
                observed_at_ms=int(row["observed_at_ms"]),
                valid_until_ms=int(row["valid_until_ms"]),
                projection_version=int(row["projection_version"]),
            )
            for row in rows
        )


def _signal_values(signal: StrategySignal) -> dict[str, object]:
    return {
        "signal_event_id": signal.signal_event_id,
        "exposure_episode_id": signal.exposure_episode_id,
        "runtime_scope_id": signal.runtime_scope_id,
        "runtime_scope_version": signal.runtime_scope_version,
        "strategy_group_id": signal.strategy_group_id,
        "strategy_version_id": signal.strategy_version_id,
        "event_spec_id": signal.event_spec_id,
        "universe_version_id": signal.universe_version_id,
        "selection_authority_id": signal.selection_authority_id,
        "universe_semantic_digest": signal.universe_semantic_digest,
        "exchange_instrument_id": signal.exchange_instrument_id,
        "position_side": signal.position_side,
        "fact_digest": signal.fact_digest,
        "occurred_at_ms": signal.occurred_at_ms,
        "observed_at_ms": signal.observed_at_ms,
        "expires_at_ms": signal.expires_at_ms,
    }


def _fact_snapshot_values(
    signal_event_id: str,
    fact: SignalFactSnapshot,
) -> dict[str, object]:
    return {
        "signal_event_id": signal_event_id,
        "fact_definition_id": fact.fact_definition_id,
        "role": fact.role,
        "value": fact.value,
        "satisfied": fact.satisfied,
        "observed_at_ms": fact.observed_at_ms,
        "valid_until_ms": fact.valid_until_ms,
        "projection_version": fact.projection_version,
    }


def _signal_from_row(
    row: RowMapping,
    facts: tuple[SignalFactSnapshot, ...],
) -> StrategySignal:
    return StrategySignal(
        signal_event_id=str(row["signal_event_id"]),
        exposure_episode_id=str(row["exposure_episode_id"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        event_spec_id=str(row["event_spec_id"]),
        universe_version_id=str(row["universe_version_id"]),
        selection_authority_id=row["selection_authority_id"],
        universe_semantic_digest=str(row["universe_semantic_digest"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(row["position_side"])),
        fact_digest=str(row["fact_digest"]),
        occurred_at_ms=int(row["occurred_at_ms"]),
        observed_at_ms=int(row["observed_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        facts=facts,
    )


def _current_fact_matches(
    row: RowMapping,
    fact: SignalFactSnapshot,
) -> bool:
    return (
        row["value"] == fact.value
        and bool(row["satisfied"]) is fact.satisfied
        and int(row["observed_at_ms"]) == fact.observed_at_ms
        and int(row["valid_until_ms"]) == fact.valid_until_ms
    )
