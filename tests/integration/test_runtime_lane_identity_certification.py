"""Certify the current five-group production lane matrix without exchange writes.

This is deliberately PG-shaped: the test starts from the current seed, adds
one selected runtime instance for each registered candidate scope, resolves the
immutable lane identity, and exercises the non-executing Event-Spec adapter.
The full PG signal -> promotion -> lane -> Ticket simulation is certified for
the same explicit 22-lane matrix in the action-time materialization tests.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from src.application.runtime_lane_identity_service import (
    RuntimeLaneIdentityResolution,
    RuntimeLaneIdentityResolutionError,
    RuntimeLaneIdentityService,
)
from src.application.runtime_strategy_signal_evaluation_service import (
    RuntimeLaneEventEvaluationStatus,
    RuntimeStrategySignalEvaluationService,
)
from src.domain.execution_eligibility import RequiredExecutionMode, SignalGrade
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    ExpectedRiskShape,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    pg_control_connection,
)


# This accepted matrix is intentionally independent from generic evaluator
# output. A new side requires an explicit PG candidate-scope/Event-Spec binding
# and an Owner strategy-admission decision, not an inferred market pattern.
EXPECTED_EVENT_SCOPE = {
    "CPM-RO-001": {
        "symbols": ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
        "events": (("long", "CPM-LONG", "1h"),),
    },
    "MPG-001": {
        "symbols": ("OPUSDT", "SOLUSDT", "AVAXUSDT", "SUIUSDT"),
        "events": (("long", "MPG-LONG", "1h"),),
    },
    "MI-001": {
        "symbols": ("AVAXUSDT", "ETHUSDT", "SOLUSDT"),
        "events": (("long", "MI-LONG", "1h"),),
    },
    "SOR-001": {
        "symbols": ("ETHUSDT", "SOLUSDT", "AVAXUSDT", "BTCUSDT"),
        "events": (
            ("long", "SOR-LONG", "15m"),
            ("short", "SOR-SHORT", "15m"),
        ),
    },
    "BRF2-001": {
        "symbols": ("BTCUSDT", "AVAXUSDT", "ETHUSDT"),
        "events": (("short", "BRF2-SHORT", "1h"),),
    },
}


def _expected_lanes() -> frozenset[tuple[str, str, str, str, str]]:
    return frozenset(
        (strategy_group_id, symbol, side, event_id, timeframe)
        for strategy_group_id, scope in EXPECTED_EVENT_SCOPE.items()
        for symbol in scope["symbols"]
        for side, event_id, timeframe in scope["events"]
    )


def _registered_rows(conn: sa.engine.Connection) -> list[dict]:
    return list(
        conn.execute(
            text(
                """
                SELECT c.candidate_scope_id,
                       c.strategy_group_id,
                       c.symbol,
                       c.side,
                       c.asset_class,
                       b.binding_id,
                       b.event_spec_id,
                       e.event_id,
                       e.event_spec_version,
                       e.timeframe,
                       e.time_authority
                FROM brc_strategy_group_candidate_scope c
                JOIN brc_candidate_scope_event_bindings b
                  ON b.candidate_scope_id = c.candidate_scope_id
                 AND b.status = 'active'
                JOIN brc_strategy_side_event_specs e
                  ON e.event_spec_id = b.event_spec_id
                 AND e.status = 'current'
                WHERE c.status = 'active'
                ORDER BY c.strategy_group_id, c.symbol, c.side
                """
            )
        ).mappings()
    )


def _install_selected_runtime_instances(
    conn: sa.engine.Connection,
    rows: list[dict],
) -> dict[tuple[str, str, str], str]:
    assert not sa.inspect(conn).has_table("strategy_runtime_instances")
    conn.execute(
        text(
            """
            CREATE TABLE strategy_runtime_instances (
              runtime_instance_id TEXT PRIMARY KEY,
              strategy_family_id TEXT NOT NULL,
              strategy_family_version_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              side TEXT NOT NULL,
              status TEXT NOT NULL
            )
            """
        )
    )
    runtime_ids: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = (str(row["strategy_group_id"]), str(row["symbol"]), str(row["side"]))
        runtime_instance_id = "runtime:lane-cert:" + ":".join(key)
        runtime_ids[key] = runtime_instance_id
        conn.execute(
            text(
                """
                INSERT INTO strategy_runtime_instances (
                  runtime_instance_id, strategy_family_id, strategy_family_version_id,
                  symbol, side, status
                ) VALUES (
                  :runtime_instance_id, :strategy_family_id,
                  :strategy_family_version_id, :symbol, :side, 'active'
                )
                """
            ),
            {
                "runtime_instance_id": runtime_instance_id,
                "strategy_family_id": key[0],
                # Implementation provenance is intentionally not the Event-Spec
                # semantic version carried by RuntimeLaneIdentity.
                "strategy_family_version_id": f"{key[0]}-v0",
                "symbol": key[1],
                "side": key[2],
            },
        )
    return runtime_ids


class _ControlledEvaluator:
    """Pure deterministic evaluator used to certify adapter semantics only."""

    def __init__(self, *, mode: str) -> None:
        self._mode = mode

    def evaluate(
        self,
        signal_input: StrategyFamilySignalInput,
    ) -> StrategyFamilySignalOutput:
        expected_side = SignalSide(str(signal_input.strategy_family_metadata["expected_side"]))
        if self._mode == "no_signal":
            signal_type = SignalType.NO_ACTION
            side = SignalSide.NONE
            signal_grade = SignalGrade.OBSERVE_ONLY_SIGNAL
            required_execution_mode = RequiredExecutionMode.OBSERVE_ONLY
            reason_codes = ["certification_exact_event_not_satisfied"]
        else:
            signal_type = SignalType.WOULD_ENTER
            side = (
                expected_side
                if self._mode == "exact_signal"
                else (
                    SignalSide.SHORT
                    if expected_side == SignalSide.LONG
                    else SignalSide.LONG
                )
            )
            signal_grade = SignalGrade.TRIAL_GRADE_SIGNAL
            required_execution_mode = RequiredExecutionMode.TRIAL_LIVE
            reason_codes = [f"certification_{self._mode}"]

        return StrategyFamilySignalOutput(
            signal_id=f"certification:{self._mode}:{signal_input.evaluation_id}",
            evaluation_id=signal_input.evaluation_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            timestamp_ms=signal_input.timestamp_ms,
            trigger_candle_close_time_ms=signal_input.trigger_candle_close_time_ms,
            timeframe=signal_input.primary_timeframe,
            signal_type=signal_type,
            side=side,
            confidence=Decimal("0.9") if signal_type == SignalType.WOULD_ENTER else Decimal("0"),
            reason_codes=reason_codes,
            human_summary="deterministic runtime-lane certification evaluator",
            signal_grade=signal_grade,
            required_execution_mode=required_execution_mode,
            expected_risk_shape=ExpectedRiskShape.UNKNOWN,
        )


def _evaluation_input(
    resolution: RuntimeLaneIdentityResolution,
    *,
    symbol: str | None = None,
    primary_timeframe: str | None = None,
) -> StrategyFamilySignalInput:
    identity = resolution.identity
    return StrategyFamilySignalInput(
        evaluation_id=f"certification:{identity.runtime_instance_id}",
        strategy_family_id=identity.strategy_group_id,
        strategy_family_version_id=resolution.evaluator_version_id,
        binding_id=identity.candidate_scope_event_binding_id,
        symbol=symbol or identity.symbol,
        timestamp_ms=NOW_MS,
        trigger_candle_close_time_ms=NOW_MS - 1,
        primary_timeframe=primary_timeframe or identity.timeframe,
        market_snapshot=MarketSnapshot(
            symbol=symbol or identity.symbol,
            timestamp_ms=NOW_MS,
            source="pytest-runtime-lane-certification",
            freshness="fresh",
            timeframe=primary_timeframe or identity.timeframe,
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="pytest-runtime-lane-certification",
            truth_level="test",
            timestamp_ms=NOW_MS,
            freshness="fresh",
        ),
        strategy_family_metadata={"expected_side": identity.side},
        source="pytest-runtime-lane-certification",
        freshness="fresh",
    )


def _evaluation_service(
    resolutions: list[RuntimeLaneIdentityResolution],
    *,
    mode: str,
) -> RuntimeStrategySignalEvaluationService:
    evaluators = {
        (resolution.identity.strategy_group_id, resolution.evaluator_version_id): _ControlledEvaluator(
            mode=mode
        )
        for resolution in resolutions
    }
    return RuntimeStrategySignalEvaluationService(evaluators=evaluators)


def _runtime_write_counts(conn: sa.engine.Connection) -> dict[str, int]:
    return {
        table_name: int(
            conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        )
        for table_name in (
            "brc_live_signal_events",
            "brc_promotion_candidates",
            "brc_action_time_lane_inputs",
            "brc_action_time_tickets",
            "brc_runtime_process_outcomes",
        )
    }


def test_current_pg_registration_matches_accepted_five_group_matrix(
    pg_control_connection,
) -> None:
    rows = _registered_rows(pg_control_connection)
    actual_lanes = {
        (
            str(row["strategy_group_id"]),
            str(row["symbol"]),
            str(row["side"]),
            str(row["event_id"]),
            str(row["timeframe"]),
        )
        for row in rows
    }

    assert actual_lanes == _expected_lanes()
    assert len(actual_lanes) == 22
    assert {row["strategy_group_id"] for row in rows} == set(EXPECTED_EVENT_SCOPE)
    assert len({row["event_spec_id"] for row in rows}) == 6
    assert not any(
        row["strategy_group_id"] == "CPM-RO-001" and row["side"] == "short"
        for row in rows
    )


def test_all_22_lanes_resolve_and_evaluate_without_runtime_persistence(
    pg_control_connection,
) -> None:
    rows = _registered_rows(pg_control_connection)
    runtime_ids = _install_selected_runtime_instances(pg_control_connection, rows)
    resolver = RuntimeLaneIdentityService()
    resolutions = [
        resolver.resolve(pg_control_connection, runtime_instance_id=runtime_instance_id)
        for runtime_instance_id in runtime_ids.values()
    ]

    assert len(resolutions) == 22
    assert len({resolution.identity.identity_key for resolution in resolutions}) == 22
    assert {
        (
            resolution.identity.strategy_group_id,
            resolution.identity.symbol,
            resolution.identity.side,
            resolution.identity.event_id,
            resolution.identity.timeframe,
        )
        for resolution in resolutions
    } == _expected_lanes()

    before = _runtime_write_counts(pg_control_connection)
    no_signal_service = _evaluation_service(resolutions, mode="no_signal")
    exact_signal_service = _evaluation_service(resolutions, mode="exact_signal")
    for resolution in resolutions:
        no_signal = no_signal_service.evaluate_for_runtime_lane(
            _evaluation_input(resolution),
            lane_identity=resolution.identity,
            freshness_window_ms=resolution.freshness_window_ms,
        )
        assert no_signal.status == RuntimeLaneEventEvaluationStatus.COMPUTED_NOT_SATISFIED
        assert no_signal.can_materialize_live_signal_event is False
        assert no_signal.lane_identity == resolution.identity
        assert "computed_not_satisfied" in no_signal.reason_codes
        assert no_signal.exchange_called is False

        exact_signal = exact_signal_service.evaluate_for_runtime_lane(
            _evaluation_input(resolution),
            lane_identity=resolution.identity,
            freshness_window_ms=resolution.freshness_window_ms,
        )
        assert exact_signal.status == RuntimeLaneEventEvaluationStatus.EVENT_SATISFIED
        assert exact_signal.can_materialize_live_signal_event is True
        assert exact_signal.lane_identity == resolution.identity
        assert exact_signal.signal is not None
        assert exact_signal.signal.side.value == resolution.identity.side
        assert exact_signal.exchange_called is False

    assert _runtime_write_counts(pg_control_connection) == before


def test_each_strategy_family_rejects_cross_scope_inputs_without_persistence(
    pg_control_connection,
) -> None:
    rows = _registered_rows(pg_control_connection)
    runtime_ids = _install_selected_runtime_instances(pg_control_connection, rows)
    resolver = RuntimeLaneIdentityService()
    representatives = [
        resolver.resolve(
            pg_control_connection,
            runtime_instance_id=runtime_ids[(strategy_group_id, scope["symbols"][0], scope["events"][0][0])],
        )
        for strategy_group_id, scope in EXPECTED_EVENT_SCOPE.items()
    ]
    before = _runtime_write_counts(pg_control_connection)

    opposite_side_service = _evaluation_service(representatives, mode="opposite_side")
    for resolution in representatives:
        wrong_symbol = opposite_side_service.evaluate_for_runtime_lane(
            _evaluation_input(resolution, symbol="XRPUSDT"),
            lane_identity=resolution.identity,
            freshness_window_ms=resolution.freshness_window_ms,
        )
        assert wrong_symbol.status == RuntimeLaneEventEvaluationStatus.BLOCKED
        assert wrong_symbol.blockers == ["runtime_lane_identity_mismatch:symbol"]

        wrong_timeframe = opposite_side_service.evaluate_for_runtime_lane(
            _evaluation_input(resolution, primary_timeframe="5m"),
            lane_identity=resolution.identity,
            freshness_window_ms=resolution.freshness_window_ms,
        )
        assert wrong_timeframe.status == RuntimeLaneEventEvaluationStatus.BLOCKED
        assert wrong_timeframe.blockers == [
            "runtime_lane_identity_mismatch:primary_timeframe"
        ]

        opposite_side = opposite_side_service.evaluate_for_runtime_lane(
            _evaluation_input(resolution),
            lane_identity=resolution.identity,
            freshness_window_ms=resolution.freshness_window_ms,
        )
        assert opposite_side.status == RuntimeLaneEventEvaluationStatus.COMPUTED_NOT_SATISFIED
        assert opposite_side.can_materialize_live_signal_event is False
        assert "event_side_not_satisfied" in opposite_side.reason_codes

        replacement_event_spec_id = next(
            str(row["event_spec_id"])
            for row in rows
            if row["event_spec_id"] != resolution.identity.event_spec_id
        )
        pg_control_connection.execute(
            text(
                "UPDATE brc_candidate_scope_event_bindings "
                "SET event_spec_id = :replacement_event_spec_id "
                "WHERE binding_id = :binding_id"
            ),
            {
                "replacement_event_spec_id": replacement_event_spec_id,
                "binding_id": resolution.identity.candidate_scope_event_binding_id,
            },
        )
        with pytest.raises(
            RuntimeLaneIdentityResolutionError,
            match="runtime_lane_identity_mismatch",
        ):
            resolver.resolve(
                pg_control_connection,
                runtime_instance_id=resolution.identity.runtime_instance_id,
            )
        pg_control_connection.execute(
            text(
                "UPDATE brc_candidate_scope_event_bindings "
                "SET event_spec_id = :event_spec_id "
                "WHERE binding_id = :binding_id"
            ),
            {
                "event_spec_id": resolution.identity.event_spec_id,
                "binding_id": resolution.identity.candidate_scope_event_binding_id,
            },
        )

        pg_control_connection.execute(
            text(
                "UPDATE strategy_runtime_instances SET symbol = 'XRP/USDT:USDT' "
                "WHERE runtime_instance_id = :runtime_instance_id"
            ),
            {"runtime_instance_id": resolution.identity.runtime_instance_id},
        )
        with pytest.raises(
            RuntimeLaneIdentityResolutionError,
            match="runtime_instance_not_selected",
        ):
            resolver.resolve(
                pg_control_connection,
                runtime_instance_id=resolution.identity.runtime_instance_id,
            )
        pg_control_connection.execute(
            text(
                "UPDATE strategy_runtime_instances SET symbol = :symbol "
                "WHERE runtime_instance_id = :runtime_instance_id"
            ),
            {
                "symbol": resolution.identity.symbol,
                "runtime_instance_id": resolution.identity.runtime_instance_id,
            },
        )

    assert _runtime_write_counts(pg_control_connection) == before
