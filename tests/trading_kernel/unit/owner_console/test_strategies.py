from decimal import Decimal

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    MoneyMetric,
    StrategyObservationFacts,
    StrategyObservationPageFacts,
    StrategyPageFacts,
    StrategyProductEventFacts,
    StrategyTicketFacts,
    StrategyVersionFacts,
)
from src.trading_kernel.application.owner_console.strategies import (
    build_strategy_observation_page,
    build_strategy_page,
)


def _evidence(kind: str, identity: str, occurred_at_ms: int) -> EvidenceRef:
    return EvidenceRef(
        kind=kind,  # type: ignore[arg-type]
        identity=identity,
        occurred_at_ms=occurred_at_ms,
    )


def _metric(value: str | None, unit: str = "USDT") -> MoneyMetric:
    return MoneyMetric(
        value=None if value is None else Decimal(value),
        unit=unit,  # type: ignore[arg-type]
        unavailable_reason=("review_incomplete" if value is None else None),
    )


def _ticket(
    ticket_id: str,
    *,
    exit_reason: str,
    tp1_reached: bool,
    completeness: str = "complete",
    net_pnl: str | None = "1.00",
    net_r: str | None = "0.10",
) -> StrategyTicketFacts:
    return StrategyTicketFacts(
        ticket_id=ticket_id,
        issued_at_ms=1_800_000_000_000,
        terminal_at_ms=1_800_000_100_000,
        ticket_status="terminal",
        aggregate_status="terminal",
        review_id=f"review:{ticket_id}" if completeness == "complete" else None,
        review_created_at_ms=(
            1_800_000_100_000 if completeness == "complete" else None
        ),
        economics_completeness=completeness,  # type: ignore[arg-type]
        net_pnl=_metric(net_pnl),
        net_r=_metric(net_r, "R"),
        exit_reason=exit_reason,
        tp1_reached=tp1_reached,
        evidence=(
            _evidence("ticket", ticket_id, 1_800_000_000_000),
            _evidence("event", f"event:{ticket_id}:exit", 1_800_000_090_000),
        ),
    )


def _observation(
    shadow_outcome_id: str,
    *,
    first_path: str,
    mfe_r: str,
    mae_r: str,
    spread_bps: str,
) -> StrategyObservationFacts:
    return StrategyObservationFacts(
        shadow_outcome_id=shadow_outcome_id,
        signal_event_id=f"signal:{shadow_outcome_id}",
        ticket_id=None,
        strategy_version_id="strategy-version:brf2:v3",
        exchange_instrument_id="binance-usdm:AAPLUSDT:perpetual",
        position_side="long",
        occurred_at_ms=1_800_000_000_000,
        horizon_start_ms=1_800_000_000_000,
        horizon_end_ms=1_800_007_200_000,
        status="completed",
        entry_reference_price=Decimal(100),
        initial_stop_price=Decimal(98),
        take_profit_price=Decimal(102),
        opening_range_boundary_price=Decimal(99),
        session_exit_deadline_ms=1_800_007_200_000,
        best_bid_price=Decimal("99.99"),
        best_ask_price=Decimal("100.01"),
        best_bid_quantity=Decimal(20),
        best_ask_quantity=Decimal(18),
        spread_bps=Decimal(spread_bps),
        mark_index_deviation_bps=Decimal("1.25"),
        max_favorable_price=Decimal(103),
        max_adverse_price=Decimal("98.5"),
        mfe_r=Decimal(mfe_r),
        mae_r=Decimal(mae_r),
        completion_reason="sor_path_observed",
        first_path=first_path,  # type: ignore[arg-type]
        first_path_at_ms=1_800_000_900_000,
        observed_bar_count=1,
        completed_at_ms=1_800_001_000_000,
        evidence=(
            _evidence("signal", f"signal:{shadow_outcome_id}", 1_800_000_000_000),
            _evidence("shadow", shadow_outcome_id, 1_800_001_000_000),
        ),
    )


def _version(
    *tickets: StrategyTicketFacts,
    observations: tuple[StrategyObservationFacts, ...] = (),
) -> StrategyVersionFacts:
    return StrategyVersionFacts(
        strategy_group_id="strategy-group:brf2",
        strategy_group_display_name="BRF2",
        strategy_version_id="strategy-version:brf2:v3",
        version=3,
        strategy_version_status="active",
        is_current=True,
        tickets=tickets,
        observations=observations,
        evidence=(
            _evidence(
                "fact",
                "strategy-version:brf2:v3",
                1_800_000_000_000,
            ),
        ),
        product_events=(
            StrategyProductEventFacts(
                event_spec_id="event_spec:BRF2-001:v3:BRF2-SHORT-1H",
                event_id="BRF2-SHORT-1H",
                position_side="short",
                timeframe="1h",
                venue_id="binance-usdm",
                product_family="crypto_perpetual",
                runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",
                active_universe_version_id="universe:brf2:v1",
                active_exchange_instrument_ids=(
                    "binance-usdm:BTCUSDT:perpetual",
                ),
                warming_universe_version_id=None,
                warming_exchange_instrument_ids=(),
            ),
        ),
    )


def test_strategy_version_summary_keeps_natural_and_controlled_outcomes_separate() -> (
    None
):
    page = build_strategy_page(
        StrategyPageFacts(
            from_ms=1_799_000_000_000,
            to_ms=1_801_000_000_000,
            view="all",
            versions=(
                _version(
                    _ticket(
                        "ticket:tp1",
                        exit_reason="runner_exit",
                        tp1_reached=True,
                        net_pnl="10.00",
                        net_r="1.00",
                    ),
                    _ticket(
                        "ticket:stop",
                        exit_reason="initial_stop_triggered",
                        tp1_reached=False,
                        net_pnl="-2.00",
                        net_r="-0.20",
                    ),
                    _ticket(
                        "ticket:controlled",
                        exit_reason="owner_flatten_all:operator_request",
                        tp1_reached=False,
                        net_pnl="-99.00",
                        net_r="-9.90",
                    ),
                    _ticket(
                        "ticket:pending",
                        exit_reason="strategy_exit",
                        tp1_reached=False,
                        completeness="funding_unavailable",
                        net_pnl=None,
                        net_r=None,
                    ),
                ),
            ),
        )
    )

    item = page.items[0]
    assert item.ticket_count == 4
    assert item.natural_terminal_count == 3
    assert item.confirmed_natural_review_count == 2
    assert item.pending_natural_review_count == 1
    assert item.controlled_exit_count == 1
    assert item.tp1_reached_count == 1
    assert item.tp1_not_reached_count == 2
    assert item.win_count == 1
    assert item.loss_count == 1
    assert item.net_pnl.value == Decimal("8.00")
    assert item.net_r.value == Decimal("0.80")
    assert item.product_events == _version().product_events


def test_strategy_version_with_no_confirmed_natural_review_never_emits_zero_return() -> (
    None
):
    page = build_strategy_page(
        StrategyPageFacts(
            from_ms=1_799_000_000_000,
            to_ms=1_801_000_000_000,
            view="current",
            versions=(
                _version(
                    _ticket(
                        "ticket:drain",
                        exit_reason="deployment_drain:release_switch",
                        tp1_reached=False,
                    ),
                ),
            ),
        )
    )

    item = page.items[0]
    assert item.confirmed_natural_review_count == 0
    assert item.net_pnl.value is None
    assert item.net_pnl.unavailable_reason == "no_confirmed_natural_review"
    assert item.net_r.value is None
    assert item.net_r.unavailable_reason == "no_confirmed_natural_review"


def test_strategy_version_summary_isolates_observation_paths_and_medians() -> None:
    observations = (
        _observation(
            "shadow:tp1",
            first_path="tp1_first",
            mfe_r="1.50",
            mae_r="0.25",
            spread_bps="2.00",
        ),
        _observation(
            "shadow:stop",
            first_path="initial_stop_first",
            mfe_r="0.20",
            mae_r="1.10",
            spread_bps="4.00",
        ),
    )
    page = build_strategy_page(
        StrategyPageFacts(
            from_ms=1_799_000_000_000,
            to_ms=1_801_000_000_000,
            view="current",
            versions=(_version(observations=observations),),
        )
    )

    item = page.items[0]
    assert item.observation_count == 2
    assert item.completed_observation_count == 2
    assert item.tp1_first_count == 1
    assert item.initial_stop_first_count == 1
    assert item.median_mfe_r == Decimal("0.85")
    assert item.median_mae_r == Decimal("0.675")
    assert item.median_spread_bps == Decimal("3.00")

    observation_page = build_strategy_observation_page(
        StrategyObservationPageFacts(items=observations, requested_limit=50)
    )
    assert observation_page.items[0].annotations[0].kind == "signal"
    assert observation_page.items[0].annotations[1].kind == "take_profit"
    assert observation_page.items[1].annotations[1].kind == "stop"
