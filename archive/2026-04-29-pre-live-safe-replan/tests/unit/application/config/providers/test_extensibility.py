"""
Provider 扩展性验证测试 - 零修改扩展场景

测试范围:
- 新增 Provider 注册
- 新增 Provider 使用
- 零修改扩展验证
- 自定义 Provider 场景

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md
"""

import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timedelta
from decimal import Decimal

from src.application.config.providers.registry import ProviderRegistry
from src.application.config.providers.base import ConfigProvider
from src.application.config.providers.cached_provider import CachedProvider, MockClock, SystemClock


# =============================================================================
# Custom Provider Implementations for Testing
# =============================================================================

class CustomExchangeProvider(CachedProvider):
    """
    自定义交易所配置 Provider - 模拟新增 Provider 场景
    """

    CACHE_TTL_SECONDS = 120  # 2 分钟缓存

    def __init__(self, exchange_name: str = "binance", clock=None):
        super().__init__(clock=clock)
        self.exchange_name = exchange_name
        self._data = {
            'name': exchange_name,
            'api_key': 'test_key',
            'api_secret': 'test_secret',
            'testnet': True,
            'rate_limit': 1200,
        }

    async def get(self, key: str = None):
        cache_key = key or '__all__'
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        result = self._data.get(key) if key else self._data
        self._set_cached(cache_key, result)
        return result

    async def update(self, key: str, value: any) -> None:
        self._data[key] = value
        self._invalidate_cache(key)

    async def refresh(self) -> None:
        self._invalidate_cache()


class CustomDatabaseProvider:
    """
    自定义数据库配置 Provider - 不继承 CachedProvider

    用于测试非缓存 Provider 的扩展性
    """

    def __init__(self, connection_string: str = None):
        self.connection_string = connection_string or "sqlite:///test.db"
        self._data = {
            'host': 'localhost',
            'port': 5432,
            'database': 'dingdingbot',
            'pool_size': 10,
        }

    async def get(self, key: str = None):
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: any) -> None:
        self._data[key] = value

    async def refresh(self) -> None:
        pass

    @property
    def cache_ttl(self) -> int:
        return 0  # 不缓存


class CustomFeatureProvider:
    """
    自定义功能开关 Provider - 模拟新功能配置

    用于测试 Feature Flag 场景
    """

    def __init__(self):
        self._features = {
            'new_ui_enabled': False,
            'beta_strategies_enabled': True,
            'advanced_charting_enabled': True,
            'max_concurrent_trades': 5,
        }

    async def get(self, key: str = None):
        if key is None:
            return self._features
        return self._features.get(key)

    async def update(self, key: str, value: any) -> None:
        self._features[key] = value

    async def refresh(self) -> None:
        pass

    @property
    def cache_ttl(self) -> int:
        return 60


# =============================================================================
# Simple ConfigManager for testing
# =============================================================================

class SimpleConfigManager:
    """简单 ConfigManager - 用于测试扩展性"""

    def __init__(self):
        self._registry = ProviderRegistry()

    def register_provider(self, name: str, provider: ConfigProvider) -> None:
        self._registry.register(name, provider)

    async def get_config(self, name: str, key: str = None):
        provider = await self._registry.get_provider(name)
        return await provider.get(key)

    async def update_config(self, name: str, key: str, value: any) -> None:
        provider = await self._registry.get_provider(name)
        await provider.update(key, value)


# =============================================================================
# Tests
# =============================================================================

class TestExtensibility:
    """扩展性验证测试"""

    # --------------------------------------------------------------------------
    # 新增 Provider 注册测试
    # --------------------------------------------------------------------------

    def test_add_custom_provider(self):
        """测试添加自定义 Provider"""
        # Arrange
        manager = SimpleConfigManager()

        # Act - 注册自定义 Provider
        custom_provider = CustomExchangeProvider("bybit")
        manager.register_provider('exchange', custom_provider)

        # Assert - 注册成功
        assert 'exchange' in manager._registry.registered_names

    async def test_custom_provider_with_different_ttl(self):
        """测试自定义 Provider 配置不同 TTL"""
        # Arrange
        manager = SimpleConfigManager()
        provider = CustomExchangeProvider("okx")

        # Assert - 验证 TTL 配置
        assert provider.cache_ttl == 120  # 2 分钟

        # Act - 注册并使用
        manager.register_provider('exchange', provider)
        config = await manager.get_config('exchange')

        # Assert
        assert config['name'] == 'okx'

    async def test_provider_composition(self):
        """测试 Provider 组合使用"""
        # Arrange
        manager = SimpleConfigManager()

        # Act - 注册多个 Provider
        manager.register_provider('exchange', CustomExchangeProvider("binance"))
        manager.register_provider('database', CustomDatabaseProvider())
        manager.register_provider('features', CustomFeatureProvider())

        # Assert - 所有 Provider 都可访问
        exchange_config = await manager.get_config('exchange')
        database_config = await manager.get_config('database')
        features_config = await manager.get_config('features')

        assert exchange_config['name'] == 'binance'
        assert database_config['database'] == 'dingdingbot'
        assert features_config['beta_strategies_enabled'] == True

    # --------------------------------------------------------------------------
    # 零修改扩展验证
    # --------------------------------------------------------------------------

    async def test_zero_modification_extension(self):
        """
        测试零修改扩展 - 新增 Provider 不需要修改任何已有代码

        这是 Provider 注册模式的核心优势验证
        """
        # Arrange - 模拟已有系统
        manager = SimpleConfigManager()
        manager.register_provider('core', Mock(
            spec=ConfigProvider,
            get=AsyncMock(return_value={'core_key': 'core_value'}),
            update=AsyncMock(),
            refresh=AsyncMock(),
            cache_ttl=300
        ))

        # Act - 新增 Provider（零修改）
        new_provider = CustomFeatureProvider()
        manager.register_provider('new_feature', new_provider)

        # Assert - 新 Provider 可访问，原有 Provider 不受影响
        core_config = await manager.get_config('core')
        feature_config = await manager.get_config('new_feature')

        assert core_config == {'core_key': 'core_value'}
        assert feature_config['max_concurrent_trades'] == 5

    async def test_provider_decorator_pattern(self):
        """测试 Provider 装饰器模式（如 CachedProvider 包装其他 Provider）"""
        # Arrange
        class LoggingProvider:
            """装饰器模式 - 添加日志功能的 Provider"""

            def __init__(self, wrapped: ConfigProvider):
                self._wrapped = wrapped
                self.call_log = []

            async def get(self, key: str = None):
                self.call_log.append(('get', key))
                return await self._wrapped.get(key)

            async def update(self, key: str, value: any) -> None:
                self.call_log.append(('update', key, value))
                await self._wrapped.update(key, value)

            async def refresh(self) -> None:
                self.call_log.append(('refresh', None))
                await self._wrapped.refresh()

            @property
            def cache_ttl(self) -> int:
                return self._wrapped.cache_ttl

        # Act - 用装饰器包装
        base_provider = CustomExchangeProvider("binance")
        logging_provider = LoggingProvider(base_provider)

        manager = SimpleConfigManager()
        manager.register_provider('exchange', logging_provider)

        # 使用
        await manager.get_config('exchange')
        await manager.update_config('exchange', 'rate_limit', 2400)

        # Assert - 装饰器记录调用
        assert len(logging_provider.call_log) == 2
        assert ('get', None) in logging_provider.call_log
        assert ('update', 'rate_limit', 2400) in logging_provider.call_log

    # --------------------------------------------------------------------------
    # 动态扩展场景
    # --------------------------------------------------------------------------

    async def test_runtime_provider_registration(self):
        """测试运行时动态注册 Provider"""
        # Arrange
        manager = SimpleConfigManager()

        # Act - 初始只有一个 Provider
        manager.register_provider('core', CustomExchangeProvider("core"))

        # 运行时动态添加
        manager.register_provider('runtime_added', CustomFeatureProvider())

        # Assert
        configs = await manager.get_config('runtime_added')
        assert configs['max_concurrent_trades'] == 5

    async def test_provider_hot_swap(self):
        """测试 Provider 热替换"""
        # Arrange
        manager = SimpleConfigManager()
        provider_v1 = CustomExchangeProvider("v1")
        manager.register_provider('exchange', provider_v1)

        # Act - 热替换
        provider_v2 = CustomExchangeProvider("v2")
        manager.register_provider('exchange', provider_v2)

        # Assert
        config = await manager.get_config('exchange')
        assert config['name'] == 'v2'

    # --------------------------------------------------------------------------
    # 特殊场景测试
    # --------------------------------------------------------------------------

    async def test_provider_with_complex_initialization(self):
        """测试复杂初始化的 Provider"""
        # Arrange
        class ComplexInitProvider:
            def __init__(self):
                # 模拟复杂初始化（数据库连接、网络请求等）
                self._initialized = False
                self._data = None

            async def initialize(self):
                await asyncio.sleep(0.01)  # 模拟异步初始化
                self._data = {'initialized': True}
                self._initialized = True

            async def get(self, key: str = None):
                if not self._initialized:
                    await self.initialize()
                return self._data.get(key) if key else self._data

            async def update(self, key: str, value: any) -> None:
                pass

            async def refresh(self) -> None:
                await self.initialize()

            @property
            def cache_ttl(self) -> int:
                return 60

        import asyncio
        manager = SimpleConfigManager()
        provider = ComplexInitProvider()
        manager.register_provider('complex', provider)

        # Act
        config = await manager.get_config('complex')

        # Assert
        assert config['initialized'] == True

    async def test_provider_lazy_initialization(self):
        """测试 Provider 懒初始化"""
        # Arrange
        initialization_count = 0

        class LazyProvider:
            def __init__(self):
                self._data = None

            def _lazy_init(self):
                nonlocal initialization_count
                initialization_count += 1
                self._data = {'lazy': 'data'}

            async def get(self, key: str = None):
                if self._data is None:
                    self._lazy_init()
                return self._data.get(key) if key else self._data

            async def update(self, key: str, value: any) -> None:
                pass

            async def refresh(self) -> None:
                self._data = None

            @property
            def cache_ttl(self) -> int:
                return 300

        manager = SimpleConfigManager()
        provider = LazyProvider()
        manager.register_provider('lazy', provider)

        # Assert - 注册时不初始化
        assert initialization_count == 0

        # Act - 首次访问时初始化
        await manager.get_config('lazy')

        # Assert
        assert initialization_count == 1


class TestNewProviderScenario:
    """新增 Provider 场景完整模拟"""

    async def test_add_new_risk_config_provider(self):
        """
        模拟新增新风控配置 Provider 场景

        对应设计文档中的扩展性验证场景
        """
        # Arrange - 实现新风控 Provider
        class NewRiskConfigProvider(CachedProvider):
            CACHE_TTL_SECONDS = 60  # 1 分钟缓存

            def __init__(self, clock=None):
                super().__init__(clock=clock)
                self._data = {
                    'max_daily_loss': Decimal('0.02'),
                    'max_single_trade_loss': Decimal('0.005'),
                    'cool_down_minutes': 30,
                    'new_feature_flag': True,
                }

            async def get(self, key: str = None):
                cache_key = key or '__all__'
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                result = self._data.get(key) if key else self._data
                self._set_cached(cache_key, result)
                return result

            async def update(self, key: str, value: any) -> None:
                self._data[key] = value
                self._invalidate_cache(key)

            async def refresh(self) -> None:
                self._invalidate_cache()

        # Act - 注册新风控 Provider
        manager = SimpleConfigManager()

        # 注册原有风控 Provider（模拟）
        old_risk = Mock(spec=ConfigProvider)
        old_risk.get = AsyncMock(return_value={'legacy': 'risk'})
        manager.register_provider('risk', old_risk)

        # 注册新风控 Provider（零修改扩展）
        manager.register_provider('new_risk', NewRiskConfigProvider())

        # Assert - 新风控可访问
        new_risk_config = await manager.get_config('new_risk')
        assert new_risk_config['max_daily_loss'] == Decimal('0.02')
        assert new_risk_config['new_feature_flag'] == True

        # 原有风控不受影响
        old_risk_config = await manager.get_config('risk')
        assert old_risk_config == {'legacy': 'risk'}

    async def test_add_strategy_provider(self):
        """测试添加策略配置 Provider"""
        # Arrange
        class StrategyConfigProvider:
            def __init__(self):
                self._strategies = []

            async def get(self, key: str = None):
                if key is None:
                    return self._strategies
                return next((s for s in self._strategies if s.get('id') == key), None)

            async def update(self, key: str, value: any) -> None:
                # 更新或添加策略
                for i, s in enumerate(self._strategies):
                    if s.get('id') == key:
                        self._strategies[i] = value
                        return
                self._strategies.append({**value, 'id': key})

            async def refresh(self) -> None:
                pass

            @property
            def cache_ttl(self) -> int:
                return 0

        # Act
        manager = SimpleConfigManager()
        manager.register_provider('strategies', StrategyConfigProvider())

        # 添加策略
        await manager.update_config('strategies', 'pinbar_mtf', {
            'name': 'Pinbar MTF',
            'enabled': True,
        })

        # Assert
        strategy = await manager.get_config('strategies', 'pinbar_mtf')
        assert strategy['name'] == 'Pinbar MTF'


class TestProviderCompatibility:
    """Provider 兼容性测试"""

    def test_protocol_compliance(self):
        """测试 Provider 实现 Protocol 兼容性"""
        from typing import runtime_checkable

        # Arrange
        provider = CustomExchangeProvider()

        # Assert - 实现所有必需方法
        assert hasattr(provider, 'get')
        assert hasattr(provider, 'update')
        assert hasattr(provider, 'refresh')
        assert hasattr(provider, 'cache_ttl')

        # 验证方法签名
        import inspect
        get_sig = inspect.signature(provider.get)
        update_sig = inspect.signature(provider.update)
        refresh_sig = inspect.signature(provider.refresh)

        # get(key: str = None)
        assert 'key' in get_sig.parameters
        # update(key: str, value: any)
        assert 'key' in update_sig.parameters
        assert 'value' in update_sig.parameters

    async def test_non_cached_provider_compatibility(self):
        """测试非 CachedProvider 的兼容性"""
        # Arrange
        manager = SimpleConfigManager()
        provider = CustomDatabaseProvider()  # 不继承 CachedProvider

        # Act
        manager.register_provider('database', provider)
        config = await manager.get_config('database')

        # Assert
        assert config['host'] == 'localhost'
        assert provider.cache_ttl == 0  # 不缓存
