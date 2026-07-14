from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.exit_policy_replay import (
    ExitPolicyCandidate,
    ReplayBar,
    ReplayTrade,
    aggregate_replay_results,
    replay_trade,
)


def _candidate(**overrides) -> ExitPolicyCandidate:
    values = {
        "candidate_id": "candidate-1",
        "side": "long",
        "tp1_reward_multiple": Decimal("1"),
        "tp1_quantity_fraction": Decimal("0.5"),
        "tp1_execution_style": "limit_gtc",
        "tp1_fill_fraction": Decimal("1"),
        "entry_fee_rate": Decimal("0.0004"),
        "maker_fee_rate": Decimal("0.0002"),
        "taker_fee_rate": Decimal("0.0005"),
        "slippage_ticks": 2,
        "structure_window_bars": 3,
        "atr_buffer_multiple": Decimal("0.5"),
        "minimum_improvement_ticks": 2,
        "max_holding_bars": 12,
    }
    values.update(overrides)
    return ExitPolicyCandidate(**values)


def _bar(index: int, *, open_: str, high: str, low: str, close: str, **kwargs):
    return ReplayBar(
        close_time_ms=1_700_000_000_000 + index * 3_600_000,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        atr=Decimal(kwargs.pop("atr", "2")),
        **kwargs,
    )


def _trade(*bars: ReplayBar, side: str = "long") -> ReplayTrade:
    return ReplayTrade(
        trade_id=f"trade-{side}",
        strategy_group_id="MPG-001",
        event_spec_id="MPG-LONG" if side == "long" else "BRF2-SHORT",
        exchange_instrument_id="ETHUSDT",
        side=side,
        entry_price=Decimal("100"),
        initial_stop_price=Decimal("95") if side == "long" else Decimal("105"),
        quantity=Decimal("2"),
        price_tick=Decimal("0.1"),
        bars=tuple(bars),
    )


def test_actual_fill_r_and_long_short_tick_rounding_are_exact():
    long_result = replay_trade(
        _trade(_bar(1, open_="100", high="105.1", low="99", close="104")),
        _candidate(),
    )
    short_result = replay_trade(
        _trade(
            _bar(1, open_="100", high="101", low="94.9", close="96"),
            side="short",
        ),
        _candidate(side="short"),
    )

    assert long_result.actual_r_per_unit == Decimal("5")
    assert long_result.tp1_price == Decimal("105")
    assert short_result.tp1_price == Decimal("95")


def test_ambiguous_same_bar_tp1_and_stop_is_conservative_without_lookahead():
    result = replay_trade(
        _trade(
            _bar(1, open_="100", high="106", low="94", close="104"),
            _bar(2, open_="104", high="120", low="103", close="119"),
        ),
        _candidate(),
    )

    assert result.exit_reason == "ambiguous_same_bar_stop_first"
    assert result.tp1_filled_qty == Decimal("0")
    assert result.exit_bar_index == 0
    assert result.ambiguous_bar_count == 1


def test_partial_tp1_fill_keeps_exact_remaining_quantity_and_cost_floor():
    result = replay_trade(
        _trade(
            _bar(1, open_="100", high="105.2", low="99", close="104"),
            _bar(2, open_="104", high="106", low="100", close="105"),
        ),
        _candidate(tp1_fill_fraction=Decimal("0.5")),
    )

    assert result.tp1_filled_qty == Decimal("0.5")
    assert result.remaining_qty_after_tp1 == Decimal("1.5")
    assert result.runner_floor is None
    assert result.tp1_completion_state == "partial"


def test_complete_tp1_moves_runner_to_cost_adjusted_floor_immediately():
    result = replay_trade(
        _trade(
            _bar(1, open_="100", high="105.2", low="99", close="104"),
            _bar(2, open_="104", high="106", low="100.3", close="105"),
        ),
        _candidate(),
    )

    assert result.tp1_completion_state == "complete"
    assert result.runner_floor is not None
    assert result.runner_floor > Decimal("100")
    assert result.stop_updates[0].reason == "tp1_cost_adjusted_floor"


def test_gtc_gap_fill_is_taker_and_gtx_gap_is_rejected_without_market_fallback():
    trade = _trade(_bar(1, open_="106", high="107", low="105.5", close="106"))

    gtc = replay_trade(trade, _candidate(tp1_execution_style="limit_gtc"))
    gtx = replay_trade(trade, _candidate(tp1_execution_style="passive_limit_gtx"))

    assert gtc.tp1_liquidity_role == "taker"
    assert gtc.tp1_fee_quote > Decimal("0")
    assert gtx.tp1_completion_state == "unfilled"
    assert gtx.passive_rejection_count == 1
    assert gtx.market_fallback_used is False


def test_closed_bar_structural_trail_is_monotonic_and_applies_next_bar():
    result = replay_trade(
        _trade(
            _bar(1, open_="100", high="105.2", low="99", close="104", atr="1"),
            _bar(2, open_="104", high="108", low="103", close="107", atr="1"),
            _bar(3, open_="107", high="110", low="106", close="109", atr="1"),
            _bar(4, open_="109", high="110", low="107", close="108", atr="1"),
        ),
        _candidate(),
    )

    prices = [update.stop_price for update in result.stop_updates]
    assert prices == sorted(prices)
    assert all(update.effective_from_bar > update.source_bar for update in result.stop_updates)


@pytest.mark.parametrize(
    ("bar", "expected_reason"),
    [
        (
            _bar(
                1,
                open_="100",
                high="102",
                low="98",
                close="99",
                invalidation_hit=True,
            ),
            "strategy_invalidation",
        ),
        (_bar(1, open_="100", high="102", low="98", close="101"), "time_stop"),
    ],
)
def test_invalidation_and_time_stop_close_at_closed_bar(bar, expected_reason):
    candidate = _candidate(max_holding_bars=1)
    if expected_reason == "strategy_invalidation":
        candidate = _candidate(max_holding_bars=20)

    result = replay_trade(_trade(bar), candidate)

    assert result.exit_reason == expected_reason
    assert result.exit_price == bar.close


def test_fee_funding_mfe_mae_and_aggregate_tail_metrics_are_present():
    winning = replay_trade(
        _trade(
            _bar(
                1,
                open_="100",
                high="105.5",
                low="99",
                close="105",
                funding_quote=Decimal("0.01"),
            ),
            _bar(2, open_="105", high="112", low="103", close="111"),
        ),
        _candidate(max_holding_bars=2),
    )
    losing = replay_trade(
        ReplayTrade(
            **{
                **_trade(_bar(1, open_="100", high="101", low="94", close="95")).__dict__,
                "trade_id": "trade-loser",
            }
        ),
        _candidate(),
    )
    aggregate = aggregate_replay_results((winning, losing))

    assert winning.total_fees_quote > Decimal("0")
    assert winning.funding_quote == Decimal("0.01")
    assert winning.mfe_r > Decimal("0")
    assert winning.mae_r <= Decimal("0")
    assert aggregate.trade_count == 2
    assert aggregate.tail_contribution >= Decimal("0")
    assert aggregate.worst_rolling_net_r <= aggregate.total_net_r
    assert aggregate.capital_slot_occupancy_bars >= 2


@pytest.mark.parametrize(
    "overrides",
    [
        {"tp1_quantity_fraction": Decimal("0")},
        {"tp1_fill_fraction": Decimal("1.1")},
        {"taker_fee_rate": Decimal("-0.1")},
        {"structure_window_bars": 0},
        {"minimum_improvement_ticks": 0},
    ],
)
def test_invalid_candidate_values_fail_closed(overrides):
    with pytest.raises(ValueError):
        _candidate(**overrides)
