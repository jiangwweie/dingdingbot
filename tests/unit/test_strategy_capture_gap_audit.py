from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "build_strategy_capture_gap_audit.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("build_strategy_capture_gap_audit", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_event_sample_contract_exposes_total_sampled_and_omitted_counts():
    module = _load_module()
    events = [
        {"strategy_group_id": "BRF-001", "event_time_ms": 100},
        {"strategy_group_id": "BRF-001", "event_time_ms": 200},
        {"strategy_group_id": "BTPC-001", "event_time_ms": 300},
    ]

    packet = module._event_sample_contract(events, sample_limit=2)

    assert packet["total_count"] == 3
    assert packet["sampled_count"] == 2
    assert packet["omitted_count"] == 1
    assert packet["sample_limit"] == 2
    assert packet["events"][0]["event_time_ms"] == 300
    by_group = {row["strategy_group_id"]: row for row in packet["by_strategy_group"]}
    assert by_group["BRF-001"]["total_count"] == 2
    assert by_group["BRF-001"]["sampled_count"] == 1
    assert by_group["BRF-001"]["omitted_count"] == 1


def test_forward_outcome_summary_splits_completed_pending_and_unavailable():
    module = _load_module()
    events = [
        {
            "forward_outcome": {
                "4h": {
                    "status": "completed",
                    "tradable_mfe_after_cost": True,
                },
                "12h": {"status": "pending"},
                "24h": {"status": "unavailable"},
            }
        },
        {
            "forward_outcome": {
                "4h": {
                    "status": "completed",
                    "tradable_mfe_after_cost": False,
                },
                "12h": {"status": "not_applicable_no_clear_side"},
            }
        },
    ]

    summary = module._forward_outcome_summary(events)

    assert summary["event_count"] == 2
    assert summary["by_window"]["4h"]["completed"] == 2
    assert summary["by_window"]["4h"]["tradable_mfe_after_cost_count"] == 1
    assert summary["by_window"]["12h"]["pending"] == 1
    assert summary["by_window"]["12h"]["not_applicable"] == 1
    assert summary["by_window"]["24h"]["unavailable"] == 1


def test_decision_rows_keep_identity_review_separate_from_tier_change():
    module = _load_module()
    strategy_rows = [
        {
            "strategy_group_id": "MI-001",
            "would_enter_count": 3,
            "high_priority_no_action_count": 0,
        },
        {
            "strategy_group_id": "CPM-RO-001",
            "would_enter_count": 2,
            "high_priority_no_action_count": 0,
        },
        {
            "strategy_group_id": "BRF-001",
            "would_enter_count": 1,
            "high_priority_no_action_count": 4,
        },
    ]

    rows = module._decision_rows(strategy_rows)
    by_group = {row["strategy_group_id"]: row for row in rows}

    assert by_group["MI-001"]["decision"] == "identity_review"
    assert by_group["CPM-RO-001"]["decision"] == "identity_review"
    assert by_group["BRF-001"]["decision"] == "promote_review"
    assert "no FinalGate" in by_group["MI-001"]["authority_boundary"]
    assert "tier change" in by_group["CPM-RO-001"]["authority_boundary"]


def test_owner_visibility_state_reports_review_needed_without_live_permission():
    module = _load_module()

    state = module._owner_visibility_state(
        local_monitor={"status": "waiting_for_market"},
        decisions=[
            {"strategy_group_id": "BRF-001", "decision": "promote_review"},
            {"strategy_group_id": "BTPC-001", "decision": "revise"},
        ],
        would_enter_events=[{"strategy_group_id": "BRF-001"}],
        high_priority_no_action=[],
    )

    assert state["p0_state"] == "waiting_for_market"
    assert state["p0_5_observation_state"] == "review_needed"
    assert state["observation_active"] is True
    assert state["review_needed_strategy_groups"] == ["BRF-001", "BTPC-001"]
    assert state["no_live_permission"] is True
    assert state["owner_intervention_required"] is False
