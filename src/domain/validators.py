"""Shared validation helpers for runtime/backtest config contracts."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any, Iterable


TP_RATIO_SUM_TOLERANCE = Decimal("0.0001")


def coerce_decimal_fields(data: object, keys: Iterable[str]) -> object:
    """Convert selected dict values to Decimal while preserving other types."""
    if not isinstance(data, dict):
        return data

    converted = dict(data)
    for key in keys:
        if key in converted and converted[key] is not None and not isinstance(converted[key], Decimal):
            converted[key] = Decimal(str(converted[key]))
    return converted


def coerce_decimal_list_fields(data: object, keys: Iterable[str]) -> object:
    """Convert selected dict list values to list[Decimal]."""
    if not isinstance(data, dict):
        return data

    converted = dict(data)
    for key in keys:
        if key in converted and converted[key] is not None:
            converted[key] = [
                value if isinstance(value, Decimal) else Decimal(str(value))
                for value in converted[key]
            ]
    return converted


def validate_tp_contract(
    *,
    tp_levels: int,
    tp_ratios: Iterable[Decimal],
    tp_targets: Iterable[Decimal],
) -> None:
    """Validate TP arrays with a shared tolerance and semantics."""
    ratios = tuple(tp_ratios)
    targets = tuple(tp_targets)

    if len(ratios) != tp_levels:
        raise ValueError("tp_ratios length must match tp_levels")
    if len(targets) != tp_levels:
        raise ValueError("tp_targets length must match tp_levels")
    if any(ratio <= Decimal("0") for ratio in ratios):
        raise ValueError("tp_ratios must all be positive")
    if any(target <= Decimal("0") for target in targets):
        raise ValueError("tp_targets must all be positive")
    if abs(sum(ratios, Decimal("0")) - Decimal("1.0")) > TP_RATIO_SUM_TOLERANCE:
        raise ValueError("tp_ratios must sum to 1.0")


def stable_config_hash(payload: Any, *, schema_version: int = 1) -> str:
    """Build a stable, compact hash for config-like payloads."""
    raw = json.dumps(
        {
            "hash_schema_version": schema_version,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
