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
    EventSpecSnapshot,
    InstrumentRulesSnapshot,
    InstrumentSnapshot,
    ObservationScopeClaim,
    ReadinessSnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeProfileSnapshot,
    RuntimeScopeSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
)
from src.trading_kernel.domain.arbitration import EntryCandidate
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
)
from src.trading_kernel.infrastructure.pg_models import (
    event_specs,
    event_required_facts,
    facts_current,
    instrument_rules_current,
    instruments,
    readiness_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    signal_events,
    signal_fact_snapshots,
    strategy_candidate_scopes,
    strategy_groups,
    strategy_versions,
    trade_tickets,
    owner_policy_current,
)


class PostgresSignalRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, signal: StrategySignal) -> bool:
        result = await self._connection.execute(
            pg_insert(signal_events)
            .values(_signal_values(signal))
            .on_conflict_do_nothing(index_elements=[signal_events.c.signal_event_id])
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
                strategy_candidate_scopes.c.priority_rank.label("scope_priority"),
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
                strategy_candidate_scopes,
                sa.and_(
                    strategy_candidate_scopes.c.event_spec_id
                    == signal_events.c.event_spec_id,
                    strategy_candidate_scopes.c.exchange_instrument_id
                    == signal_events.c.exchange_instrument_id,
                    strategy_candidate_scopes.c.position_side
                    == signal_events.c.position_side,
                ),
            )
            .where(
                readiness_current.c.readiness_state == "candidate_ready",
                signal_events.c.expires_at_ms > now_ms,
                runtime_scopes_current.c.enabled.is_(True),
                owner_policy_current.c.enabled.is_(True),
                owner_policy_current.c.new_entry_submit_enabled.is_(True),
                strategy_candidate_scopes.c.status == "active",
                ~already_ticketed,
            )
            .order_by(
                owner_policy_current.c.priority_rank,
                strategy_candidate_scopes.c.priority_rank,
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
                    candidate_scope_priority=int(row["scope_priority"]),
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
                runtime_scopes_current.c.enabled.is_(True),
                event_specs.c.status == "active",
                sa.or_(
                    runtime_scopes_current.c.observation_due_at_ms.is_(None),
                    runtime_scopes_current.c.observation_due_at_ms <= now_ms,
                ),
                sa.or_(
                    runtime_scopes_current.c.observation_lease_until_ms.is_(None),
                    runtime_scopes_current.c.observation_lease_until_ms <= now_ms,
                ),
            )
            .order_by(
                sa.func.coalesce(
                    runtime_scopes_current.c.observation_due_at_ms,
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
        await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id
            )
            .values(
                observation_claim_owner=normalized_worker_id,
                observation_lease_until_ms=lease_until_ms,
            )
        )
        return ObservationScopeClaim(
            runtime_scope_id=runtime_scope_id,
            timeframe=timeframe,
            trigger_candle_close_time_ms=trigger_candle_close_time_ms,
        )

    async def schedule_observation_scope(
        self,
        *,
        runtime_scope_id: str,
        worker_id: str,
        due_at_ms: int,
    ) -> None:
        if due_at_ms <= 0:
            raise ValueError("observation due time must be positive")
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.observation_claim_owner == worker_id,
            )
            .values(
                observation_due_at_ms=due_at_ms,
                observation_claim_owner=None,
                observation_lease_until_ms=None,
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
    ) -> RuntimeScopeSnapshot | None:
        result = await self._connection.execute(
            sa.select(runtime_scopes_current).where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeScopeSnapshot.model_validate(row, extra="ignore")
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
        "runtime_scope_id": signal.runtime_scope_id,
        "runtime_scope_version": signal.runtime_scope_version,
        "strategy_group_id": signal.strategy_group_id,
        "strategy_version_id": signal.strategy_version_id,
        "event_spec_id": signal.event_spec_id,
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
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        event_spec_id=str(row["event_spec_id"]),
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
