from __future__ import annotations

from scripts import build_runtime_account_safe_facts as module


def _live_facts() -> dict:
    return {
        "status": "ready",
        "account": {
            "available_balance_present": True,
            "available_balance_positive": True,
            "exchange_account_trade_permission": True,
        },
        "active_position": {"status": "no_active_position"},
        "open_orders": {"status": "no_open_orders"},
        "budget": {"status": "available_for_candidate_specific_reservation"},
        "exchange_rules": {"status": "ready"},
        "next_attempt_gate": {"status": "ready_for_strategy_signal"},
        "protection": {"status": "ready_for_candidate_specific_plan"},
        "safety_invariants": {
            "signed_get_only": True,
            "exchange_write_called": False,
            "order_created": False,
        },
    }


def test_runtime_account_safe_facts_ready_from_live_facts():
    artifact = module.build_runtime_account_safe_facts(
        live_facts=_live_facts(),
        generated_at_utc="2026-07-03T00:00:00+00:00",
    )

    assert artifact["status"] == "runtime_account_safe_facts_ready"
    assert artifact["checks"]["account_safe_facts_ready"] is True
    assert artifact["checks"]["private_action_time_facts_ready"] is True
    assert artifact["checks"]["active_position_or_open_order_clear"] is True
    assert artifact["checks"]["action_time_available_balance"] is True
    assert artifact["blockers"] == []
    assert artifact["safety_invariants"]["calls_finalgate"] is False
    assert artifact["safety_invariants"]["calls_operation_layer"] is False
    assert artifact["safety_invariants"]["calls_exchange_write"] is False
    assert artifact["safety_invariants"]["order_created"] is False


def test_runtime_account_safe_facts_blocks_open_position():
    live_facts = _live_facts()
    live_facts["active_position"] = {"status": "active_position_present"}

    artifact = module.build_runtime_account_safe_facts(
        live_facts=live_facts,
        generated_at_utc="2026-07-03T00:00:00+00:00",
    )

    assert artifact["status"] == "runtime_account_safe_facts_blocked"
    assert artifact["checks"]["account_safe_facts_ready"] is False
    assert "active_position_clear" in artifact["blockers"]
