"""
Shared fixtures for concurrent tests.
"""
import asyncio
import os
import pytest
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import yaml

from src.application.config_manager import ConfigManager


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    """Create a temporary directory with valid config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)

        # Create minimal core.yaml
        core_config = {
            "core_symbols": ["BTC/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
            "ema": {"period": 60},
            "mtf_mapping": {"15m": "1h"},
            "warmup": {"history_bars": 100},
        }

        with open(config_dir / "core.yaml", "w") as f:
            yaml.dump(core_config, f)

        # Create minimal user.yaml
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key_12345",
                "api_secret": "test_api_secret_67890",
                "testnet": True,
            },
            "user_symbols": [],
            "timeframes": ["1h"],
            "strategy": {
                "trend_filter_enabled": True,
                "mtf_validation_enabled": True,
            },
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
            "notification": {
                "channels": [{
                    "type": "feishu",
                    "webhook_url": "https://test.feishu.cn/webhook",
                }],
            },
        }

        with open(config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)

        yield config_dir


@pytest.fixture
async def config_manager(temp_db_path: str) -> AsyncGenerator[ConfigManager, None]:
    """Create an initialized ConfigManager instance."""
    manager = ConfigManager(db_path=temp_db_path)
    await manager.initialize_from_db()
    yield manager
    await manager._db.close()


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Use default event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def cleanup_resources():
    """Cleanup resources after each test."""
    yield
    # Force garbage collection and yield to event loop
    await asyncio.sleep(0)
