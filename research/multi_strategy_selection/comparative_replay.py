"""Fixed 24-member comparative ranking for Stage-2 replay."""

from decimal import Decimal


def build_fixed_comparative(returns: dict[str, Decimal]) -> dict[str, int]:
    if len(returns) != 24 or len(set(returns)) != 24:
        raise ValueError("comparative replay requires exact 24-member universe")
    ranked = sorted(returns.items(), key=lambda item: (-item[1], item[0]))
    return {symbol: rank for rank, (symbol, _) in enumerate(ranked, start=1)}
