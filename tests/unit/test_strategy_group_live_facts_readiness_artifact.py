from __future__ import annotations

import scripts.build_strategy_group_live_facts_readiness_artifact as readiness_script
from scripts.build_strategy_group_live_facts_readiness_artifact import (
    build_readiness_artifact,
)


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
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={"exchange_rules": _exchange_rules()},
        generated_at_ms=1,
    )

    assert artifact["status"] == (
        "strategy_group_observe_ready_candidate_prerequisites_pending"
    )
    assert artifact["counts"]["observe_ready"] == 2
    assert artifact["counts"]["armed_candidate_prepare_ready"] == 0
    assert artifact["operator_path"]["can_continue_observation"] is True
    assert artifact["operator_path"]["can_prepare_fresh_candidate"] is False
    assert artifact["operator_path"]["next_gate"] == (
        "continue_observation_and_prepare_candidate_prerequisites"
    )
    assert artifact["operator_path"]["requires_action_time_final_gate_before_submit"] is True
    assert artifact["owner_state"]["status"] == (
        "observe_ready_candidate_prerequisites_missing"
    )
    assert artifact["owner_state"]["blocked_at"] == "candidate_prepare_facts"
    assert artifact["owner_state"]["downgrade_mode"] == (
        "observe_only_until_candidate_prerequisites_ready"
    )
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "continue_observation_and_prepare_candidate_prerequisite_facts"
    )
    assert artifact["owner_state"]["checkpoint_source"] == "owner_state"
    assert artifact["safety_invariants"]["places_order"] is False
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["blockers"] == []
    assert "MPG-001:account:missing" in artifact["candidate_prepare_blockers"]
    mpg = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "MPG-001"
    )
    assert mpg["observe_ready"] is True
    assert "account:missing" in mpg["blockers"]


def test_live_facts_readiness_marks_armed_ready_when_required_live_facts_pass():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={
            "exchange_rules": _exchange_rules(),
            "account": {"status": "fresh"},
            "active_position": {"status": "no_active_position"},
            "open_orders": {"status": "no_open_orders"},
            "protection": {"status": "ready_for_candidate_specific_plan"},
            "budget": {"status": "available_for_candidate_specific_reservation"},
            "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        },
        generated_at_ms=1,
    )

    assert artifact["status"] == "strategy_group_live_facts_ready_for_armed_observation"
    assert artifact["counts"]["observe_ready"] == 2
    assert artifact["counts"]["armed_candidate_prepare_ready"] == 1
    assert artifact["operator_path"]["can_prepare_fresh_candidate"] is True
    assert artifact["operator_path"]["next_gate"] == (
        "review_ready_groups_before_fresh_candidate_prepare"
    )
    assert artifact["owner_state"]["status"] == "armed_observation_ready"
    assert artifact["owner_state"]["blocked_at"] == "none"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "continue_watcher_observation"
    )
    assert artifact["blockers"] == []
    assert artifact["candidate_prepare_blockers"] == []


def test_live_facts_readiness_blocks_observation_when_exchange_rules_missing():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={},
        generated_at_ms=1,
    )

    assert artifact["status"] == "strategy_group_live_facts_blocked"
    assert artifact["counts"]["observe_ready"] == 0
    assert artifact["operator_path"]["can_continue_observation"] is False
    assert artifact["owner_state"]["blocked_at"] == "live_fact_readiness"
    assert artifact["owner_state"]["downgrade_mode"] == "not_observing"
    assert "automatic_recovery_action" not in artifact["owner_state"]
    assert artifact["owner_state"]["non_authority_checkpoint"] == (
        "refresh_strategy_group_live_facts_readonly"
    )
    assert (
        "MPG-001:exchange_rules_not_ready_for_any_supported_symbol"
        in artifact["blockers"]
    )


def test_live_facts_readiness_allows_partial_supported_symbol_availability():
    artifact = build_readiness_artifact(
        intake_artifact=_intake(),
        live_facts={
            "exchange_rules": {
                "symbols": {
                    "BTCUSDT": {"status": "TRADING"},
                    "ETHUSDT": {"status": "missing"},
                    "XAUUSDT": {"status": "missing"},
                }
            },
            "account": {"status": "fresh"},
            "active_position": {"status": "no_active_position"},
            "open_orders": {"status": "no_open_orders"},
            "protection": {"status": "ready_for_candidate_specific_plan"},
            "budget": {"status": "available_for_candidate_specific_reservation"},
            "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        },
        generated_at_ms=1,
    )

    mpg = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "MPG-001"
    )
    pmr = next(
        item for item in artifact["readiness"]
        if item["strategy_group_id"] == "PMR-001"
    )

    assert mpg["observe_ready"] is True
    assert mpg["armed_candidate_prepare_ready"] is True
    assert mpg["exchange_rules"]["ready_symbols"] == ["BTCUSDT"]
    assert mpg["exchange_rules"]["blocked_symbols"] == ["ETHUSDT"]
    assert "exchange_rules_not_ready_for_some_supported_symbols" in mpg["warnings"]
    assert (
        "MPG-001:exchange_rules_not_ready_for_any_supported_symbol"
        not in artifact["blockers"]
    )
    assert pmr["observe_ready"] is False
    assert (
        "PMR-001:exchange_rules_not_ready_for_any_supported_symbol"
        in artifact["blockers"]
    )


def test_live_facts_readiness_does_not_expose_legacy_packet_builder():
    assert not hasattr(readiness_script, "build_packet")
