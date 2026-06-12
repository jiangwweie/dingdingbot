from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal

from scripts import runtime_live_signal_routing_packet as script


def test_routes_runtime_compatible_signal_to_prepare_without_records() -> None:
    packet = script.build_routing_packet(
        selector_packet=_selector_packet(
            status="runtime_compatible_would_enter_selected",
            selected_signal={
                "strategy_family_id": "BTPC-001",
                "strategy_family_version_id": "BTPC-001-v0",
                "symbol": "AVAX/USDT:USDT",
                "side": "short",
                "signal_type": "would_enter",
            },
            output_signal_input_json="/tmp/runtime-ready-signal.json",
        ),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "ready_for_current_runtime_signal_prepare"
    assert packet["signal_input_json"] == "/tmp/runtime-ready-signal.json"
    assert packet["operator_command_plan"]["current_runtime_prepare_allowed"] is True
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["profile_proposal_packet"] is None
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_routes_non_runtime_signal_to_owner_profile_proposal() -> None:
    packet = script.build_routing_packet(
        selector_packet=_selector_packet(
            status="would_enter_available_but_not_runtime_compatible",
            non_runtime_would_enter_signals=[
                {
                    "strategy_family_id": "RBR-001",
                    "strategy_family_version_id": "RBR-001-v0",
                    "symbol": "ADA/USDT:USDT",
                    "side": "short",
                    "signal_type": "would_enter",
                    "not_order": True,
                    "not_execution_intent": True,
                }
            ],
            blockers=["would_enter_signals_not_runtime_compatible"],
        ),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "ready_for_owner_runtime_profile_decision"
    proposal = packet["profile_proposal_packet"]
    assert proposal["status"] == "ready_for_owner_runtime_profile_decision"
    assert proposal["experimental_runtime_profile_proposal"]["strategy_family_id"] == "RBR-001"
    assert proposal["experimental_runtime_profile_proposal"]["symbol"] == "ADA/USDT:USDT"
    assert packet["operator_command_plan"]["requires_owner_runtime_profile_confirmation"] is True
    assert packet["operator_command_plan"]["creates_runtime"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    assert packet["safety_invariants"]["runtime_profile_mutated"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_routes_no_signal_to_waiting_without_profile_or_candidate() -> None:
    packet = script.build_routing_packet(
        selector_packet=_selector_packet(
            status="no_would_enter_signal_available",
            blockers=["runtime_strategy_signal_not_found_in_strategy_shelf"],
        ),
        capital_base=Decimal("30"),
    )

    assert packet["status"] == "waiting_for_runtime_compatible_signal"
    assert packet["blockers"] == ["runtime_strategy_signal_not_found_in_strategy_shelf"]
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_live_signal_observation_without_forcing_entry"
    )
    assert packet["operator_command_plan"]["creates_shadow_candidate"] is False
    assert packet["profile_proposal_packet"] is None
    assert packet["right_tail_objective_context"]["forcing_entry_without_signal_forbidden"] is True


def test_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_selector(args):
        print("inner noisy selector")
        return _selector_packet(
            status="no_would_enter_signal_available",
            blockers=["runtime_strategy_signal_not_found_in_strategy_shelf"],
        )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_live_signal_routing_packet.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    exit_code = script.main_with_selector_for_test(fake_selector)

    assert exit_code == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_runtime_compatible_signal"
    assert "inner noisy selector" not in captured.out


def _selector_packet(
    *,
    status: str,
    selected_signal: dict | None = None,
    non_runtime_would_enter_signals: list[dict] | None = None,
    output_signal_input_json: str | None = None,
    blockers: list[str] | None = None,
) -> dict:
    return {
        "scope": "runtime_live_strategy_signal_selector",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "runtime_profile": {
            "runtime_instance_id": "runtime-1",
            "strategy_family_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
        },
        "selected_signal": selected_signal,
        "non_runtime_would_enter_signals": non_runtime_would_enter_signals or [],
        "runtime_current_signal": None,
        "output_signal_input_json": output_signal_input_json,
        "blockers": blockers or [],
        "warnings": ["selector_does_not_change_runtime_profile"],
        "safety_invariants": {
            "read_only_market_scan": True,
            "database_write": False,
            "runtime_profile_mutated": False,
            "runtime_created": False,
            "runtime_enabled": False,
            "signal_evaluation_created": False,
            "order_candidate_created": False,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }
