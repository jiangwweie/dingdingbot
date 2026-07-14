"""Deterministic, research-only replay for Ticket exit-policy candidates.

The model consumes already ordered closed bars.  It has no runtime, database,
filesystem, order, or exchange authority.  Ambiguous intrabar paths are resolved
conservatively and a stop derived from one closed bar can only affect a later bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from statistics import median
from typing import Literal, Sequence


Side = Literal["long", "short"]
ExecutionStyle = Literal["limit_gtc", "passive_limit_gtx"]


@dataclass(frozen=True)
class ReplayBar:
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    atr: Decimal
    funding_quote: Decimal = Decimal("0")
    invalidation_hit: bool = False

    def __post_init__(self) -> None:
        if self.close_time_ms <= 0:
            raise ValueError("close_time_ms_invalid")
        if min(self.open, self.high, self.low, self.close, self.atr) <= 0:
            raise ValueError("bar_price_or_atr_invalid")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar_high_invalid")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar_low_invalid")


@dataclass(frozen=True)
class ReplayTrade:
    trade_id: str
    strategy_group_id: str
    event_spec_id: str
    exchange_instrument_id: str
    side: Side
    entry_price: Decimal
    initial_stop_price: Decimal
    quantity: Decimal
    price_tick: Decimal
    bars: tuple[ReplayBar, ...]

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.trade_id,
                self.strategy_group_id,
                self.event_spec_id,
                self.exchange_instrument_id,
            )
        ):
            raise ValueError("trade_identity_missing")
        if min(self.entry_price, self.initial_stop_price, self.quantity, self.price_tick) <= 0:
            raise ValueError("trade_financial_value_invalid")
        if not self.bars:
            raise ValueError("replay_bars_missing")
        if tuple(sorted(bar.close_time_ms for bar in self.bars)) != tuple(
            bar.close_time_ms for bar in self.bars
        ):
            raise ValueError("replay_bars_not_ordered")
        if self.side == "long" and self.initial_stop_price >= self.entry_price:
            raise ValueError("long_initial_stop_invalid")
        if self.side == "short" and self.initial_stop_price <= self.entry_price:
            raise ValueError("short_initial_stop_invalid")


@dataclass(frozen=True)
class ExitPolicyCandidate:
    candidate_id: str
    side: Side
    tp1_reward_multiple: Decimal
    tp1_quantity_fraction: Decimal
    tp1_execution_style: ExecutionStyle
    tp1_fill_fraction: Decimal
    entry_fee_rate: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal
    slippage_ticks: int
    structure_window_bars: int
    atr_buffer_multiple: Decimal
    minimum_improvement_ticks: int
    max_holding_bars: int

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id_missing")
        if self.tp1_reward_multiple <= 0:
            raise ValueError("tp1_reward_multiple_invalid")
        if not Decimal("0") < self.tp1_quantity_fraction < Decimal("1"):
            raise ValueError("tp1_quantity_fraction_invalid")
        if not Decimal("0") < self.tp1_fill_fraction <= Decimal("1"):
            raise ValueError("tp1_fill_fraction_invalid")
        if any(
            value < 0
            for value in (
                self.entry_fee_rate,
                self.maker_fee_rate,
                self.taker_fee_rate,
                self.atr_buffer_multiple,
            )
        ):
            raise ValueError("fee_or_buffer_invalid")
        if self.slippage_ticks < 0:
            raise ValueError("slippage_ticks_invalid")
        if self.structure_window_bars < 1:
            raise ValueError("structure_window_bars_invalid")
        if self.minimum_improvement_ticks < 1:
            raise ValueError("minimum_improvement_ticks_invalid")
        if self.max_holding_bars < 1:
            raise ValueError("max_holding_bars_invalid")


@dataclass(frozen=True)
class StopUpdate:
    source_bar: int
    effective_from_bar: int
    stop_price: Decimal
    reason: str


@dataclass(frozen=True)
class ReplayResult:
    trade_id: str
    candidate_id: str
    actual_r_per_unit: Decimal
    tp1_price: Decimal
    tp1_target_qty: Decimal
    tp1_filled_qty: Decimal
    tp1_completion_state: Literal["unfilled", "partial", "complete"]
    tp1_liquidity_role: Literal["maker", "taker"] | None
    tp1_fee_quote: Decimal
    remaining_qty_after_tp1: Decimal
    runner_floor: Decimal | None
    stop_updates: tuple[StopUpdate, ...]
    exit_reason: str
    exit_price: Decimal
    exit_bar_index: int
    gross_pnl_quote: Decimal
    total_fees_quote: Decimal
    slippage_quote: Decimal
    funding_quote: Decimal
    net_pnl_quote: Decimal
    net_r: Decimal
    mfe_r: Decimal
    mae_r: Decimal
    profit_giveback_r: Decimal
    ambiguous_bar_count: int
    passive_rejection_count: int
    market_fallback_used: bool
    capital_slot_occupancy_bars: int


@dataclass(frozen=True)
class ReplayAggregate:
    trade_count: int
    total_net_r: Decimal
    mean_net_r: Decimal
    median_net_r: Decimal
    tail_contribution: Decimal
    worst_rolling_net_r: Decimal
    maker_fill_rate: Decimal
    taker_fill_rate: Decimal
    total_fees_quote: Decimal
    total_slippage_quote: Decimal
    total_funding_quote: Decimal
    stop_update_count: int
    passive_rejection_count: int
    ambiguous_bar_count: int
    capital_slot_occupancy_bars: int


def replay_trade(trade: ReplayTrade, candidate: ExitPolicyCandidate) -> ReplayResult:
    if trade.side != candidate.side:
        raise ValueError("candidate_trade_side_mismatch")
    actual_r = abs(trade.entry_price - trade.initial_stop_price)
    if actual_r <= 0:
        raise ValueError("actual_fill_r_invalid")
    tp1_price = _round_tick(
        trade.entry_price + actual_r * candidate.tp1_reward_multiple
        if trade.side == "long"
        else trade.entry_price - actual_r * candidate.tp1_reward_multiple,
        trade.price_tick,
        ROUND_CEILING if trade.side == "long" else ROUND_FLOOR,
    )
    tp1_target_qty = trade.quantity * candidate.tp1_quantity_fraction
    entry_fee = trade.entry_price * trade.quantity * candidate.entry_fee_rate
    fees = entry_fee
    funding = Decimal("0")
    slippage = Decimal("0")
    gross = Decimal("0")
    remaining = trade.quantity
    remaining_after_tp1 = trade.quantity
    tp1_filled = Decimal("0")
    tp1_fee = Decimal("0")
    tp1_role: Literal["maker", "taker"] | None = None
    tp1_attempted = False
    runner_floor: Decimal | None = None
    stop_updates: list[StopUpdate] = []
    active_stop = trade.initial_stop_price
    ambiguous_count = 0
    passive_rejections = 0
    mfe_r = Decimal("0")
    mae_r = Decimal("0")
    exit_reason = "end_of_data"
    exit_price = trade.bars[-1].close
    exit_bar_index = len(trade.bars) - 1
    terminal = False

    for index, bar in enumerate(trade.bars):
        for update in stop_updates:
            if update.effective_from_bar == index:
                active_stop = update.stop_price
        funding += bar.funding_quote
        favorable = (
            bar.high - trade.entry_price
            if trade.side == "long"
            else trade.entry_price - bar.low
        ) / actual_r
        adverse = (
            bar.low - trade.entry_price
            if trade.side == "long"
            else trade.entry_price - bar.high
        ) / actual_r
        mfe_r = max(mfe_r, favorable)
        mae_r = min(mae_r, adverse)

        stop_hit = bar.low <= active_stop if trade.side == "long" else bar.high >= active_stop
        tp1_hit = (
            not tp1_attempted
            and (bar.high >= tp1_price if trade.side == "long" else bar.low <= tp1_price)
        )
        if stop_hit and tp1_hit:
            ambiguous_count += 1
            exit_reason = "ambiguous_same_bar_stop_first"
            exit_price, gross_delta, fee_delta, slip_delta = _close_at_stop(
                trade=trade,
                candidate=candidate,
                qty=remaining,
                stop_price=active_stop,
            )
            gross += gross_delta
            fees += fee_delta
            slippage += slip_delta
            exit_bar_index = index
            remaining = Decimal("0")
            terminal = True
            break
        if stop_hit:
            exit_reason = "runner_stop" if tp1_filled else "initial_stop"
            exit_price, gross_delta, fee_delta, slip_delta = _close_at_stop(
                trade=trade,
                candidate=candidate,
                qty=remaining,
                stop_price=active_stop,
            )
            gross += gross_delta
            fees += fee_delta
            slippage += slip_delta
            exit_bar_index = index
            remaining = Decimal("0")
            terminal = True
            break

        if tp1_hit:
            tp1_attempted = True
            gap_through = (
                bar.open >= tp1_price
                if trade.side == "long"
                else bar.open <= tp1_price
            )
            if candidate.tp1_execution_style == "passive_limit_gtx" and gap_through:
                passive_rejections += 1
            else:
                tp1_role = "taker" if gap_through else "maker"
                fill_qty = tp1_target_qty * candidate.tp1_fill_fraction
                tp1_filled += fill_qty
                remaining -= fill_qty
                remaining_after_tp1 = remaining
                gross += _signed_pnl(trade.side, trade.entry_price, tp1_price, fill_qty)
                fee_rate = (
                    candidate.taker_fee_rate
                    if tp1_role == "taker"
                    else candidate.maker_fee_rate
                )
                tp1_fee = tp1_price * fill_qty * fee_rate
                fees += tp1_fee
                if tp1_filled >= tp1_target_qty:
                    runner_floor = _cost_adjusted_floor(
                        trade=trade,
                        candidate=candidate,
                        runner_qty=remaining,
                        allocated_entry_fee=(entry_fee * remaining / trade.quantity),
                    )
                    if _improves(
                        side=trade.side,
                        current=active_stop,
                        proposed=runner_floor,
                        required=(
                            trade.price_tick * candidate.minimum_improvement_ticks
                        ),
                    ):
                        stop_updates.append(
                            StopUpdate(
                                source_bar=index,
                                effective_from_bar=index + 1,
                                stop_price=runner_floor,
                                reason="tp1_cost_adjusted_floor",
                            )
                        )

        if bar.invalidation_hit and remaining > 0:
            exit_reason = "strategy_invalidation"
            exit_price = bar.close
            gross += _signed_pnl(trade.side, trade.entry_price, bar.close, remaining)
            fees += bar.close * remaining * candidate.taker_fee_rate
            exit_bar_index = index
            remaining = Decimal("0")
            terminal = True
            break
        if index + 1 >= candidate.max_holding_bars and remaining > 0:
            exit_reason = "time_stop"
            exit_price = bar.close
            gross += _signed_pnl(trade.side, trade.entry_price, bar.close, remaining)
            fees += bar.close * remaining * candidate.taker_fee_rate
            exit_bar_index = index
            remaining = Decimal("0")
            terminal = True
            break

        if tp1_filled >= tp1_target_qty and remaining > 0:
            window = trade.bars[max(0, index + 1 - candidate.structure_window_bars) : index + 1]
            raw_candidate = (
                min(item.low for item in window)
                - bar.atr * candidate.atr_buffer_multiple
                if trade.side == "long"
                else max(item.high for item in window)
                + bar.atr * candidate.atr_buffer_multiple
            )
            structural = _round_tick(
                raw_candidate,
                trade.price_tick,
                ROUND_FLOOR if trade.side == "long" else ROUND_CEILING,
            )
            effective_current = stop_updates[-1].stop_price if stop_updates else active_stop
            if _improves(
                side=trade.side,
                current=effective_current,
                proposed=structural,
                required=trade.price_tick * candidate.minimum_improvement_ticks,
            ):
                stop_updates.append(
                    StopUpdate(
                        source_bar=index,
                        effective_from_bar=index + 1,
                        stop_price=structural,
                        reason="closed_bar_structural_trail",
                    )
                )

    if not terminal and remaining > 0:
        final_bar = trade.bars[-1]
        exit_price = final_bar.close
        gross += _signed_pnl(trade.side, trade.entry_price, exit_price, remaining)
        fees += exit_price * remaining * candidate.taker_fee_rate
        remaining = Decimal("0")

    completion_state: Literal["unfilled", "partial", "complete"]
    if tp1_filled == 0:
        completion_state = "unfilled"
    elif tp1_filled < tp1_target_qty:
        completion_state = "partial"
    else:
        completion_state = "complete"
    net = gross - fees - slippage - funding
    net_r = net / (actual_r * trade.quantity)
    return ReplayResult(
        trade_id=trade.trade_id,
        candidate_id=candidate.candidate_id,
        actual_r_per_unit=actual_r,
        tp1_price=tp1_price,
        tp1_target_qty=tp1_target_qty,
        tp1_filled_qty=tp1_filled,
        tp1_completion_state=completion_state,
        tp1_liquidity_role=tp1_role,
        tp1_fee_quote=tp1_fee,
        remaining_qty_after_tp1=remaining_after_tp1,
        runner_floor=runner_floor,
        stop_updates=tuple(stop_updates),
        exit_reason=exit_reason,
        exit_price=exit_price,
        exit_bar_index=exit_bar_index,
        gross_pnl_quote=gross,
        total_fees_quote=fees,
        slippage_quote=slippage,
        funding_quote=funding,
        net_pnl_quote=net,
        net_r=net_r,
        mfe_r=mfe_r,
        mae_r=mae_r,
        profit_giveback_r=max(Decimal("0"), mfe_r - net_r),
        ambiguous_bar_count=ambiguous_count,
        passive_rejection_count=passive_rejections,
        market_fallback_used=False,
        capital_slot_occupancy_bars=exit_bar_index + 1,
    )


def aggregate_replay_results(results: Sequence[ReplayResult]) -> ReplayAggregate:
    if not results:
        raise ValueError("replay_results_missing")
    net_values = [item.net_r for item in results]
    positive = sorted((value for value in net_values if value > 0), reverse=True)
    tail_count = max(1, (len(positive) + 9) // 10) if positive else 0
    tail_contribution = (
        sum(positive[:tail_count], Decimal("0"))
        / sum(positive, Decimal("0"))
        if positive
        else Decimal("0")
    )
    rolling_width = min(3, len(net_values))
    rolling = [
        sum(net_values[index : index + rolling_width], Decimal("0"))
        for index in range(0, len(net_values) - rolling_width + 1)
    ]
    filled = [item for item in results if item.tp1_filled_qty > 0]
    return ReplayAggregate(
        trade_count=len(results),
        total_net_r=sum(net_values, Decimal("0")),
        mean_net_r=sum(net_values, Decimal("0")) / Decimal(len(results)),
        median_net_r=Decimal(str(median(net_values))),
        tail_contribution=tail_contribution,
        worst_rolling_net_r=min(rolling),
        maker_fill_rate=(
            Decimal(sum(item.tp1_liquidity_role == "maker" for item in filled))
            / Decimal(len(filled))
            if filled
            else Decimal("0")
        ),
        taker_fill_rate=(
            Decimal(sum(item.tp1_liquidity_role == "taker" for item in filled))
            / Decimal(len(filled))
            if filled
            else Decimal("0")
        ),
        total_fees_quote=sum((item.total_fees_quote for item in results), Decimal("0")),
        total_slippage_quote=sum((item.slippage_quote for item in results), Decimal("0")),
        total_funding_quote=sum((item.funding_quote for item in results), Decimal("0")),
        stop_update_count=sum(len(item.stop_updates) for item in results),
        passive_rejection_count=sum(item.passive_rejection_count for item in results),
        ambiguous_bar_count=sum(item.ambiguous_bar_count for item in results),
        capital_slot_occupancy_bars=sum(
            item.capital_slot_occupancy_bars for item in results
        ),
    )


def _cost_adjusted_floor(
    *,
    trade: ReplayTrade,
    candidate: ExitPolicyCandidate,
    runner_qty: Decimal,
    allocated_entry_fee: Decimal,
) -> Decimal:
    if runner_qty <= 0:
        raise ValueError("runner_qty_invalid")
    slippage_quote = (
        Decimal(candidate.slippage_ticks) * trade.price_tick * runner_qty
    )
    notional = trade.entry_price * runner_qty
    if trade.side == "long":
        raw = (notional + allocated_entry_fee + slippage_quote) / (
            runner_qty * (Decimal("1") - candidate.taker_fee_rate)
        )
        return _round_tick(raw, trade.price_tick, ROUND_CEILING)
    raw = (notional - allocated_entry_fee - slippage_quote) / (
        runner_qty * (Decimal("1") + candidate.taker_fee_rate)
    )
    return _round_tick(raw, trade.price_tick, ROUND_FLOOR)


def _close_at_stop(
    *,
    trade: ReplayTrade,
    candidate: ExitPolicyCandidate,
    qty: Decimal,
    stop_price: Decimal,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    slippage_per_unit = Decimal(candidate.slippage_ticks) * trade.price_tick
    execution = (
        stop_price - slippage_per_unit
        if trade.side == "long"
        else stop_price + slippage_per_unit
    )
    execution = max(execution, trade.price_tick)
    return (
        execution,
        _signed_pnl(trade.side, trade.entry_price, execution, qty),
        execution * qty * candidate.taker_fee_rate,
        slippage_per_unit * qty,
    )


def _signed_pnl(side: Side, entry: Decimal, exit_price: Decimal, qty: Decimal) -> Decimal:
    return (exit_price - entry) * qty if side == "long" else (entry - exit_price) * qty


def _improves(
    *,
    side: Side,
    current: Decimal,
    proposed: Decimal,
    required: Decimal,
) -> bool:
    improvement = proposed - current if side == "long" else current - proposed
    return improvement >= required


def _round_tick(value: Decimal, tick: Decimal, rounding: str) -> Decimal:
    return (value / tick).to_integral_value(rounding=rounding) * tick
