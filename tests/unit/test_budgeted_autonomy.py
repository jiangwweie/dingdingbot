from __future__ import annotations

from decimal import Decimal

from src.application.budgeted_autonomy import (
    BudgetedAutonomyAuthorization,
    BudgetedAutonomyCandidateInput,
    BudgetedAutonomyPositionEvidence,
    evaluate_budgeted_autonomy_loop,
)


def _authorization(**overrides):
    values = {
        "budget_authorization_id": "budget-auth-mr-eth-v0",
        "allowed_carriers": ["MR-001-live-readonly-v0"],
        "allowed_symbols": ["ETH/USDT:USDT"],
        "allowed_sides": ["long"],
        "max_notional_per_action": Decimal("20"),
        "daily_loss_cap": Decimal("2"),
        "max_active_positions": 1,
        "max_attempts": 1,
        "max_leverage": Decimal("1"),
        "review_required": "post_action_review_required",
        "protection_mode": "single_tp_plus_sl",
    }
    values.update(overrides)
    return BudgetedAutonomyAuthorization(**values)


def _candidate(**overrides):
    values = {
        "candidate_id": "generic-action:MR-001-live-readonly-v0",
        "family": "Mean reversion",
        "carrier_id": "MR-001-live-readonly-v0",
        "symbol": "ETH/USDT:USDT",
        "side": "long",
        "status": "valid_blocked_final_gate",
        "action_registry_supported": True,
        "proposal_role": "range_candidate",
        "quantity": Decimal("0.01"),
        "estimated_notional_usdt": Decimal("16.80"),
        "max_notional": Decimal("20"),
        "leverage": Decimal("1"),
        "max_attempts": 1,
        "protection_mode": "single_tp_plus_sl",
        "review_requirement": "post_action_review_required",
    }
    values.update(overrides)
    return BudgetedAutonomyCandidateInput(**values)


def test_protected_open_position_is_budgeted_loop_outcome_and_blocks_new_candidate():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[
            BudgetedAutonomyPositionEvidence(
                carrier_id="MR-001-live-readonly-v0",
                symbol="ETH/USDT:USDT",
                side="long",
                quantity=Decimal("0.014"),
                notional=Decimal("23.48"),
                unrealized_pnl=Decimal("-0.07"),
                entry_price=Decimal("1682.57"),
                exchange_position_present=True,
                pg_position_count=1,
                open_tp_count=1,
                open_sl_count=1,
                pg_open_order_count=2,
                retry_allowed=False,
                review_recorded=True,
                audit_recorded=True,
            )
        ],
        candidates=[_candidate()],
        review_ledger={"lifecycle_status": "protected_open_from_pg_orders"},
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "protected_open_review_pending"
    assert evaluation.active_loop is True
    assert evaluation.active_position_count == 1
    assert evaluation.selected_candidate is None
    assert evaluation.blocked_candidates[0].status == "blocked"
    assert evaluation.blocked_candidates[0].blockers[0].id == (
        "BUDGETED-AUTONOMY-ACTIVE-POSITION"
    )
    assert evaluation.retry_condition == (
        "Wait for TP/SL close evidence, then complete post-action review."
    )
    assert evaluation.action_allowed is False
    assert evaluation.backend_actionable is False
    assert evaluation.frontend_action_enabled is False
    assert evaluation.auto_execution_enabled is False
    assert evaluation.places_order is False
    assert evaluation.mutates_pg is False


def test_pg_exchange_mismatch_blocks_with_cleanup_retry_condition():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[
            BudgetedAutonomyPositionEvidence(
                carrier_id="MR-001-live-readonly-v0",
                symbol="ETH/USDT:USDT",
                side="long",
                quantity=Decimal("0.014"),
                exchange_position_present=False,
                exchange_verified_flat=True,
                pg_position_count=1,
                open_tp_count=1,
                open_sl_count=1,
                pg_open_order_count=2,
                retry_allowed=False,
                review_recorded=True,
                audit_recorded=True,
            )
        ],
        candidates=[_candidate()],
        review_ledger={"lifecycle_status": "protected_open_from_pg_orders"},
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "blocked_with_retry_condition"
    assert evaluation.active_loop is True
    assert evaluation.selected_candidate is None
    assert evaluation.blocked_candidates[0].blockers[0].id == (
        "BUDGETED-AUTONOMY-PG-EXCHANGE-MISMATCH"
    )
    assert evaluation.retry_condition == (
        "Run official reconciliation/review cleanup so PG position, orders, "
        "review ledger, and exchange evidence agree."
    )
    assert evaluation.action_allowed is False
    assert evaluation.places_order is False


def test_flat_candidate_is_selected_only_for_official_final_gate_retry():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[],
        candidates=[_candidate()],
        review_ledger={},
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "blocked_with_retry_condition"
    assert evaluation.active_loop is False
    assert evaluation.selected_candidate is not None
    assert evaluation.selected_candidate.status == "eligible_for_final_gate"
    assert evaluation.selected_candidate.action_allowed is False
    assert evaluation.retry_condition == (
        "Run official Owner authorization and server-side FinalGate for the exact selected scope."
    )


def test_scope_mismatch_and_non_catalog_candidate_block():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[],
        candidates=[
            _candidate(
                carrier_id="MR-001-BTC-live-readonly-v0",
                symbol="BTC/USDT:USDT",
                side="short",
                estimated_notional_usdt=Decimal("25"),
                max_notional=Decimal("25"),
                leverage=Decimal("2"),
                max_attempts=2,
                protection_mode=None,
                review_requirement=None,
                action_registry_supported=False,
            )
        ],
        review_ledger={},
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "blocked_with_retry_condition"
    assert evaluation.selected_candidate is None
    blocked = evaluation.blocked_candidates[0]
    blocker_ids = {item.id for item in blocked.blockers}
    assert "BUDGETED-AUTONOMY-CANDIDATE-NOT-REGISTERED" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-CARRIER" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-SYMBOL" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-SIDE" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-NOTIONAL" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-MAX-NOTIONAL" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-LEVERAGE" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-ATTEMPTS" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-PROTECTION" in blocker_ids
    assert "BUDGETED-AUTONOMY-SCOPE-REVIEW" in blocker_ids
    assert blocked.frontend_action_enabled is False
    assert blocked.places_order is False


def test_closed_reviewed_ledger_closes_loop_without_selecting_candidate():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[],
        candidates=[_candidate()],
        review_ledger={
            "lifecycle_status": "closed_from_pg_exit_order",
            "review_decision": {"status": "revise"},
        },
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "closed_reviewed"
    assert evaluation.active_loop is False
    assert evaluation.selected_candidate is None
    assert evaluation.blocked_candidates == []
    assert evaluation.action_allowed is False
    assert evaluation.auto_execution_enabled is False


def test_external_flat_reviewed_ledger_closes_loop_without_selecting_candidate():
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=_authorization(),
        positions=[],
        candidates=[_candidate()],
        review_ledger={
            "lifecycle_status": "closed_external_exchange_flat_unresolved",
            "review_decision": {"status": "revise"},
        },
        now_ms=1780496665000,
    )

    assert evaluation.outcome == "closed_reviewed"
    assert evaluation.active_loop is False
    assert evaluation.selected_candidate is None
    assert evaluation.blocked_candidates == []
    assert evaluation.action_allowed is False
    assert evaluation.auto_execution_enabled is False
