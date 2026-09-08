"""Deterministic typed market inputs shared by domain and PostgreSQL tests."""

from decimal import Decimal

from src.trading_kernel.domain.generic_selection_core import (
    GenericSelectionInput,
)
from src.trading_kernel.domain.generic_selection_source import (
    GenericSelectionCandle,
    GenericSelectionMemberWindow,
    GenericSelectionQualification,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.product import InstrumentProductProfile

HOUR = 3600000
CUTOFF = 100 * HOUR


def inputs(group: str) -> GenericSelectionInput:
    spec = generic_selection_spec(group)
    windows = tuple(GenericSelectionMemberWindow(
        exchange_instrument_id=member,
        candles=tuple(GenericSelectionCandle(
            open_time_ms=CUTOFF-(spec.window_bars-i)*HOUR, close_time_ms=CUTOFF-(spec.window_bars-1-i)*HOUR,
            open=Decimal(100), high=Decimal(200), low=Decimal(99),
            close=Decimal(100)+Decimal(i*(index+1))/100, base_volume=Decimal(10), quote_volume=Decimal(1000),
        ) for i in range(spec.window_bars)),
        qualification=GenericSelectionQualification(event_spec_id=spec.event_spec_id,
            product_profile=InstrumentProductProfile(exchange_instrument_id=member, product_family="crypto_perpetual",
                asset_class="crypto", contract_type="PERPETUAL", underlying_type="CRYPTO", entry_session_policy="continuous", status="candidate"),
            venue_contract_type="PERPETUAL", venue_margin_asset="USDT", venue_status="TRADING", observed_at_ms=CUTOFF+1),
    ) for index, member in enumerate(spec.candidate_ids))
    return GenericSelectionInput(
        spec=spec, selection_epoch_id="epoch:1", feature_cutoff_at_ms=CUTOFF,
        decision_at_ms=CUTOFF, source_observed_at_ms=CUTOFF + 10, committed_at_ms=CUTOFF + 20,
        member_windows=windows, predecessor_snapshot=None,
    )


def shift_window(window: GenericSelectionMemberWindow, step_ms: int) -> GenericSelectionMemberWindow:
    return window.model_copy(update={
        "candles": tuple(c.model_copy(update={"open_time_ms": c.open_time_ms+step_ms, "close_time_ms": c.close_time_ms+step_ms}) for c in window.candles),
        "qualification": window.qualification.model_copy(update={"observed_at_ms": window.qualification.observed_at_ms+step_ms}),
    })


def qualify_window(window: GenericSelectionMemberWindow, qualified: bool) -> GenericSelectionMemberWindow:
    return window.model_copy(update={"qualification": window.qualification.model_copy(update={"venue_status": "TRADING" if qualified else "PENDING_TRADING"})})
