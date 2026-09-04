from decimal import Decimal

from research.multi_strategy_selection.comparative_replay import build_fixed_comparative


def test_hypothetical_tradable_universe_cannot_change_rank() -> None:
    returns = {f"S{i:02d}": Decimal(i) for i in range(24)}
    full = build_fixed_comparative(returns)
    hypothetical_subset = {"S23", "S01", "S00"}

    assert full["S23"] == 1
    assert full["S01"] == 23
    assert {symbol: full[symbol] for symbol in hypothetical_subset}["S01"] == 23
