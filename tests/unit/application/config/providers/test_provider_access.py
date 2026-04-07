"""
Provider 动态访问测试 - ConfigManager 委托逻辑验证

测试范围:
- get_config(name) 正常访问
- get_config(name, key) 获取特定配置项
- update_config(name, key, value) 更新
- Provider 委托调用验证
- 异常传播测试

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md

注意：本测试文件测试 Provider 层的动态访问模式，
ConfigManager 外观层的完整测试在其实现完成后进行。
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime

from src.application.config.providers.registry import ProviderRegistry
from src.application.config.providers.base import ConfigProvider
from src.application.config.providers.cached_provider import CachedProvider, MockClock


# =============================================================================
# Mock Provider for testing dynamic access patterns
# =============================================================================

class DynamicAccessMockProvider:
    """
    动态访问 Mock Provider - 用于测试 ConfigManager 委托逻辑

    实现 ConfigProvider Protocol 接口，支持追踪调用参数
    """

    def __init__(self, initial_data: dict = None):
        self._data = initial_data or {}
        self._cache_ttl = 300
        self.get_call_count = 0
        self.get_call_args = []
        self.update_call_count = 0
        self.update_call_args = []
        self.refresh_call_count = 0

    async def get(self, key: str = None):
        """获取配置数据，追踪调用参数"""
        self.get_call_count += 1
        self.get_call_args.append(key)
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: any) -> None:
        """更新配置数据，追踪调用参数"""
        self.update_call_count += 1
        self.update_call_args.append((key, value))
        self._data[key] = value

    async def refresh(self) -> None:
        """刷新缓存"""
        self.refresh_call_count += 1

    @property
    def cache_ttl(self) -> int:
        return self._cache_ttl


# =============================================================================
# Simple ConfigManager for testing delegation
# =============================================================================

class SimpleConfigManager:
    """
    简单 ConfigManager - 用于测试委托模式

    这是 ConfigManager 的简化版本，仅包含动态访问方法，
    用于测试 Provider 委托调用逻辑。
    """

    def __init__(self):
        self._registry = ProviderRegistry()

    def register_provider(self, name: str, provider: ConfigProvider) -> None:
        """注册 Provider"""
        self._registry.register(name, provider)

    async def get_config(self, name: str, key: str = None):
        """
        统一配置访问入口

        Args:
            name: Provider 名称
            key: 配置键，None 表示获取全部
        """
        provider = await self._registry.get_provider(name)
        return await provider.get(key)

    async def update_config(self, name: str, key: str, value: any) -> None:
        """
        统一配置更新入口

        Args:
            name: Provider 名称
            key: 配置键
            value: 新值
        """
        provider = await self._registry.get_provider(name)
        await provider.update(key, value)


# =============================================================================
# Tests
# =============================================================================

class TestConfigManagerDynamicAccess:
    """ConfigManager 动态访问测试"""

    @pytest.fixture
    def manager(self):
        """创建 SimpleConfigManager 实例"""
        return SimpleConfigManager()

    @pytest.fixture
    def mock_provider(self):
        """创建 Mock Provider"""
        return DynamicAccessMockProvider({
            'key1': 'value1',
            'key2': 'value2',
            'nested': {'a': 1, 'b': 2}
        })

    # --------------------------------------------------------------------------
    # get_config 正常访问测试
    # --------------------------------------------------------------------------

    async def test_get_config_all(self, manager, mock_provider):
        """测试获取全部配置 get_config(name)"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        result = await manager.get_config('test')

        # Assert
        assert result == {
            'key1': 'value1',
            'key2': 'value2',
            'nested': {'a': 1, 'b': 2}
        }
        assert mock_provider.get_call_count == 1
        assert mock_provider.get_call_args == [None]

    async def test_get_config_specific_key(self, manager, mock_provider):
        """测试获取特定配置项 get_config(name, key)"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        result = await manager.get_config('test', 'key1')

        # Assert
        assert result == 'value1'
        assert mock_provider.get_call_count == 1
        assert mock_provider.get_call_args == ['key1']

    async def test_get_config_nested_key(self, manager, mock_provider):
        """测试获取嵌套配置项"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        result = await manager.get_config('test', 'nested')

        # Assert
        assert result == {'a': 1, 'b': 2}

    # --------------------------------------------------------------------------
    # get_config 异常测试
    # --------------------------------------------------------------------------

    async def test_get_config_unknown_provider(self, manager):
        """测试获取未知 Provider 的配置（应抛出 KeyError）"""
        # Arrange
        # Act & Assert
        with pytest.raises(KeyError, match="Provider 'unknown' not registered"):
            await manager.get_config('unknown')

    async def test_get_config_provider_returns_none(self, manager):
        """测试 Provider 返回 None 的处理"""
        # Arrange
        empty_provider = DynamicAccessMockProvider({})
        manager.register_provider('empty', empty_provider)

        # Act
        result_all = await manager.get_config('empty')
        result_key = await manager.get_config('empty', 'nonexistent')

        # Assert
        assert result_all == {}
        assert result_key is None

    async def test_get_config_missing_key(self, manager, mock_provider):
        """测试获取不存在的配置键"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        result = await manager.get_config('test', 'nonexistent')

        # Assert
        assert result is None

    # --------------------------------------------------------------------------
    # update_config 测试
    # --------------------------------------------------------------------------

    async def test_update_config(self, manager, mock_provider):
        """测试更新配置 update_config(name, key, value)"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        await manager.update_config('test', 'new_key', 'new_value')

        # Assert
        assert mock_provider.update_call_count == 1
        assert mock_provider.update_call_args == [('new_key', 'new_value')]
        assert mock_provider._data['new_key'] == 'new_value'

        # Verify by getting
        result = await manager.get_config('test', 'new_key')
        assert result == 'new_value'

    async def test_update_config_overwrites(self, manager, mock_provider):
        """测试更新配置覆盖旧值"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        await manager.update_config('test', 'key1', 'updated_value')

        # Assert
        result = await manager.get_config('test', 'key1')
        assert result == 'updated_value'

    # --------------------------------------------------------------------------
    # Provider 委托调用验证
    # --------------------------------------------------------------------------

    async def test_provider_delegation_verification(self, manager):
        """测试 Provider 委托调用验证"""
        # Arrange
        mock_provider = Mock(spec=ConfigProvider)
        mock_provider.get = AsyncMock(return_value={'delegated': 'data'})
        mock_provider.update = AsyncMock()
        mock_provider.refresh = AsyncMock()
        mock_provider.cache_ttl = 300

        manager.register_provider('test', mock_provider)

        # Act
        result = await manager.get_config('test')

        # Assert
        assert result == {'delegated': 'data'}
        mock_provider.get.assert_called_once_with(None)

    async def test_update_config_delegation(self, manager):
        """测试 update_config 委托调用"""
        # Arrange
        mock_provider = Mock(spec=ConfigProvider)
        mock_provider.get = AsyncMock(return_value={})
        mock_provider.update = AsyncMock()
        mock_provider.refresh = AsyncMock()
        mock_provider.cache_ttl = 300

        manager.register_provider('test', mock_provider)

        # Act
        await manager.update_config('test', 'key', 'value')

        # Assert
        mock_provider.update.assert_called_once_with('key', 'value')

    async def test_update_config_propagates_exception(self, manager):
        """测试更新配置时 Provider 异常正确传播"""
        # Arrange
        faulty_provider = DynamicAccessMockProvider()
        original_update = faulty_provider.update

        async def faulty_update(key, value):
            raise RuntimeError("Simulated update error")

        faulty_provider.update = faulty_update
        manager.register_provider('faulty', faulty_provider)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Simulated update error"):
            await manager.update_config('faulty', 'key', 'value')

    # --------------------------------------------------------------------------
    # 多 Provider 测试
    # --------------------------------------------------------------------------

    async def test_multiple_providers_isolation(self, manager):
        """测试多个 Provider 之间的隔离性"""
        # Arrange
        provider1 = DynamicAccessMockProvider({'p1_key': 'p1_value'})
        provider2 = DynamicAccessMockProvider({'p2_key': 'p2_value'})

        manager.register_provider('provider1', provider1)
        manager.register_provider('provider2', provider2)

        # Act
        result1 = await manager.get_config('provider1')
        result2 = await manager.get_config('provider2')

        # Assert
        assert result1 == {'p1_key': 'p1_value'}
        assert result2 == {'p2_key': 'p2_value'}
        assert provider1.get_call_count == 1
        assert provider2.get_call_count == 1

    async def test_cross_provider_update_does_not_affect_others(self, manager):
        """测试跨 Provider 更新不影响其他 Provider"""
        # Arrange
        provider1 = DynamicAccessMockProvider({'shared': 'initial1'})
        provider2 = DynamicAccessMockProvider({'shared': 'initial2'})

        manager.register_provider('p1', provider1)
        manager.register_provider('p2', provider2)

        # Act - 只更新 p1
        await manager.update_config('p1', 'shared', 'updated1')

        # Assert
        result1 = await manager.get_config('p1', 'shared')
        result2 = await manager.get_config('p2', 'shared')

        assert result1 == 'updated1'
        assert result2 == 'initial2'  # p2 未受影响

    # --------------------------------------------------------------------------
    # 注册新 Provider 后动态访问测试
    # --------------------------------------------------------------------------

    async def test_register_provider_extends_access(self, manager):
        """测试注册新 Provider 后可动态访问"""
        # Arrange
        initial_provider = DynamicAccessMockProvider({'initial': 'data'})
        manager.register_provider('initial', initial_provider)

        # Act - 注册新 Provider
        new_provider = DynamicAccessMockProvider({'new': 'data'})
        manager.register_provider('new_provider', new_provider)

        # Assert - 新 Provider 可访问
        result = await manager.get_config('new_provider')
        assert result == {'new': 'data'}

        # 原有 Provider 仍可访问
        result = await manager.get_config('initial')
        assert result == {'initial': 'data'}

    # --------------------------------------------------------------------------
    # 类型验证测试
    # --------------------------------------------------------------------------

    async def test_get_config_type_verification(self, manager, mock_provider):
        """测试返回值的类型验证"""
        # Arrange
        manager.register_provider('test', mock_provider)

        # Act
        all_config = await manager.get_config('test')
        string_value = await manager.get_config('test', 'key1')
        nested_value = await manager.get_config('test', 'nested')

        # Assert
        assert isinstance(all_config, dict)
        assert isinstance(string_value, str)
        assert isinstance(nested_value, dict)


class TestProviderAccessWithCachedProvider:
    """使用 CachedProvider 的动态访问测试"""

    @pytest.fixture
    def manager(self):
        """创建 SimpleConfigManager 实例"""
        return SimpleConfigManager()

    @pytest.fixture
    def mock_clock(self):
        """创建 Mock Clock"""
        return MockClock(datetime(2026, 4, 7, 10, 0, 0))

    @pytest.fixture
    def cached_provider(self, mock_clock):
        """创建带缓存的 Mock Provider"""
        class TestCachedProvider(CachedProvider):
            CACHE_TTL_SECONDS = 60

            def __init__(self, initial_data, clock):
                super().__init__(clock=clock)
                self._data = initial_data
                self._fetch_count = 0

            async def get(self, key=None):
                cache_key = key or '__all__'
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                self._fetch_count += 1
                if key:
                    result = self._data.get(key)
                else:
                    result = self._data

                self._set_cached(cache_key, result)
                return result

            async def update(self, key, value):
                self._data[key] = value
                self._invalidate_cache(key)

            async def refresh(self):
                self._invalidate_cache()

        return TestCachedProvider({'key': 'value'}, mock_clock)

    async def test_cached_provider_cache_hit(self, manager, cached_provider, mock_clock):
        """测试缓存命中场景"""
        # Arrange
        manager.register_provider('cached', cached_provider)

        # Act - 首次访问（无缓存）
        result1 = await manager.get_config('cached')
        assert cached_provider._fetch_count == 1

        # Act - 推进时间但仍在 TTL 内
        mock_clock.advance(30)
        result2 = await manager.get_config('cached')

        # Assert - 缓存命中，未重新 fetch
        assert cached_provider._fetch_count == 1
        assert result1 == result2

    async def test_cached_provider_cache_miss_after_ttl(self, manager, cached_provider, mock_clock):
        """测试 TTL 过期后缓存未命中"""
        # Arrange
        manager.register_provider('cached', cached_provider)

        # Act - 首次访问
        await manager.get_config('cached')
        assert cached_provider._fetch_count == 1

        # Act - 推进时间超过 TTL
        mock_clock.advance(61)  # TTL=60 秒
        result = await manager.get_config('cached')

        # Assert - 重新 fetch
        assert cached_provider._fetch_count == 2


class TestProviderAccessEdgeCases:
    """Provider 动态访问边界条件测试"""

    @pytest.fixture
    def manager(self):
        """创建 SimpleConfigManager 实例"""
        return SimpleConfigManager()

    async def test_get_config_with_empty_string_key(self):
        """测试空字符串键"""
        manager = SimpleConfigManager()
        provider = DynamicAccessMockProvider({'': 'empty_key_value'})
        manager.register_provider('test', provider)

        result = await manager.get_config('test', '')
        assert result == 'empty_key_value'

    async def test_update_config_with_special_characters(self):
        """测试特殊字符键值更新"""
        manager = SimpleConfigManager()
        provider = DynamicAccessMockProvider()
        manager.register_provider('test', provider)

        await manager.update_config('test', 'key:with/special@chars', 'value!@#$%')
        result = await manager.get_config('test', 'key:with/special@chars')
        assert result == 'value!@#$%'

    async def test_get_config_concurrent_same_provider(self, manager):
        """测试并发访问同一 Provider"""
        import asyncio

        provider = DynamicAccessMockProvider({'concurrent': 'test'})
        manager.register_provider('test', provider)

        # 并发访问
        results = await asyncio.gather(
            manager.get_config('test'),
            manager.get_config('test'),
            manager.get_config('test'),
        )

        # 所有结果应相同
        assert all(r == {'concurrent': 'test'} for r in results)
