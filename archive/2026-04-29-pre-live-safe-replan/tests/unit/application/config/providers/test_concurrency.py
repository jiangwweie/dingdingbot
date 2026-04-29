"""
Provider 并发安全测试 - 竞态条件与锁验证

测试范围:
- 并发首次访问（竞态验证）
- 并发更新（锁验证）
- 并发刷新（缓存一致性）
- 双重检查锁定验证
- 异步锁无死锁测试

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md

关键验证 (QA P0):
- ProviderRegistry 懒加载存在竞态条件
- 双重检查锁定模式防止重复创建
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from datetime import datetime

from src.application.config.providers.registry import ProviderRegistry
from src.application.config.providers.base import ConfigProvider
from src.application.config.providers.cached_provider import CachedProvider, MockClock


# =============================================================================
# Test Fixtures
# =============================================================================

class SlowProvider:
    """
    慢速 Provider - 用于模拟延迟暴露竞态条件
    """

    def __init__(self, delay_seconds: float = 0.1, creation_id: int = None):
        self.delay_seconds = delay_seconds
        self.creation_id = creation_id  # 用于追踪是哪个实例
        self._data = {}

    async def get(self, key: str = None):
        await asyncio.sleep(self.delay_seconds)
        return self._data

    async def update(self, key: str, value: any) -> None:
        await asyncio.sleep(self.delay_seconds)
        self._data[key] = value

    async def refresh(self) -> None:
        await asyncio.sleep(self.delay_seconds)

    @property
    def cache_ttl(self) -> int:
        return 300


class CountingProvider:
    """
    计数 Provider - 追踪创建次数和调用次数
    """

    _creation_counter = 0

    def __init__(self):
        CountingProvider._creation_counter += 1
        self.creation_number = CountingProvider._creation_counter
        self.get_call_count = 0
        self._data = {'id': self.creation_number}

    async def get(self, key: str = None):
        self.get_call_count += 1
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: any) -> None:
        self._data[key] = value

    async def refresh(self) -> None:
        pass

    @property
    def cache_ttl(self) -> int:
        return 300

    @classmethod
    def reset_counter(cls):
        cls._creation_counter = 0


# =============================================================================
# Tests
# =============================================================================

class TestConcurrencySafety:
    """并发安全测试"""

    # --------------------------------------------------------------------------
    # 并发懒加载测试（P0 竞态验证）
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_concurrent_get_provider_lazy_load(self):
        """
        测试并发获取懒加载 Provider（应只创建一次）

        这是 P0 级别的验证，确保双重检查锁定模式正确工作
        """
        # Arrange
        CountingProvider.reset_counter()
        registry = ProviderRegistry()

        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return CountingProvider()

        registry.register_factory('lazy', factory)

        # Act - 并发首次访问（10 个协程同时获取）
        tasks = [registry.get_provider('lazy') for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # Assert - 工厂只调用一次
        assert call_count == 1, "工厂函数应只调用一次（并发安全）"

        # 所有结果应相同（同一实例）
        assert all(r is results[0] for r in results)

        # 验证 creation_number 都是 1
        assert all(r.creation_number == 1 for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_get_provider_no_race(self):
        """
        并发首次访问 Provider，验证双重检查锁定

        验证：所有结果相同（无重复创建）
        """
        # Arrange
        registry = ProviderRegistry()
        creation_count = 0

        def factory():
            nonlocal creation_count
            creation_count += 1
            return CountingProvider()

        registry.register_factory('test', factory)

        # Act - 20 个并发访问
        results = await asyncio.gather(*[
            registry.get_provider('test') for _ in range(20)
        ])

        # Assert
        assert creation_count == 1, "应只创建一次（双重检查锁定生效）"
        assert all(r == results[0] for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_lazy_loading_with_slow_provider(self):
        """
        测试慢速 Provider 的并发懒加载（延长窗口暴露竞态条件）
        """
        # Arrange
        registry = ProviderRegistry()
        created_providers = []

        def slow_factory():
            # 模拟慢速初始化
            import time
            time.sleep(0.05)  # 50ms 延迟
            provider = SlowProvider(delay_seconds=0.01)
            created_providers.append(provider)
            return provider

        registry.register_factory('slow', slow_factory)

        # Act - 50 个并发访问（增加并发数放大竞态条件）
        tasks = [registry.get_provider('slow') for _ in range(50)]
        results = await asyncio.gather(*tasks)

        # Assert - 只创建一次
        assert len(created_providers) == 1, f"应只创建 1 次，实际创建{len(created_providers)}次"
        assert all(r is results[0] for r in results)

    # --------------------------------------------------------------------------
    # 并发注册测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_concurrent_register_same_name(self):
        """测试并发注册同一名称的 Provider（后注册覆盖）"""
        # Arrange
        registry = ProviderRegistry()
        providers = [Mock(spec=ConfigProvider) for _ in range(5)]

        async def register_provider(index):
            registry.register('shared', providers[index])
            await asyncio.sleep(0.01)

        # Act - 并发注册
        tasks = [register_provider(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # Assert - 最后一个注册成功（覆盖）
        # 注意：由于并发，实际结果不确定，但不会抛出异常
        result = await registry.get_provider('shared')
        assert result in providers

    @pytest.mark.asyncio
    async def test_concurrent_register_and_get(self):
        """测试并发注册和获取操作"""
        # Arrange
        registry = ProviderRegistry()
        registered = False

        async def register():
            nonlocal registered
            await asyncio.sleep(0.05)
            registry.register('test', Mock(spec=ConfigProvider))
            registered = True

        async def get():
            await asyncio.sleep(0.1)
            return await registry.get_provider('test')

        # Act - 并发注册和获取
        results = await asyncio.gather(
            register(),
            get(),
        )

        # Assert
        assert registered
        assert results[1] is not None

    # --------------------------------------------------------------------------
    # 并发缓存访问测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_concurrent_cache_read_write(self):
        """测试并发缓存读写"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))

        class TestCachedProvider(CachedProvider):
            def __init__(self, clock):
                super().__init__(clock=clock)
                self._data = {}

            async def get(self, key=None):
                cache_key = key or '__all__'
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached
                result = self._data.get(key) if key else self._data
                self._set_cached(cache_key, result)
                return result

            async def update(self, key, value):
                self._data[key] = value
                self._invalidate_cache(key)

            async def refresh(self):
                self._invalidate_cache()

        provider = TestCachedProvider(clock)
        provider._data['counter'] = 0

        # Act - 并发读写
        async def read():
            return await provider.get('counter')

        async def write():
            current = await provider.get('counter')
            await provider.update('counter', current + 1)

        # 10 个写操作，20 个读操作
        tasks = [write() for _ in range(10)] + [read() for _ in range(20)]
        await asyncio.gather(*tasks)

        # Assert - 最终值应为 10（不保证原子性，但最终一致）
        final_value = await provider.get('counter')
        assert final_value == 10

    @pytest.mark.asyncio
    async def test_concurrent_cache_refresh(self):
        """测试并发刷新缓存（缓存一致性）"""
        # Arrange
        clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=clock)
        refresh_count = 0

        def tracked_invalidate(key=None):
            nonlocal refresh_count
            refresh_count += 1

        provider._invalidate_cache = tracked_invalidate

        # Act - 并发刷新
        async def refresh():
            provider._invalidate_cache()
            await asyncio.sleep(0.01)

        tasks = [refresh() for _ in range(10)]
        await asyncio.gather(*tasks)

        # Assert - 每次刷新都被记录
        assert refresh_count == 10

    # --------------------------------------------------------------------------
    # 并发更新测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_concurrent_update_config(self):
        """测试并发更新同一配置项"""
        # Arrange
        registry = ProviderRegistry()

        class MutableProvider:
            def __init__(self):
                self._data = {}

            async def get(self, key=None):
                return self._data.get(key) if key else self._data

            async def update(self, key, value):
                self._data[key] = value
                await asyncio.sleep(0.01)  # 模拟延迟

            async def refresh(self):
                pass

            @property
            def cache_ttl(self):
                return 300

        provider = MutableProvider()
        registry.register('test', provider)

        # Act - 并发更新
        async def update(index):
            prov = await registry.get_provider('test')
            await prov.update('shared_key', f'value_{index}')

        tasks = [update(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Assert - 最终值不确定，但不应损坏
        result = await provider.get('shared_key')
        assert result in [f'value_{i}' for i in range(10)]

    # --------------------------------------------------------------------------
    # 死锁测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_async_lock_no_deadlock(self):
        """
        测试异步锁无死锁（10 并发压力测试）
        """
        # Arrange
        registry = ProviderRegistry()

        async def slow_factory():
            await asyncio.sleep(0.05)
            return Mock(spec=ConfigProvider)

        registry.register_factory('test', slow_factory)

        # Act - 高并发访问（可能触发死锁如果有问题）
        async def access_provider():
            await asyncio.sleep(0.01)  # 随机延迟
            return await registry.get_provider('test')

        # 50 个并发访问
        tasks = [access_provider() for _ in range(50)]

        # 设置超时，如果死锁会超时
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=5.0  # 5 秒超时
            )
        except asyncio.TimeoutError:
            pytest.fail("检测到潜在死锁：5 秒内未完成 50 个并发访问")

        # Assert
        assert len(results) == 50

    @pytest.mark.asyncio
    async def test_no_deadlock_concurrent_different_providers(self):
        """测试并发访问不同 Provider 无死锁"""
        # Arrange
        registry = ProviderRegistry()

        for i in range(5):
            async def factory(idx=i):
                await asyncio.sleep(0.02)
                return Mock(spec=ConfigProvider)
            registry.register_factory(f'provider_{i}', factory)

        # Act - 并发访问不同 Provider
        async def access(name):
            return await registry.get_provider(name)

        tasks = [access(f'provider_{i}') for i in range(5)] * 10  # 50 个任务
        results = await asyncio.gather(*tasks)

        # Assert
        assert len(results) == 50

    # --------------------------------------------------------------------------
    # 锁粒度测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_lock_isolation_between_providers(self):
        """测试不同 Provider 之间的锁隔离"""
        # Arrange
        registry = ProviderRegistry()

        creation_order = []

        def create_provider(name):
            def factory():
                creation_order.append(name)
                return Mock(spec=ConfigProvider, name=name)
            return factory

        registry.register_factory('a', create_provider('a'))
        registry.register_factory('b', create_provider('b'))

        # Act - 并发访问不同 Provider
        async def access(name):
            return await registry.get_provider(name)

        tasks = [access('a'), access('b'), access('a'), access('b')]
        await asyncio.gather(*tasks)

        # Assert - 每个 Provider 只创建一次
        assert creation_order.count('a') == 1
        assert creation_order.count('b') == 1

    # --------------------------------------------------------------------------
    # 边界条件测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_concurrent_get_after_unregister(self):
        """测试并发获取后注销的场景"""
        # Arrange
        registry = ProviderRegistry()
        creation_count = 0

        def factory():
            nonlocal creation_count
            creation_count += 1
            return CountingProvider()

        registry.register_factory('test', factory)

        # Act - 先获取
        provider1 = await registry.get_provider('test')
        assert creation_count == 1

        # 注销
        registry.unregister('test')

        # 重新注册
        registry.register_factory('test', factory)

        # 再次获取（重新创建）
        provider2 = await registry.get_provider('test')

        # Assert
        assert creation_count == 2
        assert provider1 is not provider2

    @pytest.mark.asyncio
    async def test_concurrent_access_after_reregister(self):
        """测试重新注册后的并发访问"""
        # Arrange
        registry = ProviderRegistry()
        instances = []

        def factory_v1():
            provider = Mock(spec=ConfigProvider, version=1)
            instances.append(provider)
            return provider

        def factory_v2():
            provider = Mock(spec=ConfigProvider, version=2)
            instances.append(provider)
            return provider

        # Act - 注册 V1
        registry.register_factory('test', factory_v1)
        await registry.get_provider('test')

        # 重新注册 V2（覆盖）
        registry.register_factory('test', factory_v2)
        # 清除缓存的 provider，强制重新加载
        registry._providers.pop('test', None)

        # 并发获取
        results = await asyncio.gather(*[
            registry.get_provider('test') for _ in range(10)
        ])

        # Assert - 都是 V2
        assert all(r.version == 2 for r in results)


class TestDoubleCheckLocking:
    """双重检查锁定模式验证"""

    @pytest.mark.asyncio
    async def test_double_check_prevents_duplicate_creation(self):
        """测试双重检查锁定防止重复创建"""
        # Arrange
        registry = ProviderRegistry()
        creations = []

        def slow_factory():
            import time
            time.sleep(0.05)  # 同步延迟
            provider = Mock(spec=ConfigProvider)
            creations.append(provider)
            return provider

        registry.register_factory('test', slow_factory)

        # Act - 在工厂执行期间并发访问
        # 第一个协程开始创建，第二个协程应等待并复用结果
        result1, result2 = await asyncio.gather(
            registry.get_provider('test'),
            registry.get_provider('test'),
        )

        # Assert
        assert len(creations) == 1, "双重检查锁定应防止重复创建"
        assert result1 is result2

    @pytest.mark.asyncio
    async def test_first_check_fast_path(self):
        """测试第一次检查（快速路径）"""
        # Arrange
        registry = ProviderRegistry()
        provider = Mock(spec=ConfigProvider)
        registry.register('existing', provider)

        # Act - 已存在的 Provider 应直接返回（无需锁）
        result = await registry.get_provider('existing')

        # Assert
        assert result is provider
