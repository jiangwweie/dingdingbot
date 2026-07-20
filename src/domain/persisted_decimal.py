"""Canonical Decimal values at the PostgreSQL Numeric(36,18) boundary."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_UP


PERSISTENCE_QUANTUM = Decimal("0.000000000000000001")


def canonical_persisted_decimal(value: Decimal, *, semantic: str = "exact") -> Decimal:
    """Return the stable Decimal representation used by PG payload/hash checks.

    Allowances never round upward and consumption never rounds downward.  Exact
    venue values are already instrument-quantized before this boundary and use
    deterministic half-even persistence rounding.
    """

    rounding = {
        "allowance": ROUND_DOWN,
        "consumption": ROUND_UP,
        "exact": ROUND_HALF_EVEN,
        "observation": ROUND_HALF_EVEN,
    }.get(semantic)
    if rounding is None:
        raise ValueError(f"persisted_decimal_semantic_unknown:{semantic}")
    return Decimal(value).quantize(PERSISTENCE_QUANTUM, rounding=rounding)
