"""Exact committed runtime schema identity for the current kernel head."""

from __future__ import annotations

from typing import Final, Literal

TradingKernelSchemaRevision = Literal[
    "0003_portfolio_admission_observability"
]
CURRENT_SCHEMA_REVISION: Final[TradingKernelSchemaRevision] = (
    "0003_portfolio_admission_observability"
)
