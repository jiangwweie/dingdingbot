from decimal import Decimal

import pandas as pd

from research.multi_strategy_selection.analyze_features import (
    CPM_FEATURES,
    MARKET_FEATURES,
    freeze_cutoffs,
)
from research.multi_strategy_selection.market_data import INTERVAL_MS
from src.trading_kernel.application.produce_strategy_signal import (
    evaluate_strategy_snapshot,
)
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.detector import detector_for
from src.trading_kernel.domain.market import ClosedCandle, MarketSnapshot
from src.trading_kernel.domain.strategy_registry import strategy_contract_for


def _candles(symbol: str, lookback: int, cutoff: int) -> tuple[ClosedCandle, ...]:
    return tuple(
        ClosedCandle(
            open_time_ms=cutoff - (lookback + 1 - index) * 3_600_000,
            close_time_ms=cutoff - (lookback - index) * 3_600_000,
            open=Decimal(100 + index),
            high=Decimal(101 + index),
            low=Decimal(99 + index),
            close=Decimal(100 + index),
            volume=Decimal(1),
        )
        for index in range(lookback + 1)
    )


def _rank_candles(index: int, cutoff: int) -> tuple[ClosedCandle, ...]:
    return tuple(
        ClosedCandle(
            open_time_ms=cutoff - (13 - offset) * 3_600_000,
            close_time_ms=cutoff - (12 - offset) * 3_600_000,
            open=Decimal(100) + Decimal(offset * (index + 1)) / Decimal(10),
            high=Decimal(101) + Decimal(offset * (index + 1)) / Decimal(10),
            low=Decimal(99) + Decimal(offset * (index + 1)) / Decimal(10),
            close=Decimal(100) + Decimal(offset * (index + 1)) / Decimal(10),
            volume=Decimal(1),
        )
        for offset in range(13)
    )


def test_mpg_and_mi_rank_use_production_projection_with_all_24_members() -> None:
    cutoff = 2_000_000_000_000
    members = tuple(f"binance-usdm:S{i:02d}:perpetual" for i in range(24))
    windows = tuple(
        ComparativeMemberWindow(
            exchange_instrument_id=member,
            candles_1h=_rank_candles(index, cutoff),
        )
        for index, member in enumerate(members)
    )
    for group, lookback in (("MPG-001", 8), ("MI-001", 12)):
        projection = build_comparative_universe_projection(
            event_spec_id=f"event:{group}",
            universe_version_id="research:24",
            strategy_group_id=group,
            exchange_instrument_ids=members,
            closed_bar_time_ms=cutoff,
            lookback_bars=lookback,
            freshness_window_ms=3_600_000,
            member_windows=windows,
        )
        assert len(projection.comparative_strength.members) == 24
        assert sorted(item.rank for item in projection.comparative_strength.members) == list(range(1, 25))


def test_replay_evaluation_is_direct_current_dev_detector_invocation() -> None:
    event_spec_id = "event_spec:CPM-RO-001:CPM-LONG:v3"
    contract = strategy_contract_for(event_spec_id)
    cutoff = 2_000_000_000_000
    snapshot = MarketSnapshot(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        trigger_candle_close_time_ms=cutoff,
        candles_1h=_candles("BTCUSDT", 24, cutoff),
        candles_4h=tuple(
            candle.model_copy(
                update={
                    "open_time_ms": cutoff - (25 - index) * 14_400_000,
                    "close_time_ms": cutoff - (24 - index) * 14_400_000,
                }
            )
            for index, candle in enumerate(_candles("BTCUSDT", 24, cutoff))
        ),
    )
    assert evaluate_strategy_snapshot(contract, snapshot) == detector_for(event_spec_id).evaluate(snapshot)


def test_discovery_cutoffs_ignore_holdout_values() -> None:
    discovery = pd.DataFrame(
        {
            "feature_cutoff_at_ms": [1_786_000_000_000] * 6,
            **{feature: [1, 2, 3, 4, 5, 6] for feature in MARKET_FEATURES},
        }
    )
    holdout = discovery.copy()
    holdout["feature_cutoff_at_ms"] = 1_787_000_000_000
    holdout[list(MARKET_FEATURES)] = 1_000_000
    candidate = pd.DataFrame(
        {
            "feature_cutoff_at_ms": [1_786_000_000_000] * 6 + [1_787_000_000_000] * 6,
            "directional_efficiency_24h": [1, 2, 3, 4, 5, 6] + [999] * 6,
        }
    )
    first = freeze_cutoffs(pd.concat([discovery, holdout]), candidate)
    second = freeze_cutoffs(discovery, candidate.iloc[:6])
    assert first == second


def test_feature_scope_contains_no_ticker_or_detector_duplicate_feature() -> None:
    assert CPM_FEATURES == (*MARKET_FEATURES, "directional_efficiency_24h")
    assert all("symbol" not in feature and "rank" not in feature for feature in CPM_FEATURES)
    assert set(MARKET_FEATURES) == {
        "cross_sectional_dispersion_24h",
        "avg_cross_asset_corr_24h",
        "market_breadth_24h",
        "market_rv_24h",
        "market_return_24h",
    }


def test_archive_boundary_is_canonicalized_to_runtime_close_semantics() -> None:
    assert INTERVAL_MS == {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}
