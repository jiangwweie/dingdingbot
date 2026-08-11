from decimal import Decimal

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    MoneyMetric,
    StrategyPageFacts,
    StrategyProductEventFacts,
    StrategyTicketFacts,
    StrategyVersionFacts,
)
from src.trading_kernel.application.owner_console.strategies import (
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


def _version(*tickets: StrategyTicketFacts) -> StrategyVersionFacts:
    return StrategyVersionFacts(
        strategy_group_id="strategy-group:brf2",
        strategy_group_display_name="BRF2",
        strategy_version_id="strategy-version:brf2:v3",
        version=3,
        strategy_version_status="active",
        is_current=True,
        tickets=tickets,
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
