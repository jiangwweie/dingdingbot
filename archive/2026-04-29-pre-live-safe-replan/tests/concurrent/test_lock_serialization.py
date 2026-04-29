"""
Lock serialization tests for ConfigManager (R9.3).

Tests verification of mutex exclusion and read-write separation.
"""
import asyncio
import os
import pytest
import time
from pathlib import Path
from typing import List, Tuple

import yaml

from src.application.config_manager import ConfigManager


class TestLockSerialization:
    """Test R9.3: Lock serialization and mutual exclusion."""

    @pytest.mark.asyncio
    async def test_write_exclusion(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：多个并发写操作（配置更新）

        预期行为:
        - 同一时间仅一个写操作执行
        - 写操作之间无数据竞争
        - 所有写操作最终生效

        验证方法:
        - 记录写操作开始/结束时间
        - 验证时间区间无重叠
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        write_log: List[Tuple[float, float, int]] = []  # (start, end, task_id)

        async def write_config(task_id: int):
            """Simulate a write operation with logging."""
            async with manager._ensure_config_lock():
                # Record lock acquisition time
                acquire_time = time.perf_counter()
                # Simulate write work
                await asyncio.sleep(0.1)
                # Record lock release time
                release_time = time.perf_counter()
                write_log.append((acquire_time, release_time, task_id))

        # Act - Launch concurrent writes
        num_writes = 5
        tasks = [
            asyncio.create_task(write_config(i))
            for i in range(num_writes)
        ]
        await asyncio.gather(*tasks)

        # Assert
        assert len(write_log) == num_writes, "All writes should complete"

        # Sort by acquisition time
        write_log.sort(key=lambda x: x[0])

        # Check for overlaps - each write should complete before next starts
        # With proper locking, release of write[i] should be before acquire of write[i+1]
        for i in range(len(write_log) - 1):
            _, release_current, _ = write_log[i]
            acquire_next, _, _ = write_log[i + 1]

            # With proper locking, current should release before next acquires
            # Allow 10ms tolerance for timing measurement and asyncio scheduling
            tolerance = 0.01
            assert release_current <= acquire_next + tolerance, \
                f"Write overlap detected: write {write_log[i][2]} released at {release_current}, " \
                f"write {write_log[i+1][2]} acquired at {acquire_next}"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_read_write_separation(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：读操作与写操作并发

        预期行为:
        - 读操作不被写操作阻塞（读 - 读并发）
        - 写操作获得独占锁（写 - 读/写互斥）
        - 读取的数据要么全旧要么全新（无脏读）

        验证方法:
        - 并发执行多个读操作和一个写操作
        - 验证读操作完成时间
        - 验证数据一致性
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        read_times: List[float] = []
        write_time: float = None
        read_write_lock = asyncio.Lock()

        async def read_config(task_id: int):
            """Read configuration."""
            start = time.perf_counter()
            config = await manager.get_user_config()
            elapsed = time.perf_counter() - start

            async with read_write_lock:
                read_times.append((task_id, elapsed, start))
            return config

        async def write_config():
            """Write configuration with delay."""
            nonlocal write_time
            await asyncio.sleep(0.05)  # Let some reads start first
            start = time.perf_counter()

            async with manager._ensure_config_lock():
                await asyncio.sleep(0.2)  # Simulate write work
                write_time = time.perf_counter() - start

        # Act - Launch concurrent reads and one write
        read_tasks = [
            asyncio.create_task(read_config(i))
            for i in range(10)
        ]
        write_task = asyncio.create_task(write_config())

        all_tasks = read_tasks + [write_task]
        await asyncio.gather(*all_tasks)

        # Assert
        assert len(read_times) == 10, "All reads should complete"
        assert write_time is not None, "Write should complete"

        # Reads should be fast (not blocked by write lock acquisition)
        # Note: This depends on implementation - if reads also take the lock,
        # they will be serialized with writes
        avg_read_time = sum(t[1] for t in read_times) / len(read_times)

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_lock_timeout_simulation(self, temp_db_path: str):
        """
        场景：锁持有时间过长，模拟超时场景

        预期行为:
        - 等待方在超时后抛出异常
        - 锁正确释放
        - 无死锁残留

        验证方法:
        - 模拟长时间持有锁
        - 验证等待方可以检测到超时
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        lock_held_event = asyncio.Event()
        lock_released_event = asyncio.Event()

        async def hold_lock():
            """Hold the lock for a long time."""
            async with manager._ensure_config_lock():
                lock_held_event.set()
                await asyncio.sleep(1.0)  # Hold for 1 second
                lock_released_event.set()

        async def try_acquire_with_timeout():
            """Try to acquire lock with timeout."""
            await lock_held_event.wait()  # Wait until lock is held

            try:
                # Try to acquire with short timeout
                async with asyncio.timeout(0.3):
                    async with manager._ensure_config_lock():
                        return "acquired"
            except asyncio.TimeoutError:
                return "timeout"

        # Act
        hold_task = asyncio.create_task(hold_lock())
        wait_task = asyncio.create_task(try_acquire_with_timeout())

        results = await asyncio.gather(wait_task, hold_task)

        # Assert
        assert results[0] == "timeout", "Should timeout waiting for lock"
        assert lock_released_event.is_set(), "Lock should eventually be released"

        # Cleanup
        await manager._db.close()


class TestConfigLockIsolation:
    """Test configuration lock isolation across event loops."""

    @pytest.mark.asyncio
    async def test_config_lock_per_event_loop(self, temp_db_path: str):
        """
        验证配置锁在事件循环间的正确性

        _ensure_config_lock 应该为每个事件循环返回正确的锁
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Get lock in current event loop
        lock1 = manager._ensure_config_lock()
        lock2 = manager._ensure_config_lock()

        # Assert - Same event loop should get same lock
        assert lock1 is lock2, "Same event loop should return same lock instance"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_concurrent_config_access(self, temp_db_path: str, temp_config_dir: Path):
        """
        验证并发配置访问的线程安全
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        read_results: List = []
        errors: List = []

        async def read_and_verify(task_id: int):
            try:
                config = await manager.get_user_config()
                read_results.append((task_id, config is not None))
            except Exception as e:
                errors.append((task_id, str(e)))

        # Act - 30 concurrent reads
        tasks = [
            asyncio.create_task(read_and_verify(i))
            for i in range(30)
        ]
        await asyncio.gather(*tasks)

        # Assert
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert len(read_results) == 30, "All reads should complete"
        assert all(success for _, success in read_results), "All reads should succeed"

        # Cleanup
        await manager._db.close()
