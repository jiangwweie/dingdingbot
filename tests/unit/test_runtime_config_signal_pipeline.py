"""
Unit tests for RuntimeConfig and SignalPipeline runtime config switching semantics.

Tests verify that Codex's implementation correctly handles:
1. StrategyRuntimeConfig.to_strategy_definition()
2. ExecutionRuntimeConfig.to_order_strategy()
3. SignalPipeline._apply_runtime_direction_policy()
4. SignalPipeline._build_execution_strategy()

No real main.py, no exchange connection, no PG, no real data/v3_dev.db.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Optional

from pydantic import ValidationError

from src.domain.models import (
    CapitalProtectionConfig,
    Direction,
    OrderStrategy,
    StrategyDefinition,
    RiskConfig,
    KlineData,
    SignalAttempt,
    FilterResult,
    PatternResult,
)
from src.domain.logic_tree import TriggerConfig, FilterConfig
from src.application.runtime_config import (
    StrategyRuntimeConfig,
    ExecutionRuntimeConfig,
    RiskRuntimeConfig,
)


# ============================================================
# Test 1: StrategyRuntimeConfig.to_strategy_definition()
# ============================================================
class TestStrategyRuntimeConfigToStrategyDefinition:
    """Test StrategyRuntimeConfig.to_strategy_definition() semantics."""

    def test_to_strategy_definition_with_apply_to(self):
        """
        Test to_strategy_definition() with apply_to == ["ETH/USDT:USDT:1h"].

        Verifies:
        - apply_to correctly formatted as ["ETH/USDT:USDT:1h"]
        - trigger == pinbar
        - filters == ["ema", "mtf", "atr"]
        - is_global == False (since apply_to is provided)
        """
        # Create trigger config (pinbar)
        trigger = TriggerConfig(
            id="pinbar_trigger",
            type="pinbar",
            enabled=True,
            params={"min_wick_ratio": 0.6, "max_body_ratio": 0.3},
        )

        # Create filter configs
        filters = [
            FilterConfig(id="ema_filter", type="ema", enabled=True, params={"period": 60}),
            FilterConfig(id="mtf_filter", type="mtf", enabled=True, params={"ema_period": 60}),
            FilterConfig(id="atr_filter", type="atr", enabled=True, params={"period": 14}),
        ]

        # Create StrategyRuntimeConfig (Sim-1 requires LONG-only)
        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=trigger,
            filters=filters,
            atr_enabled=False,
        )

        # Call to_strategy_definition with symbol and timeframe
        strategy_def = config.to_strategy_definition(
            strategy_id="test_strategy",
            name="Test Strategy",
            primary_symbol="ETH/USDT:USDT",
            primary_timeframe="1h",
        )

        # Assertions
        assert strategy_def.id == "test_strategy"
        assert strategy_def.name == "Test Strategy"
        assert strategy_def.apply_to == ["ETH/USDT:USDT:1h"]
        assert strategy_def.is_global is False

        # Verify trigger is pinbar
        assert strategy_def.trigger is not None
        assert strategy_def.trigger.type == "pinbar"
        assert strategy_def.trigger.enabled is True

        # Verify filters
        assert len(strategy_def.filters) == 3
        filter_types = [f.type for f in strategy_def.filters]
        assert "ema" in filter_types
        assert "mtf" in filter_types
        assert "atr" in filter_types

    def test_to_strategy_definition_global_scope(self):
        """
        Test to_strategy_definition() without symbol/timeframe.

        When no symbol/timeframe provided:
        - apply_to == []
        - is_global == True
        """
        trigger = TriggerConfig(
            id="pinbar_trigger",
            type="pinbar",
            enabled=True,
            params={},
        )

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=trigger,
            filters=[],
            atr_enabled=False,
        )

        strategy_def = config.to_strategy_definition(
            strategy_id="global_strategy",
            name="Global Strategy",
        )

        assert strategy_def.apply_to == []
        assert strategy_def.is_global is True

    def test_get_mtf_ema_period_returns_configured_value(self):
        """
        Test get_mtf_ema_period() == 60.

        Verifies that MTF filter's ema_period param is correctly extracted.
        """
        filters = [
            FilterConfig(id="ema_filter", type="ema", enabled=True, params={"period": 60}),
            FilterConfig(id="mtf_filter", type="mtf", enabled=True, params={"ema_period": 60}),
            FilterConfig(id="atr_filter", type="atr", enabled=True, params={"period": 14}),
        ]

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=TriggerConfig(id="t", type="pinbar", enabled=True, params={}),
            filters=filters,
            atr_enabled=False,
        )

        assert config.get_mtf_ema_period() == 60

    def test_get_mtf_ema_period_accepts_string_value(self):
        """Test get_mtf_ema_period() converts string ema_period to int."""
        filters = [
            FilterConfig(id="mtf_filter", type="mtf", enabled=True, params={"ema_period": "60"}),
        ]

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=TriggerConfig(id="t", type="pinbar", enabled=True, params={}),
            filters=filters,
            atr_enabled=False,
        )

        assert config.get_mtf_ema_period() == 60

    def test_get_mtf_ema_period_returns_default_when_no_mtf(self):
        """Test get_mtf_ema_period() returns default when no MTF filter."""
        filters = [
            FilterConfig(id="ema_filter", type="ema", enabled=True, params={"period": 60}),
        ]

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=TriggerConfig(id="t", type="pinbar", enabled=True, params={}),
            filters=filters,
            atr_enabled=False,
        )

        assert config.get_mtf_ema_period(default=60) == 60

    def test_get_mtf_ema_period_ignores_disabled_mtf(self):
        """Test get_mtf_ema_period() ignores disabled MTF filter."""
        filters = [
            FilterConfig(id="mtf_filter", type="mtf", enabled=False, params={"ema_period": 60}),
        ]

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=TriggerConfig(id="t", type="pinbar", enabled=True, params={}),
            filters=filters,
            atr_enabled=False,
        )

        # Should return default since MTF is disabled
        assert config.get_mtf_ema_period(default=60) == 60


# ============================================================
# Test 2: ExecutionRuntimeConfig.to_order_strategy()
# ============================================================
class TestExecutionRuntimeConfigToOrderStrategy:
    """Test ExecutionRuntimeConfig.to_order_strategy() semantics."""

    def test_to_order_strategy_basic(self):
        """
        Test to_order_strategy() with:
        - tp_levels=2
        - tp_ratios=[Decimal("0.5"), Decimal("0.5")]
        - tp_targets=[Decimal("1.0"), Decimal("3.5")]
        - initial_stop_loss_rr=Decimal("-1.0")
        - trailing_stop_enabled=False
        - oco_enabled=True
        """
        config = ExecutionRuntimeConfig(
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        strategy = config.to_order_strategy(strategy_id="test_exec")

        assert strategy.id == "test_exec"
        assert strategy.name == "test_exec"
        assert strategy.tp_levels == 2
        assert strategy.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
        assert strategy.tp_targets == [Decimal("1.0"), Decimal("3.5")]
        assert strategy.initial_stop_loss_rr == Decimal("-1.0")
        assert strategy.trailing_stop_enabled is False
        assert strategy.oco_enabled is True

    def test_runtime_config_is_immutable(self):
        """
        RuntimeConfig models must be frozen (no hot-edit during Sim runtime).

        This protects config_hash auditability and prevents accidental mutation.
        """
        config = ExecutionRuntimeConfig(
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        copy = config.model_copy(deep=True)

        with pytest.raises(TypeError):
            copy.tp_ratios[0] = Decimal("0.6")

        with pytest.raises(TypeError):
            copy.tp_targets[0] = Decimal("2.0")

        with pytest.raises(ValidationError):
            copy.tp_levels = 3

    def test_to_order_strategy_returns_independent_copy(self):
        """
        Test that to_order_strategy() returns independent object.

        Each call should return a new object that can be modified independently.
        """
        config = ExecutionRuntimeConfig(
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        strategy1 = config.to_order_strategy(strategy_id="exec1")
        strategy2 = config.to_order_strategy(strategy_id="exec2")

        # Modify strategy1
        strategy1.tp_ratios[0] = Decimal("0.7")

        # strategy2 should be unaffected
        assert strategy2.tp_ratios[0] == Decimal("0.5")

        # config should be unaffected
        assert config.tp_ratios[0] == Decimal("0.5")

    def test_tp_ratios_must_sum_to_one(self):
        """Test that tp_ratios must sum to 1.0."""
        # Valid: sums to 1.0
        config_valid = ExecutionRuntimeConfig(
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("2.0")],
        )
        assert config_valid.tp_ratios == (Decimal("0.5"), Decimal("0.5"))

        # Invalid: does not sum to 1.0
        with pytest.raises(ValueError, match="tp_ratios must sum to 1.0"):
            ExecutionRuntimeConfig(
                tp_levels=2,
                tp_ratios=[Decimal("0.4"), Decimal("0.5")],  # sums to 0.9
                tp_targets=[Decimal("1.0"), Decimal("2.0")],
            )

    def test_tp_ratios_length_must_match_tp_levels(self):
        """Test that tp_ratios length must match tp_levels."""
        with pytest.raises(ValueError, match="tp_ratios length must match tp_levels"):
            ExecutionRuntimeConfig(
                tp_levels=3,
                tp_ratios=[Decimal("0.5"), Decimal("0.5")],  # only 2, should be 3
                tp_targets=[Decimal("1.0"), Decimal("2.0"), Decimal("3.0")],
            )

    def test_tp_ratios_must_all_be_positive(self):
        """Test that tp_ratios cannot contain zero or negative values."""
        with pytest.raises(ValueError, match="tp_ratios must all be positive"):
            ExecutionRuntimeConfig(
                tp_levels=2,
                tp_ratios=[Decimal("0"), Decimal("1.0")],
                tp_targets=[Decimal("1.0"), Decimal("2.0")],
            )

        with pytest.raises(ValueError, match="tp_ratios must all be positive"):
            ExecutionRuntimeConfig(
                tp_levels=2,
                tp_ratios=[Decimal("-0.5"), Decimal("1.5")],
                tp_targets=[Decimal("1.0"), Decimal("2.0")],
            )

    def test_tp_targets_must_all_be_positive(self):
        """Test that tp_targets cannot contain zero or negative RR values."""
        with pytest.raises(ValueError, match="tp_targets must all be positive"):
            ExecutionRuntimeConfig(
                tp_levels=2,
                tp_ratios=[Decimal("0.5"), Decimal("0.5")],
                tp_targets=[Decimal("0"), Decimal("2.0")],
            )


# ============================================================
# Test 3: SignalPipeline._apply_runtime_direction_policy()
# ============================================================
class TestSignalPipelineApplyRuntimeDirectionPolicy:
    """Test SignalPipeline._apply_runtime_direction_policy() semantics."""

    def _create_mock_pipeline(
        self,
        runtime_allowed_directions: Optional[List[Direction]] = None,
    ):
        """Create a mock SignalPipeline for testing."""
        # Mock ConfigManager
        mock_config_manager = MagicMock()

        # Mock core config with signal_pipeline settings
        mock_core_config = MagicMock()
        mock_core_config.signal_pipeline.queue.batch_size = 10
        mock_core_config.signal_pipeline.queue.flush_interval = 5.0
        mock_core_config.signal_pipeline.queue.max_queue_size = 1000
        mock_config_manager.get_core_config.return_value = mock_core_config

        # Mock user config
        mock_user_config = MagicMock()
        mock_user_config.active_strategies = []
        mock_user_config.mtf_ema_period = 60
        mock_config_manager.get_user_config_sync.return_value = mock_user_config

        # Create RiskConfig
        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        # Import SignalPipeline here to avoid circular import
        from src.application.signal_pipeline import SignalPipeline

        # Create pipeline with runtime config
        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=MagicMock(),
            signal_repository=None,
            runtime_allowed_directions=runtime_allowed_directions,
        )

        return pipeline

    def test_short_fired_attempt_is_filtered_when_only_long_allowed(self):
        """
        Test that SHORT attempt with SIGNAL_FIRED is changed to FILTERED
        when runtime_allowed_directions={Direction.LONG}.

        Verifies:
        - final_result changed from "SIGNAL_FIRED" to "FILTERED"
        - filter_results appended with "runtime_direction_policy"
        """
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=[Direction.LONG]
        )

        # Create a SHORT signal attempt that would fire
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.SHORT,
                score=Decimal("0.8"),
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        # Create a mock kline
        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        # Apply direction policy
        pipeline._apply_runtime_direction_policy(kline, [attempt])

        # Verify attempt was filtered
        assert attempt.final_result == "FILTERED"

        # Verify filter_results was appended
        assert len(attempt.filter_results) == 1
        filter_name, filter_result = attempt.filter_results[0]
        assert filter_name == "runtime_direction_policy"
        assert filter_result.passed is False
        assert filter_result.reason == "direction_not_allowed_by_runtime_profile"
        assert filter_result.metadata["actual_direction"] == "SHORT"
        assert "LONG" in filter_result.metadata["allowed_directions"]

    def test_long_fired_attempt_not_modified_when_long_allowed(self):
        """
        Test that LONG attempt with SIGNAL_FIRED is NOT modified
        when runtime_allowed_directions={Direction.LONG}.
        """
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=[Direction.LONG]
        )

        # Create a LONG signal attempt that would fire
        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.LONG,
                score=Decimal("0.8"),
                details={},
            ),
            filter_results=[("ema", FilterResult(passed=True, reason="trend_match"))],
            final_result="SIGNAL_FIRED",
        )

        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        # Apply direction policy
        pipeline._apply_runtime_direction_policy(kline, [attempt])

        # Verify attempt was NOT modified
        assert attempt.final_result == "SIGNAL_FIRED"
        assert len(attempt.filter_results) == 1  # Only original filter

    def test_no_modification_when_no_runtime_policy(self):
        """
        Test that attempts are not modified when runtime_allowed_directions is empty.
        """
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=None
        )

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.SHORT,
                score=Decimal("0.8"),
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        # Apply direction policy (should be no-op)
        pipeline._apply_runtime_direction_policy(kline, [attempt])

        # Verify attempt was NOT modified
        assert attempt.final_result == "SIGNAL_FIRED"
        assert len(attempt.filter_results) == 0

    def test_no_modification_when_runtime_policy_empty_list(self):
        """Test empty allowed directions list behaves as no runtime policy."""
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=[]
        )

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.SHORT,
                score=Decimal("0.8"),
                details={},
            ),
            filter_results=[],
            final_result="SIGNAL_FIRED",
        )

        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        pipeline._apply_runtime_direction_policy(kline, [attempt])

        assert attempt.final_result == "SIGNAL_FIRED"
        assert len(attempt.filter_results) == 0

    def test_filtered_attempt_not_modified(self):
        """
        Test that already FILTERED attempts are not modified.
        """
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=[Direction.LONG]
        )

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=PatternResult(
                strategy_name="pinbar",
                direction=Direction.SHORT,
                score=Decimal("0.8"),
                details={},
            ),
            filter_results=[],
            final_result="FILTERED",  # Already filtered
        )

        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        pipeline._apply_runtime_direction_policy(kline, [attempt])

        # Should remain FILTERED, no additional filter_results
        assert attempt.final_result == "FILTERED"
        assert len(attempt.filter_results) == 0

    def test_no_pattern_attempt_not_modified(self):
        """
        Test that attempts without pattern (NO_PATTERN) are not modified.
        """
        pipeline = self._create_mock_pipeline(
            runtime_allowed_directions=[Direction.LONG]
        )

        attempt = SignalAttempt(
            strategy_name="pinbar",
            pattern=None,  # No pattern detected
            filter_results=[],
            final_result="NO_PATTERN",
        )

        kline = KlineData(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            timestamp=1700000000000,
            open=Decimal("2000"),
            high=Decimal("2100"),
            low=Decimal("1950"),
            close=Decimal("2050"),
            volume=Decimal("1000"),
            is_closed=True,
        )

        pipeline._apply_runtime_direction_policy(kline, [attempt])

        # Should remain unchanged
        assert attempt.final_result == "NO_PATTERN"
        assert len(attempt.filter_results) == 0


# ============================================================
# Test 4: SignalPipeline._build_execution_strategy()
# ============================================================
class TestSignalPipelineBuildExecutionStrategy:
    """Test SignalPipeline._build_execution_strategy() semantics."""

    def _create_mock_pipeline(
        self,
        runtime_execution_strategy: Optional[OrderStrategy] = None,
    ):
        """Create a mock SignalPipeline for testing."""
        mock_config_manager = MagicMock()

        mock_core_config = MagicMock()
        mock_core_config.signal_pipeline.queue.batch_size = 10
        mock_core_config.signal_pipeline.queue.flush_interval = 5.0
        mock_core_config.signal_pipeline.queue.max_queue_size = 1000
        mock_config_manager.get_core_config.return_value = mock_core_config

        mock_user_config = MagicMock()
        mock_user_config.active_strategies = []
        mock_user_config.mtf_ema_period = 60
        mock_config_manager.get_user_config_sync.return_value = mock_user_config

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
            max_total_exposure=Decimal("0.8"),
        )

        from src.application.signal_pipeline import SignalPipeline

        pipeline = SignalPipeline(
            config_manager=mock_config_manager,
            risk_config=risk_config,
            notification_service=MagicMock(),
            signal_repository=None,
            runtime_execution_strategy=runtime_execution_strategy,
        )

        return pipeline

    def _create_signal_result(self) -> Any:
        """Create a mock SignalResult for testing."""
        from src.domain.models import SignalResult

        return SignalResult(
            symbol="ETH/USDT:USDT",
            timeframe="1h",
            direction=Direction.LONG,
            entry_price=Decimal("2000"),
            suggested_stop_loss=Decimal("1900"),
            suggested_position_size=Decimal("0.1"),
            current_leverage=10,
            tags=[],
            risk_reward_info="Risk 1% = 200 USDT",
            strategy_name="pinbar",
            take_profit_levels=[
                {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.0"},
                {"id": "TP2", "position_ratio": "0.5", "risk_reward": "3.5"},
            ],
        )

    def test_returns_deep_copy_when_runtime_strategy_injected(self):
        """
        Test that _build_execution_strategy() returns deep copy
        when runtime_execution_strategy is injected.

        Modifying the returned object should not pollute the pipeline's
        internal runtime_execution_strategy.
        """
        # Create runtime execution strategy
        runtime_strategy = OrderStrategy(
            id="runtime_exec",
            name="Runtime Execution",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        pipeline = self._create_mock_pipeline(
            runtime_execution_strategy=runtime_strategy
        )

        signal = self._create_signal_result()

        # Get execution strategy
        strategy1 = pipeline._build_execution_strategy(signal)

        # Modify the returned strategy
        strategy1.tp_ratios[0] = Decimal("0.7")
        strategy1.tp_targets[0] = Decimal("2.0")

        # Get another execution strategy
        strategy2 = pipeline._build_execution_strategy(signal)

        # strategy2 should have original values (not polluted by strategy1 modification)
        assert strategy2.tp_ratios[0] == Decimal("0.5")
        assert strategy2.tp_targets[0] == Decimal("1.0")

        # Internal runtime_execution_strategy should also be unchanged
        assert pipeline._runtime_execution_strategy.tp_ratios[0] == Decimal("0.5")
        assert pipeline._runtime_execution_strategy.tp_targets[0] == Decimal("1.0")

    def test_builds_from_signal_when_no_runtime_strategy(self):
        """
        Test that _build_execution_strategy() builds from SignalResult
        when no runtime_execution_strategy is injected.
        """
        pipeline = self._create_mock_pipeline(
            runtime_execution_strategy=None
        )

        signal = self._create_signal_result()

        # Get execution strategy
        strategy = pipeline._build_execution_strategy(signal)

        # Should be built from signal's take_profit_levels
        assert strategy.tp_levels == 2
        assert strategy.tp_ratios == [Decimal("0.5"), Decimal("0.5")]
        assert strategy.tp_targets == [Decimal("1.0"), Decimal("3.5")]

    def test_multiple_calls_return_independent_copies(self):
        """
        Test that multiple calls return independent copies.

        Each call should return a new object that can be modified independently.
        """
        runtime_strategy = OrderStrategy(
            id="runtime_exec",
            name="Runtime Execution",
            tp_levels=2,
            tp_ratios=[Decimal("0.5"), Decimal("0.5")],
            tp_targets=[Decimal("1.0"), Decimal("3.5")],
            initial_stop_loss_rr=Decimal("-1.0"),
            trailing_stop_enabled=False,
            oco_enabled=True,
        )

        pipeline = self._create_mock_pipeline(
            runtime_execution_strategy=runtime_strategy
        )

        signal = self._create_signal_result()

        strategy1 = pipeline._build_execution_strategy(signal)
        strategy2 = pipeline._build_execution_strategy(signal)

        # Modify strategy1
        strategy1.tp_ratios[0] = Decimal("0.8")

        # strategy2 should be unaffected
        assert strategy2.tp_ratios[0] == Decimal("0.5")


# ============================================================
# Edge Cases and Boundary Tests
# ============================================================
class TestRuntimeConfigEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_strategy_runtime_config_long_only_validation(self):
        """
        Test that Sim-1 StrategyRuntimeConfig requires LONG-only.

        This is a Sim-1 constraint: allowed_directions must be [Direction.LONG].
        """
        trigger = TriggerConfig(
            id="pinbar_trigger",
            type="pinbar",
            enabled=True,
            params={},
        )

        # Valid: LONG-only
        config_valid = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=trigger,
            filters=[],
            atr_enabled=False,
        )
        assert config_valid.allowed_directions == (Direction.LONG,)

        # Invalid: SHORT allowed
        with pytest.raises(ValueError, match="Sim-1 strategy must be LONG-only"):
            StrategyRuntimeConfig(
                allowed_directions=[Direction.SHORT],
                trigger=trigger,
                filters=[],
                atr_enabled=False,
            )

        # Invalid: Both directions allowed
        with pytest.raises(ValueError, match="Sim-1 strategy must be LONG-only"):
            StrategyRuntimeConfig(
                allowed_directions=[Direction.LONG, Direction.SHORT],
                trigger=trigger,
                filters=[],
                atr_enabled=False,
            )

    def test_strategy_runtime_config_atr_disabled_validation(self):
        """
        Test that Sim-1 StrategyRuntimeConfig requires ATR disabled.
        """
        trigger = TriggerConfig(
            id="pinbar_trigger",
            type="pinbar",
            enabled=True,
            params={},
        )

        # Invalid: ATR enabled
        with pytest.raises(ValueError, match="Sim-1 strategy requires ATR disabled"):
            StrategyRuntimeConfig(
                allowed_directions=[Direction.LONG],
                trigger=trigger,
                filters=[],
                atr_enabled=True,  # Should be False for Sim-1
            )

    def test_execution_runtime_config_decimal_precision(self):
        """
        Test that ExecutionRuntimeConfig maintains Decimal precision.

        Financial calculations must use Decimal, not float.
        """
        config = ExecutionRuntimeConfig(
            tp_levels=2,
            tp_ratios=[Decimal("0.333333"), Decimal("0.666667")],  # Sums to 1.0
            tp_targets=[Decimal("1.5"), Decimal("3.5")],
        )

        # Verify Decimal type is preserved
        assert isinstance(config.tp_ratios[0], Decimal)
        assert isinstance(config.tp_ratios[1], Decimal)
        assert isinstance(config.tp_targets[0], Decimal)

        # Verify precision
        assert config.tp_ratios[0] == Decimal("0.333333")
        assert config.tp_ratios[1] == Decimal("0.666667")

    def test_empty_filters_list(self):
        """Test StrategyRuntimeConfig with empty filters list."""
        trigger = TriggerConfig(
            id="pinbar_trigger",
            type="pinbar",
            enabled=True,
            params={},
        )

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=trigger,
            filters=[],  # Empty filters
            atr_enabled=False,
        )

        strategy_def = config.to_strategy_definition()
        assert strategy_def.filters == []

    def test_multiple_filters_preserve_order(self):
        """Test that filter order is preserved in to_strategy_definition()."""
        filters = [
            FilterConfig(id="f1", type="ema", enabled=True, params={}),
            FilterConfig(id="f2", type="mtf", enabled=True, params={}),
            FilterConfig(id="f3", type="atr", enabled=True, params={}),
        ]

        config = StrategyRuntimeConfig(
            allowed_directions=[Direction.LONG],
            trigger=TriggerConfig(id="t", type="pinbar", enabled=True, params={}),
            filters=filters,
            atr_enabled=False,
        )

        strategy_def = config.to_strategy_definition()

        # Verify order is preserved
        assert strategy_def.filters[0].type == "ema"
        assert strategy_def.filters[1].type == "mtf"
        assert strategy_def.filters[2].type == "atr"

    def test_risk_runtime_config_derives_capital_protection_with_startup_equity(self):
        """Runtime risk 应派生 CapitalProtectionConfig，并冻结启动权益口径。"""
        config = RiskRuntimeConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=20,
            max_total_exposure=Decimal("1.0"),
            daily_max_trades=8,
            daily_max_loss_percent=Decimal("0.10"),
        )

        protection = config.to_capital_protection_config(
            account_equity=Decimal("1000"),
            base=CapitalProtectionConfig(),
        )

        assert protection.single_trade["max_loss_percent"] == Decimal("1.00")
        assert protection.daily["max_loss_percent"] == Decimal("10.00")
        assert protection.daily["max_loss_amount"] == Decimal("100.00")
        assert protection.daily["max_trade_count"] == 8
        assert protection.account["max_leverage"] == 20

    def test_risk_runtime_config_derives_capital_protection_without_equity_snapshot(self):
        """启动时没有账户快照时，应保留百分比口径而不是伪造金额。"""
        config = RiskRuntimeConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=20,
            max_total_exposure=Decimal("1.0"),
            daily_max_trades=None,
            daily_max_loss_percent=Decimal("0.10"),
        )

        protection = config.to_capital_protection_config()

        assert protection.daily["max_loss_percent"] == Decimal("10.00")
        assert protection.daily["max_loss_amount"] is None
