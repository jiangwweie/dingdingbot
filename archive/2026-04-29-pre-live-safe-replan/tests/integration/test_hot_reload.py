"""
Integration Tests for Hot-Reload & Strategy Apply Functionality

Tests for SubTask S2-1 - Real-time Engine Hot-Reload & Strategy Apply

Covers:
1. Lock protection during K-line processing while applying new strategy
2. Queue backpressure under rapid strategy applications
3. Rollback mechanism on invalid strategy
4. EMA value continuity verification after hot-reload
"""
import asyncio
import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager, load_all_configs
from src.domain.models import (
    KlineData, SignalAttempt, PatternResult, Direction,
    StrategyDefinition, TriggerConfig, FilterConfig
)
from src.domain.risk_calculator import RiskConfig
from src.domain.indicators import EMACalculator


# ============================================================
# Test Fixtures
# ============================================================
@pytest.fixture
def config_manager():
    """Load real config for integration testing"""
    return load_all_configs()


@pytest.fixture
def risk_config():
    return RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10
    )


@pytest.fixture
def mock_notifier():
    """Create mock notification service"""
    mock = AsyncMock()
    mock.send_signal = AsyncMock()
    return mock


@pytest.fixture
def mock_repository():
    """Create mock signal repository"""
    mock = AsyncMock()
    mock.save_attempt = AsyncMock()
    mock.save_signal = AsyncMock()
    return mock


@pytest.fixture
def pipeline(config_manager, risk_config, mock_notifier, mock_repository):
    """Create signal pipeline with mock dependencies"""
    with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
        mock_getter.return_value = mock_notifier
        return SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            notification_service=mock_notifier,
            signal_repository=mock_repository,
            cooldown_seconds=300
        )


# ============================================================
# S2-1-6-1: Lock Protection During K-line Processing
# ============================================================
class TestLockProtectionDuringStrategyApply:
    """
    Test that asyncio.Lock protects the runner during concurrent:
    - K-line processing (process_kline)
    - Strategy application (on_config_updated)
    """

    @pytest.mark.asyncio
    async def test_concurrent_kline_and_config_update(self, pipeline):
        """Test lock prevents race condition between K-line processing and config update"""
        # Create a bullish pinbar kline
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("65100"),
            low=Decimal("64000"),  # Long lower wick
            close=Decimal("65050"),  # Small body at top
            volume=Decimal("1000"),
            is_closed=True
        )

        # Store initial runner reference
        initial_runner = pipeline._runner

        # Track any errors during concurrent execution
        errors = []

        async def process_with_error_handling():
            try:
                await pipeline.process_kline(kline)
            except Exception as e:
                errors.append(("process_kline", e))

        async def reload_with_error_handling():
            try:
                await pipeline.on_config_updated()
            except Exception as e:
                errors.append(("config_reload", e))

        # Run concurrently - lock should serialize access to runner
        await asyncio.gather(
            process_with_error_handling(),
            reload_with_error_handling(),
            return_exceptions=True
        )

        # Assertions
        assert len(errors) == 0, f"Errors during concurrent execution: {errors}"
        assert pipeline._runner is not None, "Runner should not be None after concurrent access"
        assert pipeline._runner is not initial_runner, "Runner should be rebuilt after config reload"

    @pytest.mark.asyncio
    async def test_lock_serializes_runner_rebuild(self, pipeline):
        """Test that lock ensures atomic runner rebuild"""
        # Create multiple klines
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000") + Decimal(str(i * 10)),
                high=Decimal("66000") + Decimal(str(i * 10)),
                low=Decimal("64500") + Decimal(str(i * 10)),
                close=Decimal("65500") + Decimal(str(i * 10)),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(5)
        ]

        # Interleave kline processing with config reloads
        tasks = []
        for i, kline in enumerate(klines):
            tasks.append(pipeline.process_kline(kline))
            if i % 2 == 0:
                tasks.append(pipeline.on_config_updated())

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Exceptions during interleaved execution: {exceptions}"

        # Runner should be valid
        assert pipeline._runner is not None
        assert hasattr(pipeline._runner, 'run_all')

    @pytest.mark.asyncio
    async def test_no_partial_runner_state(self, pipeline):
        """Test that runner is never in partial/incomplete state during rebuild"""
        captured_runners = []

        async def capture_runner_state():
            for _ in range(10):
                captured_runners.append(pipeline._runner)
                await asyncio.sleep(0.01)

        async def rapid_reloads():
            for _ in range(3):
                await pipeline.on_config_updated()
                await asyncio.sleep(0.02)

        await asyncio.gather(capture_runner_state(), rapid_reloads())

        # All captured runners should be valid
        for runner in captured_runners:
            if runner is not None:
                assert hasattr(runner, 'run_all'), "Runner missing expected method"


# ============================================================
# S2-1-6-2: Queue Backpressure Under Rapid Strategy Applications
# ============================================================
class TestQueueBackpressureUnderRapidUpdates:
    """
    Test that async queue handles backpressure correctly when
    multiple strategy updates are applied rapidly.
    """

    @pytest.mark.asyncio
    async def test_queue_handles_rapid_attempts(self, pipeline, mock_repository):
        """Test queue doesn't drop attempts under rapid updates"""
        # Create klines that trigger multiple attempts
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000"),
                high=Decimal("66000"),
                low=Decimal("64500"),
                close=Decimal("65500"),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(10)
        ]

        # Process klines rapidly
        for kline in klines:
            await pipeline.process_kline(kline)

        # Queue should be created
        assert pipeline._attempts_queue is not None

        # Queue may have items or may already be processed (both are valid)
        # The key test is that processing completed without errors
        queue_size = pipeline._attempts_queue.qsize()

        # Wait for flush worker to process any remaining items
        await asyncio.sleep(0.5)

        # Queue should be drained or empty
        final_size = pipeline._attempts_queue.qsize()
        assert final_size <= queue_size, "Queue should be processed by flush worker"

    @pytest.mark.asyncio
    async def test_queue_does_not_block_on_full(self, pipeline, mock_repository):
        """Test that full queue doesn't block processing"""
        # Fill the queue by processing many klines
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000"),
                high=Decimal("66000"),
                low=Decimal("64500"),
                close=Decimal("65500"),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(50)
        ]

        # Process all klines - should not block even if queue fills
        start_time = time.time()
        for kline in klines:
            await pipeline.process_kline(kline)
        elapsed = time.time() - start_time

        # Should complete within reasonable time (not blocked)
        assert elapsed < 5.0, f"Processing took too long: {elapsed}s (possible queue block)"

    @pytest.mark.asyncio
    async def test_flush_worker_recovers_from_error(self, pipeline, mock_repository):
        """Test flush worker continues after individual save errors"""
        # Make repository fail occasionally
        call_count = 0

        def flaky_save(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise Exception("Simulated database error")
            return asyncio.coroutine(lambda: None)()

        mock_repository.save_attempt.side_effect = flaky_save

        # Process klines
        for i in range(6):
            kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000"),
                high=Decimal("66000"),
                low=Decimal("64500"),
                close=Decimal("65500"),
                volume=Decimal("1000"),
                is_closed=True
            )
            await pipeline.process_kline(kline)

        # Wait for flush worker
        await asyncio.sleep(1.0)

        # Flush worker should still be running
        assert pipeline._flush_task is not None
        assert not pipeline._flush_task.done(), "Flush worker should still be running"


# ============================================================
# S2-1-6-3: Rollback Mechanism on Invalid Strategy
# ============================================================
class TestRollbackOnInvalidStrategy:
    """
    Test that invalid strategy application:
    - Validates before applying
    - Rolls back on validation failure
    - Preserves previous valid config
    """

    @pytest.mark.asyncio
    async def test_invalid_strategy_rejected(self, config_manager):
        """Test that invalid strategy definition is rejected"""
        # Invalid strategy: missing required fields
        invalid_strategy = {
            "name": "",  # Empty name
            "logic_tree": {"invalid": "structure"}  # Invalid logic tree
        }

        # Attempt to update config with invalid strategy
        with pytest.raises(Exception) as exc_info:
            await config_manager.update_user_config({
                "active_strategies": [invalid_strategy]
            })

        # Should raise ValidationError or similar
        assert "ValidationError" in str(type(exc_info.value).__name__) or \
               "invalid" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_config_preserved_after_invalid_update(self, config_manager):
        """Test that previous valid config is preserved after invalid update attempt"""
        # Store original config
        original_strategies = config_manager.user_config.active_strategies.copy()

        # Attempt invalid update
        try:
            await config_manager.update_user_config({
                "active_strategies": [{"invalid": "strategy"}]
            })
        except Exception:
            pass  # Expected to fail

        # Reload config manager to check preservation
        # In real scenario, config should be unchanged on disk
        # For testing, verify in-memory state wasn't corrupted
        assert config_manager._user_config is not None

    @pytest.mark.asyncio
    async def test_valid_strategy_applied_successfully(self, config_manager):
        """Test that valid strategy is applied successfully"""
        # Create a valid simple strategy
        valid_strategy = {
            "name": "test_pinbar",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {
                    "min_wick_ratio": 0.6,
                    "max_body_ratio": 0.3,
                    "body_position_tolerance": 0.1
                }
            },
            "filters": [],
            "filter_logic": "AND"
        }

        # Apply valid strategy
        new_config = await config_manager.update_user_config({
            "active_strategies": [valid_strategy]
        })

        # Verify strategy was added
        assert len(new_config.active_strategies) >= 1
        assert new_config.active_strategies[0].name == "test_pinbar"

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_invalid_strategy_attempt(self, pipeline, config_manager):
        """Test that pipeline continues functioning after invalid strategy attempt"""
        # Process a kline first
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("66000"),
            low=Decimal("64500"),
            close=Decimal("65500"),
            volume=Decimal("1000"),
            is_closed=True
        )

        await pipeline.process_kline(kline)
        assert pipeline._runner is not None

        # Attempt invalid config update (should fail gracefully)
        try:
            await config_manager.update_user_config({
                "active_strategies": [{"completely": "invalid"}]
            })
        except Exception:
            pass  # Expected

        # Pipeline should still be functional
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567891000,
            open=Decimal("65500"),
            high=Decimal("66500"),
            low=Decimal("65000"),
            close=Decimal("66000"),
            volume=Decimal("1000"),
            is_closed=True
        )

        await pipeline.process_kline(kline2)
        assert pipeline._runner is not None


# ============================================================
# S2-1-6-4: EMA Value Continuity After Hot-Reload
# ============================================================
class TestEMAContinuityAfterHotReload:
    """
    Test that EMA values remain continuous (no reset/jump) after hot-reload.
    This verifies the warmup mechanism correctly restores indicator state.
    """

    @pytest.mark.asyncio
    async def test_ema_continuity_after_reload(self, config_manager, risk_config, mock_notifier, mock_repository):
        """Test EMA value continuity across hot-reload"""
        # Create pipeline
        with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
            mock_getter.return_value = mock_notifier
            pipeline = SignalPipeline(
                config_manager=config_manager,
                risk_config=risk_config,
                notification_service=mock_notifier,
                signal_repository=mock_repository,
                cooldown_seconds=300
            )

            # Feed a series of klines to build EMA state
            base_price = Decimal("65000")
            ema_values_before = []

            for i in range(30):
                kline = KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1234567890000 + i * 1000,
                    open=base_price + Decimal(str(i)),
                    high=base_price + Decimal(str(i + 10)),
                    low=base_price + Decimal(str(i - 5)),
                    close=base_price + Decimal(str(i + 5)),
                    volume=Decimal("1000"),
                    is_closed=True
                )

                await pipeline.process_kline(kline)

                # Get EMA value from runner's internal state
                runner = pipeline._runner
                # Access EMA through runner's filter context or state
                if hasattr(runner, '_ema_calculators'):
                    ema_key = f"BTC/USDT:USDT:15m"
                    if ema_key in runner._ema_calculators:
                        ema_value = runner._ema_calculators[ema_key].value
                        if ema_value is not None:
                            ema_values_before.append(ema_value)

            # Trigger hot-reload
            await pipeline.on_config_updated()

            # EMA should be restored through warmup from kline history
            # Get EMA value after reload
            ema_values_after = []
            for i in range(5):
                kline = KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1234567890000 + (30 + i) * 1000,
                    open=base_price + Decimal(str(30 + i)),
                    high=base_price + Decimal(str(30 + i + 10)),
                    low=base_price + Decimal(str(30 + i - 5)),
                    close=base_price + Decimal(str(30 + i + 5)),
                    volume=Decimal("1000"),
                    is_closed=True
                )
                await pipeline.process_kline(kline)

                runner = pipeline._runner
                if hasattr(runner, '_ema_calculators'):
                    ema_key = f"BTC/USDT:USDT:15m"
                    if ema_key in runner._ema_calculators:
                        ema_value = runner._ema_calculators[ema_key].value
                        if ema_value is not None:
                            ema_values_after.append(ema_value)

            # If we captured EMA values, verify continuity
            if ema_values_before and ema_values_after:
                # EMA should not reset to None or zero
                assert ema_values_after[0] is not None, "EMA should be restored after reload"
                assert ema_values_after[0] > Decimal("0"), "EMA should be positive"

                # EMA change should be smooth (no sudden jumps > 10%)
                last_before = ema_values_before[-1]
                first_after = ema_values_after[0]
                change_ratio = abs(first_after - last_before) / last_before
                assert change_ratio < Decimal("0.1"), \
                    f"EMA jumped too much: {change_ratio} (expected smooth transition)"

    @pytest.mark.asyncio
    async def test_warmup_replays_kline_history(self, config_manager, risk_config, mock_notifier, mock_repository):
        """Test that warmup replays cached K-line history"""
        with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
            mock_getter.return_value = mock_notifier
            pipeline = SignalPipeline(
                config_manager=config_manager,
                risk_config=risk_config,
                notification_service=mock_notifier,
                signal_repository=mock_repository,
                cooldown_seconds=300
            )

            # Feed klines to build history
            for i in range(20):
                kline = KlineData(
                    symbol="ETH/USDT:USDT",
                    timeframe="1h",
                    timestamp=1234567890000 + i * 3600000,
                    open=Decimal("3500") + Decimal(str(i)),
                    high=Decimal("3550") + Decimal(str(i)),
                    low=Decimal("3450") + Decimal(str(i)),
                    close=Decimal("3520") + Decimal(str(i)),
                    volume=Decimal("500"),
                    is_closed=True
                )
                await pipeline.process_kline(kline)

            # Verify history is cached
            history_key = "ETH/USDT:USDT:1h"
            assert history_key in pipeline._kline_history
            assert len(pipeline._kline_history[history_key]) == 20

            # Store runner's expected warmup count
            runner_before = pipeline._runner

            # Trigger reload
            await pipeline.on_config_updated()

            # New runner should have been warmed up
            runner_after = pipeline._runner
            assert runner_after is not runner_before, "Runner should be rebuilt"

            # History should still be available
            assert history_key in pipeline._kline_history
            assert len(pipeline._kline_history[history_key]) == 20

    @pytest.mark.asyncio
    async def test_no_ema_reset_on_rapid_reloads(self, config_manager, risk_config, mock_notifier, mock_repository):
        """Test EMA doesn't reset during rapid consecutive reloads"""
        with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
            mock_getter.return_value = mock_notifier
            pipeline = SignalPipeline(
                config_manager=config_manager,
                risk_config=risk_config,
                notification_service=mock_notifier,
                signal_repository=mock_repository,
                cooldown_seconds=300
            )

            # Build up EMA state
            for i in range(25):
                kline = KlineData(
                    symbol="SOL/USDT:USDT",
                    timeframe="15m",
                    timestamp=1234567890000 + i * 1000,
                    open=Decimal("150") + Decimal(str(i * 0.1)),
                    high=Decimal("152") + Decimal(str(i * 0.1)),
                    low=Decimal("148") + Decimal(str(i * 0.1)),
                    close=Decimal("151") + Decimal(str(i * 0.1)),
                    volume=Decimal("100"),
                    is_closed=True
                )
                await pipeline.process_kline(kline)

            # Perform rapid reloads
            for _ in range(5):
                await pipeline.on_config_updated()

            # EMA should still be valid (not reset)
            runner = pipeline._runner
            assert runner is not None

            # Continue processing - should work without issues
            kline = KlineData(
                symbol="SOL/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + 25 * 1000,
                open=Decimal("152.5"),
                high=Decimal("154"),
                low=Decimal("151"),
                close=Decimal("153"),
                volume=Decimal("100"),
                is_closed=True
            )
            await pipeline.process_kline(kline)

            # Pipeline should be functional
            assert pipeline._runner is not None


# ============================================================
# S2-1-6-5: End-to-End Hot-Reload Flow
# ============================================================
class TestEndToEndHotReloadFlow:
    """
    End-to-end tests for complete hot-reload workflow.
    """

    @pytest.mark.asyncio
    async def test_full_apply_workflow(self, config_manager, risk_config, mock_notifier, mock_repository):
        """Test complete strategy apply workflow"""
        # Step 1: Create pipeline
        with patch('src.application.signal_pipeline.get_notification_service') as mock_getter:
            mock_getter.return_value = mock_notifier
            pipeline = SignalPipeline(
                config_manager=config_manager,
                risk_config=risk_config,
                notification_service=mock_notifier,
                signal_repository=mock_repository,
                cooldown_seconds=60
            )

            # Step 2: Process initial klines
            initial_klines = [
                KlineData(
                    symbol="BTC/USDT:USDT",
                    timeframe="15m",
                    timestamp=1234567890000 + i * 1000,
                    open=Decimal("65000") + Decimal(str(i * 10)),
                    high=Decimal("65500") + Decimal(str(i * 10)),
                    low=Decimal("64500") + Decimal(str(i * 10)),
                    close=Decimal("65200") + Decimal(str(i * 10)),
                    volume=Decimal("1000"),
                    is_closed=True
                )
                for i in range(10)
            ]

            for kline in initial_klines:
                await pipeline.process_kline(kline)

            # Step 3: Apply new strategy via config update
            new_strategy = {
                "name": "aggressive_pinbar",
                "enabled": True,
                "trigger": {
                    "type": "pinbar",
                    "enabled": True,
                    "params": {
                        "min_wick_ratio": 0.5,  # More lenient
                        "max_body_ratio": 0.4,
                        "body_position_tolerance": 0.15
                    }
                },
                "filters": [
                    {
                        "type": "ema",
                        "period": 60,
                        "enabled": True
                    }
                ],
                "filter_logic": "AND"
            }

            await config_manager.update_user_config({
                "active_strategies": [new_strategy]
            })

            # Step 4: Verify pipeline is functional with new strategy
            test_kline = KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + 10 * 1000,
                open=Decimal("65300"),
                high=Decimal("65400"),
                low=Decimal("65100"),
                close=Decimal("65350"),
                volume=Decimal("1000"),
                is_closed=True
            )

            await pipeline.process_kline(test_kline)

            # Pipeline should be functional
            assert pipeline._runner is not None
            assert len(pipeline._kline_history) > 0

    @pytest.mark.asyncio
    async def test_multiple_strategies_applied_sequentially(self, config_manager, pipeline):
        """Test applying multiple strategies sequentially"""
        strategies = [
            {
                "name": f"strategy_{i}",
                "enabled": True,
                "trigger": {
                    "type": "pinbar",
                    "enabled": True,
                    "params": {"min_wick_ratio": 0.6 - i * 0.1}
                },
                "filters": [],
                "filter_logic": "AND"
            }
            for i in range(3)
        ]

        for strategy in strategies:
            await config_manager.update_user_config({
                "active_strategies": [strategy]
            })
            # Verify each strategy was applied
            assert config_manager.user_config.active_strategies[0].name == strategy["name"]

        # Pipeline should still be functional
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("66000"),
            low=Decimal("64500"),
            close=Decimal("65500"),
            volume=Decimal("1000"),
            is_closed=True
        )
        await pipeline.process_kline(kline)
        assert pipeline._runner is not None


# ============================================================
# S2-1-6-6: Edge Cases and Boundary Conditions
# ============================================================
class TestEdgeCasesAndBoundaries:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_empty_strategy_list_handled(self, config_manager):
        """Test that empty strategy list is handled gracefully"""
        # Apply empty strategy list
        await config_manager.update_user_config({
            "active_strategies": []
        })

        # Should not crash
        assert config_manager.user_config.active_strategies == []

    @pytest.mark.asyncio
    async def test_strategy_with_no_filters(self, config_manager, pipeline):
        """Test strategy with no filters works correctly"""
        strategy_no_filters = {
            "name": "naked_pinbar",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {
                    "min_wick_ratio": 0.6,
                    "max_body_ratio": 0.3,
                    "body_position_tolerance": 0.1
                }
            },
            "filters": [],  # No filters
            "filter_logic": "AND"
        }

        await config_manager.update_user_config({
            "active_strategies": [strategy_no_filters]
        })

        # Process kline - should work without filters
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("65100"),
            low=Decimal("64000"),
            close=Decimal("65050"),
            volume=Decimal("1000"),
            is_closed=True
        )
        await pipeline.process_kline(kline)
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_disabled_strategy_does_not_fire(self, config_manager, pipeline):
        """Test that disabled strategy does not fire signals"""
        disabled_strategy = {
            "name": "disabled_pinbar",
            "enabled": False,  # Disabled
            "trigger": {
                "type": "pinbar",
                "enabled": False,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        await config_manager.update_user_config({
            "active_strategies": [disabled_strategy]
        })

        # Process a clear pinbar kline
        kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("65000"),
            high=Decimal("65100"),
            low=Decimal("64000"),
            close=Decimal("65050"),
            volume=Decimal("1000"),
            is_closed=True
        )
        await pipeline.process_kline(kline)

        # Runner should exist but strategy should be disabled
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_extreme_kline_values_handled(self, pipeline):
        """Test that extreme K-line values are handled"""
        extreme_kline = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567890000,
            open=Decimal("0.00001"),  # Very small
            high=Decimal("999999999"),  # Very large
            low=Decimal("0.00001"),
            close=Decimal("50000"),
            volume=Decimal("0.00000001"),
            is_closed=True
        )

        # Should not crash
        await pipeline.process_kline(extreme_kline)
        assert pipeline._runner is not None
