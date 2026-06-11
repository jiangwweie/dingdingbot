from __future__ import annotations

import argparse
import os
import sys

from scripts import verify_runtime_next_attempt_gate_packet


def test_next_attempt_gate_env_loader_fills_empty_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / "runtime.env"
    env_file.write_text("BRC_OPERATOR_USERNAME=owner")
    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "")

    verify_runtime_next_attempt_gate_packet._load_env_file(str(env_file))

    assert os.environ["BRC_OPERATOR_USERNAME"] == "owner"


def test_next_attempt_gate_scope_uses_runtime_defaults_and_cli_overrides():
    runtime_context = {
        "symbol": "AVAX/USDT:USDT",
        "side": "short",
        "strategy_family_id": "BTPC-001",
        "carrier_id": "BTPC-001-v0",
        "max_notional": "6.5",
        "max_leverage": "1",
        "max_attempts": 3,
        "review_requirement": "required",
    }
    args = argparse.Namespace(
        symbol=None,
        side="long",
        strategy_family_id=None,
        carrier_id=None,
        family="Trend",
        quantity="1",
        target_notional_usdt=None,
        max_notional=None,
        leverage=None,
        max_attempts=None,
        protection_mode="explicit_exit",
        review_requirement=None,
    )

    scope = verify_runtime_next_attempt_gate_packet._runtime_scope(args, runtime_context)

    assert scope["symbol"] == "AVAX/USDT:USDT"
    assert scope["side"] == "long"
    assert scope["strategy_family_id"] == "BTPC-001"
    assert scope["carrier_id"] == "BTPC-001-v0"
    assert scope["family"] == "Trend"
    assert scope["quantity"] == "1"
    assert scope["max_attempts"] == 3
    assert scope["protection_mode"] == "explicit_exit"


def test_next_attempt_gate_packet_clears_without_execution_authority(monkeypatch):
    async def fake_runtime_context(runtime_instance_id):
        return {
            "runtime_instance_id": runtime_instance_id,
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
            "strategy_family_id": "BTPC-001",
            "carrier_id": "BTPC-001-v0",
            "max_attempts": 3,
            "review_requirement": "required",
        }

    def fake_request_json(method, url, *, cookie):
        assert method == "GET"
        assert "include_exchange=true" in url
        return {
            "http_status": 200,
            "body": {
                "data": {
                    "owner_action_flow": {
                        "next_attempt_gate": {
                            "status": "clear_for_preflight",
                            "gate": "clear_for_next_preflight",
                            "next_attempt_allowed_by_lifecycle": True,
                            "blockers": [],
                            "warnings": [],
                        },
                        "just_in_time_lifecycle_audit": {
                            "can_continue_to_authorization": True,
                            "can_execute_live": False,
                        },
                    }
                }
            },
        }

    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_load_runtime_context",
        fake_runtime_context,
    )
    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_session_cookie",
        lambda: "brc_operator_session=signed",
    )
    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_request_json",
        fake_request_json,
    )

    payload = __import__("asyncio").run(
        verify_runtime_next_attempt_gate_packet._build_packet(
            argparse.Namespace(
                runtime_instance_id="runtime-1",
                env_file=None,
                api_base="http://127.0.0.1:18080",
                skip_exchange=False,
                family=None,
                strategy_family_id=None,
                carrier_id=None,
                symbol=None,
                side=None,
                quantity=None,
                target_notional_usdt=None,
                max_notional=None,
                leverage=None,
                max_attempts=None,
                protection_mode=None,
                review_requirement=None,
            )
        )
    )

    assert payload["status"] == "clear_for_next_attempt_preflight"
    assert payload["operator_command_plan"]["next_preflight_allowed"] is True
    assert payload["operator_command_plan"]["live_submit_allowed"] is False
    assert payload["safety_invariants"]["execution_intent_created"] is False
    assert payload["safety_invariants"]["order_created"] is False


def test_next_attempt_gate_packet_blocks_when_lifecycle_gate_blocks(monkeypatch):
    async def fake_runtime_context(runtime_instance_id):
        return {
            "runtime_instance_id": runtime_instance_id,
            "symbol": "AVAX/USDT:USDT",
            "side": "short",
            "strategy_family_id": "BTPC-001",
            "carrier_id": "BTPC-001-v0",
        }

    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_load_runtime_context",
        fake_runtime_context,
    )
    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_session_cookie",
        lambda: "brc_operator_session=signed",
    )
    monkeypatch.setattr(
        verify_runtime_next_attempt_gate_packet,
        "_request_json",
        lambda method, url, *, cookie: {
            "http_status": 200,
            "body": {
                "data": {
                    "post_action_state": {
                        "next_attempt_gate": {
                            "status": "blocked",
                            "gate": "closed_trade_review_required",
                            "next_attempt_allowed_by_lifecycle": False,
                            "blockers": [{"id": "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED"}],
                        }
                    },
                    "owner_action_flow": {
                        "just_in_time_lifecycle_audit": {
                            "can_continue_to_authorization": False,
                            "can_execute_live": False,
                        }
                    },
                }
            },
        },
    )

    payload = __import__("asyncio").run(
        verify_runtime_next_attempt_gate_packet._build_packet(
            argparse.Namespace(
                runtime_instance_id="runtime-1",
                env_file=None,
                api_base=None,
                skip_exchange=True,
                family=None,
                strategy_family_id=None,
                carrier_id=None,
                symbol=None,
                side=None,
                quantity=None,
                target_notional_usdt=None,
                max_notional=None,
                leverage=None,
                max_attempts=None,
                protection_mode=None,
                review_requirement=None,
            )
        )
    )

    assert payload["status"] == "blocked"
    assert payload["operator_command_plan"]["next_preflight_allowed"] is False
    assert payload["blockers"][0]["id"] == "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED"


def test_next_attempt_gate_cli_stdout_is_json_only(monkeypatch, capsys):
    async def fake_build_packet(args):
        print("noisy dependency log")
        return {"status": "clear_for_next_attempt_preflight", "ok": True}

    monkeypatch.setattr(verify_runtime_next_attempt_gate_packet, "_build_packet", fake_build_packet)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_runtime_next_attempt_gate_packet.py",
            "--runtime-instance-id",
            "runtime-1",
        ],
    )

    assert verify_runtime_next_attempt_gate_packet.main() == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("{")
    assert "noisy dependency log" not in captured.out
    assert "noisy dependency log" in captured.err
