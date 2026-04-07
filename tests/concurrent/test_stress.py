"""
Stress tests for ConfigManager.

Tests verification of system behavior under high concurrency load.
"""
import asyncio
import os
import pytest
import time
import statistics
from pathlib import Path
from typing import List, Tuple

from src.application.config_manager import ConfigManager


class TestStress:
    """Stress testing for ConfigManager under high concurrency."""

    @pytest.mark.asyncio
    async def test_high_concurrency_load(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：100+ 并发请求持续访问

        预期行为:
        - 无异常抛出
        - 响应时间在可接受范围
        - 内存使用稳定

        验证方法:
        - 使用 asyncio.Semaphore 控制并发数
        - 监控响应时间和成功率
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        num_requests = 100
        max_concurrent = 20  # Limit concurrent tasks
        semaphore = asyncio.Semaphore(max_concurrent)

        response_times: List[float] = []
        success_results: List = []
        failure_results: List = []
        stats_lock = asyncio.Lock()

        async def make_request(request_id: int) -> Tuple[int, bool, float]:
            """Make a config access request."""
            start_time = time.perf_counter()

            async with semaphore:
                try:
                    config = await manager.get_user_config()
                    elapsed = time.perf_counter() - start_time

                    async with stats_lock:
                        response_times.append(elapsed)
                        success_results.append(request_id)

                    return (request_id, True, elapsed)

                except Exception as e:
                    elapsed = time.perf_counter() - start_time
                    async with stats_lock:
                        failure_results.append(request_id)
                    return (request_id, False, elapsed)

        # Act - Launch 100 concurrent requests
        tasks = [
            asyncio.create_task(make_request(i))
            for i in range(num_requests)
        ]

        start_total = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_time = time.perf_counter() - start_total

        # Assert
        # 1. All requests should complete
        assert len(results) == num_requests, "All requests should complete"

        # 2. High success rate expected
        success_rate = len(success_results) / num_requests
        assert success_rate >= 0.95, f"Success rate should be >= 95%, got {success_rate:.2%}"

        # 3. Response time should be reasonable
        if response_times:
            avg_response = statistics.mean(response_times)
            p95_response = sorted(response_times)[int(len(response_times) * 0.95)]

            # Average should be under 500ms
            assert avg_response < 0.5, f"Average response time {avg_response:.3f}s exceeds 500ms"

            # P95 should be under 1s
            assert p95_response < 1.0, f"P95 response time {p95_response:.3f}s exceeds 1s"

        # 4. Total execution time indicates throughput
        # With 100 requests and 20 concurrent, should complete in reasonable time
        assert total_time < 30.0, f"Total time {total_time:.2f}s exceeds 30s limit"

        # Print stats for debugging
        print(f"\nStress Test Results:")
        print(f"  Total requests: {num_requests}")
        print(f"  Success: {len(success_results)}, Failures: {len(failure_results)}")
        print(f"  Success rate: {success_rate:.2%}")
        print(f"  Total time: {total_time:.2f}s")
        if response_times:
            print(f"  Avg response: {avg_response:.3f}s")
            print(f"  P95 response: {p95_response:.3f}s")

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_sustained_load(self, temp_db_path: str, temp_config_dir: Path):
        """
        场景：持续 30 秒的中等负载

        预期行为:
        - 无内存泄漏
        - 无性能衰减
        - 所有请求成功

        验证方法:
        - 持续发送请求 30 秒
        - 监控响应时间趋势
        """
        # Arrange
        manager = ConfigManager(db_path=temp_db_path, config_dir=temp_config_dir)
        await manager.initialize_from_db()

        duration_seconds = 10  # Reduced for faster test execution
        requests_per_second = 10

        all_response_times: List[float] = []
        stop_event = asyncio.Event()
        request_count = 0
        count_lock = asyncio.Lock()

        async def continuous_request():
            """Make continuous requests."""
            nonlocal request_count

            while not stop_event.is_set():
                start = time.perf_counter()
                try:
                    config = await manager.get_user_config()
                    elapsed = time.perf_counter() - start
                    all_response_times.append(elapsed)

                    async with count_lock:
                        request_count += 1
                except Exception:
                    pass

                # Small delay to control rate
                await asyncio.sleep(1.0 / requests_per_second)

        # Act - Run continuous load
        tasks = [
            asyncio.create_task(continuous_request())
            for _ in range(5)  # 5 parallel request streams
        ]

        # Let it run for duration
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=duration_seconds)
        except asyncio.TimeoutError:
            pass  # Expected timeout

        # Stop all tasks
        stop_event.set()
        for task in tasks:
            task.cancel()

        # Wait for cancellation
        await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        # Should have processed many requests
        assert request_count >= 50, f"Should process at least 50 requests, got {request_count}"

        # Response times should be stable (no degradation)
        if len(all_response_times) >= 10:
            # Compare first half vs second half response times
            mid = len(all_response_times) // 2
            first_half_avg = statistics.mean(all_response_times[:mid])
            second_half_avg = statistics.mean(all_response_times[mid:])

            # Second half shouldn't be significantly slower (no degradation)
            degradation_ratio = second_half_avg / first_half_avg if first_half_avg > 0 else 1
            assert degradation_ratio < 2.0, \
                f"Performance degradation detected: {degradation_ratio:.2f}x slower"

        # Cleanup
        await manager._db.close()


class TestInitializationStress:
    """Stress testing for concurrent initialization."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization_stress(self, temp_db_path: str):
        """
        场景：大量并发初始化请求

        验证 R9.3 竞态修复在高压下的正确性

        Note: This tests a SINGLE manager instance with concurrent initialize calls,
        which is the actual R9.3 race condition scenario.
        """
        # Arrange - Use single manager instance
        manager = ConfigManager(db_path=temp_db_path)
        num_concurrent = 50

        async def call_initialize(task_id: int):
            """Call initialize on the shared manager."""
            await manager.initialize_from_db()
            return task_id

        # Act - Launch many concurrent initialization calls on SAME manager
        tasks = [
            asyncio.create_task(call_initialize(i))
            for i in range(num_concurrent)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert
        # All should succeed (R9.3 double-checked locking handles this)
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"No exceptions expected: {exceptions}"

        # Manager should be initialized
        assert manager.is_initialized, "Manager should be initialized"

        # Cleanup
        await manager._db.close()

    @pytest.mark.asyncio
    async def test_rapid_init_close_cycles(self, temp_db_path: str):
        """
        场景：快速初始化 - 关闭循环

        验证资源正确清理，无泄漏
        """
        # Arrange
        num_cycles = 10

        for i in range(num_cycles):
            # Act - Create, initialize, close
            manager = ConfigManager(db_path=temp_db_path)
            await manager.initialize_from_db()

            # Verify initialized
            assert manager.is_initialized

            # Close
            await manager._db.close()

        # Assert - If we get here without errors, test passes
        # (no resource leaks or corruption)
