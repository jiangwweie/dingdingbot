from __future__ import annotations

from scripts import runtime_dry_run_audit_chain as audit_chain
from scripts import runtime_execution_chain_closure_status as closure_status


def test_closure_status_marks_non_market_chain_ready_but_not_real_submit_ready(tmp_path):
    audit_packet = audit_chain.build_audit_chain(tmp_path / "audit")

    packet = closure_status.build_status_packet(audit_packet=audit_packet)

    assert packet["scope"] == "runtime_execution_chain_closure_status"
    assert packet["status"] == "non_market_execution_chain_ready"
    assert packet["dry_run_chain"]["status"] == "passed"
    assert packet["dry_run_chain"]["scenario_count"] == 14
    assert packet["dry_run_chain"]["required_checks_passed"] is True
    assert packet["dry_run_chain"]["dangerous_effects_absent"] is True
    assert packet["real_execution"]["status"] == "waiting_for_live_action_time_proof"
    assert packet["real_execution"]["real_order_allowed"] is False
    assert packet["real_execution"]["disabled_smoke_is_real_execution_proof"] is False
    assert packet["real_execution"]["missing_live_proofs"] == [
        "live_fresh_signal",
        "same_run_action_time_finalgate_pass",
        "official_operation_layer_real_gateway_action",
        "post_submit_finalize_reconciliation_budget_settlement",
    ]
    assert packet["next_safe_actions"] == [
        "keep_watcher_running",
        "run_dry_run_audit_chain_after_runtime_changes",
        "on_fresh_signal_run_same_run_finalgate_then_official_operation_layer",
    ]
    assert packet["safety_invariants"] == {
        "calls_tokyo_api": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "withdrawal_or_transfer_created": False,
        "modifies_secret_or_credentials": False,
        "modifies_live_profile": False,
        "modifies_order_sizing_defaults": False,
        "finalgate_bypassed": False,
        "operation_layer_bypassed": False,
    }


def test_closure_status_blocks_when_required_dry_run_check_fails(tmp_path):
    audit_packet = audit_chain.build_audit_chain(tmp_path / "audit")
    audit_packet["required_checks"]["fresh_signal_fast_auto_chain_checked"] = False

    packet = closure_status.build_status_packet(audit_packet=audit_packet)

    assert packet["status"] == "non_market_execution_chain_blocked"
    assert packet["dry_run_chain"]["status"] == "blocked"
    assert packet["dry_run_chain"]["failed_required_checks"] == [
        "fresh_signal_fast_auto_chain_checked"
    ]
    assert packet["real_execution"]["real_order_allowed"] is False
    assert packet["next_safe_actions"] == [
        "repair_failed_dry_run_checks_before_waiting_for_market",
        "do_not_call_real_operation_layer",
    ]
