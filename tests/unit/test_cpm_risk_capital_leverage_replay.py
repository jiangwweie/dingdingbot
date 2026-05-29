from __future__ import annotations

from decimal import Decimal

from src.domain.cpm_replay_cost_model import cpm_frozen_cost_model
from src.domain.cpm_risk_capital_leverage_replay import (
    CPMRiskCapitalReplayMetrics,
    equity_adverse_proxy_pct,
    equity_return_pct,
    summarize_risk_capital_replay,
)


def test_leverage_formula_applies_cost_before_leverage() -> None:
    result = equity_return_pct(
        gross_underlying_return_pct=Decimal("1.00"),
        cost_model=cpm_frozen_cost_model(),
        leverage_multiple=Decimal("3"),
    )

    assert result == Decimal("2.1600")


def test_adverse_proxy_is_scaled_by_leverage_as_loss_magnitude() -> None:
    assert (
        equity_adverse_proxy_pct(
            underlying_adverse_proxy_pct=Decimal("-1.25"),
            leverage_multiple=Decimal("5"),
        )
        == Decimal("6.25")
    )


def test_risk_capital_stop_estimates_are_computed_from_average_loss() -> None:
    metrics = summarize_risk_capital_replay(
        gross_underlying_returns_pct=[
            Decimal("1.00"),
            Decimal("-0.72"),
            Decimal("-0.22"),
            Decimal("2.00"),
        ],
        underlying_adverse_proxies_pct=[
            Decimal("-0.50"),
            Decimal("-1.00"),
            Decimal("-0.80"),
            Decimal("-0.30"),
        ],
        cost_model=cpm_frozen_cost_model(),
        leverage_multiple=Decimal("2"),
    )

    assert metrics.trades == 4
    assert metrics.average_loss_pct == Decimal("-1.5000")
    assert metrics.estimated_trades_to_soft_stop == Decimal("30") / Decimal("1.5000")
    assert metrics.estimated_trades_to_hard_stop == Decimal("50") / Decimal("1.5000")
    assert metrics.estimated_trades_to_ruin == Decimal("100") / Decimal("1.5000")


def test_right_tail_threshold_counts_are_computed() -> None:
    metrics = summarize_risk_capital_replay(
        gross_underlying_returns_pct=[
            Decimal("12.00"),
            Decimal("6.00"),
            Decimal("3.00"),
            Decimal("-2.00"),
            Decimal("-6.00"),
        ],
        underlying_adverse_proxies_pct=[
            Decimal("-1"),
            Decimal("-1"),
            Decimal("-1"),
            Decimal("-2"),
            Decimal("-3"),
        ],
        cost_model=cpm_frozen_cost_model(),
        leverage_multiple=Decimal("2"),
    )

    assert metrics.gain_threshold_counts["5pct"] == 3
    assert metrics.gain_threshold_counts["10pct"] == 2
    assert metrics.gain_threshold_counts["20pct"] == 1
    assert metrics.loss_threshold_counts["5pct"] == 1
    assert metrics.loss_threshold_counts["10pct"] == 1
    assert metrics.right_tail_contribution_pct > Decimal("0")


def test_no_execution_or_order_dependencies_are_exposed() -> None:
    metrics = summarize_risk_capital_replay(
        gross_underlying_returns_pct=[Decimal("1.00"), Decimal("-1.00")],
        underlying_adverse_proxies_pct=[Decimal("-0.50"), Decimal("-1.50")],
        cost_model=cpm_frozen_cost_model(),
        leverage_multiple=Decimal("3"),
    )
    payload = metrics.model_dump(mode="python")

    for forbidden in [
        "quantity",
        "notional",
        "leverage",
        "order_type",
        "client_order_id",
        "order_id",
        "venue",
        "reduce_only",
        "router_target",
        "cancel_instruction",
        "close_instruction",
        "flatten_instruction",
    ]:
        assert forbidden not in payload

    assert not hasattr(metrics, "create_order")
    assert not hasattr(metrics, "create_execution_intent")
    assert not hasattr(metrics, "write_trial_trade_intent")


def test_forbidden_execution_field_rejected_by_metric_model() -> None:
    try:
        CPMRiskCapitalReplayMetrics(
            trades=0,
            leverage_multiple=Decimal("2"),
            order_type="MARKET",
        )
    except Exception as exc:
        assert "Extra inputs are not permitted" in str(exc) or "forbidden" in str(exc)
    else:
        raise AssertionError("forbidden execution field was accepted")
