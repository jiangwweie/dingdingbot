from __future__ import annotations

import argparse
from decimal import Decimal
import os
import sys
from types import SimpleNamespace

from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)
from scripts import build_runtime_strategy_signal_input_artifact


NOW_MS = 1781000000000


def _candle(index: int, open_: str, high: str, low: str, close: str) -> SimpleNamespace:
    return SimpleNamespace(
        open_time_ms=NOW_MS - (30 - index) * 3_600_000,
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


def test_signal_input_artifact_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("PG_DATABASE_URL=postgresql+asyncpg://signal")
    monkeypatch.setenv("PG_DATABASE_URL", "")

    build_runtime_strategy_signal_input_artifact._load_env_file(str(env_file))

    assert os.environ["PG_DATABASE_URL"] == "postgresql+asyncpg://signal"


def test_build_btpc_signal_input_uses_runtime_boundary_and_placeholder_account():
    signal_input = build_runtime_strategy_signal_input_artifact._build_signal_input(
        runtime=_runtime(),
        one_hour=_btpc_1h(),
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


def test_signal_input_artifact_observe_only_for_btpc_non_entry_snapshot(monkeypatch, tmp_path):
    class FakeSource:
        source_id = "unit_market_source"
        source_type = "unit_read_only"

        def latest_closed_candles(self, *, symbol, timeframe, limit):
            return _down_context_4h() if timeframe == "4h" else _btpc_1h()

    async def fake_load_runtime(runtime_instance_id):
        return _runtime()

    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_load_runtime",
        fake_load_runtime,
    )
    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_market_source",
        lambda args: FakeSource(),
    )
    output_path = tmp_path / "signal-input.json"

    payload = __import__("asyncio").run(
        build_runtime_strategy_signal_input_artifact._build_artifact(
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
                output_signal_input_json=str(output_path),
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
    assert output_path.exists()


def test_signal_input_artifact_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_artifact(args):
        print("noisy market source")
        return {"status": "ready_for_shadow_candidate_prepare", "ok": True}

    monkeypatch.setattr(
        build_runtime_strategy_signal_input_artifact,
        "_build_artifact",
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

    assert build_runtime_strategy_signal_input_artifact.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy market source" not in captured.out
    assert "noisy market source" in captured.err


def test_signal_input_artifact_module_has_no_packet_builder() -> None:
    assert not hasattr(build_runtime_strategy_signal_input_artifact, "_build_packet")
