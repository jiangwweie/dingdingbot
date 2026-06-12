from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

from scripts import runtime_live_strategy_signal_selector as selector


def _runtime(
    *,
    family: str = "BTPC-001",
    version: str = "BTPC-001-v0",
    symbol: str = "AVAX/USDT:USDT",
    side: str = "short",
) -> SimpleNamespace:
    return SimpleNamespace(
        runtime_instance_id="strategy-runtime-unit",
        strategy_family_id=family,
        strategy_family_version_id=version,
        symbol=symbol,
        side=side,
        status=SimpleNamespace(value="active"),
        execution_enabled=True,
        shadow_mode=False,
    )


def _row(
    *,
    family: str,
    version: str,
    symbol: str,
    side: str,
    signal_type: str,
) -> dict:
    return {
        "candidate_id": f"{family}-{symbol}-{side}",
        "strategy_group_id": family,
        "strategy_family_version_id": version,
        "symbol": symbol,
        "side": side,
        "signal_type": signal_type,
        "confidence": "0.62",
        "reason_codes": ["unit_signal"],
        "human_summary": "unit signal",
        "market_bar_timestamp_ms": 1781283600000,
        "not_order": True,
        "not_execution_intent": True,
        "no_execution_permission": True,
        "no_order_permission": True,
        "no_runtime_start": True,
        "signal_input_snapshot": {
            "evaluation_id": f"eval-{family}-{symbol}-{side}",
            "strategy_family_id": family,
            "strategy_family_version_id": version,
            "symbol": symbol,
            "timestamp_ms": 1781283600000,
            "primary_timeframe": "1h",
            "context_timeframes": ["4h"],
            "market_snapshot": {
                "symbol": symbol,
                "timestamp_ms": 1781283600000,
                "source": "unit",
                "freshness": "fresh",
                "candle_context": {"windows": {"1h": [], "4h": []}},
            },
            "account_facts_snapshot": {
                "source": "unit",
                "truth_level": "summary",
                "timestamp_ms": 1781283600000,
                "freshness": "fresh",
            },
            "source": "unit",
            "freshness": "fresh",
        },
    }


def _preview(rows: list[dict]) -> dict:
    return {
        "scope": "strategy_group_readonly_observation_preview",
        "status": "preview_built",
        "source_requested": "sample",
        "market_source": "unit_market",
        "checks": {
            "candidate_count": len(rows),
            "current_signal_count": len(rows),
            "would_enter_signal_count": sum(
                1 for row in rows if row["signal_type"] == "would_enter"
            ),
            "forbidden_effects": [],
        },
        "preview": {"current_signals": rows},
    }


def test_selector_writes_runtime_compatible_would_enter_signal(tmp_path: Path) -> None:
    output_path = tmp_path / "selected-signal-input.json"
    packet = selector._build_packet_from_preview(
        runtime=_runtime(),
        preview_packet=_preview(
            [
                _row(
                    family="BTPC-001",
                    version="BTPC-001-v0",
                    symbol="AVAX/USDT:USDT",
                    side="short",
                    signal_type="would_enter",
                )
            ]
        ),
        output_signal_input_json=str(output_path),
    )

    assert packet["status"] == "runtime_compatible_would_enter_selected"
    assert packet["blockers"] == []
    assert packet["selected_signal"]["strategy_family_id"] == "BTPC-001"
    assert packet["selected_signal"]["symbol"] == "AVAX/USDT:USDT"
    assert packet["operator_command_plan"]["signal_input_json"] == str(output_path)
    assert json.loads(output_path.read_text())["strategy_family_id"] == "BTPC-001"
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_candidate_created"] is False


def test_selector_reports_non_runtime_would_enter_without_profile_change() -> None:
    packet = selector._build_packet_from_preview(
        runtime=_runtime(),
        preview_packet=_preview(
            [
                _row(
                    family="RBR-001",
                    version="RBR-001-v0",
                    symbol="ADA/USDT:USDT",
                    side="short",
                    signal_type="would_enter",
                )
            ]
        ),
    )

    assert packet["status"] == "would_enter_available_but_not_runtime_compatible"
    assert packet["blockers"] == ["would_enter_signals_not_runtime_compatible"]
    assert packet["selected_signal"] is None
    assert packet["non_runtime_would_enter_signals"][0][
        "runtime_compatibility_blockers"
    ] == [
        "runtime_strategy_family_mismatch",
        "runtime_strategy_family_version_mismatch",
        "runtime_symbol_mismatch",
    ]
    assert (
        packet["operator_command_plan"]["requires_owner_runtime_profile_confirmation"]
        is True
    )
    assert packet["safety_invariants"]["runtime_profile_mutated"] is False


def test_selector_reports_runtime_observe_only_signal() -> None:
    packet = selector._build_packet_from_preview(
        runtime=_runtime(),
        preview_packet=_preview(
            [
                _row(
                    family="BTPC-001",
                    version="BTPC-001-v0",
                    symbol="AVAX/USDT:USDT",
                    side="short",
                    signal_type="no_action",
                )
            ]
        ),
    )

    assert packet["status"] == "runtime_signal_observe_only"
    assert packet["blockers"] == ["runtime_strategy_signal_not_would_enter"]
    assert packet["runtime_current_signal"]["signal_type"] == "no_action"
    assert packet["selected_signal"] is None
