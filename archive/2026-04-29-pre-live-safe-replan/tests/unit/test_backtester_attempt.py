"""Unit tests for Backtester._attempt_to_dict() method.

ADR-001 Task 5: Verify that _attempt_to_dict serialization includes
pnl_ratio and exit_reason fields for BT-4 strategy attribution analysis.
"""
from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.models import (
    Direction,
    PatternResult,
    SignalAttempt,
    FilterResult,
)


def create_sample_pattern() -> PatternResult:
    """Create a sample pattern result for testing."""
    return PatternResult(
        strategy_name="pinbar",
        direction=Direction.LONG,
        score=Decimal("0.8"),
        details={"wick_ratio": 0.7, "body_ratio": 0.2},
    )


def create_sample_filter_results() -> list:
    """Create sample filter results for testing."""
    return [
        ("ema_trend", FilterResult(
            passed=True,
            reason="trend_match",
            metadata={
                "filter_name": "ema_trend",
                "filter_type": "ema_trend",
                "period": 60,
                "ema_value": 50000.0,
                "trend_direction": "bullish",
            },
        )),
        ("mtf", FilterResult(
            passed=True,
            reason="mtf_confirmed_bullish",
            metadata={
                "filter_name": "mtf",
                "filter_type": "mtf",
                "higher_timeframe": "1h",
                "higher_trend": "bullish",
                "current_timeframe": "15m",
            },
        )),
        ("atr_volatility", FilterResult(
            passed=True,
            reason="volatility_sufficient",
            metadata={
                "filter_name": "atr_volatility",
                "filter_type": "atr_volatility",
                "candle_range": 100.0,
                "atr_value": 50.0,
                "volatility_ratio": 2.0,
            },
        )),
    ]


class TestAttemptToDict:
    """Test Backtester._attempt_to_dict() serialization."""

    def test_attempt_to_dict_includes_pnl_ratio_and_exit_reason(self):
        """ADR-001 Task 5: Verify _attempt_to_dict includes pnl_ratio and exit_reason.

        BT-4 策略归因分析需要这两个关键字段来追踪：
        - pnl_ratio: 盈亏比（如 2.0 表示 2R 盈利，-1.0 表示 1R 亏损）
        - exit_reason: 出场原因（STOP_LOSS / TAKE_PROFIT / TIME_EXIT）
        """
        from src.application.backtester import Backtester

        # Create mock gateway
        mock_gateway = MagicMock()

        # Create backtester instance
        backtester = Backtester(mock_gateway)

        # Create SignalAttempt with SIGNAL_FIRED result
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=create_sample_pattern(),
            filter_results=create_sample_filter_results(),
            final_result="SIGNAL_FIRED",
            kline_timestamp=1711785600000,
            _pnl_ratio=2.0,
            _exit_reason="TAKE_PROFIT",
        )

        # Call _attempt_to_dict
        result = backtester._attempt_to_dict(attempt)

        # ADR-001: Verify pnl_ratio field exists and has correct value
        assert "pnl_ratio" in result, "Result must contain 'pnl_ratio' field"
        assert result["pnl_ratio"] == 2.0, f"Expected pnl_ratio=2.0, got {result['pnl_ratio']}"

        # ADR-001: Verify exit_reason field exists and has correct value
        assert "exit_reason" in result, "Result must contain 'exit_reason' field"
        assert result["exit_reason"] == "TAKE_PROFIT", f"Expected exit_reason='TAKE_PROFIT', got {result['exit_reason']}"

    def test_attempt_to_dict_pnl_ratio_none_for_non_fired_signals(self):
        """ADR-001 Task 5: Verify pnl_ratio is None for non-SIGNAL_FIRED attempts."""
        from src.application.backtester import Backtester

        mock_gateway = MagicMock()
        backtester = Backtester(mock_gateway)

        # Create attempt with NO_PATTERN result
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,  # No pattern detected
            filter_results=[],
            final_result="NO_PATTERN",
            kline_timestamp=1711785600000,
            _pnl_ratio=None,
            _exit_reason=None,
        )

        result = backtester._attempt_to_dict(attempt)

        # pnl_ratio and exit_reason should be None for non-fired signals
        assert result["pnl_ratio"] is None
        assert result["exit_reason"] is None

    def test_attempt_to_dict_preserves_filter_metadata(self):
        """ADR-001 Task 5: Verify filter metadata is preserved in serialization."""
        from src.application.backtester import Backtester

        mock_gateway = MagicMock()
        backtester = Backtester(mock_gateway)

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=create_sample_pattern(),
            filter_results=create_sample_filter_results(),
            final_result="SIGNAL_FIRED",
            kline_timestamp=1711785600000,
            _pnl_ratio=2.0,
            _exit_reason="TAKE_PROFIT",
        )

        result = backtester._attempt_to_dict(attempt)

        # Verify filter_results contains metadata
        assert len(result["filter_results"]) == 3

        # Verify each filter's metadata contains standard fields
        for filter_result in result["filter_results"]:
            assert "filter" in filter_result
            assert "passed" in filter_result
            assert "reason" in filter_result
            assert "metadata" in filter_result
            assert isinstance(filter_result["metadata"], dict)

        # Verify specific metadata fields
        ema_metadata = result["filter_results"][0]["metadata"]
        assert ema_metadata["filter_name"] == "ema_trend"
        assert ema_metadata["filter_type"] == "ema_trend"

        mtf_metadata = result["filter_results"][1]["metadata"]
        assert mtf_metadata["filter_name"] == "mtf"
        assert mtf_metadata["filter_type"] == "mtf"

        atr_metadata = result["filter_results"][2]["metadata"]
        assert atr_metadata["filter_name"] == "atr_volatility"
        assert atr_metadata["filter_type"] == "atr_volatility"

    def test_attempt_to_dict_all_exit_reasons(self):
        """ADR-001 Task 5: Verify all exit_reason types are properly serialized."""
        from src.application.backtester import Backtester

        mock_gateway = MagicMock()
        backtester = Backtester(mock_gateway)

        exit_reasons = ["STOP_LOSS", "TAKE_PROFIT", "TIME_EXIT"]

        for exit_reason in exit_reasons:
            attempt = SignalAttempt(
                strategy_name="pinbar",
                pattern=create_sample_pattern(),
                filter_results=[],
                final_result="SIGNAL_FIRED",
                kline_timestamp=1711785600000,
                _pnl_ratio=-1.0 if exit_reason == "STOP_LOSS" else 2.0,
                _exit_reason=exit_reason,
            )

            result = backtester._attempt_to_dict(attempt)

            assert result["exit_reason"] == exit_reason, \
                f"Expected exit_reason='{exit_reason}', got '{result['exit_reason']}'"

    def test_attempt_to_dict_basic_fields(self):
        """Verify _attempt_to_dict preserves all basic fields."""
        from src.application.backtester import Backtester

        mock_gateway = MagicMock()
        backtester = Backtester(mock_gateway)

        attempt = SignalAttempt(
            strategy_name="test_strategy",
            pattern=create_sample_pattern(),
            filter_results=[],
            final_result="SIGNAL_FIRED",
            kline_timestamp=1711785600000,
            _pnl_ratio=1.5,
            _exit_reason="TAKE_PROFIT",
        )

        result = backtester._attempt_to_dict(attempt)

        # Verify all basic fields
        assert result["strategy_name"] == "test_strategy"
        assert result["final_result"] == "SIGNAL_FIRED"
        assert result["direction"] == "LONG"
        assert result["kline_timestamp"] == 1711785600000
        assert result["pattern_score"] == Decimal("0.8")
