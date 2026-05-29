from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.directional_opportunity_forward_outcome import pack_forward_outcome_windows
from src.domain.directional_opportunity_pack import (
    DirectionalPackCandidateRole,
    btc_eth_sol_bnb_directional_opportunity_pack,
)
from src.domain.forward_outcome_review import calculate_forward_outcomes
from src.domain.historical_ohlcv import HistoricalOhlcvBar
from src.domain.historical_signal_evaluation import HistoricalForwardOutcomeStatus
from src.domain.strategy_family_signal import (
    SignalSide,
    SignalType,
    StrategyFamilySignalOutput,
)


NOW_MS = 1770000000000
HOUR_MS = 60 * 60 * 1000


def _bar(index: int, close: Decimal) -> HistoricalOhlcvBar:
    return HistoricalOhlcvBar(
        source="test",
        market="historical",
        symbol="BTC/USDT:USDT",
        timeframe="1h",
        open_time_ms=NOW_MS + index * HOUR_MS,
        open=close,
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("100"),
        quote_volume=None,
        close_time_ms=NOW_MS + (index + 1) * HOUR_MS - 1,
        created_at_ms=NOW_MS,
    )


def _signal_output() -> StrategyFamilySignalOutput:
    return StrategyFamilySignalOutput(
        signal_id="sig-directional-pack-001",
        evaluation_id="eval-directional-pack-001",
        strategy_family_id="PULLBACK-CONT-001",
        strategy_family_version_id="PULLBACK-CONT-001",
        playbook_id="PULLBACK-CONT-001",
        symbol="BTC/USDT:USDT",
        timestamp_ms=NOW_MS,
        timeframe="1h",
        signal_type=SignalType.WOULD_ENTER,
        side=SignalSide.LONG,
        confidence=Decimal("0.5"),
        required_execution_mode="observe_only",
    )


def test_directional_pack_windows_convert_to_forward_outcome_request_windows():
    request = pack_forward_outcome_windows(btc_eth_sol_bnb_directional_opportunity_pack())

    assert request.primary_timeframe == "1h"
    assert request.windows == {
        "1h": 1,
        "4h": 4,
        "12h": 12,
        "24h": 24,
        "72h": 72,
        "7d": 168,
    }


def test_directional_pack_windows_work_with_existing_forward_outcome_calculator():
    request = pack_forward_outcome_windows(btc_eth_sol_bnb_directional_opportunity_pack())
    entry = _bar(0, Decimal("100"))
    future = [_bar(index, Decimal("100") + Decimal(index)) for index in range(1, 169)]

    outcomes = calculate_forward_outcomes(
        run_id="directional-pack-window-proof",
        signal_output=_signal_output(),
        entry_bar=entry,
        future_bars=future,
        created_at_ms=NOW_MS,
        windows=request.windows,
    )

    assert [outcome.window_label for outcome in outcomes] == ["1h", "4h", "12h", "24h", "72h", "7d"]
    assert [outcome.bars_ahead for outcome in outcomes] == [1, 4, 12, 24, 72, 168]
    assert all(outcome.status == HistoricalForwardOutcomeStatus.COMPLETE for outcome in outcomes)
    assert outcomes[0].time_to_mfe_bars == 1
    assert outcomes[-1].time_to_mfe_bars == 168


def test_directional_forward_outcome_adapter_preserves_cpm_reference_role():
    pack = btc_eth_sol_bnb_directional_opportunity_pack()
    by_id = {candidate.family_id: candidate for candidate in pack.candidate_families}

    pack_forward_outcome_windows(pack)

    assert by_id["CPM-RO-001"].candidate_roles == [
        DirectionalPackCandidateRole.BENCHMARK_COMPONENT,
        DirectionalPackCandidateRole.RESEARCH_REFERENCE,
    ]
    assert DirectionalPackCandidateRole.CAMPAIGN_ENGINE_CANDIDATE not in by_id[
        "CPM-RO-001"
    ].candidate_roles


def test_directional_forward_outcome_adapter_rejects_unsupported_primary_timeframe():
    with pytest.raises(ValueError, match="primary_timeframe=1h"):
        pack_forward_outcome_windows(
            btc_eth_sol_bnb_directional_opportunity_pack(),
            primary_timeframe="4h",
        )


def test_directional_forward_outcome_adapter_output_has_no_runtime_order_surface():
    payload = pack_forward_outcome_windows(
        btc_eth_sol_bnb_directional_opportunity_pack()
    ).model_dump_json().lower()

    forbidden_fragments = [
        "executionintent",
        "execution_intent",
        "order_router",
        "submit_order",
        "cancel_order",
        "place_order",
        "flatten",
        "close_position",
        "leverage",
        "signaloutput",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in payload
