"""Exact committed runtime schema identity for the current kernel head."""

from __future__ import annotations

from typing import Final, Literal

TradingKernelSchemaRevision = Literal[
    "0004_owner_control_plane",
    "0005_tradfi_instrument_center",
    "0006_sor_dynamic_selection_v0",
    "0007_exit_profile_authority_v1",
]
CURRENT_SCHEMA_REVISION: Final[TradingKernelSchemaRevision] = (
    "0007_exit_profile_authority_v1"
)
