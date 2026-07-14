from __future__ import annotations

from decimal import Decimal
import json

from sqlalchemy import text

from src.application.comparative_strength_fact_service import (
    load_comparative_strength_fact_plan,
    materialize_comparative_strength_fact_snapshots,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    pg_control_connection,
)


TRIGGER_CLOSE_MS = NOW_MS - 1_000


def _install_comparative_policies(conn):
    policies = {
        "leader_strength_confirmed": {
            "event_id": "MPG-LONG",
            "event_ids": ["MPG-LONG"],
            "fact_role": "required",
            "operator": "eq",
            "expected_value": True,
            "disable_on_match": False,
            "comparative_strength": {
                "timeframe": "1h",
                "lookback_bars": 8,
                "max_rank": 1,
                "require_positive_return": True,
            },
        },
        "relative_strength_confirmed": {
            "event_id": "MI-LONG",
            "event_ids": ["MI-LONG"],
            "fact_role": "required",
            "operator": "eq",
            "expected_value": True,
            "disable_on_match": False,
            "comparative_strength": {
                "timeframe": "1h",
                "lookback_bars": 12,
                "max_rank": 1,
                "require_positive_return": True,
            },
        },
    }
    for fact_key, payload in policies.items():
        conn.execute(
            text(
                """
                UPDATE brc_required_fact_contracts
                SET definition_payload = :definition_payload
                WHERE fact_key = :fact_key
                """
            ),
            {
                "fact_key": fact_key,
                "definition_payload": json.dumps(payload, sort_keys=True),
            },
        )


def _candles(start: str, hourly_step: str):
    start_value = Decimal(start)
    step = Decimal(hourly_step)
    first_open_ms = TRIGGER_CLOSE_MS - 13 * 3_600_000
    return [
        {
            "open_time_ms": first_open_ms + index * 3_600_000,
            "close_time_ms": first_open_ms + (index + 1) * 3_600_000,
            "close": str(start_value + step * index),
        }
        for index in range(13)
    ]


def test_pg_plan_derives_two_group_universes_and_five_unique_symbols(
    pg_control_connection,
):
    _install_comparative_policies(pg_control_connection)

    plan = load_comparative_strength_fact_plan(pg_control_connection)

    assert [item.strategy_group_id for item in plan.groups] == ["MI-001", "MPG-001"]
    assert plan.required_symbols == (
        "AVAXUSDT",
        "ETHUSDT",
        "OPUSDT",
        "SOLUSDT",
        "SUIUSDT",
    )
    assert {item.strategy_group_id: item.lookback_bars for item in plan.groups} == {
        "MPG-001": 8,
        "MI-001": 12,
    }


def test_materializer_writes_seven_pg_comparative_fact_rows(
    pg_control_connection,
):
    _install_comparative_policies(pg_control_connection)
    candles_by_symbol = {
        "AVAXUSDT": _candles("100", "2.0"),
        "ETHUSDT": _candles("100", "1.0"),
        "OPUSDT": _candles("100", "2.5"),
        "SOLUSDT": _candles("100", "1.5"),
        "SUIUSDT": _candles("100", "0.5"),
    }

    result = materialize_comparative_strength_fact_snapshots(
        pg_control_connection,
        candles_by_symbol=candles_by_symbol,
        observed_at_ms=NOW_MS,
        source_ref="binance_closed_1h",
    )

    assert result["status"] == "comparative_strength_fact_snapshots_materialized"
    assert result["materialized_count"] == 7
    rows = list(
        pg_control_connection.execute(
            text(
                """
                SELECT strategy_group_id, symbol, satisfied, freshness_state,
                       fact_values, blocker_class
                FROM brc_runtime_fact_snapshots
                WHERE fact_surface = 'strategy_comparative'
                ORDER BY strategy_group_id, symbol
                """
            )
        ).mappings()
    )
    assert len(rows) == 7
    mpg_op = next(
        row
        for row in rows
        if row["strategy_group_id"] == "MPG-001" and row["symbol"] == "OPUSDT"
    )
    values = json.loads(str(mpg_op["fact_values"]))
    member = next(item for item in values["members"] if item["symbol"] == "OPUSDT")
    assert member["rank"] == 1
    assert mpg_op["satisfied"] in {True, 1}
    assert mpg_op["freshness_state"] == "fresh"
    assert mpg_op["blocker_class"] is None


def test_materializer_fails_closed_for_missing_peer_data(pg_control_connection):
    _install_comparative_policies(pg_control_connection)
    candles_by_symbol = {
        "AVAXUSDT": _candles("100", "2.0"),
        "ETHUSDT": _candles("100", "1.0"),
        "OPUSDT": _candles("100", "2.5"),
        "SOLUSDT": _candles("100", "1.5"),
    }

    result = materialize_comparative_strength_fact_snapshots(
        pg_control_connection,
        candles_by_symbol=candles_by_symbol,
        observed_at_ms=NOW_MS,
        source_ref="binance_closed_1h",
    )

    assert result["status"] == "comparative_strength_fact_snapshots_blocked"
    assert "MPG-001:missing universe symbol: SUIUSDT" in result["blockers"]
    mpg_rows = list(
        pg_control_connection.execute(
            text(
                """
                SELECT satisfied, freshness_state, blocker_class, failed_facts
                FROM brc_runtime_fact_snapshots
                WHERE fact_surface = 'strategy_comparative'
                  AND strategy_group_id = 'MPG-001'
                """
            )
        ).mappings()
    )
    assert len(mpg_rows) == 4
    assert all(row["satisfied"] in {False, 0} for row in mpg_rows)
    assert all(row["freshness_state"] == "unknown" for row in mpg_rows)
    assert all(row["blocker_class"] == "computed_not_satisfied" for row in mpg_rows)


def test_materializer_fails_closed_when_comparative_fetch_returns_no_candles(
    pg_control_connection,
):
    _install_comparative_policies(pg_control_connection)

    result = materialize_comparative_strength_fact_snapshots(
        pg_control_connection,
        candles_by_symbol={},
        observed_at_ms=NOW_MS,
        source_ref="binance_closed_1h",
    )

    assert result["status"] == "comparative_strength_fact_snapshots_blocked"
    assert result["materialized_count"] == 0
    assert result["blocked_count"] == 7
