from __future__ import annotations

from decimal import Decimal

from src.domain.cpm_replay_cost_model import (
    CPMReplayCostModel,
    adjust_returns_pct,
    cpm_frozen_cost_model,
    stress_40bps_round_trip_model,
    summarize_replay_returns,
    zero_cost_model,
)


def test_zero_cost_leaves_return_unchanged() -> None:
    model = zero_cost_model()

    assert model.round_trip_drag_pct == Decimal("0")
    assert model.adjust_return_pct(Decimal("0.6067")) == Decimal("0.6067")


def test_cpm_frozen_cost_model_deducts_28bps() -> None:
    model = cpm_frozen_cost_model()

    assert model.round_trip_drag_pct == Decimal("0.2800")
    assert model.adjust_return_pct(Decimal("0.6067")) == Decimal("0.3267")


def test_stress_model_deducts_40bps() -> None:
    model = stress_40bps_round_trip_model()

    assert model.round_trip_drag_pct == Decimal("0.40")
    assert model.adjust_return_pct(Decimal("0.6067")) == Decimal("0.2067")


def test_replay_adjustment_updates_win_rate_and_metrics() -> None:
    gross_returns = [
        Decimal("0.50"),
        Decimal("0.20"),
        Decimal("-0.10"),
        Decimal("1.00"),
    ]
    net_returns = adjust_returns_pct(gross_returns, cpm_frozen_cost_model())
    metrics = summarize_replay_returns(net_returns)

    assert net_returns == [
        Decimal("0.2200"),
        Decimal("-0.0800"),
        Decimal("-0.3800"),
        Decimal("0.7200"),
    ]
    assert metrics.trades == 4
    assert metrics.win_rate == Decimal("0.5")
    assert metrics.mean_return_pct == Decimal("0.1200")
    assert metrics.cumulative_return_proxy_pct == Decimal("0.4800")


def test_cost_model_requires_no_order_or_execution_fields() -> None:
    model = cpm_frozen_cost_model()
    payload = model.model_dump(mode="python")

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

    assert not hasattr(model, "create_order")
    assert not hasattr(model, "create_execution_intent")
    assert not hasattr(model, "write_trial_trade_intent")


def test_forbidden_execution_fields_are_rejected() -> None:
    try:
        CPMReplayCostModel(
            model_id="zero_cost",
            fee_rate=Decimal("0"),
            entry_slippage_rate=Decimal("0"),
            exit_slippage_rate=Decimal("0"),
            notes="bad",
            order_type="MARKET",
        )
    except Exception as exc:
        assert "Extra inputs are not permitted" in str(exc) or "forbidden" in str(exc)
    else:
        raise AssertionError("forbidden execution field was accepted")
