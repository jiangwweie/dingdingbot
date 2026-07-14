"""Bounded, PG-backed closed-market facts for Ticket exit-policy evaluation."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, model_validator
import sqlalchemy as sa

from src.application.action_time.ticket_exit_policy_projection import (
    claim_ticket_exit_market_watermark,
    record_ticket_exit_market_blocker,
)
from src.domain.ticket_exit_policy import (
    NoRunnerRule,
    StructuralAtrRunnerRule,
    TicketExitPolicySnapshot,
)


TIMEFRAME_MS = {
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}
FACT_SURFACE = "ticket_exit_market"
RETRY_DELAY_MS = 30_000


class ClosedCandle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    venue_id: str
    timeframe: str
    open_time_ms: int
    close_time_ms: int
    observed_at_ms: int
    valid_until_ms: int
    is_final_closed_candle: bool
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")

    @model_validator(mode="after")
    def _validate_candle(self) -> "ClosedCandle":
        if not self.exchange_instrument_id.strip() or not self.venue_id.strip():
            raise ValueError("closed candle scope is required")
        if self.timeframe not in TIMEFRAME_MS:
            raise ValueError("closed candle timeframe is unsupported")
        if (
            self.open_time_ms < 0
            or self.close_time_ms <= self.open_time_ms
            or self.observed_at_ms < self.close_time_ms
            or self.valid_until_ms <= self.close_time_ms
        ):
            raise ValueError("closed candle timestamps are invalid")
        if min(self.open, self.high, self.low, self.close) <= 0 or self.volume < 0:
            raise ValueError("closed candle financial values are invalid")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("closed candle OHLC ordering is invalid")
        return self


class ClosedCandleSource(Protocol):
    async def fetch_closed_candles(
        self,
        *,
        exchange_instrument_id: str,
        venue_id: str,
        timeframe: str,
        through_ms: int,
        limit: int,
        timeout_seconds: Decimal,
    ) -> Sequence[ClosedCandle]: ...


class TicketExitMarketScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket_id: str
    strategy_group_id: str
    symbol: str
    side: str
    runtime_profile_id: str
    exchange_instrument_id: str
    venue_id: str
    timeframe: str
    fetch_limit: int
    previous_watermark_ms: int | None


class ExistingClosedCandleSourceAdapter:
    """Adapt the existing public latest-closed-candle port with exact mapping."""

    def __init__(
        self,
        *,
        source: Any,
        exchange_symbol_resolver: Callable[[str, str], str],
    ) -> None:
        self._source = source
        self._exchange_symbol_resolver = exchange_symbol_resolver

    async def fetch_closed_candles(
        self,
        *,
        exchange_instrument_id: str,
        venue_id: str,
        timeframe: str,
        through_ms: int,
        limit: int,
        timeout_seconds: Decimal,
    ) -> Sequence[ClosedCandle]:
        del timeout_seconds
        symbol = self._exchange_symbol_resolver(exchange_instrument_id, venue_id)
        rows = await asyncio.to_thread(
            self._source.latest_closed_candles,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        interval_ms = TIMEFRAME_MS[timeframe]
        return [
            ClosedCandle(
                exchange_instrument_id=exchange_instrument_id,
                venue_id=venue_id,
                timeframe=timeframe,
                open_time_ms=int(row.open_time_ms),
                close_time_ms=int(
                    row.close_time_ms
                    if row.close_time_ms is not None
                    else row.open_time_ms + interval_ms - 1
                ),
                observed_at_ms=through_ms,
                valid_until_ms=int(
                    row.close_time_ms
                    if row.close_time_ms is not None
                    else row.open_time_ms + interval_ms - 1
                )
                + interval_ms,
                is_final_closed_candle=bool(row.is_closed),
                open=Decimal(str(row.open)),
                high=Decimal(str(row.high)),
                low=Decimal(str(row.low)),
                close=Decimal(str(row.close)),
                volume=Decimal(str(row.volume)),
            )
            for row in rows
        ]


async def materialize_due_ticket_exit_market_facts(
    engine: sa.Engine,
    *,
    ticket_ids: Sequence[str],
    now_ms: int,
    source: ClosedCandleSource,
    timeout_seconds: Decimal = Decimal("5"),
) -> list[dict[str, Any]]:
    """Fetch each exact due market scope once, then persist per-Ticket facts."""

    if now_ms <= 0 or timeout_seconds <= 0:
        raise ValueError("ticket_exit_market_fact_service_input_invalid")
    ordered_ticket_ids = list(dict.fromkeys(str(item) for item in ticket_ids if str(item)))
    if not ordered_ticket_ids:
        return []
    with engine.begin() as conn:
        scopes, immediate = _load_due_scopes(
            conn,
            ticket_ids=ordered_ticket_ids,
            now_ms=now_ms,
        )
    results_by_ticket = {item["ticket_id"]: item for item in immediate}
    grouped: dict[tuple[str, str, str], list[TicketExitMarketScope]] = defaultdict(list)
    for scope in scopes:
        grouped[
            (scope.exchange_instrument_id, scope.venue_id, scope.timeframe)
        ].append(scope)

    for (instrument_id, venue_id, timeframe), grouped_scopes in grouped.items():
        try:
            raw = await asyncio.wait_for(
                source.fetch_closed_candles(
                    exchange_instrument_id=instrument_id,
                    venue_id=venue_id,
                    timeframe=timeframe,
                    through_ms=now_ms,
                    limit=max(scope.fetch_limit for scope in grouped_scopes),
                    timeout_seconds=timeout_seconds,
                ),
                timeout=float(timeout_seconds),
            )
            candles = sorted(
                [
                    item
                    if isinstance(item, ClosedCandle)
                    else ClosedCandle.model_validate(item)
                    for item in raw
                ],
                key=lambda item: item.close_time_ms,
            )
        except Exception:
            for scope in grouped_scopes:
                results_by_ticket[scope.ticket_id] = _record_blocker(
                    engine,
                    scope=scope,
                    blocker="exit_market_fact_source_unavailable",
                    now_ms=now_ms,
                )
            continue
        for scope in grouped_scopes:
            blocker = _candle_blocker(scope=scope, candles=candles, now_ms=now_ms)
            if blocker:
                results_by_ticket[scope.ticket_id] = _record_blocker(
                    engine,
                    scope=scope,
                    blocker=blocker,
                    now_ms=now_ms,
                )
                continue
            results_by_ticket[scope.ticket_id] = _persist_fact(
                engine,
                scope=scope,
                candles=candles,
                now_ms=now_ms,
            )
    return [results_by_ticket[ticket_id] for ticket_id in ordered_ticket_ids]


def _load_due_scopes(
    conn: sa.engine.Connection,
    *,
    ticket_ids: Sequence[str],
    now_ms: int,
) -> tuple[list[TicketExitMarketScope], list[dict[str, Any]]]:
    tickets = _table(conn, "brc_action_time_tickets")
    projections = _table(conn, "brc_ticket_exit_policy_current")
    instruments = _table(conn, "brc_exchange_instruments")
    rows = conn.execute(
        sa.select(tickets, projections, instruments)
        .select_from(
            tickets.join(
                projections,
                projections.c.ticket_id == tickets.c.ticket_id,
            ).join(
                instruments,
                instruments.c.exchange_instrument_id
                == tickets.c.exchange_instrument_id,
            )
        )
        .where(tickets.c.ticket_id.in_(tuple(ticket_ids)))
    ).mappings().all()
    by_ticket = {str(row["ticket_id"]): dict(row) for row in rows}
    scopes: list[TicketExitMarketScope] = []
    immediate: list[dict[str, Any]] = []
    for ticket_id in ticket_ids:
        row = by_ticket.get(ticket_id)
        if row is None:
            immediate.append(
                {
                    "status": "exit_market_fact_blocked",
                    "ticket_id": ticket_id,
                    "blockers": ["ticket_exit_market_scope_missing"],
                }
            )
            continue
        due_at = _optional_int(row.get("next_evaluation_not_before_ms"))
        if due_at is not None and due_at > now_ms:
            immediate.append(
                {
                    "status": "exit_market_fact_not_due",
                    "ticket_id": ticket_id,
                    "blockers": [],
                }
            )
            continue
        try:
            policy = TicketExitPolicySnapshot.model_validate(
                _mapping(row.get("exit_policy_snapshot"))
            )
        except Exception:
            immediate.append(
                {
                    "status": "exit_market_fact_blocked",
                    "ticket_id": ticket_id,
                    "blockers": ["ticket_exit_policy_snapshot_invalid"],
                }
            )
            continue
        if isinstance(policy.runner_rule, NoRunnerRule):
            immediate.append(
                {
                    "status": "exit_market_fact_not_required",
                    "ticket_id": ticket_id,
                    "blockers": [],
                }
            )
            continue
        timeframe = policy.runner_rule.timeframe
        fetch_limit = 3
        if isinstance(policy.runner_rule, StructuralAtrRunnerRule):
            fetch_limit = max(
                policy.runner_rule.structure_window_bars,
                policy.runner_rule.atr_period + 1,
            )
        scopes.append(
            TicketExitMarketScope(
                ticket_id=ticket_id,
                strategy_group_id=str(row.get("strategy_group_id") or ""),
                symbol=str(row.get("symbol") or ""),
                side=str(row.get("side") or ""),
                runtime_profile_id=str(row.get("runtime_profile_id") or ""),
                exchange_instrument_id=str(row.get("exchange_instrument_id") or ""),
                venue_id=str(row.get("exchange_id") or ""),
                timeframe=timeframe,
                fetch_limit=fetch_limit,
                previous_watermark_ms=_optional_int(
                    row.get("last_evaluated_watermark_ms")
                ),
            )
        )
    return scopes, immediate


def _candle_blocker(
    *,
    scope: TicketExitMarketScope,
    candles: Sequence[ClosedCandle],
    now_ms: int,
) -> str | None:
    if not candles:
        return "exit_market_fact_source_unavailable"
    if any(
        candle.exchange_instrument_id != scope.exchange_instrument_id
        or candle.venue_id != scope.venue_id
        or candle.timeframe != scope.timeframe
        for candle in candles
    ):
        return "exit_market_fact_scope_mismatch"
    latest = candles[-1]
    if not latest.is_final_closed_candle or latest.close_time_ms > now_ms:
        return "exit_market_fact_not_final"
    if latest.valid_until_ms <= now_ms:
        return "exit_market_fact_stale"
    return None


def _record_blocker(
    engine: sa.Engine,
    *,
    scope: TicketExitMarketScope,
    blocker: str,
    now_ms: int,
) -> dict[str, Any]:
    with engine.begin() as conn:
        return record_ticket_exit_market_blocker(
            conn,
            ticket_id=scope.ticket_id,
            blocker=blocker,
            retry_not_before_ms=now_ms + RETRY_DELAY_MS,
            now_ms=now_ms,
        )


def _persist_fact(
    engine: sa.Engine,
    *,
    scope: TicketExitMarketScope,
    candles: Sequence[ClosedCandle],
    now_ms: int,
) -> dict[str, Any]:
    latest = candles[-1]
    watermark_ms = latest.close_time_ms
    fact_snapshot_id = _stable_id(
        "fact_ticket_exit_market",
        scope.ticket_id,
        str(watermark_ms),
    )
    interval_ms = TIMEFRAME_MS[scope.timeframe]
    with engine.begin() as conn:
        projections = _table(conn, "brc_ticket_exit_policy_current")
        current = conn.execute(
            sa.select(projections).where(projections.c.ticket_id == scope.ticket_id)
        ).mappings().one()
        current_watermark = _optional_int(current.get("last_evaluated_watermark_ms"))
        if current_watermark is not None and current_watermark >= watermark_ms:
            return {
                "status": "exit_market_watermark_already_claimed",
                "ticket_id": scope.ticket_id,
                "blockers": [],
            }
        fact_table = _table(conn, "brc_runtime_fact_snapshots")
        existing = conn.execute(
            sa.select(fact_table.c.fact_snapshot_id).where(
                fact_table.c.fact_snapshot_id == fact_snapshot_id
            )
        ).first()
        if existing is None:
            conn.execute(
                fact_table.insert().values(
                    fact_snapshot_id=fact_snapshot_id,
                    strategy_group_id=scope.strategy_group_id,
                    symbol=scope.symbol,
                    side=scope.side,
                    runtime_profile_id=scope.runtime_profile_id,
                    fact_surface=FACT_SURFACE,
                    source_kind="public_closed_candle",
                    source_ref=(
                        f"{scope.venue_id}:{scope.exchange_instrument_id}:"
                        f"{scope.timeframe}:{watermark_ms}"
                    ),
                    computed=True,
                    satisfied=True,
                    freshness_state="fresh",
                    failed_facts=[],
                    fact_values={
                        "schema": "brc.ticket_exit_market_fact.v1",
                        "ticket_id": scope.ticket_id,
                        "exchange_instrument_id": scope.exchange_instrument_id,
                        "venue_id": scope.venue_id,
                        "timeframe": scope.timeframe,
                        "watermark_ms": watermark_ms,
                        "candles": [
                            candle.model_dump(mode="json") for candle in candles
                        ],
                    },
                    blocker_class=None,
                    observed_at_ms=latest.observed_at_ms,
                    valid_until_ms=latest.valid_until_ms,
                    created_at_ms=now_ms,
                )
            )
        claim = claim_ticket_exit_market_watermark(
            conn,
            ticket_id=scope.ticket_id,
            expected_previous_watermark_ms=current_watermark,
            watermark_ms=watermark_ms,
            next_evaluation_not_before_ms=watermark_ms + interval_ms,
            fact_snapshot_id=fact_snapshot_id,
            now_ms=now_ms,
        )
        if claim["status"] == "watermark_claimed":
            return {
                "status": "exit_market_fact_materialized",
                "ticket_id": scope.ticket_id,
                "fact_snapshot_id": fact_snapshot_id,
                "watermark_ms": watermark_ms,
                "blockers": [],
            }
        return {
            "status": "exit_market_watermark_already_claimed",
            "ticket_id": scope.ticket_id,
            "blockers": [],
        }


def _table(conn: sa.engine.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _mapping(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return {}
    return dict(value) if isinstance(value, dict) else {}


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{sha256('|'.join(parts).encode('utf-8')).hexdigest()}"
