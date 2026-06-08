from decimal import Decimal

from src.application.notional_sizing import (
    ContractMarketRules,
    compute_notional_sizing,
    validate_fixed_quantity_scope,
)


def _eth_rules() -> ContractMarketRules:
    return ContractMarketRules(
        symbol="ETH/USDT:USDT",
        min_notional=Decimal("20"),
        min_qty=Decimal("0.001"),
        qty_step=Decimal("0.001"),
        price_tick=Decimal("0.01"),
        current_price=Decimal("1681.64"),
        freshness="fresh",
        source="test_binance_usdt_m_futures_market_rules",
        observed_at_ms=1780883681000,
    )


def test_notional_sizing_rounds_up_to_valid_eth_quantity_for_entry_and_protection():
    result = compute_notional_sizing(
        symbol="ETH/USDT:USDT",
        side="long",
        target_notional_usdt=Decimal("22"),
        max_notional_usdt=Decimal("25"),
        market_rules=_eth_rules(),
    )

    assert result.status == "valid"
    assert result.computed_quantity == Decimal("0.014")
    assert result.estimated_notional_usdt == Decimal("23.54296")
    assert result.estimated_worst_protection_notional_usdt >= Decimal("20")
    assert result.validation.entry_notional_valid is True
    assert result.validation.protection_notional_valid is True
    assert result.validation.max_notional_valid is True
    assert result.blockers == []


def test_notional_sizing_blocks_exact_old_eth_quantity_and_surfaces_repair_scope():
    result = validate_fixed_quantity_scope(
        symbol="ETH/USDT:USDT",
        side="long",
        quantity=Decimal("0.01"),
        max_notional_usdt=Decimal("20"),
        market_rules=_eth_rules(),
    )

    assert result.status == "blocked"
    assert "requested_quantity_below_market_rule_minimum" in result.blockers
    assert result.computed_quantity == Decimal("0.01")
    assert result.estimated_notional_usdt == Decimal("16.8164")
    assert result.estimated_worst_protection_notional_usdt < Decimal("20")
    assert result.validation.entry_notional_valid is False
    assert result.validation.protection_notional_valid is False
    assert "requested_entry_notional_below_min_notional" in result.blockers
    assert "requested_protection_notional_below_min_notional" in result.blockers
    assert result.suggested_quantity == Decimal("0.013")
    assert result.suggested_minimum_notional_usdt == Decimal("21.86132")


def test_notional_sizing_blocks_when_computed_quantity_exceeds_owner_cap():
    result = compute_notional_sizing(
        symbol="ETH/USDT:USDT",
        side="long",
        target_notional_usdt=Decimal("22"),
        max_notional_usdt=Decimal("20"),
        market_rules=_eth_rules(),
    )

    assert result.status == "blocked"
    assert result.computed_quantity == Decimal("0.014")
    assert "computed_notional_exceeds_owner_max_notional" in result.blockers
