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
    ReadinessSnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeProfileSnapshot,
    RuntimeScopeSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
)
from src.trading_kernel.domain.signal import (
    ActionableSignal,
    SignalFactSnapshot,
    SignalTicketTerms,
)
from src.trading_kernel.domain.ticket import EntryOrderType
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
    strategy_groups,
    strategy_versions,
    trade_tickets,
)


class PostgresSignalRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, signal: ActionableSignal) -> bool:
        result = await self._connection.execute(
            pg_insert(signal_events)
            .values(_signal_values(signal))
            .on_conflict_do_nothing(index_elements=[signal_events.c.signal_event_id])
        )
        return result.rowcount == 1

    async def get(self, signal_event_id: str) -> ActionableSignal | None:
        result = await self._connection.execute(
            sa.select(signal_events).where(
                signal_events.c.signal_event_id == signal_event_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else _signal_from_row(row)

    async def get_next_ready(self, *, now_ms: int) -> ActionableSignal | None:
        return await self._get_next_ticket_ready(
            expiry_predicate=signal_events.c.expires_at_ms > now_ms
        )

    async def get_next_stale_ready(self, *, now_ms: int) -> ActionableSignal | None:
        return await self._get_next_ticket_ready(
            expiry_predicate=signal_events.c.expires_at_ms <= now_ms
        )

    async def _get_next_ticket_ready(
        self,
        *,
        expiry_predicate: sa.ColumnElement[bool],
    ) -> ActionableSignal | None:
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
                readiness_current.c.readiness_state == "ticket_ready",
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
        return None if row is None else _signal_from_row(row)

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
        exchange_instrument_id: str,
    ) -> InstrumentRulesSnapshot | None:
        result = await self._connection.execute(
            sa.select(instrument_rules_current).where(
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
            sa.select(event_required_facts.c.fact_definition_id)
            .where(
                event_required_facts.c.event_spec_id == event_spec_id,
                event_required_facts.c.required.is_(True),
            )
            .order_by(event_required_facts.c.fact_definition_id)
        )
        required_ids = tuple(required_result.scalars())
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
            SignalFactSnapshot.model_validate(row, extra="ignore") for row in rows
        )


def _signal_values(signal: ActionableSignal) -> dict[str, object]:
    terms = signal.terms
    return {
        "signal_event_id": signal.signal_event_id,
        "runtime_scope_id": signal.runtime_scope_id,
        "runtime_scope_version": signal.runtime_scope_version,
        "strategy_group_id": signal.strategy_group_id,
        "strategy_version_id": signal.strategy_version_id,
        "event_spec_id": signal.event_spec_id,
        "exchange_instrument_id": signal.exchange_instrument_id,
        "position_side": signal.position_side,
        "signal_grade": "trade",
        "fact_digest": signal.fact_digest,
        "quantity": terms.quantity,
        "notional": terms.notional,
        "leverage": terms.leverage,
        "risk_at_stop": terms.risk_at_stop,
        "entry_order_type": terms.entry_order_type,
        "entry_limit_price": terms.entry_limit_price,
        "initial_stop_price": terms.initial_stop_price,
        "take_profit_prices": [str(value) for value in terms.take_profit_prices],
        "occurred_at_ms": signal.occurred_at_ms,
        "expires_at_ms": signal.expires_at_ms,
    }


def _signal_from_row(row: RowMapping) -> ActionableSignal:
    return ActionableSignal(
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
        expires_at_ms=int(row["expires_at_ms"]),
        terms=SignalTicketTerms(
            quantity=Decimal(row["quantity"]),
            notional=Decimal(row["notional"]),
            leverage=Decimal(row["leverage"]),
            risk_at_stop=Decimal(row["risk_at_stop"]),
            entry_order_type=EntryOrderType(str(row["entry_order_type"])),
            entry_limit_price=(
                None
                if row["entry_limit_price"] is None
                else Decimal(row["entry_limit_price"])
            ),
            initial_stop_price=Decimal(row["initial_stop_price"]),
            take_profit_prices=tuple(
                Decimal(value) for value in row["take_profit_prices"]
            ),
        ),
    )
