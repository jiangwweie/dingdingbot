"""
Smoke test for Donchian Distance Filter in backtest context.

Validates:
1. Filter can be created via FilterFactory
2. Filter integrates with strategy engine lifecycle
3. Filter correctly filters signals near Donchian high
"""
from decimal import Decimal
from datetime import datetime, timezone

from src.domain.filter_factory import FilterFactory, FilterContext
from src.domain.models import KlineData, Direction, PatternResult


def test_donchian_filter_smoke():
    """Smoke test: filter creation and basic behavior."""
    print("\n=== Donchian Distance Filter Smoke Test ===\n")

    # 1. Create filter via factory
    print("1. Creating filter via FilterFactory...")
    config = {
        "type": "donchian_distance",
        "enabled": True,
        "params": {
            "lookback": 20,
            "max_distance_to_high_pct": "-0.016809"
        }
    }

    filter = FilterFactory.create(config)
    print(f"   ✓ Filter created: {filter.name}")
    print(f"   ✓ Lookback: {filter._lookback}")
    print(f"   ✓ Threshold: {filter._max_distance_to_high_pct}")
    print(f"   ✓ Enabled: {filter._enabled}")

    # 2. Simulate backtest lifecycle: update_state for 25 bars
    print("\n2. Simulating backtest lifecycle (25 bars)...")
    symbol = "ETH/USDT:USDT"
    timeframe = "1h"

    # Build history: highs ranging from 100 to 124
    for i in range(25):
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000) + i * 3600000
        kline = KlineData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open=Decimal(str(100 + i)),
            high=Decimal(str(105 + i)),
            low=Decimal(str(95 + i)),
            close=Decimal(str(100 + i)),
            volume=Decimal("1000"),
            is_closed=True
        )
        filter.update_state(kline, symbol, timeframe)

    print(f"   ✓ Updated state for 25 bars")

    # 3. Check state
    state = filter._state.get(f"{symbol}:{timeframe}")
    print(f"   ✓ State window size: {len(state['highs'])} (expected: 21)")
    assert len(state['highs']) == 21, "Window should be lookback+1"

    # 4. Test signal near Donchian high (should be filtered)
    print("\n3. Testing LONG signal near Donchian high...")
    # Previous 20 bars: highs [110, 111, ..., 129]
    # Current bar: close=128, high=135
    # Donchian high (excluding current) = 129
    # Distance = (128 - 129) / 129 = -0.00775
    # Threshold = -0.016809
    # -0.00775 >= -0.016809 → TOO CLOSE → filtered

    current_kline = KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=int(datetime.now(timezone.utc).timestamp() * 1000),
        open=Decimal("125"),
        high=Decimal("135"),  # New high
        low=Decimal("120"),
        close=Decimal("128"),  # Close to high
        volume=Decimal("1000"),
        is_closed=True
    )
    filter.update_state(current_kline, symbol, timeframe)

    pattern = PatternResult(
        strategy_name="pinbar",
        direction=Direction.LONG,
        score=Decimal("0.8"),
        details={}
    )

    context = FilterContext(
        higher_tf_trends={},
        current_timeframe=timeframe,
        kline=current_kline,
        current_price=current_kline.close
    )

    result = filter.check(pattern, context)
    print(f"   ✓ Signal direction: LONG")
    print(f"   ✓ Current close: {current_kline.close}")
    print(f"   ✓ Donchian high: {result.metadata['donchian_high']}")
    print(f"   ✓ Distance: {result.metadata['distance_pct']:.6f}")
    print(f"   ✓ Threshold: {result.metadata['threshold']}")
    print(f"   ✓ Result: {'PASSED' if result.passed else 'FILTERED'}")
    print(f"   ✓ Reason: {result.reason}")

    assert result.passed is False, "Signal near high should be filtered"
    assert result.reason == "too_close_to_donchian_high"

    # 5. Test signal far from Donchian high (should pass)
    print("\n4. Testing LONG signal far from Donchian high...")
    # Current bar: close=110, high=135
    # Donchian high (excluding current) = 129
    # Distance = (110 - 129) / 129 = -0.1473
    # Threshold = -0.016809
    # -0.1473 < -0.016809 → FAR ENOUGH → passes

    current_kline2 = KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=int(datetime.now(timezone.utc).timestamp() * 1000) + 3600000,
        open=Decimal("110"),
        high=Decimal("135"),
        low=Decimal("105"),
        close=Decimal("110"),  # Far from high
        volume=Decimal("1000"),
        is_closed=True
    )
    filter.update_state(current_kline2, symbol, timeframe)

    context2 = FilterContext(
        higher_tf_trends={},
        current_timeframe=timeframe,
        kline=current_kline2,
        current_price=current_kline2.close
    )

    result2 = filter.check(pattern, context2)
    print(f"   ✓ Signal direction: LONG")
    print(f"   ✓ Current close: {current_kline2.close}")
    print(f"   ✓ Donchian high: {result2.metadata['donchian_high']}")
    print(f"   ✓ Result: {'PASSED' if result2.passed else 'FILTERED'}")
    print(f"   ✓ Reason: {result2.reason}")

    assert result2.passed is True, "Signal far from high should pass"

    # 6. Test disabled filter
    print("\n5. Testing disabled filter...")
    disabled_filter = FilterFactory.create({
        "type": "donchian_distance",
        "enabled": False,
        "params": {"lookback": 20}
    })

    result3 = disabled_filter.check(pattern, context)
    print(f"   ✓ Result: {'PASSED' if result3.passed else 'FILTERED'}")
    print(f"   ✓ Reason: {result3.reason}")

    assert result3.passed is True, "Disabled filter should always pass"
    assert result3.reason == "filter_disabled"

    print("\n=== All smoke tests passed ✓ ===\n")


if __name__ == "__main__":
    test_donchian_filter_smoke()
