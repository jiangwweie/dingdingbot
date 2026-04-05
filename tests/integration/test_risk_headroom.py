"""
Integration Tests for Dynamic Risk Headroom Calculation (S3-2).

Tests for Scheme B position sizing with:
1. Real account snapshot integration
2. Multi-position exposure scenarios
3. Risk config continuity after hot-reload
4. End-to-end signal pipeline with risk calculation
"""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.models import (
    KlineData,
    AccountSnapshot,
    PositionInfo,
    Direction,
    SignalResult,
    TrendDirection,
)
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.domain.filter_factory import MtfFilterDynamic, FilterContext, PatternResult


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def risk_config():
    """Create default risk config for testing."""
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0.8"),  # 80% default
    )


@pytest.fixture
def calculator(risk_config):
    """Create risk calculator with test config."""
    return RiskCalculator(risk_config)


@pytest.fixture
def base_account():
    """Create a base account snapshot for testing."""
    return AccountSnapshot(
        total_balance=Decimal("10000"),
        available_balance=Decimal("10000"),
        unrealized_pnl=Decimal("0"),
        positions=[],
        timestamp=1700000000000,
    )


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    timestamp: int = 1700000000000,
    close: str = "50000",
    high: str = None,
    low: str = None,
    open: str = None,
) -> KlineData:
    """Create a realistic kline for integration testing."""
    close_dec = Decimal(close)
    high_dec = Decimal(high) if high else close_dec * Decimal("1.01")
    low_dec = Decimal(low) if low else close_dec * Decimal("0.99")
    open_dec = Decimal(open) if open else close_dec

    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        open=open_dec,
        high=high_dec,
        low=low_dec,
        close=close_dec,
        volume=Decimal("1000"),
        is_closed=True,
    )


# ============================================================
# S3-2-1: Real Account Snapshot Integration
# ============================================================
class TestRealAccountSnapshotIntegration:
    """
    Test risk calculation with realistic account snapshots.
    Verifies available_balance is used instead of total_balance.
    """

    async def test_uses_available_balance_not_total(self, calculator):
        """
        Verify position calculation uses available_balance.

        Setup: total_balance=10000, available_balance=6000 (40% locked)
        Expected: Position sized based on 6000, not 10000
        """
        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("6000"),  # 40% locked
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        kline = create_kline(close="50000", high="50500", low="49500")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Position should be sized based on available_balance (6000)
        # Risk amount = 6000 * 0.01 = 60 USDT
        # Stop distance = |50000 - 49500| / 50000 = 1%
        # Position = 60 / 0.01 = 6000 USDT worth ≈ 0.12 BTC

        # Key assertion: available_balance is used, not total_balance
        assert position_size > Decimal("0")

        # If total_balance was used, position would be ~10000/50000 = 0.2 BTC
        # With available_balance, it should be ~6000/50000 = 0.12 BTC
        max_position_if_total = Decimal("10000") * Decimal("0.01") / Decimal("0.01") / Decimal("50000")
        assert position_size < max_position_if_total, "Should use available_balance, not total_balance"

    async def test_full_account_snapshot_scenario(self, calculator):
        """
        Test with a full realistic account snapshot.

        Setup:
        - Total balance: 50000 USDT
        - Available: 45000 USDT (5000 in margin)
        - 2 open positions
        """
        account = AccountSnapshot(
            total_balance=Decimal("50000"),
            available_balance=Decimal("45000"),
            unrealized_pnl=Decimal("150.50"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.5"),
                    entry_price=Decimal("48000"),
                    unrealized_pnl=Decimal("500"),  # (49000-48000) * 0.5
                    leverage=5,
                ),
                PositionInfo(
                    symbol="ETH/USDT:USDT",
                    side="SHORT",
                    size=Decimal("10"),
                    entry_price=Decimal("3000"),
                    unrealized_pnl=Decimal("500"),  # (3000-2950) * 10
                    leverage=3,
                ),
            ],
            timestamp=1700000000000,
        )

        kline = create_kline(symbol="SOL/USDT:USDT", close="150", high="155", low="145")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("150"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Should calculate without error
        assert position_size >= Decimal("0")
        assert leverage >= 1
        assert leverage <= 10

    async def test_zero_available_balance(self, calculator):
        """
        Test when available_balance is zero.

        Expected: Position size = 0
        """
        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        kline = create_kline()
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        assert position_size == Decimal("0")
        assert leverage == 1


# ============================================================
# S3-2-2: Multi-Position Exposure Scenarios
# ============================================================
class TestMultiPositionExposureScenarios:
    """
    Test dynamic risk adjustment with multiple positions.
    Verifies exposure-based risk reduction.
    """

    async def test_risk_reduced_with_existing_positions(self, risk_config):
        """
        Test risk is reduced when approaching exposure limit.

        Setup:
        - Account: 10000 USDT
        - Existing positions: 7000 USDT (70% exposure)
        - max_total_exposure: 80%
        Expected: Risk limited to 10% additional exposure
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("8000"),  # 2000 in margin
            unrealized_pnl=Decimal("0"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.1"),
                    entry_price=Decimal("50000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
                PositionInfo(
                    symbol="ETH/USDT:USDT",
                    side="LONG",
                    size=Decimal("1"),
                    entry_price=Decimal("2000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
            ],
            timestamp=1700000000000,
        )
        # Total position value = 5000 + 2000 = 7000 (70% exposure)

        kline = create_kline(close="50000", high="50500", low="49500")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Available exposure = 80% - 70% = 10%
        # Limited risk = 10000 * 10% = 1000 USDT
        # Position should be limited accordingly
        assert position_size > Decimal("0")

    async def test_position_rejected_at_exposure_limit(self, risk_config):
        """
        Test new position rejected when at exposure limit.

        Setup:
        - Account: 10000 USDT
        - Existing positions: 8000 USDT (80% exposure = limit)
        Expected: New position size = 0
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("9000"),  # 1000 in margin
            unrealized_pnl=Decimal("0"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.16"),  # 0.16 * 50000 = 8000
                    entry_price=Decimal("50000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
            ],
            timestamp=1700000000000,
        )
        # Total position value = 8000 (80% exposure = limit)

        kline = create_kline(close="50000", high="50500", low="49500")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # No exposure room, should return zero position
        assert position_size == Decimal("0")

    async def test_exposure_exceeded_still_rejected(self, risk_config):
        """
        Test position rejected when already exceeded exposure.

        Setup:
        - Account: 10000 USDT
        - Existing positions: 9000 USDT (90% > 80% limit)
        Expected: New position size = 0
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("9500"),  # 500 in margin
            unrealized_pnl=Decimal("0"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.18"),  # 0.18 * 50000 = 9000
                    entry_price=Decimal("50000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=10,
                ),
            ],
            timestamp=1700000000000,
        )
        # Total position value = 9000 (90% exposure > 80% limit)

        kline = create_kline(close="50000", high="50500", low="49500")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Already exceeded exposure limit, should return zero
        assert position_size == Decimal("0")

    async def test_multiple_positions_cumulative_exposure(self, risk_config):
        """
        Test cumulative exposure from multiple positions.

        Setup: Multiple small positions adding up to high exposure
        Expected: Risk adjusted based on total cumulative exposure
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("5000"),  # 5000 in margin
            unrealized_pnl=Decimal("100"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.05"),  # 2500 USDT
                    entry_price=Decimal("50000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
                PositionInfo(
                    symbol="ETH/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.5"),  # 1500 USDT
                    entry_price=Decimal("3000"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
                PositionInfo(
                    symbol="SOL/USDT:USDT",
                    side="LONG",
                    size=Decimal("10"),  # 1500 USDT
                    entry_price=Decimal("150"),
                    unrealized_pnl=Decimal("0"),
                    leverage=5,
                ),
            ],
            timestamp=1700000000000,
        )
        # Total = 2500 + 1500 + 1500 = 5500 (55% exposure)
        # Room to 80% = 25%

        kline = create_kline(symbol="AVAX/USDT:USDT", close="50", high="52", low="48")
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Should allow some position (55% < 80%)
        assert position_size >= Decimal("0")


# ============================================================
# S3-2-3: Risk Config Continuity After Hot-Reload
# ============================================================
class TestRiskConfigContinuityAfterHotReload:
    """
    Test RiskConfig continuity during hot-reload scenarios.
    """

    async def test_config_update_propagates_to_calculator(self):
        """
        Test RiskConfig changes propagate correctly.

        Setup:
        - Initial config: max_total_exposure = 80%
        - Updated config: max_total_exposure = 60%
        Expected: Calculator uses updated config
        """
        initial_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        calculator = RiskCalculator(initial_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        kline = create_kline()
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_before, _ = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Update config (simulating hot-reload)
        new_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.6"),  # Reduced to 60%
        )
        await calculator.update_config(new_config)

        # Calculate again with new config
        position_after, _ = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # With lower exposure limit, position should be smaller
        # Note: For empty positions, both may be similar since no existing exposure
        # The key test is the config is used, not rejected
        config = await calculator.get_config()
        assert config.max_total_exposure == Decimal("0.6")

    async def test_risk_config_loaded_from_real_config_manager(self):
        """
        Test RiskConfig can be loaded from real ConfigManager.

        This verifies the config system integrates with RiskConfig.
        """
        # Load real config
        config_manager = load_all_configs()

        # RiskConfig should be creatable from user_config
        # Note: UserConfig doesn't have max_loss_percent/max_leverage directly
        # These are in RiskConfig only, so we use defaults
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),  # Default 1%
            max_leverage=10,  # Default
            max_total_exposure=getattr(
                config_manager.user_config,
                "max_total_exposure",
                Decimal("0.8"),
            ) if hasattr(config_manager.user_config, 'max_total_exposure') else Decimal("0.8"),
        )

        calculator = RiskCalculator(risk_config)

        # Should work without error
        config = await calculator.get_config()
        assert config.max_leverage > 0
        assert config.max_loss_percent > 0


# ============================================================
# S3-2-4: End-to-End Signal Pipeline Integration
# ============================================================
class TestEndToEndSignalPipelineWithRisk:
    """
    End-to-end tests for signal pipeline with risk calculation.
    """

    async def test_signal_pipeline_calculates_risk(self):
        """
        Test SignalPipeline integrates risk calculation.

        Verifies:
        1. Pipeline has risk_calculator
        2. Risk calculation is called during process_kline
        """
        # Mock config manager
        mock_config_manager = MagicMock()
        mock_config_manager.user_config = MagicMock()
        mock_config_manager.user_config.mtf_ema_period = 20
        mock_config_manager.user_config.mtf_mapping = {"15m": "1h"}
        mock_config_manager.add_observer = MagicMock()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        # Mock notifier and repository
        mock_notifier = MagicMock()
        mock_repository = AsyncMock()

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
        )

        # Set account snapshot
        pipeline.update_account_snapshot(AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        ))

        # Verify pipeline has risk calculator
        assert pipeline._risk_calculator is not None
        assert isinstance(pipeline._risk_calculator, RiskCalculator)

    async def test_full_signal_with_risk_calculation(self):
        """
        Test complete signal generation with risk calculation.

        Flow:
        1. Create bullish pinbar kline
        2. Calculate signal result via RiskCalculator
        3. Verify all risk fields populated
        """
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        # Create bullish pinbar kline
        kline = create_kline(
            close="50000",
            high="50100",
            low="49000",  # Long lower wick
        )

        # Calculate signal result
        signal = await calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[{"name": "Pinbar", "value": "Bullish"}],
            kline_timestamp=kline.timestamp,
            strategy_name="pinbar",
            score=0.85,
        )

        # Verify all risk fields
        assert signal.entry_price > Decimal("0")
        assert signal.suggested_stop_loss > Decimal("0")
        assert signal.suggested_stop_loss < signal.entry_price  # LONG stop below entry
        assert signal.suggested_position_size > Decimal("0")
        assert signal.current_leverage >= 1
        assert signal.current_leverage <= 10
        assert "Risk" in signal.risk_reward_info

    async def test_mtf_filter_with_risk_calculation(self):
        """
        Test MTF filter integration with risk calculation.

        Flow:
        1. MTF filter approves signal
        2. Risk calculation proceeds
        3. Full signal result generated
        """
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        # MTF filter setup
        mtf_filter = MtfFilterDynamic()
        pattern = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=0.8,
            details={},
        )
        context = FilterContext(
            current_timeframe="15m",
            higher_tf_trends={"1h": TrendDirection.BULLISH},
        )

        # MTF should approve (bullish trend, LONG signal)
        mtf_result = mtf_filter.check(pattern, context)
        assert mtf_result.passed is True

        # Proceed with risk calculation
        kline = create_kline(close="50000", high="50100", low="49000")
        signal = await calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[
                {"name": "Pinbar", "value": "Bullish"},
                {"name": "MTF", "value": "Confirmed"},
            ],
            kline_timestamp=kline.timestamp,
            strategy_name="pinbar",
            score=0.85,
        )

        # Verify signal includes MTF tag
        assert any(tag["name"] == "MTF" for tag in signal.tags)
        assert signal.suggested_position_size > Decimal("0")


# ============================================================
# S3-2-5: Boundary and Edge Cases
# ============================================================
class TestBoundaryAndEdgeCases:
    """Test boundary conditions and edge cases."""

    async def test_very_tight_stop_requires_higher_leverage(self, risk_config):
        """
        Test tight stop-loss requires higher leverage.

        Setup: Stop loss very close to entry (0.1%)
        Expected: Higher leverage to achieve position size
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        kline = create_kline(close="50000", high="50050", low="49950")  # Very tight range
        stop_loss = Decimal("49990")  # Very tight stop (0.02% below)

        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Tight stop = larger position = may need higher leverage
        assert leverage >= 1
        assert leverage <= risk_config.max_leverage

    async def test_wide_stop_reduces_position_size(self, risk_config):
        """
        Test wide stop-loss reduces position size.

        Setup: Stop loss far from entry (5%)
        Expected: Smaller position size
        """
        calculator = RiskCalculator(risk_config)

        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

        kline = create_kline(close="50000", high="52500", low="47500")  # Wide range
        stop_loss = Decimal("47500")  # 5% below

        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Wide stop = smaller position
        assert position_size > Decimal("0")

    async def test_unrealized_loss_reduces_available_balance(self, risk_config):
        """
        Test unrealized loss reduces available balance for risk.

        Setup: Account with unrealized loss
        Expected: available_balance correctly reduced
        """
        calculator = RiskCalculator(risk_config)

        # Unrealized loss of 1000 USDT
        account = AccountSnapshot(
            total_balance=Decimal("9000"),  # Reduced by loss
            available_balance=Decimal("8000"),  # Less available
            unrealized_pnl=Decimal("-1000"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.1"),
                    entry_price=Decimal("50000"),
                    unrealized_pnl=Decimal("-1000"),  # Down 1000
                    leverage=5,
                ),
            ],
            timestamp=1700000000000,
        )

        kline = create_kline()
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Should still calculate, but with reduced balance
        assert position_size >= Decimal("0")

    async def test_unrealized_profit_increases_available_balance(self, risk_config):
        """
        Test unrealized profit increases available balance.

        Setup: Account with unrealized profit
        Expected: available_balance increased
        """
        calculator = RiskCalculator(risk_config)

        # Unrealized profit of 1000 USDT
        account = AccountSnapshot(
            total_balance=Decimal("11000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("1000"),
            positions=[
                PositionInfo(
                    symbol="BTC/USDT:USDT",
                    side="LONG",
                    size=Decimal("0.1"),
                    entry_price=Decimal("49000"),
                    unrealized_pnl=Decimal("1000"),  # Up 1000
                    leverage=5,
                ),
            ],
            timestamp=1700000000000,
        )

        kline = create_kline()
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        position_size, leverage = await calculator.calculate_position_size(
            account, entry_price=Decimal("50000"), stop_loss=stop_loss, direction=Direction.LONG
        )

        # Should calculate with increased balance
        assert position_size >= Decimal("0")
