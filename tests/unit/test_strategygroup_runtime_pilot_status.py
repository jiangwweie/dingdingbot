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
                "watcher_scope": {
                    "business_signal_validity": "15-30m",
                    "candidate_packet_freshness_seconds": 120,
                },
                "picker": {"rank": 1, "default_mode": "armed_observation"},
            },
            {
                "strategy_group_id": "TEQ-001",
                "name": "Tokenized Equity Momentum",
                "supported_symbols": ["NVDAUSDT", "TSLAUSDT"],
                "supported_sides": ["long"],
                "risk_defaults": {"max_notional_per_action_usdt": "8"},
                "watcher_scope": {
                    "business_signal_validity": "15-30m",
                    "candidate_packet_freshness_seconds": 120,
                },
                "picker": {"rank": 2, "default_mode": "armed_observation"},
            },
        ],
    }


def _readiness(
    *,
    mpg_observe_ready: bool = True,
    mpg_blockers: list[str] | None = None,
    teq_blockers: list[str] | None = None,
) -> dict:
    resolved_mpg_blockers = (
        ["protection:missing", "budget:missing", "next_attempt_gate:missing"]
        if mpg_blockers is None
        else mpg_blockers
    )
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
                "armed_candidate_prepare_ready": resolved_mpg_blockers == [],
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
                "blockers": resolved_mpg_blockers,
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
                "post_signal_auto_resume": {
                    "status": "waiting_for_market",
                    "blocked_at": "watcher_signal",
                    "blocked_reason": "no_fresh_strategy_signal",
                    "next_recover_condition": (
                        "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
                    ),
                    "automatic_recovery_action": "continue_watcher_observation",
                    "downgrade_mode": "observe_only",
                    "can_continue_without_owner_chat": True,
                    "requires_action_time_final_gate": True,
                    "requires_official_operation_layer": True,
                },
            },
            "post_signal_auto_resume": {
                "status": "waiting_for_market",
                "blocked_at": "watcher_signal",
                "blocked_reason": "no_fresh_strategy_signal",
                "next_recover_condition": (
                    "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
                ),
                "automatic_recovery_action": "continue_watcher_observation",
                "downgrade_mode": "observe_only",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
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


def _watcher_ready() -> dict:
    watcher = _watcher_waiting()
    watcher["data"]["watcher"]["wakeup_status"] = (
        "runtime_signal_ready_for_non_executing_prepare"
    )
    watcher["data"]["watcher"]["blockers"] = []
    watcher["data"]["post_signal_resume"]["can_continue_steps_5_8"] = True
    watcher["data"]["post_signal_resume"]["current_gate"] = (
        "fresh_signal_or_prepared_shadow_ready"
    )
    ready_auto_resume = {
        "status": "ready_for_non_executing_prepare",
        "blocked_at": "non_executing_prepare_records",
        "blocked_reason": "fresh_strategy_signal_ready",
        "next_recover_condition": (
            "shadow_candidate_runtime_grant_authorization_evidence_exists"
        ),
        "automatic_recovery_action": (
            "wait_for_prepare_records_then_rebuild_final_gate_status"
        ),
        "downgrade_mode": "armed_observation_no_real_submit",
        "can_continue_without_owner_chat": True,
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
    }
    watcher["data"]["post_signal_resume"]["post_signal_auto_resume"] = (
        ready_auto_resume
    )
    watcher["data"]["post_signal_auto_resume"] = ready_auto_resume
    return watcher


def _watcher_prepared() -> dict:
    watcher = _watcher_ready()
    prepared_auto_resume = {
        "status": "ready_for_action_time_final_gate",
        "blocked_at": "FinalGate",
        "blocked_reason": "action_time_final_gate_not_run_yet",
        "next_recover_condition": (
            "official_final_gate_preflight_passes_with_current_facts"
        ),
        "automatic_recovery_action": "run_official_action_time_final_gate_preflight",
        "downgrade_mode": "no_real_submit_until_final_gate_pass",
        "can_continue_without_owner_chat": True,
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
        "signal_input_json": "/reports/runtime-mpg/signal-input.json",
        "shadow_candidate_id": "shadow-candidate-1",
        "prepared_authorization_id": "auth-ready-1",
    }
    watcher["data"]["post_signal_resume"]["post_signal_auto_resume"] = (
        prepared_auto_resume
    )
    watcher["data"]["post_signal_auto_resume"] = prepared_auto_resume
    watcher["data"]["post_signal_resume"]["prepared_evidence"] = {
        "signal_input_json": "/reports/runtime-mpg/signal-input.json",
        "shadow_candidate_id": "shadow-candidate-1",
        "prepared_authorization_id": "auth-ready-1",
        "ready_for_action_time_final_gate": True,
    }
    return watcher


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
    assert packet["runtime_bridge"] == {
        "status": "configured",
        "strategy_family_id": "MPG-001",
        "strategy_family_version_id": "MPG-001-v0",
        "semantics_binding_found": True,
        "evaluator_route_configured": True,
        "candidate_mode": "shadow_order_candidate_allowed",
        "runtime_confirmation_mode": "runtime_bounded_auto_attempts",
        "blockers": [],
        "automatic_recovery_action": "continue_to_runtime_scope_alignment",
        "next_recover_condition": (
            "strategy_semantics_binding_and_evaluator_route_are_configured"
        ),
        "non_executing": True,
    }
    assert packet["owner_state"]["blocked_reason"] == "no_fresh_strategy_signal"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "continue_watcher_observation"
    )
    assert packet["post_signal_auto_resume"]["can_continue_without_owner_chat"] is True
    assert packet["action_time_resume"]["status"] == "waiting_for_market"
    assert packet["action_time_resume"]["next_step"] == "continue_watcher_observation"
    assert packet["action_time_resume"]["allowed_auto_actions"] == [
        "continue_watcher_observation"
    ]
    assert packet["action_time_resume"]["places_order"] is False
    assert packet["dual_freshness"]["strategy_signal"] == {
        "status": "missing",
        "freshness_window": "15-30m",
        "candidate_packet_freshness_seconds": 120,
        "source": "runtime_signal_watcher",
        "current_gate": "waiting_for_fresh_strategy_signal",
        "blockers": [
            "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
        ],
    }
    assert packet["dual_freshness"]["action_time_facts"]["status"] == (
        "not_reached_waiting_for_signal"
    )
    strategy_signal_gate = next(
        item for item in packet["gate_failure_ledger"]
        if item["gate"] == "strategy_signal"
    )
    required_facts_gate = next(
        item for item in packet["gate_failure_ledger"]
        if item["gate"] == "RequiredFacts"
    )
    assert strategy_signal_gate["status"] == "waiting"
    assert strategy_signal_gate["blocker_class"] == "waiting_for_market"
    assert strategy_signal_gate["blocked_reason"] == "no_fresh_strategy_signal"
    assert required_facts_gate["status"] == "progressive_pending"
    assert required_facts_gate["automatic_recovery_action"] == (
        "wait_for_fresh_signal_before_candidate_specific_fact_materialization"
    )
    assert required_facts_gate["blockers"] == [
        "protection:missing",
        "budget:missing",
        "next_attempt_gate:missing",
    ]
    assert (
        "candidate_specific_protection_budget_next_gate_pending_until_fresh_signal"
        in packet["why_not_executable"]
    )
    assert packet["control_board"]["strategy_group_row"]["next_action"] == (
        "continue_watcher_observation"
    )
    assert packet["safety_invariants"]["places_order"] is False
    assert packet["safety_invariants"]["creates_candidate"] is False
    assert packet["safety_invariants"]["mutates_pg"] is False


def test_pilot_status_marks_fresh_signal_and_ready_facts_as_non_executing_prepare_only():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(mpg_blockers=[]),
        watcher_status=_watcher_ready(),
        generated_at_ms=1,
    )

    assert packet["status"] == "ready_for_non_executing_prepare"
    assert packet["dual_freshness"]["strategy_signal"]["status"] == "fresh"
    assert packet["dual_freshness"]["action_time_facts"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    final_gate = next(
        item for item in packet["gate_failure_ledger"] if item["gate"] == "FinalGate"
    )
    operation_layer = next(
        item for item in packet["gate_failure_ledger"]
        if item["gate"] == "Operation Layer"
    )
    assert final_gate["status"] == "not_reached"
    assert operation_layer["status"] == "not_reached"
    assert packet["control_board"]["candidate_row"]["candidate_state"] == (
        "ready_for_non_executing_prepare"
    )
    assert packet["safety_invariants"]["places_order"] is False


def test_pilot_status_promotes_prepared_evidence_to_candidate_row_and_final_gate():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(mpg_blockers=[]),
        watcher_status=_watcher_prepared(),
        generated_at_ms=1,
    )

    assert packet["status"] == "ready_for_action_time_final_gate"
    assert packet["owner_state"]["blocked_at"] == "FinalGate"
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["candidate_evidence"] == {
        "signal_input_json": "/reports/runtime-mpg/signal-input.json",
        "shadow_candidate_id": "shadow-candidate-1",
        "prepared_authorization_id": "auth-ready-1",
        "ready_for_action_time_final_gate": True,
    }
    candidate = packet["control_board"]["candidate_row"]
    assert candidate["fresh_signal_id"] == "/reports/runtime-mpg/signal-input.json"
    assert candidate["signal_input_json"] == "/reports/runtime-mpg/signal-input.json"
    assert candidate["shadow_candidate_id"] == "shadow-candidate-1"
    assert candidate["prepared_authorization_id"] == "auth-ready-1"
    assert candidate["candidate_state"] == "prepared_authorization_ready"
    assert candidate["runtime_grant_status"] == "prepared_authorization_ready"
    assert candidate["authorization_evidence_status"] == (
        "fresh_authorization_evidence_ready"
    )
    assert candidate["final_gate_status"] == "ready_to_run"
    assert candidate["action_time_resume_status"] == (
        "ready_for_action_time_final_gate"
    )
    assert candidate["action_time_next_step"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["action_time_resume"]["status"] == (
        "ready_for_action_time_final_gate"
    )
    assert packet["action_time_resume"]["allowed_auto_actions"] == [
        "run_official_action_time_final_gate_preflight"
    ]
    assert "official_operation_layer_submit" in packet["action_time_resume"][
        "forbidden_auto_actions_until_final_gate_pass"
    ]
    assert packet["action_time_resume"]["requires_fresh_action_time_facts"] is True
    final_gate = next(
        item for item in packet["gate_failure_ledger"] if item["gate"] == "FinalGate"
    )
    assert final_gate["status"] == "ready_to_run"
    assert final_gate["automatic_recovery_action"] == (
        "run_official_action_time_final_gate_preflight"
    )
    assert packet["safety_invariants"]["places_order"] is False
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


def test_pilot_status_blocks_strategy_group_missing_runtime_bridge():
    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        watcher_status=_watcher_waiting(),
        selected_strategy_group_id="TEQ-001",
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_runtime_bridge_missing"
    assert packet["owner_state"]["blocker_class"] == "missing_fact"
    assert packet["owner_state"]["blocked_at"] == "runtime_bridge"
    assert packet["runtime_bridge"]["strategy_family_id"] == "TEQ-001"
    assert packet["runtime_bridge"]["strategy_family_version_id"] == "TEQ-001-v0"
    assert packet["runtime_bridge"]["semantics_binding_found"] is False
    assert packet["runtime_bridge"]["evaluator_route_configured"] is False
    assert packet["runtime_bridge"]["blockers"] == [
        "strategy_evaluator_not_configured",
        "strategy_semantics_binding_missing",
    ]
    runtime_bridge_gate = next(
        item for item in packet["gate_failure_ledger"]
        if item["gate"] == "runtime_bridge"
    )
    assert runtime_bridge_gate["status"] == "blocked"
    assert packet["control_board"]["runtime_row"]["runtime_bridge"] == "missing"


def test_pilot_status_blocks_when_watcher_scope_does_not_match_selected_pilot():
    watcher = _watcher_waiting()
    watcher["data"]["watcher"]["runtime_signal_summaries"] = [
        {
            "runtime_instance_id": "strategy-runtime-rbr-ada-short",
            "strategy_family_id": "RBR-001",
            "strategy_family_version_id": "RBR-001-v0",
            "symbol": "ADA/USDT:USDT",
            "side": "short",
            "status": "waiting_for_signal",
        },
        {
            "runtime_instance_id": "strategy-runtime-cpm-bnb-long",
            "strategy_family_id": "CPM-001",
            "strategy_family_version_id": "CPM-001-v0",
            "symbol": "BNB/USDT:USDT",
            "side": "long",
            "status": "waiting_for_signal",
        },
    ]

    packet = build_packet(
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        watcher_status=watcher,
        generated_at_ms=1,
    )

    assert packet["status"] == "blocked_runtime_scope_mismatch"
    assert packet["owner_state"]["blocker_class"] == "runtime_scope_mismatch"
    assert packet["owner_state"]["blocked_at"] == "runtime_signal_watcher_scope"
    assert packet["owner_state"]["blocked_reason"] == (
        "watcher_not_monitoring_selected_strategygroup_universe"
    )
    assert packet["owner_state"]["automatic_recovery_action"] == (
        "create_or_attach_selected_strategygroup_runtime_then_constrain_watcher_scope"
    )
    assert packet["watcher_scope_alignment"]["status"] == "mismatch"
    assert packet["watcher_scope_alignment"]["matched_runtime_signal_summary_count"] == 0
    assert packet["watcher_scope_alignment"]["out_of_scope_runtime_signal_summary_count"] == 2
    watcher_scope_gate = next(
        item for item in packet["gate_failure_ledger"]
        if item["gate"] == "watcher_scope"
    )
    assert watcher_scope_gate["status"] == "blocked"
    assert watcher_scope_gate["blocker_class"] == "runtime_scope_mismatch"
    assert "watcher_scope_not_bound_to_selected_pilot" in packet["why_not_executable"]
    assert packet["control_board"]["runtime_row"]["watcher_scope"] == "mismatch"


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
            "post_signal_auto_resume": {
                "status": "waiting_for_market",
                "blocked_at": "watcher_signal",
                "blocked_reason": "no_fresh_strategy_signal",
                "next_recover_condition": (
                    "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
                ),
                "automatic_recovery_action": "continue_watcher_observation",
                "downgrade_mode": "observe_only",
                "can_continue_without_owner_chat": True,
                "requires_action_time_final_gate": True,
                "requires_official_operation_layer": True,
            },
            "blockers": [
                "runtime-1:strategy_signal_not_ready_for_shadow_candidate_prepare"
            ],
            "runtime_signal_summaries": [
                {
                    "runtime_instance_id": "runtime-1",
                    "strategy_family_id": "MPG-001",
                    "strategy_family_version_id": "MPG-001-v0",
                    "symbol": "BTCUSDT",
                    "side": "long",
                    "status": "waiting_for_signal",
                }
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
    assert packet["post_signal_auto_resume"]["status"] == "waiting_for_market"
    assert packet["watcher_scope_alignment"]["status"] == "aligned"
    assert packet["control_board"]["runtime_row"]["watcher_scope"] == "aligned"
