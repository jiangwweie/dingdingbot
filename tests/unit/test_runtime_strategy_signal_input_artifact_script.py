from __future__ import annotations

import argparse
from decimal import Decimal
import json
import sys
from types import SimpleNamespace

import pytest

from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from src.application.readmodels import runtime_strategy_signal_input
from scripts import build_runtime_strategy_signal_input_artifact


NOW_MS = 1781000000000


class _AsyncMappingsResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _AsyncConnection:
    def __init__(self, row):
        self.row = row
        self.params = None

    async def execute(self, statement, params):
        self.params = params
        return _AsyncMappingsResult(self.row)


def _comparative_row(
    *,
    strategy_group_id: str = "MPG-001",
    symbol: str = "BTCUSDT",
    side: str = "long",
    freshness_state: str = "fresh",
    valid_until_ms: int = NOW_MS + 60_000,
):
    return {
        "strategy_group_id": strategy_group_id,
        "symbol": symbol,
        "side": side,
        "computed": True,
        "satisfied": True,
        "freshness_state": freshness_state,
        "valid_until_ms": valid_until_ms,
        "fact_values": json.dumps(
            {
                "strategy_group_id": strategy_group_id,
                "timeframe": "1h",
                "lookback_bars": 8,
                "trigger_candle_close_time_ms": NOW_MS - 1,
                "universe_symbols": ["BTCUSDT", "ETHUSDT"],
                "members": [
                    {
                        "symbol": "BTCUSDT",
                        "start_close": "100",
                        "end_close": "112",
                        "return_pct": "12",
                        "rank": 1,
                    },
                    {
                        "symbol": "ETHUSDT",
                        "start_close": "100",
                        "end_close": "108",
                        "return_pct": "8",
                        "rank": 2,
                    },
                ],
                "observed_at_ms": NOW_MS - 1,
                "valid_until_ms": valid_until_ms,
                "source_ref": "binance_closed_1h",
                "candidate_symbol": symbol,
                "fact_key": "leader_strength_confirmed",
            },
        ),
    }


def _candle(index: int, open_: str, high: str, low: str, close: str) -> SimpleNamespace:
    return SimpleNamespace(
        open_time_ms=NOW_MS - (30 - index) * 3_600_000,
        close_time_ms=NOW_MS - (30 - index) * 3_600_000 + 3_600_000 - 1,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def _btpc_1h() -> list[SimpleNamespace]:
    return [
        _candle(0, "110", "111", "108", "109"),
        _candle(1, "109", "110", "107", "108"),
        _candle(2, "108", "109", "106", "107"),
        _candle(3, "107", "108", "105", "106"),
        _candle(4, "106", "107", "104", "105"),
        _candle(5, "105", "106", "103", "104"),
        _candle(6, "104", "105", "102", "103"),
        _candle(7, "103", "104", "101", "102"),
        _candle(8, "102", "104", "100", "103"),
        _candle(9, "103", "105", "101", "104"),
        _candle(10, "104", "106", "102", "105"),
        _candle(11, "105", "106", "100", "101"),
        _candle(12, "101", "102", "99", "100"),
        _candle(13, "100", "101", "95", "96"),
    ]


def _down_context_4h() -> list[SimpleNamespace]:
    return [
        _candle(0, "122", "123", "119", "120"),
        _candle(1, "120", "121", "117", "118"),
        _candle(2, "118", "119", "115", "116"),
        _candle(3, "116", "117", "113", "114"),
    ]


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-btpc-1",
        trial_binding_id="trial-btpc-1",
        admission_decision_id="admission-btpc-1",
        strategy_family_id="BTPC-001",
        strategy_family_version_id="BTPC-001-v0",
        carrier_id="BTPC-001-runtime",
        symbol="AVAX/USDT:USDT",
        side="short",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=1,
            budget_reserved=Decimal("0.10"),
            total_budget=Decimal("6"),
            max_notional_per_attempt=Decimal("8"),
            max_active_positions=1,
            allowed_symbols=["AVAX/USDT:USDT"],
            allowed_sides=["short"],
            max_leverage=Decimal("1"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def test_build_btpc_signal_input_uses_runtime_boundary_and_placeholder_account():
    one_hour = _btpc_1h()
    latest_close_time_ms = one_hour[-1].close_time_ms
    signal_input = runtime_strategy_signal_input.build_signal_input(
        runtime=_runtime(),
        one_hour=one_hour,
        four_hour=_down_context_4h(),
        source_id="unit_market",
        source_type="unit_read_only",
        evaluation_id="eval-btpc-unit",
        playbook_id=None,
        now_ms=NOW_MS,
    )

    assert signal_input.strategy_family_id == "BTPC-001"
    assert signal_input.strategy_family_version_id == "BTPC-001-v0"
    assert signal_input.symbol == "AVAX/USDT:USDT"
    assert signal_input.timestamp_ms == latest_close_time_ms
    assert signal_input.trigger_candle_close_time_ms == latest_close_time_ms
    assert signal_input.market_snapshot.timestamp_ms == latest_close_time_ms
    assert signal_input.trial_constraints_snapshot["attempts_remaining"] == 2
    assert signal_input.trial_constraints_snapshot["max_notional_per_attempt"] == "8"
    assert signal_input.account_facts_snapshot.truth_level == (
        "placeholder_replaced_by_trusted_runtime_overlay"
    )
    assert (
        signal_input.reconciliation_status[
            "trusted_overlay_required_before_candidate_planning"
        ]
        is True
    )


@pytest.mark.asyncio
async def test_load_comparative_strength_snapshot_accepts_exact_fresh_pg_row():
    conn = _AsyncConnection(_comparative_row())

    snapshot = await runtime_strategy_signal_input.load_comparative_strength_snapshot(
        conn,
        strategy_group_id="MPG-001",
        symbol="BTC/USDT:USDT",
        side="long",
        trigger_candle_close_time_ms=NOW_MS - 1,
        now_ms=NOW_MS,
    )

    assert snapshot is not None
    assert snapshot.strategy_group_id == "MPG-001"
    assert snapshot.member("BTC/USDT:USDT").rank == 1
    assert conn.params == {
        "fact_surface": "strategy_comparative",
        "strategy_group_id": "MPG-001",
        "symbol": "BTCUSDT",
        "side": "long",
        "now_ms": NOW_MS,
    }


@pytest.mark.asyncio
async def test_load_comparative_strength_snapshot_returns_none_when_missing():
    conn = _AsyncConnection(None)

    snapshot = await runtime_strategy_signal_input.load_comparative_strength_snapshot(
        conn,
        strategy_group_id="MPG-001",
        symbol="BTCUSDT",
        side="long",
        trigger_candle_close_time_ms=NOW_MS - 1,
        now_ms=NOW_MS,
    )

    assert snapshot is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        _comparative_row(freshness_state="stale"),
        _comparative_row(valid_until_ms=NOW_MS),
        _comparative_row(strategy_group_id="MI-001"),
        _comparative_row(symbol="ETHUSDT"),
        _comparative_row(side="short"),
    ],
)
async def test_load_comparative_strength_snapshot_rejects_stale_or_cross_scope_row(row):
    conn = _AsyncConnection(row)

    snapshot = await runtime_strategy_signal_input.load_comparative_strength_snapshot(
        conn,
        strategy_group_id="MPG-001",
        symbol="BTCUSDT",
        side="long",
        trigger_candle_close_time_ms=NOW_MS - 1,
        now_ms=NOW_MS,
    )

    assert snapshot is None


def test_build_signal_input_attaches_typed_pg_comparative_snapshot():
    row = _comparative_row()
    snapshot_payload = json.loads(row["fact_values"])
    snapshot_payload = {
        key: snapshot_payload[key]
        for key in runtime_strategy_signal_input.COMPARATIVE_SNAPSHOT_KEYS
    }

    signal_input = runtime_strategy_signal_input.build_signal_input(
        runtime=_runtime(),
        one_hour=_btpc_1h(),
        four_hour=_down_context_4h(),
        source_id="unit_market",
        source_type="unit_read_only",
        evaluation_id="eval-btpc-unit",
        playbook_id=None,
        now_ms=NOW_MS,
        comparative_strength_snapshot=snapshot_payload,
    )

    assert signal_input.comparative_strength_snapshot is not None
    assert signal_input.comparative_strength_snapshot.member("BTCUSDT").rank == 1


def test_signal_input_artifact_observe_only_for_btpc_non_entry_snapshot(monkeypatch, tmp_path):
    class FakeSource:
        source_id = "unit_market_source"
        source_type = "unit_read_only"

        def latest_closed_candles(self, *, symbol, timeframe, limit):
            return _down_context_4h() if timeframe == "4h" else _btpc_1h()

    async def fake_load_runtime(runtime_instance_id):
        return _runtime()

    monkeypatch.setattr(
        runtime_strategy_signal_input,
        "_load_runtime",
        fake_load_runtime,
    )
    monkeypatch.setattr(
        runtime_strategy_signal_input,
        "market_source",
        lambda args: FakeSource(),
    )
    async def fake_load_comparative_strength(**kwargs):
        return None

    monkeypatch.setattr(
        runtime_strategy_signal_input,
        "load_runtime_comparative_strength_snapshot",
        fake_load_comparative_strength,
    )
    output_path = tmp_path / "signal-input.json"

    payload = __import__("asyncio").run(
        runtime_strategy_signal_input.build_artifact(
            argparse.Namespace(
                runtime_instance_id="runtime-btpc-1",
                env_file=None,
                source="live_market",
                symbol=None,
                evaluation_id="eval-btpc-unit",
                playbook_id=None,
                one_hour_limit=25,
                four_hour_limit=12,
                timeout_seconds=10.0,
            )
        )
    )

    assert payload["status"] == "observe_only"
    assert payload["evaluation_result"]["status"] == "observe_only"
    assert "operator_command_plan" not in payload
    assert payload["signal_input_artifact_plan"]["next_step"] == (
        "observe_only_or_wait_for_next_closed_bar"
    )
    assert payload["scope"] == "runtime_strategy_signal_input_artifact"
    assert payload["safety_invariants"]["signal_observation_artifact_only"] is True
    assert "packet_only" not in payload["safety_invariants"]
    assert payload["safety_invariants"]["execution_intent_created"] is False
    assert payload["safety_invariants"]["order_candidate_created"] is False
    assert not output_path.exists()


def test_signal_input_artifact_readmodel_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_artifact(args):
        print("noisy market source")
        return {"status": "ready_for_action_time_ticket_materialization", "ok": True}

    monkeypatch.setattr(
        runtime_strategy_signal_input,
        "build_artifact",
        fake_build_artifact,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_runtime_strategy_signal_input_artifact.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert runtime_strategy_signal_input.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy market source" not in captured.out
    assert "noisy market source" in captured.err


def test_signal_input_artifact_module_has_no_packet_builder() -> None:
    assert not hasattr(build_runtime_strategy_signal_input_artifact, "_build_packet")
    assert not hasattr(build_runtime_strategy_signal_input_artifact, "_build_artifact")
    assert not hasattr(build_runtime_strategy_signal_input_artifact, "_build_signal_input")


def test_signal_input_artifact_script_is_thin_cli_wrapper(monkeypatch) -> None:
    monkeypatch.setattr(runtime_strategy_signal_input, "main", lambda: 7)

    assert build_runtime_strategy_signal_input_artifact.main() == 7
