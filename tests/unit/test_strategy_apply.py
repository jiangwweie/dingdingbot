"""
Tests for S2-1: Strategy Apply endpoint (hot-reload integration).

Tests:
1. StrategyApplyRequest/Response model validation
2. Apply endpoint loads and validates strategy template
3. ConfigManager.update_user_config() integration
4. Observer notification on config update
5. Warmup K-line replay accuracy
"""
import pytest
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.models import (
    StrategyDefinition, TriggerConfig, FilterConfig,
    KlineData, Direction,
)
from src.application.config_manager import ConfigManager, UserConfig
from src.domain.risk_calculator import RiskConfig


# ============================================================
# Test Models
# ============================================================
def test_strategy_apply_request_model():
    """Test StrategyApplyRequest validation."""
    from src.interfaces.api import StrategyApplyRequest, StrategyApplyResponse

    # Default values
    request = StrategyApplyRequest()
    assert request.enabled is True
    assert request.apply_to is None

    # Custom values
    request = StrategyApplyRequest(
        enabled=False,
        apply_to=["BTC/USDT:USDT:15m", "ETH/USDT:USDT:15m"]
    )
    assert request.enabled is False
    assert len(request.apply_to) == 2


# ============================================================
# Test ConfigManager Hot-Reload
# ============================================================
@pytest.mark.asyncio
async def test_config_manager_update_user_config():
    """Test ConfigManager.update_user_config() atomic update and observer notification."""
    from src.application.config_manager import ConfigManager, UserConfig, CoreConfig

    # Create mock config manager
    config_manager = ConfigManager()

    # Mock loaded configs
    config_manager._core_config = CoreConfig(
        core_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        pinbar_defaults={
            "min_wick_ratio": Decimal("0.6"),
            "max_body_ratio": Decimal("0.3"),
            "body_position_tolerance": Decimal("0.1"),
        },
        ema={"period": 60},
        mtf_mapping={},
        warmup={"history_bars": 100},
        signal_pipeline={"cooldown_seconds": 14400},
    )

    # Mock initial user config
    config_manager._user_config = UserConfig(
        exchange={
            "name": "binance",
            "api_key": "test_key",
            "api_secret": "test_secret",
            "testnet": True,
        },
        user_symbols=[],
        timeframes=["15m", "1h"],
        active_strategies=[],
        risk={"max_loss_percent": "0.01", "max_leverage": 125},
        asset_polling={"interval_seconds": 60},
        notification={"channels": [{"type": "feishu", "webhook_url": "https://example.com/webhook"}]},
    )

    # Track observer calls
    observer_called = []

    async def mock_observer():
        observer_called.append(True)

    config_manager.add_observer(mock_observer)

    # Call update_user_config
    new_strategy = {
        "name": "test_pinbar",
        "trigger": {"type": "pinbar", "enabled": True, "params": {}},
        "filters": [],
    }

    updated_config = await config_manager.update_user_config({
        "active_strategies": [new_strategy]
    })

    # Verify config updated
    assert len(updated_config.active_strategies) == 1
    assert updated_config.active_strategies[0].name == "test_pinbar"

    # Verify observer called
    assert len(observer_called) == 1


# ============================================================
# Test SignalPipeline Warmup
# ============================================================
def test_signal_pipeline_warmup_kline_replay():
    """Test SignalPipeline._build_and_warmup_runner() replays K-lines correctly."""
    from src.application.signal_pipeline import SignalPipeline
    from src.application.config_manager import ConfigManager, CoreConfig, UserConfig

    # Create mock config manager
    config_manager = ConfigManager()
    config_manager._core_config = CoreConfig(
        core_symbols=["BTC/USDT:USDT"],
        pinbar_defaults={
            "min_wick_ratio": Decimal("0.6"),
            "max_body_ratio": Decimal("0.3"),
            "body_position_tolerance": Decimal("0.1"),
        },
        ema={"period": 60},
        mtf_mapping={},
        warmup={"history_bars": 100},
        signal_pipeline={"cooldown_seconds": 14400},
    )
    config_manager._user_config = UserConfig(
        exchange={
            "name": "binance",
            "api_key": "test_key",
            "api_secret": "test_secret",
            "testnet": True,
        },
        user_symbols=[],
        timeframes=["15m"],
        active_strategies=[],
        risk={"max_loss_percent": "0.01", "max_leverage": 125},
        asset_polling={"interval_seconds": 60},
        notification={"channels": [{"type": "feishu", "webhook_url": "https://example.com/webhook"}]},
    )

    # Create pipeline (this will fail without event loop, so we test the warmup method directly)
    pipeline = SignalPipeline.__new__(SignalPipeline)
    pipeline._config_manager = config_manager
    pipeline._risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=125)
    pipeline._kline_history = {}

    # Create mock K-line history
    kline1 = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000000000,
        open=Decimal("50000"),
        high=Decimal("50100"),
        low=Decimal("49900"),
        close=Decimal("50050"),
        volume=Decimal("1000"),
        is_closed=True,
    )
    kline2 = KlineData(
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        timestamp=1000000090000,
        open=Decimal("50050"),
        high=Decimal("50200"),
        low=Decimal("50000"),
        close=Decimal("50150"),
        volume=Decimal("1200"),
        is_closed=True,
    )

    pipeline._kline_history["BTC/USDT:USDT:15m"] = [kline1, kline2]

    # Mock create_dynamic_runner
    with patch('src.application.signal_pipeline.create_dynamic_runner') as mock_create:
        mock_runner = MagicMock()
        mock_create.return_value = mock_runner

        # Call warmup
        runner = pipeline._build_and_warmup_runner()

        # Verify update_state called for each K-line
        assert mock_runner.update_state.call_count == 2


# ============================================================
# Test SignalPipeline Hot-Reload Lock
# ============================================================
@pytest.mark.asyncio
async def test_signal_pipeline_on_config_updated_uses_lock():
    """Test SignalPipeline.on_config_updated() uses lock correctly."""
    from src.application.signal_pipeline import SignalPipeline
    from src.application.config_manager import ConfigManager, CoreConfig, UserConfig

    # Create mock config manager
    config_manager = ConfigManager()
    config_manager._core_config = CoreConfig(
        core_symbols=["BTC/USDT:USDT"],
        pinbar_defaults={
            "min_wick_ratio": Decimal("0.6"),
            "max_body_ratio": Decimal("0.3"),
            "body_position_tolerance": Decimal("0.1"),
        },
        ema={"period": 60},
        mtf_mapping={},
        warmup={"history_bars": 100},
        signal_pipeline={"cooldown_seconds": 14400},
    )
    config_manager._user_config = UserConfig(
        exchange={
            "name": "binance",
            "api_key": "test_key",
            "api_secret": "test_secret",
            "testnet": True,
        },
        user_symbols=[],
        timeframes=["15m"],
        active_strategies=[],
        risk={"max_loss_percent": "0.01", "max_leverage": 125},
        asset_polling={"interval_seconds": 60},
        notification={"channels": [{"type": "feishu", "webhook_url": "https://example.com/webhook"}]},
    )

    # Create pipeline with proper initialization
    pipeline = SignalPipeline.__new__(SignalPipeline)
    pipeline._config_manager = config_manager
    pipeline._risk_config = RiskConfig(max_loss_percent=Decimal("0.01"), max_leverage=125)
    pipeline._kline_history = {}
    pipeline._runner_lock = None
    pipeline._attempts_queue = None  # Initialize to None for lazy init
    pipeline._flush_task = None
    pipeline._signal_cooldown_cache = {}
    pipeline._account_snapshot = None

    # Mock _build_and_warmup_runner
    build_called = []

    def mock_build():
        build_called.append(True)
        return MagicMock()

    pipeline._build_and_warmup_runner = mock_build

    # Mock _ensure_async_primitives to handle the lock creation
    def mock_ensure():
        if pipeline._runner_lock is None:
            import asyncio
            try:
                pipeline._runner_lock = asyncio.Lock()
            except RuntimeError:
                pass
        if pipeline._attempts_queue is None:
            import asyncio
            try:
                pipeline._attempts_queue = asyncio.Queue()
            except RuntimeError:
                pass

    pipeline._ensure_async_primitives = mock_ensure

    # Call on_config_updated
    await pipeline.on_config_updated()

    # Verify runner rebuilt
    assert len(build_called) == 1
    # Verify cooldown cache cleared
    assert len(pipeline._signal_cooldown_cache) == 0


# ============================================================
# Test API Endpoint Integration
# ============================================================
@pytest.mark.asyncio
async def test_apply_strategy_endpoint_integration():
    """Test apply strategy endpoint integration with ConfigManager."""
    from src.interfaces.api import StrategyApplyRequest, StrategyApplyResponse
    from fastapi import HTTPException

    # Mock repository and config_manager
    mock_repo = AsyncMock()
    mock_config_manager = AsyncMock()

    # Mock strategy record from database - use logic_tree format
    strategy_json = json.dumps({
        "name": "my_pinbar",
        "logic_tree": {
            "type": "trigger",
            "id": "trigger_0",
            "config": {"type": "pinbar", "enabled": True, "params": {"min_wick_ratio": 0.6}}
        },
    })

    mock_repo.get_custom_strategy_by_id = AsyncMock(return_value={
        "id": 1,
        "name": "my_pinbar",
        "description": "Test strategy",
        "strategy_json": strategy_json,
    })

    # Mock config manager
    mock_config_manager.user_config = MagicMock(
        active_strategies=[]
    )

    updated_config = MagicMock()
    mock_config_manager.update_user_config = AsyncMock(return_value=updated_config)

    # Import and test apply_strategy function directly
    import sys
    sys.modules['src.interfaces.api']._repository = mock_repo
    sys.modules['src.interfaces.api']._config_manager = mock_config_manager

    from src.interfaces.api import apply_strategy

    # Call endpoint
    request = StrategyApplyRequest(enabled=True, apply_to=None)
    response = await apply_strategy(strategy_id=1, request=request)

    # Verify response
    assert response.status == "success"
    assert response.strategy_id == 1
    assert response.strategy_name == "my_pinbar"

    # Verify config_manager.update_user_config called
    assert mock_config_manager.update_user_config.called
