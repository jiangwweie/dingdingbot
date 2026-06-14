from __future__ import annotations

from scripts.build_strategygroup_runtime_pilot_status import build_packet


def _intake() -> dict:
    return {
        "source_anchor": {"commit": "unit"},
        "strategy_picker": [
            {
                "strategy_group_id": "MPG-001",
                "name": "Momentum Persistence Group",
                "supported_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "supported_sides": ["long"],
                "risk_defaults": {
                    "risk_tier": "tiny",
                    "default_leverage": "1",
                    "max_active_positions": 1,
                    "max_notional_per_action_usdt": "8",
                },
                "picker": {"rank": 1, "default_mode": "armed_observation"},
            },
            {
                "strategy_group_id": "TEQ-001",
                "name": "Tokenized Equity Momentum",
                "supported_symbols": ["NVDAUSDT", "TSLAUSDT"],
                "supported_sides": ["long"],
                "risk_defaults": {"max_notional_per_action_usdt": "8"},
                "picker": {"rank": 2, "default_mode": "armed_observation"},
            },
        ],
    }


def _readiness(*, mpg_observe_ready: bool = True, teq_blockers: list[str] | None = None) -> dict:
    resolved_teq_blockers = (
        ["protection:missing", "budget:missing", "next_attempt_gate:missing"]
        if teq_blockers is None
        else teq_blockers
    )
    return {
        "readiness": [
            {
                "strategy_group_id": "MPG-001",
                "observe_ready": mpg_observe_ready,
                "armed_candidate_prepare_ready": False,
                "exchange_rules": {
                    "ready_symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                },
                "candidate_fact_checks": [
                    {"live_fact_key": "account", "status": "fresh", "ready": True},
                    {
                        "live_fact_key": "active_position",
                        "status": "no_active_position",
                        "ready": True,
                    },
                    {
                        "live_fact_key": "open_orders",
                        "status": "no_open_orders",
                        "ready": True,
                    },
                    {"live_fact_key": "protection", "status": "missing", "ready": False},
                    {"live_fact_key": "budget", "status": "missing", "ready": False},
                    {
                        "live_fact_key": "next_attempt_gate",
                        "status": "missing",
                        "ready": False,
                    },
                ],
                "blockers": ["protection:missing", "budget:missing", "next_attempt_gate:missing"],
            },
            {
                "strategy_group_id": "TEQ-001",
                "observe_ready": True,
                "armed_candidate_prepare_ready": resolved_teq_blockers == [],
                "exchange_rules": {"ready_symbols": ["NVDAUSDT", "TSLAUSDT"]},
                "candidate_fact_checks": [
                    {"live_fact_key": "account", "status": "fresh", "ready": True},
                    {
                        "live_fact_key": "active_position",
                        "status": "no_active_position",
                        "ready": True,
                    },
                    {
                        "live_fact_key": "open_orders",
                        "status": "no_open_orders",
                        "ready": True,
                    },
                ],
                "blockers": resolved_teq_blockers,
            },
        ],
        "live_facts_source": {"path": "/tmp/facts.json", "present": True},
    }


def _watcher_waiting() -> dict:
    return {
        "data": {
            "deployment_readiness": {"status": "ready", "report_dir": "/reports"},
            "watcher": {
                "wakeup_status": "operator_packet_needs_review",
                "operator_status": "operator_review",
                "status_packet_status": "ok",
                "blockers": [
                    "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
                ],
            },
            "post_signal_resume": {
                "can_continue_steps_5_8": False,
                "current_gate": "waiting_for_fresh_strategy_signal",
            },
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effect_flags": [],
            },
        }
    }


def test_pilot_status_defaults_to_mpg_and_waits_for_market_without_hiding_progressive_gaps():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        watcher_status=_watcher_waiting(),
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_market"
    assert packet["pilot_selection"]["strategy_group_id"] == "MPG-001"
    assert packet["pilot_selection"]["selected_universe"] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert packet["pilot_selection"]["risk_profile"] == {
        "tier": "tiny",
        "leverage": "1",
        "max_active_position": 1,
        "max_symbols": 3,
        "max_notional_per_action_usdt": "8",
    }
    assert packet["owner_state"]["blocker_class"] == "waiting_for_market"
    assert packet["owner_state"]["blocked_reason"] == "no_fresh_strategy_signal"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "continue_watcher_observation_and_notify_on_material_change"
    )
    assert (
        "candidate_specific_protection_budget_next_gate_pending_until_fresh_signal"
        in packet["why_not_executable"]
    )
    assert packet["control_board"]["strategy_group_row"]["next_action"] == (
        "continue_watcher_observation_and_notify_on_material_change"
    )
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["creates_candidate"] is False
    assert packet["safety_invariants"]["mutates_pg"] is False


def test_pilot_status_switches_to_teq_only_when_engineering_readiness_is_better():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(mpg_observe_ready=False, teq_blockers=[]),
        watcher_status=_watcher_waiting(),
        generated_at_ms=1,
    )

    assert packet["pilot_selection"]["strategy_group_id"] == "TEQ-001"
    assert packet["pilot_selection"]["selection_reason"] == (
        "fallback_teq_has_better_engineering_readiness"
    )


def test_pilot_status_blocks_active_position_resolution_before_signal_resume():
    readiness = _readiness()
    readiness["readiness"][0]["candidate_fact_checks"][1]["status"] = "active_position_present"
    readiness["readiness"][0]["blockers"] = ["active_position:active_position_present"]

    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=readiness,
        watcher_status=_watcher_waiting(),
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_active_position_resolution"
    assert packet["owner_state"]["blocker_class"] == "active_position_resolution"
    assert packet["owner_state"]["blocked_at"] == "live_account_facts"
    assert packet["control_board"]["runtime_row"]["active_position"] == "active_position_present"


def test_pilot_status_hard_stops_on_forbidden_watcher_effect():
    watcher = _watcher_waiting()
    watcher["data"]["safety_invariants"]["exchange_write_called"] = True

    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        watcher_status=watcher,
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_hard_safety_stop"
    assert packet["owner_state"]["blocker_class"] == "hard_safety_stop"
    assert packet["owner_state"]["blocked_at"] == "watcher_safety_invariants"


def test_pilot_status_accepts_raw_post_signal_resume_pack():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        watcher_status={
            "scope": "runtime_signal_watcher_post_signal_resume_pack",
            "status": "operator_packet_needs_review",
            "can_continue_steps_5_8": False,
            "current_wakeup_status": "operator_packet_needs_review",
            "current_operator_status": "operator_review",
            "blockers": [
                "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "safety_invariants": {
                "exchange_write_called": False,
                "order_created": False,
                "order_lifecycle_called": False,
                "execution_intent_created": False,
                "runtime_budget_mutated": False,
                "withdrawal_or_transfer_created": False,
                "forbidden_effect_flags": [],
            },
        },
        generated_at_ms=1,
    )

    assert packet["status"] == "waiting_for_market"
    assert packet["owner_state"]["blocker_class"] == "waiting_for_market"
