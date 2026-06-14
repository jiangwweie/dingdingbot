from __future__ import annotations

from scripts.build_strategy_group_live_facts_readiness_packet import build_packet


def _intake() -> dict:
    return {
        "source_anchor": {
            "repo": "/strategy-repo",
            "branch": "codex/strategy-research-20260613-goal",
            "commit": "05f616b0",
        },
        "strategy_picker": [
            {
                "strategy_group_id": "MPG-001",
                "supported_symbols": ["BTCUSDT", "ETHUSDT"],
                "supported_symbol_count": 2,
                "picker": {"default_mode": "armed_observation"},
                "warnings": [],
            },
            {
                "strategy_group_id": "PMR-001",
                "supported_symbols": ["XAUUSDT"],
                "supported_symbol_count": 1,
                "picker": {"default_mode": "observe_only"},
                "warnings": ["observe_only_until_role_session_mark_readiness"],
            },
        ],
    }


def _exchange_rules() -> dict:
    return {
        "symbols": {
            "BTCUSDT": {"status": "TRADING"},
            "ETHUSDT": {"status": "TRADING"},
            "XAUUSDT": {"status": "TRADING"},
        }
    }


def test_live_facts_readiness_allows_observation_when_candidate_facts_missing():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts={"exchange_rules": _exchange_rules()},
        generated_at_ms=1,
    )

    assert packet["status"] == "strategy_group_observe_ready_armed_blocked"
    assert packet["counts"]["observe_ready"] == 2
    assert packet["counts"]["armed_candidate_prepare_ready"] == 0
    assert packet["operator_path"]["can_continue_observation"] is True
    assert packet["operator_path"]["can_prepare_fresh_candidate"] is False
    assert packet["operator_path"]["requires_action_time_final_gate_before_submit"] is True
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["creates_candidate"] is False
    mpg = next(item for item in packet["readiness"] if item["strategy_group_id"] == "MPG-001")
    assert mpg["observe_ready"] is True
    assert "account:missing" in mpg["blockers"]


def test_live_facts_readiness_marks_armed_ready_when_required_live_facts_pass():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts={
            "exchange_rules": _exchange_rules(),
            "account": {"status": "fresh"},
            "active_position": {"status": "no_active_position"},
            "open_orders": {"status": "no_open_orders"},
            "protection": {"status": "ready"},
            "budget": {"status": "available"},
            "next_attempt_gate": {"status": "waiting_for_fresh_strategy_signal"},
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "strategy_group_live_facts_ready_for_armed_observation"
    assert packet["counts"]["observe_ready"] == 2
    assert packet["counts"]["armed_candidate_prepare_ready"] == 1
    assert packet["operator_path"]["can_prepare_fresh_candidate"] is True
    assert packet["blockers"] == []


def test_live_facts_readiness_blocks_observation_when_exchange_rules_missing():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts={},
        generated_at_ms=1,
    )

    assert packet["status"] == "strategy_group_live_facts_blocked"
    assert packet["counts"]["observe_ready"] == 0
    assert packet["operator_path"]["can_continue_observation"] is False
    assert "MPG-001:exchange_rules_not_ready_for_all_symbols" in packet["blockers"]
