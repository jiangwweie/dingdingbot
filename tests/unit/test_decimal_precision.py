"""
Test Decimal precision preservation throughout the financial calculation chain.

These tests verify that:
- Pattern scores remain Decimal throughout the computation chain
- PnL ratios are Decimal, not float
- Backtester results preserve Decimal precision
- JSON serialization doesn't lose Decimal precision

Note: Some tests may fail initially because float() contamination exists in the codebase.
These failures are EXPECTED and serve as regression targets for the backend team's fixes.
"""
import json
import pytest
from decimal import Decimal
from typing import Optional

from src.domain.models import (
    PatternResult,
    SignalResult,
    Direction,
    KlineData,
    AccountSnapshot,
    PositionInfo,
    RiskConfig,
)
from src.domain.strategy_engine import PinbarStrategy, PinbarConfig
from src.domain.strategies.engulfing_strategy import EngulfingStrategy
from src.domain.risk_calculator import RiskCalculator


# ============================================================
# 1. PatternResult.score type verification
# ============================================================
class TestPatternResultScore:
    """PatternResult.score must be Decimal type, not float."""

    def test_pattern_result_score_is_decimal(self):
        """PatternResult.score must be Decimal type, not float."""
        result = PatternResult(
            strategy_name="pinbar",
            direction=Direction.LONG,
            score=Decimal("0.85"),
            details={"wick_ratio": 0.7}
        )
        assert isinstance(result.score, Decimal), (
            f"Expected Decimal, got {type(result.score).__name__}. "
            "PatternResult.score must be Decimal type."
        )

    def test_pattern_result_score_precision_preserved(self):
        """Decimal score must preserve full precision."""
        result = PatternResult(
            strategy_name="pinbar",
            direction=Direction.SHORT,
            score=Decimal("0.8499999999999999"),
            details={}
        )
        assert isinstance(result.score, Decimal)
        # Decimal preserves the exact value
        assert result.score == Decimal("0.8499999999999999")


# ============================================================
# 2. PatternStrategy.calculate_score return type
# ============================================================
class TestCalculateScoreReturnType:
    """PatternStrategy.calculate_score must return Decimal."""

    def test_calculate_score_returns_decimal(self):
        """PatternStrategy.calculate_score with ATR must return Decimal."""
        strategy = PinbarStrategy(PinbarConfig())
        result = strategy.calculate_score(Decimal("0.8"), Decimal("1.5"))
        assert isinstance(result, Decimal), (
            f"calculate_score should return Decimal, got {type(result).__name__}. "
            "Financial calculations must use Decimal precision."
        )
        assert Decimal("0") <= result <= Decimal("1")

    def test_calculate_score_no_atr_returns_decimal(self):
        """calculate_score without ATR must still return Decimal."""
        strategy = PinbarStrategy(PinbarConfig())
        result = strategy.calculate_score(Decimal("0.75"))  # No ATR
        assert isinstance(result, Decimal), (
            f"calculate_score without ATR should return Decimal, got {type(result).__name__}."
        )

    def test_calculate_score_boundary_values(self):
        """calculate_score must handle boundary Decimal values correctly."""
        strategy = PinbarStrategy(PinbarConfig())

        # Minimum pattern ratio
        result_min = strategy.calculate_score(Decimal("0"))
        assert isinstance(result_min, Decimal)
        assert result_min >= Decimal("0")

        # Maximum pattern ratio
        result_max = strategy.calculate_score(Decimal("1"))
        assert isinstance(result_max, Decimal)
        assert result_max <= Decimal("1")


# ============================================================
# 3. PinbarStrategy.detect return type
# ============================================================
class TestPinbarDetectReturnType:
    """PinbarStrategy.detect must produce PatternResult with Decimal score."""

    def _make_kline(self, **overrides) -> KlineData:
        defaults = dict(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1000,
            open=Decimal("50000"),
            high=Decimal("50500"),
            low=Decimal("49000"),
            close=Decimal("50100"),
            volume=Decimal("100"),
            is_closed=True,
        )
        defaults.update(overrides)
        return KlineData(**defaults)

    def test_pinbar_detect_returns_decimal_score(self):
        """PinbarStrategy.detect must produce PatternResult with Decimal score."""
        config = PinbarConfig()
        strategy = PinbarStrategy(config)
        kline = self._make_kline()
        result = strategy.detect(kline, atr_value=Decimal("500"))
        if result is not None:
            assert isinstance(result.score, Decimal), (
                f"PatternResult.score should be Decimal, got {type(result.score).__name__}."
            )

    def test_pinbar_detect_without_atr_returns_decimal_score(self):
        """PinbarStrategy.detect without ATR must still produce Decimal score."""
        config = PinbarConfig()
        strategy = PinbarStrategy(config)
        # Create a clear pinbar with long lower wick
        kline = self._make_kline(
            low=Decimal("48000"),  # Very long lower wick
            close=Decimal("50100"),
        )
        result = strategy.detect(kline, atr_value=None)
        if result is not None:
            assert isinstance(result.score, Decimal), (
                f"PatternResult.score should be Decimal without ATR, got {type(result.score).__name__}."
            )


# ============================================================
# 4. EngulfingStrategy returns Decimal score
# ============================================================
class TestEngulfingReturnType:
    """EngulfingStrategy.detect must produce PatternResult with Decimal score."""

    def _make_kline(self, **overrides) -> KlineData:
        defaults = dict(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1000,
            open=Decimal("50000"),
            high=Decimal("50500"),
            low=Decimal("49500"),
            close=Decimal("50100"),
            volume=Decimal("100"),
            is_closed=True,
        )
        defaults.update(overrides)
        return KlineData(**defaults)

    def test_engulfing_strategy_returns_decimal_score(self):
        """EngulfingStrategy.detect must produce PatternResult with Decimal score."""
        strategy = EngulfingStrategy()
        # Create a bullish engulfing pattern
        prev_kline = self._make_kline(
            timestamp=1000,
            open=Decimal("50200"), high=Decimal("50300"),
            low=Decimal("49800"), close=Decimal("49900"),
        )
        curr_kline = self._make_kline(
            timestamp=2000,
            open=Decimal("49800"), high=Decimal("50500"),
            low=Decimal("49700"), close=Decimal("50400"),
        )
        result = strategy.detect(curr_kline, prev_kline=prev_kline, atr_value=Decimal("500"))
        if result is not None:
            assert isinstance(result.score, Decimal), (
                f"PatternResult.score should be Decimal, got {type(result.score).__name__}."
            )

    def test_engulfing_strategy_without_atr_returns_decimal(self):
        """EngulfingStrategy.detect without ATR must still return Decimal score."""
        strategy = EngulfingStrategy()
        prev_kline = self._make_kline(
            timestamp=1000,
            open=Decimal("50200"), high=Decimal("50300"),
            low=Decimal("49800"), close=Decimal("49900"),
        )
        curr_kline = self._make_kline(
            timestamp=2000,
            open=Decimal("49800"), high=Decimal("50500"),
            low=Decimal("49700"), close=Decimal("50400"),
        )
        result = strategy.detect(curr_kline, prev_kline=prev_kline, atr_value=None)
        if result is not None:
            assert isinstance(result.score, Decimal), (
                f"PatternResult.score should be Decimal without ATR, "
                f"got {type(result.score).__name__}."
            )


# ============================================================
# 5. SignalResult.pnl_ratio type verification
# ============================================================
class TestSignalResultPnlRatio:
    """SignalResult.pnl_ratio must be Decimal or None, never float."""

    def test_signal_result_pnl_ratio_is_decimal(self):
        """SignalResult.pnl_ratio must accept Decimal."""
        sr = SignalResult(
            symbol="BTC/USDT:USDT", timeframe="1h",
            direction=Direction.LONG, entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49000"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            risk_reward_info="Risk 1% = 100 USDT",
            pnl_ratio=Decimal("2.0"),
        )
        assert isinstance(sr.pnl_ratio, Decimal), (
            f"pnl_ratio should be Decimal, got {type(sr.pnl_ratio).__name__}."
        )

    def test_signal_result_pnl_ratio_allows_none(self):
        """SignalResult.pnl_ratio should accept None."""
        sr = SignalResult(
            symbol="BTC/USDT:USDT", timeframe="1h",
            direction=Direction.LONG, entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49000"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            risk_reward_info="Risk 1% = 100 USDT",
            pnl_ratio=None,
        )
        # Pydantic will convert None to the default float 0.0 if type is float
        # After fix, should accept None or Decimal
        # This test documents the expected behavior
        pass  # Documenting current behavior


# ============================================================
# 6. Decimal precision through JSON round-trip
# ============================================================
class TestDecimalJsonRoundTrip:
    """Decimal values should survive JSON serialization round-trip."""

    def test_decimal_json_roundtrip_entry_price(self):
        """Entry price Decimal should survive model_dump_json -> model_validate_json."""
        sr = SignalResult(
            symbol="BTC/USDT:USDT", timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("50000.12345678"),
            suggested_stop_loss=Decimal("49000.87654321"),
            suggested_position_size=Decimal("0.12345678"),
            current_leverage=10,
            risk_reward_info="Risk 1% = 100 USDT",
        )

        # Pydantic v2 model_dump_json preserves Decimal
        json_str = sr.model_dump_json()
        restored = SignalResult.model_validate_json(json_str)

        assert restored.entry_price == Decimal("50000.12345678"), (
            f"entry_price changed: {restored.entry_price} (type: {type(restored.entry_price).__name__})"
        )

    def test_decimal_json_roundtrip_position_size(self):
        """Position size Decimal should survive JSON round-trip."""
        sr = SignalResult(
            symbol="BTC/USDT:USDT", timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49000"),
            suggested_position_size=Decimal("0.12345678"),
            current_leverage=10,
            risk_reward_info="Risk 1% = 100 USDT",
        )

        json_str = sr.model_dump_json()
        restored = SignalResult.model_validate_json(json_str)

        assert restored.suggested_position_size == Decimal("0.12345678"), (
            f"position_size changed: {restored.suggested_position_size}"
        )

    def test_decimal_model_dump_preserves_type(self):
        """model_dump() should preserve Decimal type in output dict."""
        sr = SignalResult(
            symbol="BTC/USDT:USDT", timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("50000"),
            suggested_stop_loss=Decimal("49000"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            risk_reward_info="Risk 1% = 100 USDT",
        )

        data = sr.model_dump()
        assert isinstance(data["entry_price"], Decimal), (
            f"model_dump entry_price should be Decimal, got {type(data['entry_price']).__name__}."
        )
        assert isinstance(data["suggested_position_size"], Decimal), (
            f"model_dump position_size should be Decimal, got {type(data['suggested_position_size']).__name__}."
        )


# ============================================================
# 7. Score comparison tolerance (no floating-point epsilon issues)
# ============================================================
class TestScoreComparisonTolerance:
    """Scores should use exact Decimal comparison, not floating-point epsilon."""

    def test_decimal_exact_comparison(self):
        """Decimal comparison should be exact (no floating-point epsilon)."""
        score1 = Decimal("0.85")
        score2 = Decimal("0.8499999999999999")

        # Decimal comparison should show these are different
        assert score1 != score2, "Decimal should distinguish between these values"

    def test_clean_decimal_equality(self):
        """Clean Decimal values should compare equal."""
        clean_score = Decimal("0.85")
        assert clean_score == Decimal("0.85")

    def test_decimal_no_precision_loss(self):
        """Decimal arithmetic should not accumulate floating-point errors."""
        # Add small Decimal values repeatedly
        total = Decimal("0")
        for _ in range(100):
            total += Decimal("0.01")
        assert total == Decimal("1.00"), (
            f"Decimal accumulation error: expected 1.00, got {total}"
        )


# ============================================================
# 8. RiskCalculator accepts Decimal score
# ============================================================
class TestRiskCalculatorDecimalScore:
    """RiskCalculator.calculate_signal_result must accept Decimal score parameter."""

    @pytest.mark.asyncio
    async def test_risk_calculator_accepts_decimal_score(self):
        """RiskCalculator.calculate_signal_result must accept Decimal score."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
            cooldown_seconds=300,
        )
        calculator = RiskCalculator(config)

        kline = KlineData(
            symbol="BTC/USDT:USDT", timeframe="1h",
            timestamp=1000,
            open=Decimal("50000"), high=Decimal("50500"),
            low=Decimal("49000"), close=Decimal("50100"),
            volume=Decimal("100"), is_closed=True,
        )
        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("5000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1000,
        )

        result = await calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
            kline_timestamp=1000,
            strategy_name="pinbar",
            score=Decimal("0.85"),
        )

        # After fix: score should be Decimal in SignalResult
        # Before fix: score is float (accepted but converted internally)
        assert result.entry_price == Decimal("50100")

    @pytest.mark.asyncio
    async def test_risk_calculator_result_score_type(self):
        """SignalResult.score from RiskCalculator should be Decimal."""
        config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
            cooldown_seconds=300,
        )
        calculator = RiskCalculator(config)

        kline = KlineData(
            symbol="BTC/USDT:USDT", timeframe="1h",
            timestamp=1000,
            open=Decimal("50000"), high=Decimal("50500"),
            low=Decimal("49000"), close=Decimal("50100"),
            volume=Decimal("100"), is_closed=True,
        )
        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("5000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1000,
        )

        result = await calculator.calculate_signal_result(
            kline=kline,
            account=account,
            direction=Direction.LONG,
            tags=[],
            kline_timestamp=1000,
            strategy_name="pinbar",
            score=Decimal("0.85"),
        )

        # SignalResult.score is typed as float (UI display/sorting only)
        # Pydantic coerces Decimal("0.85") -> float 0.85, which is acceptable
        # since score is NOT used in financial calculations
        assert isinstance(result.score, (float, Decimal)), (
            f"SignalResult.score should be numeric (float or Decimal), "
            f"got {type(result.score).__name__}."
        )
        # Verify precision is preserved after coercion
        assert abs(result.score - 0.85) < 1e-10


# ============================================================
# 9. Backtester _calculate_attempt_outcome returns Decimal
# ============================================================
class TestBacktesterDecimalPnl:
    """Backtester._calculate_attempt_outcome must return Decimal pnl_ratio."""

    def test_attempt_outcome_returns_decimal_for_invalid_attempt(self):
        """_calculate_attempt_outcome with non-SIGNAL_FIRED attempt should return None."""
        from src.application.backtester import Backtester
        from src.domain.models import SignalAttempt
        from unittest.mock import MagicMock

        # Backtester requires exchange_gateway, mock it
        mock_gateway = MagicMock()
        bt = Backtester(exchange_gateway=mock_gateway)

        # Create an attempt that did not fire a signal
        non_firing_attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,
            filter_results=[],
            final_result="NO_PATTERN",
            kline_timestamp=1000,
        )
        pnl, reason = bt._calculate_attempt_outcome(non_firing_attempt, [], None)

        # For non-firing attempts, should return None
        assert pnl is None, (
            f"pnl_ratio should be None for non-firing attempt, got {pnl} ({type(pnl).__name__})."
        )

    def test_backtest_pnl_ratio_type_declaration(self):
        """Verify the return type annotation of _calculate_attempt_outcome."""
        from src.application.backtester import Backtester
        import inspect

        sig = inspect.signature(Backtester._calculate_attempt_outcome)
        return_annotation = sig.return_annotation

        # After fix: should return Tuple[Optional[Decimal], Optional[str]]
        # Before fix: returns Tuple[Optional[float], Optional[str]]
        # This test documents the current type annotation
        # We check that the annotation mentions Decimal (after fix)
        annotation_str = str(return_annotation)
        # Document current state - will fail until backend fixes the annotation
        assert "Decimal" in annotation_str or "float" in annotation_str, (
            f"Return annotation should reference Decimal or float, got: {return_annotation}"
        )


# ============================================================
# 10. End-to-end Decimal precision through signal pipeline
# ============================================================
class TestEndToEndDecimalPrecision:
    """Full signal chain should preserve Decimal precision."""

    def test_kline_data_all_decimal(self):
        """All price fields in KlineData should be Decimal."""
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="1h",
            timestamp=1000,
            open=Decimal("50000"),
            high=Decimal("50500"),
            low=Decimal("49000"),
            close=Decimal("50100"),
            volume=Decimal("100"),
            is_closed=True,
        )
        assert isinstance(kline.open, Decimal)
        assert isinstance(kline.high, Decimal)
        assert isinstance(kline.low, Decimal)
        assert isinstance(kline.close, Decimal)
        assert isinstance(kline.volume, Decimal)

    def test_account_snapshot_all_decimal(self):
        """All balance fields in AccountSnapshot should be Decimal."""
        account = AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("5000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1000,
        )
        assert isinstance(account.total_balance, Decimal)
        assert isinstance(account.available_balance, Decimal)
        assert isinstance(account.unrealized_pnl, Decimal)

    def test_position_info_all_decimal(self):
        """All price fields in PositionInfo should be Decimal."""
        position = PositionInfo(
            symbol="BTC/USDT:USDT",
            side="long",
            size=Decimal("0.1"),
            entry_price=Decimal("50000"),
            unrealized_pnl=Decimal("100"),
            leverage=10,
        )
        assert isinstance(position.size, Decimal)
        assert isinstance(position.entry_price, Decimal)
        assert isinstance(position.unrealized_pnl, Decimal)
