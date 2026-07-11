from __future__ import annotations

import inspect
from pathlib import Path

from src.application.action_time import full_chain_simulation_harness as harness
from tests.unit.test_tokyo_runtime_server_monitor import _load_module


def test_producer_input_does_not_insert_downstream_ready_authority_rows():
    source = inspect.getsource(harness._insert_constructed_raw_input)

    assert "INSERT INTO" not in source
    assert "_insert_fact(" not in source
    assert "_insert_signal(" not in source
    assert "_insert_readiness(" not in source
    assert "DELETE FROM brc_pretrade_readiness_rows" not in source
    assert "write_pretrade_public_fact_snapshots" in source
    assert "write_account_safe_fact_snapshots" in source
    assert "write_runtime_signal_summaries_to_pg" in source


def test_success_harness_uses_production_projection_not_fixture_closure():
    source = inspect.getsource(harness.run_ticket_bound_full_chain_simulation)

    assert "_record_simulated_closure_evidence_events" not in source
    assert "materialize_ticket_bound_lifecycle_closure" not in source
    assert "execute_ticket_bound_runner_mutation_command" not in source
    assert "run_ticket_bound_lifecycle_maintenance_scheduler" in source


def test_legacy_lifecycle_modules_have_no_direct_gateway_mutation_call():
    root = Path(__file__).resolve().parents[2]
    for relative in (
        "src/application/action_time/runner_mutation_executor.py",
        "src/application/action_time/protection_recovery_command.py",
        "src/application/action_time/orphan_protection_cleanup_command.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "gateway.place_order(" not in source
        assert "gateway.cancel_order(" not in source


def test_unprotected_real_position_preempts_new_natural_signal_acceptance():
    monitor = _load_module()
    now_ms = 1_770_000_000_000
    event = monitor._recent_pg_chain_event(
        {
            "read_now_ms": now_ms,
            "ticket_bound_order_lifecycle_runs": [
                {
                    "lifecycle_run_id": "lifecycle:unsafe",
                    "strategy_group_id": "SOR-001",
                    "symbol": "BTCUSDT",
                    "side": "short",
                    "status": "protection_missing",
                    "updated_at_ms": now_ms - 1,
                }
            ],
            "ticket_bound_exchange_commands": [],
            "ticket_bound_protected_submit_attempts": [],
            "action_time_tickets": [],
            "action_time_lane_inputs": [],
            "promotion_candidates": [],
            "live_signal_events": [
                {
                    "signal_event_id": "signal:new-natural-identity",
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                    "source_kind": "live_market",
                    "status": "facts_validated",
                    "freshness_state": "fresh",
                }
            ],
            "runtime_process_outcomes": [],
        }
    )

    assert event["event_type"] == "submitted_position_unprotected"
    assert event["blocker_class"] == "submitted_position_unprotected"


def test_different_natural_signal_identity_is_exact_acceptance_event():
    monitor = _load_module()
    signal_id = "signal:different-natural-identity"
    event = monitor._recent_pg_chain_event(
        {
            "read_now_ms": 1_770_000_000_000,
            "ticket_bound_order_lifecycle_runs": [],
            "ticket_bound_exchange_commands": [],
            "ticket_bound_protected_submit_attempts": [],
            "action_time_tickets": [],
            "action_time_lane_inputs": [],
            "promotion_candidates": [],
            "live_signal_events": [
                {
                    "signal_event_id": signal_id,
                    "strategy_group_id": "CPM-RO-001",
                    "symbol": "ETHUSDT",
                    "side": "long",
                    "source_kind": "live_market",
                    "status": "facts_validated",
                    "freshness_state": "fresh",
                }
            ],
            "runtime_process_outcomes": [],
        }
    )

    assert event["event_type"] == "fresh_signal"
    assert event["blocker_class"] == "fresh_signal"
    assert event["reasons"] == ["fresh_signal_detected", signal_id]
