from decimal import Decimal

from src.domain.ticket_exit_policy_adoption import (
    TicketExitPolicyAdoptionEligibilitySnapshot,
    canonical_eligibility_hash,
    evaluate_ticket_exit_policy_adoption_snapshot,
)


def _snapshot(**overrides):
    values = {
        "ticket_id": "ticket:avax",
        "ticket_created_at_ms": 2000,
        "ticket_exit_policy_id": "legacy_unbound",
        "ticket_exit_policy_version": "legacy_unbound",
        "ticket_exit_policy_hash": "a" * 64,
        "ticket_status": "submitted",
        "lifecycle_state": "position_protected",
        "ticket_strategy_group_id": "SOR-001",
        "ticket_strategy_version": "sgv:SOR-001:v2",
        "ticket_event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
        "ticket_event_spec_version": "v2",
        "ticket_side": "long",
        "to_exit_policy_id": "exit-policy:SOR-001:SOR-LONG:right-tail-v1",
        "to_exit_policy_version": "2026-07-15-v1",
        "to_exit_policy_hash": "b" * 64,
        "policy_status": "current",
        "policy_approved_at_ms": 1000,
        "policy_strategy_group_id": "SOR-001",
        "policy_strategy_version": "sgv:SOR-001:v2",
        "policy_event_spec_id": "event_spec:SOR-001:SOR-LONG:v2",
        "policy_event_spec_version": "v2",
        "policy_side": "long",
        "owner_authorization_ref": "owner:approved",
        "owner_authorization_ticket_id": None,
        "runtime_head": "c" * 40,
        "migration_revision": 125,
        "account_id": "owner-subaccount-runtime-v0",
        "exchange_id": "binance_usdm",
        "exchange_instrument_id": "binance_usdm:AVAX/USDT:USDT",
        "position_mode": "one_way",
        "position_side": "BOTH",
        "pg_position_qty": Decimal("65"),
        "exchange_position_qty": Decimal("65"),
        "entry_avg_fill_price": Decimal("6.658784615384615385"),
        "exit_protection_set_id": "protection:avax",
        "protection_state": "complete_reconciled",
        "sl_order_id": "4000001769200556",
        "sl_order_type": "STOP_MARKET",
        "sl_qty": Decimal("65"),
        "sl_trigger_price": Decimal("6.449"),
        "sl_reduce_only": True,
        "sl_side": "sell",
        "sl_position_side": "BOTH",
        "tp1_order_id": "39583407650",
        "tp1_order_type": "LIMIT",
        "tp1_qty": Decimal("32"),
        "tp1_price": Decimal("6.875"),
        "tp1_filled_qty": Decimal("0"),
        "tp1_reduce_only": True,
        "tp1_market_fallback_allowed": False,
        "tp1_side": "sell",
        "tp1_position_side": "BOTH",
        "unsafe_command_count": 0,
        "evaluated_at_ms": 3000,
    }
    values.update(overrides)
    return TicketExitPolicyAdoptionEligibilitySnapshot(**values)


def test_exact_avax_shaped_snapshot_is_eligible_and_hash_is_canonical():
    first = _snapshot()
    second = _snapshot()

    result = evaluate_ticket_exit_policy_adoption_snapshot(first)

    assert result.status == "eligible"
    assert result.blockers == ()
    assert result.eligibility_hash == canonical_eligibility_hash(second)
    assert len(result.eligibility_hash) == 64


def test_identity_approval_quantity_protection_and_command_mismatches_block():
    cases = {
        "strategy": (
            {"policy_strategy_group_id": "OTHER"},
            "adoption_strategy_group_mismatch",
        ),
        "approval": (
            {"policy_approved_at_ms": 2500},
            "adoption_policy_approved_after_ticket",
        ),
        "position": (
            {"exchange_position_qty": Decimal("64")},
            "adoption_position_quantity_mismatch",
        ),
        "protection": (
            {"protection_state": "missing"},
            "adoption_protection_not_reconciled",
        ),
        "command": (
            {"unsafe_command_count": 1},
            "adoption_unsafe_command_pending",
        ),
    }

    for overrides, expected in cases.values():
        result = evaluate_ticket_exit_policy_adoption_snapshot(
            _snapshot(**overrides)
        )
        assert result.status == "blocked"
        assert expected in result.blockers


def test_ticket_specific_owner_authorization_allows_later_policy_approval():
    result = evaluate_ticket_exit_policy_adoption_snapshot(
        _snapshot(
            policy_approved_at_ms=2500,
            owner_authorization_ticket_id="ticket:avax",
        )
    )

    assert result.status == "eligible"


def test_exit_orders_must_be_reduce_only_close_side_and_tp1_limit_only():
    result = evaluate_ticket_exit_policy_adoption_snapshot(
        _snapshot(
            sl_reduce_only=False,
            tp1_order_type="MARKET",
            tp1_market_fallback_allowed=True,
            tp1_side="buy",
        )
    )

    assert result.status == "blocked"
    assert "adoption_sl_not_reduce_only" in result.blockers
    assert "adoption_tp1_not_limit" in result.blockers
    assert "adoption_tp1_market_fallback_present" in result.blockers
    assert "adoption_tp1_close_side_mismatch" in result.blockers
