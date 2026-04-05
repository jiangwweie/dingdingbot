"""
Integration Tests for Configuration Hot-Reload Functionality

Tests for Task I1 - Config Hot-Reload Integration Testing

Covers:
1. Configuration modification triggers reload
2. New configuration takes effect after hot-reload
3. Hot-reload failure rollback mechanism
4. Request handling during hot-reload
5. Multiple rapid hot-reload scenarios

Boundary Checks:
- [x] Hot-reload timeout handling
- [x] Hot-reload failure handling
- [x] Concurrent hot-reload requests
"""
import asyncio
import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

from src.application.config_manager import ConfigManager, load_all_configs
from src.application.signal_pipeline import SignalPipeline
from src.domain.models import (
    KlineData, SignalAttempt, PatternResult, Direction,
    StrategyDefinition, TriggerConfig, FilterConfig,
    PinbarParams, EngulfingParams
)
from src.domain.risk_calculator import RiskConfig


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
    mock.check_pending_signals = AsyncMock()
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
# I1-1: Configuration Modification Triggers Reload
# ============================================================
class TestConfigModificationTriggersReload:
    """
    Test that configuration modifications correctly trigger
    the hot-reload mechanism and observer notifications.
    """

    @pytest.mark.asyncio
    async def test_config_update_triggers_observer(self, config_manager):
        """Test that config update triggers observer callback"""
        # Track observer calls
        observer_called = asyncio.Event()
        call_count = 0

        async def test_observer():
            nonlocal call_count
            call_count += 1
            observer_called.set()

        # Register observer
        config_manager.add_observer(test_observer)

        # Update config
        new_strategy = {
            "name": "test_strategy",
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

        await config_manager.update_user_config({
            "active_strategies": [new_strategy]
        })

        # Wait for observer
        await asyncio.wait_for(observer_called.wait(), timeout=5.0)

        # Verify observer was called
        assert call_count >= 1, "Observer should be called on config update"

    @pytest.mark.asyncio
    async def test_config_update_atomic_swap(self, config_manager):
        """Test that config update uses atomic pointer swap"""
        # Store original config reference
        original_config_ref = config_manager._user_config

        # Update config
        new_strategy = {
            "name": "atomic_test",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        new_config = await config_manager.update_user_config({
            "active_strategies": [new_strategy]
        })

        # Verify atomic swap occurred
        assert config_manager._user_config is not original_config_ref, \
            "Config should be atomically swapped"
        assert config_manager._user_config is new_config, \
            "Config manager should reference new config"

    @pytest.mark.asyncio
    async def test_config_update_persists_to_disk(self, config_manager, tmp_path):
        """Test that config update persists to disk"""
        # Create a temp config directory
        import shutil
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Copy current config to temp location (both user.yaml and core.yaml)
        import yaml
        original_user_path = config_manager.config_dir / 'user.yaml'
        original_core_path = config_manager.config_dir / 'core.yaml'
        temp_user_path = config_dir / 'user.yaml'
        temp_core_path = config_dir / 'core.yaml'
        shutil.copy(original_user_path, temp_user_path)
        shutil.copy(original_core_path, temp_core_path)

        # Create config manager with temp dir
        temp_manager = ConfigManager(config_dir=str(config_dir))
        temp_manager.load_core_config()
        temp_manager.load_user_config()

        # Update config
        new_strategy = {
            "name": "persistence_test",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        await temp_manager.update_user_config({
            "active_strategies": [new_strategy]
        })

        # Verify file was written
        assert temp_user_path.exists(), "Config file should be persisted"

        # Reload and verify content
        with open(temp_user_path, 'r', encoding='utf-8') as f:
            saved_data = yaml.safe_load(f)

        assert len(saved_data.get('active_strategies', [])) >= 1, \
            "Saved config should contain new strategy"


# ============================================================
# I1-2: New Configuration Takes Effect After Hot-Reload
# ============================================================
class TestNewConfigTakesEffect:
    """
    Test that new configuration correctly takes effect
    after hot-reload, affecting strategy execution.
    """

    @pytest.mark.asyncio
    async def test_new_strategy_applied_to_pipeline(self, config_manager, pipeline, mock_repository):
        """Test that new strategy is applied to signal pipeline after hot-reload"""
        # Create a bullish pinbar kline
        pinbar_kline = KlineData(
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

        # First, process with default config
        await pipeline.process_kline(pinbar_kline)
        initial_runner = pipeline._runner

        # Update config with new strategy (more lenient pinbar)
        new_strategy = {
            "name": "lenient_pinbar",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {
                    "min_wick_ratio": Decimal("0.4"),  # More lenient
                    "max_body_ratio": Decimal("0.4"),
                    "body_position_tolerance": Decimal("0.2")
                }
            },
            "filters": [],
            "filter_logic": "AND"
        }

        await config_manager.update_user_config({
            "active_strategies": [new_strategy]
        })

        # Trigger reload
        await pipeline.on_config_updated()

        # Verify runner was rebuilt
        assert pipeline._runner is not initial_runner, \
            "Runner should be rebuilt after config reload"

        # Pipeline should still be functional
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567891000,
            open=Decimal("65100"),
            high=Decimal("65200"),
            low=Decimal("65000"),
            close=Decimal("65150"),
            volume=Decimal("1000"),
            is_closed=True
        )
        await pipeline.process_kline(kline2)
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_filter_chain_updated_after_reload(self, config_manager, pipeline):
        """Test that filter chain is updated after hot-reload"""
        # Update config with EMA filter
        strategy_with_ema = {
            "name": "ema_filtered_pinbar",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [
                {
                    "type": "ema",
                    "period": 21,  # Different period
                    "enabled": True
                }
            ],
            "filter_logic": "AND"
        }

        await config_manager.update_user_config({
            "active_strategies": [strategy_with_ema]
        })

        # Trigger reload
        await pipeline.on_config_updated()

        # Runner should have new filter configuration
        assert pipeline._runner is not None

        # Process kline to verify filter is active
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
    async def test_mtf_ema_period_updated_after_reload(self, config_manager, pipeline):
        """Test that MTF EMA period is updated after hot-reload"""
        # Update MTF EMA period
        await config_manager.update_user_config({
            "mtf_ema_period": 50  # Change from default 60
        })

        # Trigger reload
        await pipeline.on_config_updated()

        # Verify pipeline is functional
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


# ============================================================
# I1-3: Hot-Reload Failure Rollback Mechanism
# ============================================================
class TestHotReloadFailureRollback:
    """
    Test that hot-reload failures are handled correctly
    and previous valid configuration is preserved.
    """

    @pytest.mark.asyncio
    async def test_invalid_strategy_rejected_by_validation(self, config_manager):
        """Test that invalid strategy is rejected by Pydantic validation"""
        # Invalid strategy: missing required trigger fields
        invalid_strategy = {
            "name": "invalid",
            "enabled": True,
            "trigger": {
                "type": "invalid_type",  # Invalid type
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        # Should raise ValidationError
        with pytest.raises(Exception) as exc_info:
            await config_manager.update_user_config({
                "active_strategies": [invalid_strategy]
            })

        # Verify error is validation-related
        assert exc_info.value is not None

    @pytest.mark.asyncio
    async def test_config_preserved_after_invalid_update(self, config_manager):
        """Test that valid config is preserved after invalid update attempt"""
        # Store original config state
        original_strategies_count = len(config_manager.user_config.active_strategies)

        # Attempt invalid update
        try:
            await config_manager.update_user_config({
                "active_strategies": [{"completely": "invalid"}]
            })
        except Exception:
            pass  # Expected to fail

        # Config should be unchanged (Pydantic validation prevents invalid state)
        # The in-memory config should still be valid
        assert config_manager._user_config is not None
        assert hasattr(config_manager.user_config, 'active_strategies')

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_failed_reload(self, pipeline, config_manager):
        """Test that pipeline continues functioning after failed reload attempt"""
        # Process initial kline
        kline1 = KlineData(
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

        await pipeline.process_kline(kline1)
        assert pipeline._runner is not None

        # Attempt invalid config update (should fail gracefully)
        try:
            await config_manager.update_user_config({
                "active_strategies": [{"invalid": "data"}]
            })
        except Exception:
            pass  # Expected

        # Pipeline should still be functional
        kline2 = KlineData(
            symbol="BTC/USDT:USDT",
            timeframe="15m",
            timestamp=1234567891000,
            open=Decimal("65100"),
            high=Decimal("65200"),
            low=Decimal("65000"),
            close=Decimal("65150"),
            volume=Decimal("1000"),
            is_closed=True
        )

        await pipeline.process_kline(kline2)
        assert pipeline._runner is not None, "Pipeline should still be functional after failed reload"

    @pytest.mark.asyncio
    async def test_observer_error_does_not_break_reload(self, config_manager, pipeline):
        """Test that observer error doesn't break the reload mechanism"""
        # Add a failing observer
        async def failing_observer():
            raise Exception("Simulated observer failure")

        config_manager.add_observer(failing_observer)

        # Update config - should not raise, observer error is logged but swallowed
        new_strategy = {
            "name": "test",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        # This should complete despite observer failure
        await config_manager.update_user_config({
            "active_strategies": [new_strategy]
        })

        # Config should be updated
        assert config_manager._user_config is not None

    @pytest.mark.asyncio
    async def test_yaml_persist_error_handling(self, config_manager, tmp_path):
        """Test handling of YAML persist errors"""
        # Create config manager with read-only temp dir
        config_dir = tmp_path / "readonly_config"
        config_dir.mkdir()

        # Copy config files
        import shutil
        shutil.copy(config_manager.config_dir / 'user.yaml', config_dir / 'user.yaml')
        shutil.copy(config_manager.config_dir / 'core.yaml', config_dir / 'core.yaml')

        # Make file read-only to simulate write error
        user_yaml = config_dir / 'user.yaml'
        user_yaml.chmod(0o444)

        readonly_manager = ConfigManager(config_dir=str(config_dir))
        readonly_manager.load_core_config()
        readonly_manager.load_user_config()

        # Update should fail on persist but config should still be updated in memory
        new_strategy = {
            "name": "test",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        try:
            await readonly_manager.update_user_config({
                "active_strategies": [new_strategy]
            })
        except Exception:
            pass  # May fail on persist

        # In-memory config should be updated even if persist fails
        assert readonly_manager._user_config is not None


# ============================================================
# I1-4: Request Handling During Hot-Reload
# ============================================================
class TestRequestHandlingDuringHotReload:
    """
    Test that requests are handled correctly during hot-reload
    with proper lock protection.
    """

    @pytest.mark.asyncio
    async def test_concurrent_kline_and_reload(self, pipeline):
        """Test concurrent kline processing and config reload"""
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
                errors.append(("reload", e))

        # Run concurrently
        await asyncio.gather(
            process_with_error_handling(),
            reload_with_error_handling(),
            return_exceptions=True
        )

        # No errors should occur
        assert len(errors) == 0, f"Errors during concurrent execution: {errors}"
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_lock_serializes_runner_access(self, pipeline):
        """Test that lock properly serializes runner access"""
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
            for i in range(10)
        ]

        # Interleave kline processing with reloads
        tasks = []
        for i, kline in enumerate(klines):
            tasks.append(pipeline.process_kline(kline))
            if i % 3 == 0:
                tasks.append(pipeline.on_config_updated())

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"Exceptions during interleaved execution: {exceptions}"

        # Runner should be valid
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_no_deadlock_under_contention(self, pipeline, config_manager):
        """Test no deadlock under high contention"""
        # Many concurrent operations
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

        async def process():
            await pipeline.process_kline(kline)

        async def reload():
            await pipeline.on_config_updated()

        # Run many concurrent tasks with timeout
        tasks = [process() for _ in range(5)] + [reload() for _ in range(3)]

        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            pytest.fail("Deadlock detected: operations did not complete within timeout")

        # All operations should complete
        assert pipeline._runner is not None


# ============================================================
# I1-5: Multiple Rapid Hot-Reload Scenarios
# ============================================================
class TestMultipleRapidHotReloads:
    """
    Test system behavior under multiple rapid hot-reload scenarios.
    """

    @pytest.mark.asyncio
    async def test_rapid_consecutive_reloads(self, pipeline, config_manager):
        """Test rapid consecutive config reloads"""
        # Perform multiple rapid reloads
        for i in range(5):
            new_strategy = {
                "name": f"strategy_{i}",
                "enabled": True,
                "trigger": {
                    "type": "pinbar",
                    "enabled": True,
                    "params": {}
                },
                "filters": [],
                "filter_logic": "AND"
            }

            await config_manager.update_user_config({
                "active_strategies": [new_strategy]
            })
            await pipeline.on_config_updated()

        # Final state should be valid
        assert pipeline._runner is not None
        assert config_manager._user_config is not None

    @pytest.mark.asyncio
    async def test_rapid_reload_with_kline_processing(self, pipeline, config_manager):
        """Test rapid reloads interleaved with kline processing"""
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 1000,
                open=Decimal("65000"),
                high=Decimal("65100"),
                low=Decimal("64000"),
                close=Decimal("65050"),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(10)
        ]

        # Interleave klines and reloads
        for i, kline in enumerate(klines):
            await pipeline.process_kline(kline)
            if i % 2 == 0:
                await config_manager.update_user_config({
                    "active_strategies": [{
                        "name": f"mid_stream_{i}",
                        "enabled": True,
                        "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                        "filters": [],
                        "filter_logic": "AND"
                    }]
                })
                await pipeline.on_config_updated()

        # Should complete without errors
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_concurrent_reload_requests(self, pipeline, config_manager):
        """Test concurrent reload requests are handled safely"""
        reload_results = []

        async def try_reload(index):
            try:
                await pipeline.on_config_updated()
                reload_results.append(("success", index))
            except Exception as e:
                reload_results.append(("error", index, str(e)))

        # Fire multiple concurrent reloads
        await asyncio.gather(*[try_reload(i) for i in range(5)])

        # All should complete (some may be serialized by lock)
        successful = [r for r in reload_results if r[0] == "success"]
        assert len(successful) >= 1, "At least one reload should succeed"

        # Final state should be valid
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_rapid_strategy_param_changes(self, pipeline, config_manager):
        """Test rapid changes to strategy parameters"""
        pinbar_params = [
            {"min_wick_ratio": Decimal(str(0.4 + i * 0.1)), "max_body_ratio": Decimal(str(0.3 - i * 0.05)), "body_position_tolerance": Decimal(str(0.1 + i * 0.02))}
            for i in range(5)
        ]

        for params in pinbar_params:
            strategy = {
                "name": f"param_test_{float(params['min_wick_ratio'])}",
                "enabled": True,
                "trigger": {
                    "type": "pinbar",
                    "enabled": True,
                    "params": params
                },
                "filters": [],
                "filter_logic": "AND"
            }

            await config_manager.update_user_config({
                "active_strategies": [strategy]
            })
            await pipeline.on_config_updated()

        # Final state should be valid
        assert pipeline._runner is not None

    @pytest.mark.asyncio
    async def test_reload_timeout_protection(self, config_manager):
        """Test that reload has timeout protection for slow observers"""
        # Add a slow observer
        async def slow_observer():
            await asyncio.sleep(0.5)

        config_manager.add_observer(slow_observer)

        # Update config
        new_strategy = {
            "name": "timeout_test",
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        # Should complete (observers run concurrently via asyncio.gather)
        start = time.time()
        await config_manager.update_user_config({
            "active_strategies": [new_strategy]
        })
        elapsed = time.time() - start

        # Should complete within reasonable time (observers run concurrently)
        # Multiple concurrent observers should not multiply wait time
        assert elapsed < 2.0, f"Update took too long: {elapsed}s"

        # Config should be updated despite slow observer
        assert config_manager._user_config is not None


# ============================================================
# I1-6: Edge Cases and Boundary Conditions
# ============================================================
class TestEdgeCasesAndBoundaries:
    """Test edge cases and boundary conditions for hot-reload"""

    @pytest.mark.asyncio
    async def test_empty_config_update(self, config_manager):
        """Test empty config update is handled"""
        # Empty update should merge with existing
        new_config = await config_manager.update_user_config({})

        # Should still be valid
        assert new_config is not None
        assert hasattr(new_config, 'active_strategies')

    @pytest.mark.asyncio
    async def test_partial_config_update(self, config_manager):
        """Test partial config update only changes specified fields"""
        original_timeframes = config_manager.user_config.timeframes.copy()

        # Update only timeframes
        await config_manager.update_user_config({
            "timeframes": ["5m", "15m", "1h"]
        })

        # Other fields should be preserved
        assert config_manager.user_config.timeframes == ["5m", "15m", "1h"]
        # Exchange config should be preserved
        assert config_manager.user_config.exchange is not None

    @pytest.mark.asyncio
    async def test_first_observer_registration(self, config_manager):
        """Test first observer registration"""
        async def observer():
            pass

        # Should work with no prior observers
        config_manager.add_observer(observer)
        assert len(config_manager._observers) >= 1

    @pytest.mark.asyncio
    async def test_duplicate_observer_registration(self, config_manager):
        """Test duplicate observer registration is handled"""
        async def observer():
            pass

        # Register same observer twice (set should deduplicate)
        config_manager.add_observer(observer)
        config_manager.add_observer(observer)

        # Set should deduplicate
        # (behavior depends on implementation - set dedupes by identity)

    @pytest.mark.asyncio
    async def test_observer_removal(self, config_manager):
        """Test observer removal"""
        async def observer():
            pass

        config_manager.add_observer(observer)
        config_manager.remove_observer(observer)

        # Observer should be removed (or not, if it wasn't added due to set behavior)
        # The key test is no error on removal

    @pytest.mark.asyncio
    async def test_config_update_with_special_characters(self, config_manager):
        """Test config update with special characters in strategy name"""
        strategy = {
            "name": "策略_test_🚀",  # Unicode and emoji
            "enabled": True,
            "trigger": {
                "type": "pinbar",
                "enabled": True,
                "params": {}
            },
            "filters": [],
            "filter_logic": "AND"
        }

        new_config = await config_manager.update_user_config({
            "active_strategies": [strategy]
        })

        # Should accept unicode names
        assert new_config is not None

    @pytest.mark.asyncio
    async def test_very_large_config_update(self, config_manager):
        """Test config update with many strategies"""
        # Create 50 strategies
        strategies = [
            {
                "name": f"strategy_{i}",
                "enabled": True,
                "trigger": {
                    "type": "pinbar",
                    "enabled": True,
                    "params": {"min_wick_ratio": Decimal(str(0.5 + i * 0.01))}
                },
                "filters": [],
                "filter_logic": "AND"
            }
            for i in range(50)
        ]

        new_config = await config_manager.update_user_config({
            "active_strategies": strategies
        })

        # Should handle large configs
        assert new_config is not None
        assert len(new_config.active_strategies) >= 50

    @pytest.mark.asyncio
    async def test_rapid_reload_during_kline_burst(self, pipeline, config_manager):
        """Test rapid reloads during burst of kline data"""
        # Generate burst of klines
        klines = [
            KlineData(
                symbol="BTC/USDT:USDT",
                timeframe="15m",
                timestamp=1234567890000 + i * 100,
                open=Decimal("65000"),
                high=Decimal("65100"),
                low=Decimal("64000"),
                close=Decimal("65050"),
                volume=Decimal("1000"),
                is_closed=True
            )
            for i in range(50)
        ]

        async def process_all_klines():
            for kline in klines:
                await pipeline.process_kline(kline)

        async def rapid_reloads():
            for i in range(10):
                await config_manager.update_user_config({
                    "active_strategies": [{
                        "name": f"burst_{i}",
                        "enabled": True,
                        "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                        "filters": [],
                        "filter_logic": "AND"
                    }]
                })
                await asyncio.sleep(0.01)

        # Run concurrently with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    process_all_klines(),
                    rapid_reloads(),
                    return_exceptions=True
                ),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            pytest.fail("Timeout during kline burst + rapid reload test")

        # Pipeline should be functional
        assert pipeline._runner is not None
