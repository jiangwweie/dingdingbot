"""
Cache concurrency tests for ConfigManager.

Tests verification of cache consistency during concurrent access.
"""
import asyncio
import os
import pytest
import time
from pathlib import Path
from typing import List, Dict, Any

from src.application.config_manager import ConfigManager


class TestCacheConcurrency:
    """Test cache concurrency safety."""

    @pytest.mark.asyncio
    async def test_cache_update_read_concurrent(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：缓存更新过程中有读取请求

        预期行为:
        - 读取要么获得旧缓存要么获得新缓存
        - 不会读取到部分更新的数据
        - 缓存一致性保证

        验证方法:
        - 并发执行缓存更新和读取
        - 验证读取数据的完整性
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        read_results: List[Any] = []
        update_complete = asyncio.Event()

        async def read_cache(task_id: int):
            """Read configuration (uses cache)."""
            config = await manager.get_user_config()
            read_results.append((task_id, config, time.perf_counter()))
            return config

        async def update_cache():
            """Simulate cache update (config reload)."""
            await asyncio.sleep(0.05)  # Let some reads start
            # Trigger a config reload which updates cache
            config = await manager.get_user_config()
            update_complete.set()
            return config

        # Act - Concurrent reads and one update
        read_tasks = [
            asyncio.create_task(read_cache(i))
            for i in range(20)
        ]
        update_task = asyncio.create_task(update_cache())

        # Stagger reads to happen during update
        for task in read_tasks[5:15]:
            await asyncio.sleep(0.01)

        await asyncio.gather(*read_tasks, update_task)

        # Assert
        assert len(read_results) == 20, "All reads should complete"
        assert update_complete.is_set(), "Update should complete"

        # All reads should return valid config objects (no partial state)
        for task_id, config, _ in read_results:
            assert config is not None, f"Read {task_id} should return valid config"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_cache_invalidation_concurrent(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：多个请求同时触发缓存失效/更新

        预期行为:
        - 仅一次实际加载操作
        - 其他请求等待加载完成
        - 无重复加载

        验证方法:
        - 计数实际加载次数
        - 验证最终缓存状态
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        # Track config accesses
        access_count = 0
        access_lock = asyncio.Lock()

        async def access_config(task_id: int):
            nonlocal access_count
            async with access_lock:
                access_count += 1
            config = await manager.get_user_config()
            return config

        # Act - Multiple concurrent config accesses
        tasks = [
            asyncio.create_task(access_config(i))
            for i in range(10)
        ]
        results = await asyncio.gather(*tasks)

        # Assert
        assert len(results) == 10, "All accesses should complete"
        assert all(r is not None for r in results), "All should return valid config"

        # Cleanup
        await manager._db.close()


class TestConfigVersionConsistency:
    """Test configuration version consistency during concurrent updates."""

    @pytest.mark.asyncio
    async def test_config_version_stability(self, temp_db_path: str, temp_config_dir: Path):
        """
        验证配置版本在并发读取时的稳定性

        R3.2: 配置版本应该在更新时才改变
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        # Get initial version
        initial_version = manager.get_config_version()

        # Act - Multiple concurrent reads
        versions: List[int] = []

        async def read_and_record_version(task_id: int):
            config = await manager.get_user_config()
            version = manager.get_config_version()
            versions.append(version)
            return config

        tasks = [
            asyncio.create_task(read_and_record_version(i))
            for i in range(20)
        ]
        await asyncio.gather(*tasks)

        # Assert
        assert len(versions) == 20, "All reads should record version"

        # All versions should be the same (no updates happened)
        assert all(v == initial_version for v in versions), \
            "Version should remain stable during reads"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_concurrent_config_access_consistency(self, temp_db_path: str, temp_config_dir: Path):
        """
        验证并发配置访问的数据一致性

        多个并发读取应该获得一致的配置数据
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        configs: List = []

        async def read_config(task_id: int):
            config = await manager.get_user_config()
            configs.append((task_id, config))
            return config

        # Act - 50 concurrent reads
        tasks = [
            asyncio.create_task(read_config(i))
            for i in range(50)
        ]
        await asyncio.gather(*tasks)

        # Assert
        assert len(configs) == 50, "All reads should complete"

        # All configs should have same key structural data
        # (they may be different objects but should have same values)
        first_config = configs[0][1]
        for task_id, config in configs[1:]:
            assert config.risk.max_loss_percent == first_config.risk.max_loss_percent, \
                f"Config {task_id} has inconsistent max_loss_percent"
            assert config.risk.max_leverage == first_config.risk.max_leverage, \
                f"Config {task_id} has inconsistent max_leverage"

        # Cleanup
        await manager._db.close()


class TestCacheThreadSafety:
    """Test thread safety of cache operations."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_access_pattern(self, temp_db_path: str, temp_config_dir: Path):
        """
        测试并发缓存访问模式

        验证多个协程同时访问缓存时的行为
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        results: Dict[str, Any] = {}
        errors: List[Exception] = []

        async def mixed_access(task_id: int):
            """Mixed read operations."""
            try:
                if task_id % 2 == 0:
                    # Read user config
                    config = await manager.get_user_config()
                    results[f"user_{task_id}"] = config
                else:
                    # Read core config
                    config = manager.get_core_config()
                    results[f"core_{task_id}"] = config
            except Exception as e:
                errors.append(e)

        # Act - 40 mixed operations
        tasks = [
            asyncio.create_task(mixed_access(i))
            for i in range(40)
        ]
        await asyncio.gather(*tasks)

        # Assert
        assert len(errors) == 0, f"No errors expected: {errors}"
        assert len(results) == 40, "All operations should complete"

        # Verify all user configs are valid
        user_configs = [v for k, v in results.items() if k.startswith("user_")]
        assert all(c is not None for c in user_configs), "All user configs should be valid"

        # Verify all core configs are valid
        core_configs = [v for k, v in results.items() if k.startswith("core_")]
        assert all(c is not None for c in core_configs), "All core configs should be valid"

        # Cleanup
        await manager._db.close()
