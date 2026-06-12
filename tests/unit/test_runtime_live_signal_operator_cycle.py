from __future__ import annotations

import json
import sys

from scripts import runtime_live_signal_operator_cycle as script


def test_operator_cycle_waits_without_prepare_records(tmp_path):
    calls = {"prepare": 0}

    async def routing_builder(args):
        return _routing_packet(
            status="waiting_for_runtime_compatible_signal",
            blockers=["runtime_strategy_signal_not_found_in_strategy_shelf"],
        )

    def prepare_runner(args, signal_input_json):
        calls["prepare"] += 1
        raise AssertionError("prepare must not run while waiting")

    packet = _run_packet(
        tmp_path,
        routing_builder=routing_builder,
        prepare_runner=prepare_runner,
    )

    assert packet["status"] == "waiting_for_runtime_compatible_signal"
    assert packet["operator_command_plan"]["next_step"] == (
        "continue_live_signal_observation_without_forcing_entry"
    )
    assert packet["prepare_packet"] is None
    assert calls["prepare"] == 0
    assert packet["safety_invariants"]["prepare_flow_called"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False


def test_operator_cycle_surfaces_profile_proposal_without_prepare(tmp_path):
    async def routing_builder(args):
        return _routing_packet(
            status="ready_for_owner_runtime_profile_decision",
            profile_proposal_packet={
                "status": "ready_for_owner_runtime_profile_decision",
                "experimental_runtime_profile_proposal": {
                    "strategy_family_id": "RBR-001",
                    "symbol": "ADA/USDT:USDT",
                },
            },
        )

    packet = _run_packet(tmp_path, routing_builder=routing_builder)

    assert packet["status"] == "ready_for_owner_runtime_profile_decision"
    assert packet["profile_proposal_packet"]["experimental_runtime_profile_proposal"][
        "strategy_family_id"
    ] == "RBR-001"
    assert packet["operator_command_plan"]["requires_owner_runtime_profile_confirmation"] is True
    assert packet["operator_command_plan"]["creates_runtime"] is False
    assert packet["prepare_packet"] is None
    assert packet["safety_invariants"]["runtime_profile_mutated"] is False


def test_operator_cycle_ready_signal_requires_explicit_prepare_flag(tmp_path):
    async def routing_builder(args):
        return _routing_packet(
            status="ready_for_current_runtime_signal_prepare",
            signal_input_json=str(tmp_path / "ready-signal.json"),
        )

    packet = _run_packet(tmp_path, routing_builder=routing_builder)

    assert packet["status"] == "ready_for_prepare"
    assert packet["signal_input_json"].endswith("ready-signal.json")
    assert packet["operator_command_plan"]["next_step"] == (
        "rerun_with_allow_prepare_records_after_operator_review"
    )
    assert packet["prepare_packet"] is None
    assert packet["safety_invariants"]["prepare_records_created"] is False
    assert packet["operator_command_plan"]["places_order"] is False


def test_operator_cycle_runs_prepare_only_with_explicit_flag(tmp_path):
    signal_path = str(tmp_path / "ready-signal.json")

    async def routing_builder(args):
        return _routing_packet(
            status="ready_for_current_runtime_signal_prepare",
            signal_input_json=signal_path,
        )

    def prepare_runner(args, signal_input_json):
        assert signal_input_json == signal_path
        assert args.routing_runtime_profile["symbol"] == "AVAX/USDT:USDT"
        return {
            "status": "ready_for_final_gate_preflight",
            "blockers": [],
            "warnings": [],
            "operator_command_plan": {
                "prepared_authorization_id": "auth-rtf067",
            },
            "created_records": {
                "shadow_candidate_created": True,
                "runtime_execution_intent_draft_created": True,
                "execution_intent_created": True,
                "submit_authorization_created": True,
                "protection_plan_created": True,
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "attempt_counter_mutated": False,
                "runtime_budget_mutated": False,
                "position_opened": False,
                "withdrawal_or_transfer_created": False,
            },
        }

    packet = _run_packet(
        tmp_path,
        extra_args=["--allow-prepare-records"],
        routing_builder=routing_builder,
        prepare_runner=prepare_runner,
    )

    assert packet["status"] == "ready_for_final_gate_preflight"
    assert packet["operator_command_plan"]["prepared_authorization_id"] == "auth-rtf067"
    assert packet["operator_command_plan"]["requires_real_submit_gate"] is True
    assert packet["safety_invariants"]["prepare_records_created"] is True
    assert packet["safety_invariants"]["shadow_candidate_created"] is True
    assert packet["safety_invariants"]["recorded_execution_intent_created"] is True
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False


def test_operator_cycle_cli_stdout_is_json_only(monkeypatch, capsys, tmp_path):
    async def routing_builder(args):
        print("inner noisy operator cycle")
        return _routing_packet(status="waiting_for_runtime_compatible_signal")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "runtime_live_signal_operator_cycle.py",
            "--runtime-instance-id",
            "runtime-1",
            "--output-json",
            str(tmp_path / "cycle.json"),
        ],
    )

    assert script.main_with_builders_for_test(routing_builder=routing_builder) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "waiting_for_runtime_compatible_signal"
    assert "inner noisy operator cycle" not in captured.out
    assert "inner noisy operator cycle" in captured.err


def _run_packet(
    tmp_path,
    *,
    extra_args=None,
    routing_builder=None,
    prepare_runner=None,
):
    argv = [
        "--runtime-instance-id",
        "runtime-1",
        "--output-json",
        str(tmp_path / "cycle.json"),
    ]
    if extra_args:
        argv.extend(extra_args)
    assert script._main(
        argv,
        routing_builder=routing_builder,
        prepare_runner=prepare_runner,
    ) == 0
    return json.loads((tmp_path / "cycle.json").read_text())


def _routing_packet(
    *,
    status: str,
    signal_input_json: str | None = None,
    blockers: list[str] | None = None,
    profile_proposal_packet: dict | None = None,
):
    return {
        "scope": "runtime_live_signal_routing_packet",
        "status": status,
        "runtime_instance_id": "runtime-1",
        "runtime_profile": {
            "runtime_instance_id": "runtime-1",
            "strategy_family_id": "BTPC-001",
            "strategy_family_version_id": "BTPC-001-v0",
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
        },
        "signal_input_json": signal_input_json,
        "profile_proposal_packet": profile_proposal_packet,
        "blockers": blockers or [],
        "warnings": [],
        "operator_command_plan": {
            "places_order": False,
            "calls_order_lifecycle": False,
        },
        "safety_invariants": {
            "runtime_created": False,
            "runtime_profile_mutated": False,
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
