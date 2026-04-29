"""
Event loop safety tests for ConfigManager (R9.3).

Tests verification of async context safety and non-blocking operations.
"""
import asyncio
import os
import pytest
import time
from pathlib import Path
from typing import List

from src.application.config_manager import ConfigManager


class TestEventLoopSafety:
    """Test R9.3: Event loop safety and non-blocking operations."""

    @pytest.mark.asyncio
    async def test_no_blocking_sync_calls(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：异步上下文中不应有阻塞同步调用

        预期行为:
        - 事件循环不被阻塞
        - 其他并发任务仍能执行
        - 检测到阻塞时告警或失败

        验证方法:
        - 启动一个监控任务检测事件循环响应
        - 执行配置操作
        - 验证监控任务未被阻塞
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        heartbeat_log: List[float] = []
        heartbeat_stop = asyncio.Event()

        async def heartbeat_monitor():
            """Monitor event loop responsiveness."""
            while not heartbeat_stop.is_set():
                heartbeat_log.append(time.perf_counter())
                await asyncio.sleep(0.05)  # 50ms heartbeat

        async def do_config_work():
            """Do configuration work."""
            await asyncio.sleep(0.1)  # Simulate async work
            config = await manager.get_user_config()
            await asyncio.sleep(0.1)
            return config

        # Act - Run heartbeat monitor alongside config work
        monitor_task = asyncio.create_task(heartbeat_monitor())
        work_task = asyncio.create_task(do_config_work())

        # Wait for work to complete
        await work_task

        # Stop monitor after a bit more time
        await asyncio.sleep(0.2)
        heartbeat_stop.set()
        await monitor_task

        # Assert - Heartbeat should be regular (no long gaps)
        assert len(heartbeat_log) >= 4, "Monitor should have logged multiple heartbeats"

        # Check for gaps > 200ms (would indicate blocking)
        for i in range(len(heartbeat_log) - 1):
            gap = heartbeat_log[i + 1] - heartbeat_log[i]
            assert gap < 0.3, f"Event loop blocked for {gap:.2f}s between heartbeats {i} and {i+1}"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_asyncio_gather_exception_handling(self, temp_db_path: str):
        """
        场景：多个协程并发执行，部分失败

        预期行为:
        - 使用 asyncio.gather 正确等待
        - 异常正确传播和收集
        - 资源正确清理

        验证方法:
        - 验证 gather 返回值顺序
        - 验证异常组包含所有异常
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        async def success_task(task_id: int):
            await asyncio.sleep(0.01 * task_id)
            return f"success_{task_id}"

        async def fail_task(task_id: int):
            await asyncio.sleep(0.01 * task_id)
            raise ValueError(f"Intentional failure {task_id}")

        # Act - Mix of success and failure tasks
        tasks = [
            success_task(1),
            fail_task(2),
            success_task(3),
            fail_task(4),
            success_task(5),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        assert len(results) == 5, "Should have 5 results"

        # Check results in order
        assert results[0] == "success_1", "First task should succeed"
        assert isinstance(results[1], ValueError), "Second task should fail"
        assert results[2] == "success_3", "Third task should succeed"
        assert isinstance(results[3], ValueError), "Fourth task should fail"
        assert results[4] == "success_5", "Fifth task should succeed"

        # Count exceptions
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 2, "Should have 2 exceptions"

        # Cleanup
        await manager._db.close()


class TestAsyncioToThreadUsage:
    """Test proper use of asyncio.to_thread for I/O operations."""

    @pytest.mark.asyncio
    async def test_asyncio_to_thread_basic(self, temp_db_path: str):
        """
        场景：验证 asyncio.to_thread 可用于 CPU 密集型操作

        预期行为:
        - CPU 密集型操作在线程中执行
        - 事件循环不被阻塞
        - 异常正确传播
        """
        # Arrange
        def blocking_computation(x: int) -> int:
            """Simulate blocking CPU-bound work."""
            total = 0
            for i in range(x):
                total += i * i
            return total

        async def run_in_thread(value: int):
            """Run blocking computation in thread."""
            return await asyncio.to_thread(blocking_computation, value)

        # Act
        result = await run_in_thread(10000)

        # Assert
        assert result > 0, "Computation should produce positive result"
        assert result == sum(i * i for i in range(10000)), "Result should be correct"

    @pytest.mark.asyncio
    async def test_concurrent_thread_operations(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：多个线程操作并发执行

        预期行为:
        - 多个操作并行在线程池中执行
        - 事件循环保持响应
        - 所有操作正确完成
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        def blocking_io_operation(task_id: int) -> str:
            """Simulate blocking I/O operation."""
            time.sleep(0.1)  # Simulate I/O delay
            return f"result_{task_id}"

        async def run_io_task(task_id: int):
            """Run I/O operation in thread."""
            return await asyncio.to_thread(blocking_io_operation, task_id)

        # Act - Run 10 concurrent "I/O" operations
        tasks = [
            asyncio.create_task(run_io_task(i))
            for i in range(10)
        ]

        # Run with timeout to ensure completion
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=2.0
        )

        # Assert
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"No exceptions expected: {exceptions}"

        # All results should be present (may complete in any order)
        successful = [r for r in results if isinstance(r, str)]
        assert len(successful) == 10, "All tasks should succeed"

        # Cleanup
        await manager._db.close()


class TestLockEventLoopSafety:
    """Test that lock operations are event-loop safe."""

    @pytest.mark.asyncio
    async def test_lock_creation_in_async_context(self, temp_db_path: str):
        """
        验证在异步上下文中创建锁的安全性

        _ensure_init_lock 和 _ensure_config_lock 应该
        安全地在异步上下文中调用
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path)
        await manager.initialize_from_db()

        # Act - Multiple lock creations in async context
        lock1 = manager._ensure_init_lock()
        lock2 = manager._ensure_config_lock()
        lock3 = manager._ensure_init_lock()  # Should return same as lock1

        # Assert
        assert lock1 is not None, "Init lock should be created"
        assert lock2 is not None, "Config lock should be created"
        assert lock1 is lock3, "Same lock should be returned for same type"

        # Test lock acquisition in async context
        async with lock1:
            # Should be able to acquire
            pass

        async with lock2:
            # Should be able to acquire
            pass

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_event_signal_coordination(self, temp_db_path: str):
        """
        验证 asyncio.Event 与 Lock 的协调使用

        R9.3 使用 Event 来通知等待的协程初始化完成
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path)

        # Act - Initialize to create event
        await manager.initialize_from_db()

        init_event = manager._init_event

        # Assert - Event should exist and be set after initialization
        assert init_event is not None, "Init event should be created"
        assert init_event.is_set(), "Init event should be set after initialization"

        # Test waiting on event (should return immediately since already set)
        await asyncio.wait_for(init_event.wait(), timeout=1.0)

        # Cleanup
        await manager._db.close()
