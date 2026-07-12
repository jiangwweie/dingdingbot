from decimal import Decimal

from src.domain.execution_sizing import (
    ExecutionAccountCapacity,
    ExecutionInstrumentRules,
    ExecutionSizingPolicy,
    decide_execution_sizing,
)


NOW_MS = 1_000_000


def _rules(
    *,
    price: str = "100",
    min_qty: str = "0.001",
    step: str = "0.001",
    min_notional: str = "5",
    side: str = "long",
) -> ExecutionInstrumentRules:
    return ExecutionInstrumentRules(
        symbol="TESTUSDT",
        side=side,
        entry_reference_price=Decimal(price),
        min_qty=Decimal(min_qty),
        qty_step=Decimal(step),
        min_notional=Decimal(min_notional),
        exchange_max_leverage=125,
        source_fact_snapshot_id="public-fact-1",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 30_000,
    )


def _account(
    *, wallet: str = "100", available: str = "100"
) -> ExecutionAccountCapacity:
    return ExecutionAccountCapacity(
        total_wallet_balance=Decimal(wallet),
        available_balance=Decimal(available),
        source_fact_snapshot_id="account-fact-1",
        observed_at_ms=NOW_MS - 1_000,
        valid_until_ms=NOW_MS + 30_000,
    )


def _policy(
    *, risk: str = "0.03", margin: str = "0.90", max_leverage: int = 10
) -> ExecutionSizingPolicy:
    return ExecutionSizingPolicy(
        planned_stop_risk_fraction=Decimal(risk),
        max_initial_margin_utilization=Decimal(margin),
        max_leverage=max_leverage,
        policy_version="owner-risk-policy-v2",
    )


def test_one_hundred_usdt_half_percent_stop_selects_seven_x() -> None:
    result = decide_execution_sizing(
        rules=_rules(),
        account=_account(),
        policy=_policy(),
        protective_stop_price=Decimal("99.5"),
        now_ms=NOW_MS,
    )

    assert result.blockers == ()
    assert result.decision is not None
    assert result.decision.intended_qty == Decimal("6")
    assert result.decision.effective_notional == Decimal("600")
    assert result.decision.selected_leverage == 7
    assert result.decision.reserved_margin == Decimal("600") / Decimal("7")
    assert result.decision.planned_stop_risk_budget == Decimal("3")
    assert result.decision.planned_stop_risk == Decimal("3.0")


def test_max_leverage_shrinks_quantity_without_blocking() -> None:
    result = decide_execution_sizing(
        rules=_rules(),
        account=_account(),
        policy=_policy(max_leverage=5),
        protective_stop_price=Decimal("99.5"),
        now_ms=NOW_MS,
    )

    assert result.blockers == ()
    assert result.decision is not None
    assert result.decision.selected_leverage == 5
    assert result.decision.intended_qty == Decimal("4.5")
    assert result.decision.effective_notional == Decimal("450.0")
    assert result.decision.reserved_margin == Decimal("90.0")
    assert result.decision.planned_stop_risk == Decimal("2.25")


def test_minimum_executable_quantity_above_risk_budget_blocks() -> None:
    result = decide_execution_sizing(
        rules=_rules(min_qty="1", step="1", min_notional="100"),
        account=_account(wallet="10", available="10"),
        policy=_policy(),
        protective_stop_price=Decimal("95"),
        now_ms=NOW_MS,
    )

    assert result.decision is None
    assert result.blockers == (
        "minimum_executable_quantity_exceeds_planned_stop_risk_budget",
    )
    assert result.minimum_executable_quantity == Decimal("1")


def test_minimum_executable_quantity_above_margin_capacity_blocks() -> None:
    result = decide_execution_sizing(
        rules=_rules(min_qty="1", step="1", min_notional="100"),
        account=_account(wallet="100", available="1"),
        policy=_policy(),
        protective_stop_price=Decimal("99.5"),
        now_ms=NOW_MS,
    )

    assert result.decision is None
    assert result.blockers == (
        "minimum_executable_quantity_exceeds_margin_capacity",
    )


def test_short_stop_must_be_above_entry() -> None:
    result = decide_execution_sizing(
        rules=_rules(side="short"),
        account=_account(),
        policy=_policy(),
        protective_stop_price=Decimal("99.5"),
        now_ms=NOW_MS,
    )

    assert result.decision is None
    assert result.blockers == ("protective_stop_side_not_valid",)


def test_stale_account_capacity_fails_closed() -> None:
    account = _account().model_copy(update={"valid_until_ms": NOW_MS})

    result = decide_execution_sizing(
        rules=_rules(),
        account=account,
        policy=_policy(),
        protective_stop_price=Decimal("99.5"),
        now_ms=NOW_MS,
    )

    assert result.decision is None
    assert result.blockers == ("execution_account_capacity_stale",)
