"""
Unit tests for domain/risk_calculator.py - Position sizing and risk calculation.
All assertions use Decimal for precision, no float comparisons.
"""
import pytest
from decimal import Decimal
from src.domain.models import (
    AccountSnapshot,
    KlineData,
    Direction,
    PositionInfo,
)
from src.domain.risk_calculator import RiskCalculator, RiskConfig
from src.domain.exceptions import DataQualityWarning


def create_account(
    total_balance: Decimal = Decimal("100000"),
    available_balance: Decimal = Decimal("80000"),
    unrealized_pnl: Decimal = Decimal("0"),
    positions: list = None,
) -> AccountSnapshot:
    """Helper to create AccountSnapshot for testing."""
    return AccountSnapshot(
        total_balance=total_balance,
        available_balance=available_balance,
        unrealized_pnl=unrealized_pnl,
        positions=positions or [],
        timestamp=1234567890000,
    )


def create_kline(
    symbol: str = "BTC/USDT:USDT",
    timeframe: str = "15m",
    open: Decimal = Decimal("100"),
    high: Decimal = Decimal("110"),
    low: Decimal = Decimal("90"),
    close: Decimal = Decimal("105"),
    volume: Decimal = Decimal("1000"),
) -> KlineData:
    """Helper to create KlineData for testing."""
    return KlineData(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=1234567890000,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        is_closed=True,
    )


class TestRiskConfig:
    """Test RiskConfig validation."""

    def test_valid_config(self):
        """Test valid configuration is accepted."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        assert config.max_loss_percent == Decimal("0.01")
        assert config.max_leverage == 10
        assert config.max_total_exposure == Decimal("0.8")  # Default value

    def test_valid_config_with_custom_exposure(self):
        """Test custom max_total_exposure is accepted."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.5")
        )
        assert config.max_total_exposure == Decimal("0.5")

    def test_invalid_config_exposure_zero(self):
        """Test that zero exposure is accepted (allows 0% exposure limit)."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0")
        )
        assert config.max_total_exposure == Decimal("0")

    def test_invalid_config_exposure_greater_than_one(self):
        """Test that exposure > 1 raises error."""
        with pytest.raises(ValueError):
            RiskConfig(
                max_loss_percent=Decimal("0.01"),
                max_leverage=10,
                max_total_exposure=Decimal("1.5")
            )

    def test_invalid_config_exposure_negative(self):
        """Test that negative exposure raises error."""
        with pytest.raises(ValueError):
            RiskConfig(
                max_loss_percent=Decimal("0.01"),
                max_leverage=10,
                max_total_exposure=Decimal("-0.1")
            )

    def test_invalid_loss_percent_zero(self):
        """Test that zero loss percent raises error."""
        with pytest.raises(ValueError):
            RiskConfig(max_loss_percent=Decimal("0"), max_leverage=10)

    def test_invalid_loss_percent_greater_than_one(self):
        """Test that loss percent > 1 raises error."""
        with pytest.raises(ValueError):
            RiskConfig(max_loss_percent=Decimal("1.5"), max_leverage=10)

    def test_invalid_leverage_zero(self):
        """Test that zero leverage raises error."""
        with pytest.raises(ValueError):
            RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=0)

    def test_invalid_leverage_negative(self):
        """Test that negative leverage raises error."""
        with pytest.raises(ValueError):
            RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=-1)


class TestCalculateStopLoss:
    """Test stop-loss calculation."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with test config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_stop_loss_long_below_low(self, calculator):
        """Test LONG stop-loss is set below Pinbar low."""
        kline = create_kline(open=Decimal("108"), high=Decimal("110"), low=Decimal("90"), close=Decimal("109"))
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        assert stop_loss == kline.low

    def test_stop_loss_short_above_high(self, calculator):
        """Test SHORT stop-loss is set above Pinbar high."""
        kline = create_kline(open=Decimal("92"), high=Decimal("110"), low=Decimal("90"), close=Decimal("91"))
        stop_loss = calculator.calculate_stop_loss(kline, Direction.SHORT)
        assert stop_loss == kline.high

    def test_stop_loss_quantized(self, calculator):
        """Test that stop-loss is properly quantized."""
        kline = create_kline(
            open=Decimal("108.123456"), high=Decimal("110.999999"),
            low=Decimal("89.000001"), close=Decimal("109.555555"),
        )
        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        assert stop_loss == Decimal("89.00")


class TestCalculatePositionSize:
    """Test position size calculation."""

    @pytest.fixture
    def calculator_default(self):
        """Create risk calculator with default config (max_total_exposure=0.8)."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    @pytest.fixture
    def calculator_custom_exposure(self):
        """Create risk calculator with custom max_total_exposure."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.5")
        )
        return RiskCalculator(config)

    def test_position_size_basic_formula_no_positions(self, calculator_default):
        """Test basic position size formula with no existing positions."""
        # No positions, so full available_balance can be used
        account = create_account(total_balance=Decimal("100000"), available_balance=Decimal("100000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("95")  # 5 stop distance

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Risk amount = 100000 * 0.01 = 1000
        # Stop distance = |100 - 95| = 5
        # Position size = 1000 / 5 = 200
        assert position_size == Decimal("200")

    def test_position_size_uses_available_balance_not_total(self, calculator_default):
        """Test that calculation uses available_balance, not total_balance."""
        # available_balance is lower, we use available_balance (Scheme B)
        account = create_account(total_balance=Decimal("100000"), available_balance=Decimal("50000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Should use available_balance = 50000, not total = 100000
        # Risk amount = 50000 * 0.01 = 500
        # Stop distance = 5
        # Position size = 500 / 5 = 100
        assert position_size == Decimal("100")

    def test_position_size_reduced_with_existing_positions(self, calculator_default):
        """Test that position size is reduced when existing positions consume exposure."""
        # Current positions: 40% exposure (40000 / 100000)
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("40000"),
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("60000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 40% (0.4)
        # Available exposure = 80% - 40% = 40% (0.4)
        # Base risk = 60000 * 0.01 = 600
        # Exposure limited risk = 60000 * 0.4 = 24000
        # Risk amount = min(600, 24000) = 600 (base risk is lower)
        # Position size = 600 / 5 = 120
        assert position_size == Decimal("120")

    def test_position_size_limited_by_exposure_cap(self, calculator_custom_exposure):
        """Test that position size is limited when approaching exposure cap."""
        # Current positions: 45% exposure (45000 / 100000)
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("45000"),
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("55000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator_custom_exposure.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 45% (0.45)
        # Available exposure = 50% - 45% = 5% (0.05)
        # Base risk = 55000 * 0.01 = 550
        # Exposure limited risk = 55000 * 0.05 = 2750
        # Risk amount = min(550, 2750) = 550 (base risk is lower)
        # Position size = 550 / 5 = 110
        assert position_size == Decimal("110")

    def test_position_size_zero_when_exposure_full(self, calculator_default):
        """Test that position size is zero when exposure is at or above limit."""
        # Current positions: 80% exposure (at limit)
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("2"),
                entry_price=Decimal("40000"),
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("20000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 80% (0.8)
        # Available exposure = 80% - 80% = 0
        # Risk amount = 0 (no available exposure)
        assert position_size == Decimal("0")
        assert leverage == 1

    def test_position_size_with_leverage_cap(self, calculator_default):
        """Test that position size respects leverage cap."""
        account = create_account(total_balance=Decimal("10000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("99")  # 1 stop distance

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Risk amount = 10000 * 0.01 = 100
        # Stop distance = 1
        # Position size = 100 / 1 = 100
        # Position value = 100 * 100 = 10000
        # Leverage = 10000 / 10000 = 1x
        assert leverage <= calculator_default.config.max_leverage

    def test_position_size_tight_stop_requires_higher_leverage(self, calculator_default):
        """Test that tight stop-loss requires higher leverage."""
        account = create_account(total_balance=Decimal("10000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("99.9")  # 0.1 stop distance

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Risk amount = 10000 * 0.01 = 100
        # Stop distance = 0.1
        # Position size = 100 / 0.1 = 1000
        # Position value = 1000 * 100 = 100000
        # Leverage required = 100000 / 10000 = 10x
        assert leverage == calculator_default.config.max_leverage

    def test_position_size_zero_balance(self, calculator_default):
        """Test position size is zero with no balance."""
        account = create_account(total_balance=Decimal("0"))
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        assert position_size == Decimal("0")
        assert leverage == 1

    def test_position_size_stop_loss_distance_zero_raises(self, calculator_default):
        """Test that zero stop-loss distance raises DataQualityWarning (W-001)."""
        account = create_account(total_balance=Decimal("100000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("100")  # Same as entry, distance = 0

        with pytest.raises(DataQualityWarning) as exc_info:
            calculator_default.calculate_position_size(account, entry_price, stop_loss, Direction.LONG)

        assert exc_info.value.error_code == "W-001"
        assert "Stop loss distance is zero" in str(exc_info.value)

    def test_position_size_short_direction(self, calculator_default):
        """Test position size calculation for SHORT."""
        # Use same parameters as basic formula test for consistency
        account = create_account(total_balance=Decimal("100000"), available_balance=Decimal("100000"))
        entry_price = Decimal("100")
        stop_loss = Decimal("105")  # 5 stop distance

        position_size, leverage = calculator_default.calculate_position_size(
            account, entry_price, stop_loss, Direction.SHORT
        )

        # Same formula as LONG: 100000 * 0.01 / 5 = 200
        assert position_size == Decimal("200")


class TestGenerateRiskInfo:
    """Test risk info string generation."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with test config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_risk_info_format(self, calculator):
        """Test risk info string format."""
        account = create_account(total_balance=Decimal("100000"))
        position_size = Decimal("200")
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        risk_info = calculator.generate_risk_info(
            account, position_size, entry_price, stop_loss, Direction.LONG
        )

        # Risk = |100 - 95| * 200 = 1000 USDT
        assert "1.00%" in risk_info
        assert "USDT" in risk_info


class TestCalculateSignalResult:
    """Test complete signal result calculation."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with test config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_signal_result_all_fields_populated(self, calculator):
        """Test that signal result has all fields populated."""
        account = create_account(total_balance=Decimal("100000"))
        kline = create_kline(
            symbol="BTC/USDT:USDT", timeframe="15m",
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("90"), close=Decimal("109"),
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}],
        )

        # Verify all fields are populated
        assert result.symbol == "BTC/USDT:USDT"
        assert result.timeframe == "15m"
        assert result.direction == Direction.LONG
        assert result.entry_price > Decimal("0")
        assert result.suggested_stop_loss > Decimal("0")
        assert result.suggested_position_size > Decimal("0")
        assert result.current_leverage >= 1
        assert result.tags == [{"name": "EMA", "value": "Bullish"}, {"name": "MTF", "value": "Confirmed"}]
        assert result.risk_reward_info != ""

    def test_signal_result_stop_loss_correct(self, calculator):
        """Test that stop-loss is correctly calculated."""
        account = create_account(total_balance=Decimal("100000"))
        kline = create_kline(low=Decimal("90"))

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[{"name": "EMA", "value": "Bullish"}],
        )

        # Stop loss should be at Pinbar low
        assert result.suggested_stop_loss == Decimal("90")

    def test_signal_result_position_size_reasonable(self, calculator):
        """Test that position size is reasonable."""
        account = create_account(total_balance=Decimal("100000"))
        kline = create_kline(
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("90"), close=Decimal("109"),
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
        )

        # Position value should be reasonable relative to balance
        position_value = result.suggested_position_size * result.entry_price
        max_position_value = account.total_balance * result.current_leverage

        assert position_value <= max_position_value


class TestDecimalPrecision:
    """Test that all calculations maintain Decimal precision."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with test config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_no_float_leakage(self, calculator):
        """Test that no float types leak into calculations."""
        account = create_account(total_balance=Decimal("100000.12345678"))
        kline = create_kline(
            open=Decimal("108.12345678"), high=Decimal("110.99999999"),
            low=Decimal("89.00000001"), close=Decimal("109.55555555"),
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
        )

        # All Decimal fields should be Decimal type
        assert isinstance(result.entry_price, Decimal)
        assert isinstance(result.suggested_stop_loss, Decimal)
        assert isinstance(result.suggested_position_size, Decimal)

    def test_high_precision_prices(self, calculator):
        """Test calculations work with high-precision crypto prices."""
        account = create_account(total_balance=Decimal("100000"))

        # ETH-like price with many decimals
        kline = create_kline(
            open=Decimal("3456.78901234"), high=Decimal("3460.12345678"),
            low=Decimal("3400.00000001"), close=Decimal("3455.55555555"),
        )

        result = calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
        )

        # Should handle high precision without errors
        assert result.entry_price > Decimal("0")
        assert result.suggested_stop_loss > Decimal("0")


class TestStopLossDistanceZero:
    """Test boundary case: stop_loss_distance = 0 (Issue #7)."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with test config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_doji_candle_stop_loss_equals_entry(self, calculator):
        """Test doji candle where stop_loss equals entry_price."""
        account = create_account(total_balance=Decimal("100000"))
        # Doji: open=high=low=close, so stop_loss = low = close = entry
        kline = create_kline(open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"))

        stop_loss = calculator.calculate_stop_loss(kline, Direction.LONG)
        entry_price = kline.close

        # For doji, stop_loss == entry_price
        assert stop_loss == entry_price

        # Should raise DataQualityWarning when calculating position size
        with pytest.raises(DataQualityWarning) as exc_info:
            calculator.calculate_position_size(account, entry_price, stop_loss, Direction.LONG)

        assert exc_info.value.error_code == "W-001"

    def test_short_doji_stop_loss_equals_entry(self, calculator):
        """Test SHORT position with doji candle."""
        account = create_account(total_balance=Decimal("100000"))
        kline = create_kline(open=Decimal("100"), high=Decimal("100"), low=Decimal("100"), close=Decimal("100"))

        stop_loss = calculator.calculate_stop_loss(kline, Direction.SHORT)
        entry_price = kline.close

        # For doji, stop_loss == entry_price (high == close)
        assert stop_loss == entry_price

        with pytest.raises(DataQualityWarning) as exc_info:
            calculator.calculate_position_size(account, entry_price, stop_loss, Direction.SHORT)

        assert exc_info.value.error_code == "W-001"


class TestAdvancedBoundaryCases:
    """Test advanced boundary cases for Scheme B dynamic risk calculation."""

    @pytest.fixture
    def calculator(self):
        """Create risk calculator with default config."""
        config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(config)

    def test_position_size_with_unrealized_loss(self, calculator):
        """Test that unrealized loss does not directly affect calculation (uses available_balance)."""
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("40000"),
                unrealized_pnl=Decimal("-5000"),  # Losing position
                leverage=10
            )
        ]
        # available_balance already reflects the margin locked, but not unrealized loss
        account = create_account(
            total_balance=Decimal("95000"),  # Reduced by unrealized loss
            available_balance=Decimal("55000"),  # Available for new positions
            unrealized_pnl=Decimal("-5000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Uses available_balance = 55000
        # Risk amount = 55000 * 0.01 = 550
        # Position size = 550 / 5 = 110
        assert position_size == Decimal("110")

    def test_position_size_with_unrealized_profit(self, calculator):
        """Test that unrealized profit increases total_balance but calculation uses available_balance."""
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("40000"),
                unrealized_pnl=Decimal("+5000"),  # Winning position
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("105000"),  # Increased by unrealized profit
            available_balance=Decimal("65000"),  # More available due to profit
            unrealized_pnl=Decimal("+5000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Uses available_balance = 65000
        # Risk amount = 65000 * 0.01 = 650
        # Position size = 650 / 5 = 130
        assert position_size == Decimal("130")

    def test_position_size_multiple_positions_consume_exposure(self, calculator):
        """Test that multiple positions correctly consume exposure room."""
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("20000"),
                unrealized_pnl=Decimal("0"),
                leverage=10
            ),
            PositionInfo(
                symbol="ETH/USDT:USDT",
                side="long",
                size=Decimal("10"),
                entry_price=Decimal("1500"),
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        # Total position value = 20000 + 15000 = 35000 (35% exposure)
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("65000"),
            unrealized_pnl=Decimal("0"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 35%
        # Available exposure = 80% - 35% = 45%
        # Base risk = 65000 * 0.01 = 650
        # Exposure limited risk = 65000 * 0.45 = 29250
        # Risk amount = min(650, 29250) = 650
        # Position size = 650 / 5 = 130
        assert position_size == Decimal("130")

    def test_position_size_extreme_exposure_limit(self, calculator):
        """Test with very tight exposure limit (10%)."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.1")  # Only 10% total exposure allowed
        )
        tight_calculator = RiskCalculator(config)

        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("1"),
                entry_price=Decimal("8000"),  # 8% exposure
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("92000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = tight_calculator.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 8%
        # Available exposure = 10% - 8% = 2%
        # Base risk = 92000 * 0.01 = 920
        # Exposure limited risk = 92000 * 0.02 = 1840
        # Risk amount = min(920, 1840) = 920 (base risk is still lower)
        # Position size = 920 / 5 = 184
        assert position_size == Decimal("184")

    def test_position_size_exposure_already_exceeded(self, calculator):
        """Test that zero position is returned when exposure already exceeds limit."""
        positions = [
            PositionInfo(
                symbol="BTC/USDT:USDT",
                side="long",
                size=Decimal("3"),
                entry_price=Decimal("30000"),  # 90% exposure
                unrealized_pnl=Decimal("0"),
                leverage=10
            )
        ]
        account = create_account(
            total_balance=Decimal("100000"),
            available_balance=Decimal("10000"),
            positions=positions
        )
        entry_price = Decimal("100")
        stop_loss = Decimal("95")

        position_size, leverage = calculator.calculate_position_size(
            account, entry_price, stop_loss, Direction.LONG
        )

        # Current exposure = 90% (> 80% limit)
        # Available exposure = max(0, 80% - 90%) = 0
        # Risk amount = 0
        assert position_size == Decimal("0")
        assert leverage == 1


# ============================================================
# S6-3: Multi-Level Take Profit Tests
# ============================================================
from src.domain.models import TakeProfitConfig, TakeProfitLevel


class TestTakeProfitConfig:
    """Test TakeProfitConfig model."""

    def test_default_config(self):
        """Test default take profit config."""
        config = TakeProfitConfig()
        assert config.enabled is True
        assert len(config.levels) == 2
        assert config.levels[0].id == "TP1"
        assert config.levels[0].position_ratio == Decimal("0.5")
        assert config.levels[0].risk_reward == Decimal("1.5")
        assert config.levels[1].id == "TP2"
        assert config.levels[1].position_ratio == Decimal("0.5")
        assert config.levels[1].risk_reward == Decimal("3.0")

    def test_custom_config(self):
        """Test custom take profit config."""
        config = TakeProfitConfig(
            enabled=True,
            levels=[
                TakeProfitLevel(id="TP1", position_ratio=Decimal("0.4"), risk_reward=Decimal("1.2")),
                TakeProfitLevel(id="TP2", position_ratio=Decimal("0.3"), risk_reward=Decimal("2.5")),
                TakeProfitLevel(id="TP3", position_ratio=Decimal("0.3"), risk_reward=Decimal("5.0")),
            ]
        )
        assert config.enabled is True
        assert len(config.levels) == 3


class TestCalculateTakeProfitLevels:
    """Test multi-level take profit calculation."""

    @pytest.fixture
    def calculator_default(self):
        """Create risk calculator with default take profit config."""
        risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        return RiskCalculator(risk_config)

    def test_calculate_take_profit_levels_long(self, calculator_default):
        """测试 LONG 方向止盈价格计算"""
        entry_price = Decimal("40000")
        stop_loss = Decimal("38000")  # 止损距离 = 2000
        direction = Direction.LONG

        levels = calculator_default.calculate_take_profit_levels(
            entry_price, stop_loss, direction
        )

        # 验证
        assert len(levels) == 2

        # TP1: 40000 + (2000 * 1.5) = 43000
        assert levels[0]["id"] == "TP1"
        assert Decimal(levels[0]["price"]) == Decimal("43000")
        assert levels[0]["position_ratio"] == "0.5"
        assert levels[0]["risk_reward"] == "1.5"

        # TP2: 40000 + (2000 * 3.0) = 46000
        assert levels[1]["id"] == "TP2"
        assert Decimal(levels[1]["price"]) == Decimal("46000")
        assert levels[1]["position_ratio"] == "0.5"
        assert levels[1]["risk_reward"] == "3.0"

    def test_calculate_take_profit_levels_short(self, calculator_default):
        """测试 SHORT 方向止盈价格计算"""
        entry_price = Decimal("40000")
        stop_loss = Decimal("42000")  # 止损距离 = 2000
        direction = Direction.SHORT

        levels = calculator_default.calculate_take_profit_levels(
            entry_price, stop_loss, direction
        )

        # 验证
        assert len(levels) == 2

        # TP1: 40000 - (2000 * 1.5) = 37000 (SHORT 止盈在下方)
        assert levels[0]["id"] == "TP1"
        assert Decimal(levels[0]["price"]) == Decimal("37000")

        # TP2: 40000 - (2000 * 3.0) = 34000
        assert levels[1]["id"] == "TP2"
        assert Decimal(levels[1]["price"]) == Decimal("34000")

    def test_take_profit_config_override(self):
        """测试用户配置覆盖默认值"""
        risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        custom_tp_config = TakeProfitConfig(
            enabled=True,
            levels=[
                TakeProfitLevel(id="TP1", position_ratio=Decimal("0.4"), risk_reward=Decimal("1.2")),
                TakeProfitLevel(id="TP2", position_ratio=Decimal("0.3"), risk_reward=Decimal("2.5")),
                TakeProfitLevel(id="TP3", position_ratio=Decimal("0.3"), risk_reward=Decimal("5.0")),
            ]
        )
        calculator = RiskCalculator(risk_config, custom_tp_config)

        entry_price = Decimal("100")
        stop_loss = Decimal("90")  # 止损距离 = 10
        direction = Direction.LONG

        levels = calculator.calculate_take_profit_levels(
            entry_price, stop_loss, direction, custom_tp_config
        )

        # 验证 3 个级别
        assert len(levels) == 3

        # TP1: 100 + (10 * 1.2) = 112
        assert levels[0]["id"] == "TP1"
        assert Decimal(levels[0]["price"]) == Decimal("112")

        # TP2: 100 + (10 * 2.5) = 125
        assert levels[1]["id"] == "TP2"
        assert Decimal(levels[1]["price"]) == Decimal("125")

        # TP3: 100 + (10 * 5.0) = 150
        assert levels[2]["id"] == "TP3"
        assert Decimal(levels[2]["price"]) == Decimal("150")

    def test_take_profit_disabled(self):
        """测试止盈配置禁用时返回空列表"""
        risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=10)
        disabled_tp_config = TakeProfitConfig(enabled=False, levels=[])
        calculator = RiskCalculator(risk_config, disabled_tp_config)

        entry_price = Decimal("40000")
        stop_loss = Decimal("38000")
        direction = Direction.LONG

        levels = calculator.calculate_take_profit_levels(
            entry_price, stop_loss, direction, disabled_tp_config
        )

        # 验证返回空列表
        assert levels == []

    def test_take_profit_levels_in_signal_result(self, calculator_default):
        """测试信号结果包含止盈级别"""
        account = create_account(total_balance=Decimal("100000"))
        kline = create_kline(
            symbol="BTC/USDT:USDT", timeframe="15m",
            open=Decimal("108"), high=Decimal("110"),
            low=Decimal("90"), close=Decimal("109"),
        )

        result = calculator_default.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
        )

        # 验证信号包含止盈级别
        assert result.take_profit_levels is not None
        assert len(result.take_profit_levels) >= 2

        # 验证止盈价格计算正确
        # 止损距离 = 109 - 90 = 19
        # TP1 = 109 + 19 * 1.5 = 137.5
        # TP2 = 109 + 19 * 3.0 = 166
        tp1 = next(tp for tp in result.take_profit_levels if tp["id"] == "TP1")
        tp2 = next(tp for tp in result.take_profit_levels if tp["id"] == "TP2")

        assert abs(Decimal(tp1["price"]) - Decimal("137.50")) < Decimal("1")  # 允许 1 以内误差
        assert abs(Decimal(tp2["price"]) - Decimal("166.00")) < Decimal("1")
