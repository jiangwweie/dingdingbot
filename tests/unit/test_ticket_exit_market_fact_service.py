from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from src.application.action_time.ticket_exit_market_fact_service import (
    ClosedCandle,
    materialize_due_ticket_exit_market_facts,
)
from src.application.action_time import action_time_ticket
from tests.unit.test_action_time_ticket_materialization import (
    NOW_MS,
    _insert_action_time_lane_graph,
)
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_exit_policy_binding import _insert_policy, _policy_payload


class _Source:
    def __init__(self, candles=None, *, error: Exception | None = None):
        self.candles = list(candles or [])
        self.error = error
        self.calls: list[dict] = []

    async def fetch_closed_candles(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return list(self.candles)


def _candle(
    *,
    watermark_ms: int = NOW_MS + 900_000,
    valid_until_ms: int = NOW_MS + 1_800_000,
    exchange_instrument_id: str = "binance_usdm:ETH/USDT:USDT",
    venue_id: str = "binance_usdm",
    timeframe: str = "15m",
) -> ClosedCandle:
    return ClosedCandle(
        exchange_instrument_id=exchange_instrument_id,
        venue_id=venue_id,
        timeframe=timeframe,
        open_time_ms=watermark_ms - 900_000,
        close_time_ms=watermark_ms,
        observed_at_ms=watermark_ms + 1,
        valid_until_ms=valid_until_ms,
        is_final_closed_candle=True,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("10"),
    )


def _materialize_versioned_ticket(conn) -> str:
    _insert_action_time_lane_graph(conn)
    _insert_policy(conn, _policy_payload())
    conn.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET status = 'enabled' "
            "WHERE capability_id = 'ticket_exit_policy_v1'"
        )
    )
    result = action_time_ticket.materialize_action_time_ticket(conn, now_ms=NOW_MS)
    assert result["status"] == "action_time_ticket_created", result
    ticket_id = str(result["ticket_id"])
    conn.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current SET state = 'execution_bound' "
            "WHERE ticket_id = :ticket_id"
        ),
        {"ticket_id": ticket_id},
    )
    return ticket_id


def _clone_ticket_and_projection(conn, *, source_ticket_id: str) -> str:
    tickets = sa.Table("brc_action_time_tickets", sa.MetaData(), autoload_with=conn)
    source_ticket = dict(
        conn.execute(
            sa.select(tickets).where(tickets.c.ticket_id == source_ticket_id)
        ).mappings().one()
    )
    clone_ticket_id = f"{source_ticket_id}:clone"
    source_ticket.update(
        {
            "ticket_id": clone_ticket_id,
            "action_time_lane_input_id": (
                f"{source_ticket['action_time_lane_input_id']}:clone"
            ),
            "ticket_hash": f"{source_ticket['ticket_hash']}:clone",
        }
    )
    conn.execute(tickets.insert().values(**source_ticket))
    projections = sa.Table(
        "brc_ticket_exit_policy_current",
        sa.MetaData(),
        autoload_with=conn,
    )
    source_projection = dict(
        conn.execute(
            sa.select(projections).where(projections.c.ticket_id == source_ticket_id)
        ).mappings().one()
    )
    source_projection["ticket_id"] = clone_ticket_id
    conn.execute(projections.insert().values(**source_projection))
    return clone_ticket_id


@pytest.mark.asyncio
async def test_before_due_time_performs_zero_source_calls(pg_control_connection):
    ticket_id = _materialize_versioned_ticket(pg_control_connection)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_exit_policy_current "
            "SET next_evaluation_not_before_ms = :due WHERE ticket_id = :ticket_id"
        ),
        {"due": NOW_MS + 60_000, "ticket_id": ticket_id},
    )
    pg_control_connection.commit()
    source = _Source(
        [_candle(exchange_instrument_id=_ticket_instrument(pg_control_connection, ticket_id))]
    )

    result = await materialize_due_ticket_exit_market_facts(
        pg_control_connection.engine,
        ticket_ids=[ticket_id],
        now_ms=NOW_MS,
        source=source,
    )

    assert result[0]["status"] == "exit_market_fact_not_due"
    assert source.calls == []


@pytest.mark.asyncio
async def test_new_final_candle_is_persisted_once_and_same_watermark_is_idempotent(
    pg_control_connection,
):
    ticket_id = _materialize_versioned_ticket(pg_control_connection)
    pg_control_connection.commit()
    source = _Source(
        [_candle(exchange_instrument_id=_ticket_instrument(pg_control_connection, ticket_id))]
    )

    first = await materialize_due_ticket_exit_market_facts(
        pg_control_connection.engine,
        ticket_ids=[ticket_id],
        now_ms=NOW_MS + 1_000_000,
        source=source,
    )
    second = await materialize_due_ticket_exit_market_facts(
        pg_control_connection.engine,
        ticket_ids=[ticket_id],
        now_ms=NOW_MS + 1_000_001,
        source=source,
    )

    assert first[0]["status"] == "exit_market_fact_materialized"
    assert second[0]["status"] in {
        "exit_market_fact_not_due",
        "exit_market_watermark_already_claimed",
    }
    with pg_control_connection.engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM brc_runtime_fact_snapshots "
                "WHERE fact_surface = 'ticket_exit_market' AND "
                "strategy_group_id = 'SOR-001'"
            )
        ).scalar_one()
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candle", "expected_blocker"),
    [
        (
            _candle(
                watermark_ms=NOW_MS + 100_000,
                valid_until_ms=NOW_MS + 500_000,
            ),
            "exit_market_fact_stale",
        ),
        (
            _candle(exchange_instrument_id="binance_usdm:BTC/USDT:USDT"),
            "exit_market_fact_scope_mismatch",
        ),
    ],
)
async def test_stale_or_scope_mismatched_candle_blocks_without_claiming_watermark(
    pg_control_connection,
    candle,
    expected_blocker,
):
    ticket_id = _materialize_versioned_ticket(pg_control_connection)
    pg_control_connection.commit()
    if expected_blocker == "exit_market_fact_stale":
        candle = candle.model_copy(
            update={
                "exchange_instrument_id": _ticket_instrument(
                    pg_control_connection,
                    ticket_id,
                )
            }
        )
    source = _Source([candle])

    result = await materialize_due_ticket_exit_market_facts(
        pg_control_connection.engine,
        ticket_ids=[ticket_id],
        now_ms=NOW_MS + 1_000_000,
        source=source,
    )

    assert result[0]["status"] == "exit_market_fact_blocked"
    assert result[0]["blockers"] == [expected_blocker]
    with pg_control_connection.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT last_evaluated_watermark_ms, active_runner_stop "
                "FROM brc_ticket_exit_policy_current WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).mappings().one()
    assert row["last_evaluated_watermark_ms"] is None


@pytest.mark.asyncio
async def test_duplicate_ticket_scope_is_coalesced_and_timeout_preserves_projection(
    pg_control_connection,
):
    ticket_id = _materialize_versioned_ticket(pg_control_connection)
    second_ticket_id = _clone_ticket_and_projection(
        pg_control_connection,
        source_ticket_id=ticket_id,
    )
    pg_control_connection.commit()
    source = _Source(error=TimeoutError("public source timeout"))

    result = await materialize_due_ticket_exit_market_facts(
        pg_control_connection.engine,
        ticket_ids=[ticket_id, second_ticket_id],
        now_ms=NOW_MS + 1_000_000,
        source=source,
        timeout_seconds=Decimal("0.1"),
    )

    assert len(source.calls) == 1
    assert result == [
        {
            "status": "exit_market_fact_blocked",
            "ticket_id": current_ticket_id,
            "blockers": ["exit_market_fact_source_unavailable"],
        }
        for current_ticket_id in (ticket_id, second_ticket_id)
    ]
    with pg_control_connection.engine.connect() as conn:
        assert conn.execute(
            text(
                "SELECT last_evaluated_watermark_ms "
                "FROM brc_ticket_exit_policy_current WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).scalar_one() is None


def _ticket_instrument(conn, ticket_id: str) -> str:
    return str(
        conn.execute(
            text(
                "SELECT exchange_instrument_id FROM brc_action_time_tickets "
                "WHERE ticket_id = :ticket_id"
            ),
            {"ticket_id": ticket_id},
        ).scalar_one()
    )
