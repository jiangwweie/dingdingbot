"""Deterministic typed market inputs shared by domain and PostgreSQL tests."""

from decimal import Decimal

from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
    GenericSelectionMemberWindow,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec

HOUR = 3600000
CUTOFF = 100 * HOUR


def inputs(group: str) -> GenericSelectionInput:
    spec = generic_selection_spec(group)
    windows = tuple(GenericSelectionMemberWindow(
        exchange_instrument_id=member,
        closed_at_ms=tuple(CUTOFF - (spec.window_bars - 1 - i) * HOUR for i in range(spec.window_bars)),
        closes=tuple(Decimal(100) + Decimal(i * (index + 1)) / 100 for i in range(spec.window_bars)),
        qualified=True,
    ) for index, member in enumerate(spec.candidate_ids))
    return GenericSelectionInput(
        spec=spec, selection_epoch_id="epoch:1", feature_cutoff_at_ms=CUTOFF,
        decision_at_ms=CUTOFF, source_observed_at_ms=CUTOFF + 10, committed_at_ms=CUTOFF + 20,
        member_windows=windows, predecessor_snapshot=None,
    )
