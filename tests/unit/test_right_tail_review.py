from __future__ import annotations

from decimal import Decimal

from src.domain.right_tail_review import (
    RightTailTradeClassification,
    RightTailTradePathFacts,
    StopEffectiveness,
    summarize_right_tail_reviews,
)


def test_right_tail_review_classifies_tail_win_and_coverage() -> None:
    summary = summarize_right_tail_reviews(
        [
            RightTailTradePathFacts(
                trade_id="win-1",
                symbol="BNB/USDT:USDT",
                side="long",
                strategy_family_id="CPM-001",
                entry_price=Decimal("100"),
                exit_price=Decimal("115"),
                mfe_price=Decimal("118"),
                mae_price=Decimal("98"),
                realized_pnl=Decimal("15"),
                max_loss_budget=Decimal("3"),
                opened_at_ms=1000,
                closed_at_ms=5000,
                runner_preserved=True,
            ),
            RightTailTradePathFacts(
                trade_id="loss-1",
                symbol="BNB/USDT:USDT",
                side="long",
                strategy_family_id="CPM-001",
                entry_price=Decimal("100"),
                exit_price=Decimal("98"),
                mfe_price=Decimal("101"),
                mae_price=Decimal("97"),
                realized_pnl=Decimal("-2"),
                max_loss_budget=Decimal("3"),
                opened_at_ms=6000,
                closed_at_ms=8000,
                runner_preserved=False,
            ),
        ]
    )

    assert summary.status == "reviewed"
    assert summary.trade_count == 2
    assert summary.right_tail_win_count == 1
    assert summary.small_loss_count == 1
    assert summary.max_r_multiple == Decimal("5.0000")
    assert summary.largest_tail_win == Decimal("15")
    assert summary.average_small_loss == Decimal("2.0000")
    assert summary.single_tail_win_covers_small_losses == Decimal("7.5000")
    assert summary.payoff_asymmetry_present is True

    win = summary.trade_reviews[0]
    assert win.classification == RightTailTradeClassification.RIGHT_TAIL_WIN
    assert win.mfe_pct == Decimal("18.0000")
    assert win.mae_pct == Decimal("-2.0000")
    assert win.winner_hold_time_ms == 4000
    assert win.stop_effectiveness == StopEffectiveness.NOT_APPLICABLE_WIN
    assert win.places_order is False
    assert win.creates_execution_intent is False
    assert win.calls_exchange is False
    assert win.mutates_runtime_budget is False
    assert win.mutates_strategy_pnl is False
    assert win.creates_withdrawal_instruction is False


def test_right_tail_review_supports_short_side_direction() -> None:
    summary = summarize_right_tail_reviews(
        [
            RightTailTradePathFacts(
                trade_id="short-win-1",
                symbol="BNB/USDT:USDT",
                side="short",
                strategy_family_id="BRF-001",
                entry_price=Decimal("100"),
                exit_price=Decimal("90"),
                mfe_price=Decimal("88"),
                mae_price=Decimal("103"),
                realized_pnl=Decimal("10"),
                max_loss_budget=Decimal("3"),
                opened_at_ms=1000,
                closed_at_ms=9000,
                runner_preserved=True,
            )
        ]
    )

    trade = summary.trade_reviews[0]
    assert trade.classification == RightTailTradeClassification.RIGHT_TAIL_WIN
    assert trade.mfe_pct == Decimal("12.0000")
    assert trade.mae_pct == Decimal("-3.0000")
    assert trade.realized_move_pct == Decimal("10.0000")


def test_right_tail_review_requires_explicit_trade_path_facts() -> None:
    summary = summarize_right_tail_reviews(
        [
            RightTailTradePathFacts(
                trade_id="missing-1",
                symbol="BNB/USDT:USDT",
                side="long",
            )
        ]
    )

    assert summary.status == "review_inputs_required"
    assert summary.reviewed_trade_count == 0
    assert summary.missing_input_trade_count == 1
    assert set(summary.required_inputs) == {
        "entry_price",
        "exit_price",
        "mfe_price",
        "mae_price",
        "realized_pnl",
        "opened_at_ms",
        "closed_at_ms",
        "max_loss_budget_or_protection_stop_price",
    }


def test_right_tail_review_never_exposes_execution_or_capital_actions() -> None:
    summary = summarize_right_tail_reviews([])
    payload = summary.model_dump(mode="python")

    assert payload["no_action_guarantee"]["places_order"] is False
    assert payload["no_action_guarantee"]["creates_execution_intent"] is False
    assert payload["no_action_guarantee"]["calls_exchange"] is False
    assert payload["no_action_guarantee"]["mutates_runtime_budget"] is False
    assert payload["no_action_guarantee"]["mutates_strategy_pnl"] is False
    assert payload["no_action_guarantee"]["creates_withdrawal_instruction"] is False
    assert not hasattr(summary, "create_order")
    assert not hasattr(summary, "create_execution_intent")
