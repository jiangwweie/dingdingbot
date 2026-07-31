"""Exact committed runtime schema identity for the current kernel head."""

from __future__ import annotations

from typing import Final, Literal

TradingKernelSchemaRevision = Literal[
    "0002_sor_v3_strategy_group_capacity"
]
CURRENT_SCHEMA_REVISION: Final[TradingKernelSchemaRevision] = (
    "0002_sor_v3_strategy_group_capacity"
)
