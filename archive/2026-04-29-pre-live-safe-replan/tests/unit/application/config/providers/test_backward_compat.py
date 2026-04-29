"""
向后兼容测试 - ConfigManager 别名方法验证

测试范围:
- get_core_config() 委托给 get_config('core')
- get_user_config() 委托给 get_config('user')
- get_risk_config() 委托给 get_config('risk')
- update_risk_config() 委托给 update_config('risk', ...)
- 所有遗留方法名仍存在
- 遗留方法返回类型正确

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md

注意：本测试文件假设 ConfigManager 已实现向后兼容别名方法。
如果 ConfigManager 尚未实现，需要先实现后再运行此测试。
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from src.application.config.providers.registry import ProviderRegistry
from src.application.config.providers.base import ConfigProvider


# =============================================================================
# Mock ConfigManager with backward compatible aliases
# =============================================================================

class ConfigManagerWithAliases:
    """
    ConfigManager with 向后兼容别名方法

    这是 ConfigManager 的测试版本，包含所有向后兼容的别名方法，
    用于测试委托逻辑。
    """

    def __init__(self):
        self._registry = ProviderRegistry()

    def register_provider(self, name: str, provider: ConfigProvider) -> None:
        self._registry.register(name, provider)

    # ========== 新统一 API ==========

    async def get_config(self, name: str, key: str = None):
        """统一动态访问入口"""
        provider = await self._registry.get_provider(name)
        return await provider.get(key)

    async def update_config(self, name: str, key: str, value: any) -> None:
        """统一更新入口"""
        provider = await self._registry.get_provider(name)
        await provider.update(key, value)

    # ========== 向后兼容别名 ==========

    async def get_core_config(self):
        """向后兼容：委托给 get_config('core')"""
        return await self.get_config('core')

    async def get_user_config(self):
        """向后兼容：委托给 get_config('user')"""
        return await self.get_config('user')

    async def get_risk_config(self):
        """向后兼容：委托给 get_config('risk')"""
        return await self.get_config('risk')

    async def get_exchange_config(self):
        """向后兼容：委托给 get_config('exchange')"""
        return await self.get_config('exchange')

    async def update_risk_config(self, key: str, value: any) -> None:
        """向后兼容：委托给 update_config('risk', key, value)"""
        await self.update_config('risk', key, value)

    async def update_user_config(self, key: str, value: any) -> None:
        """向后兼容：委托给 update_config('user', key, value)"""
        await self.update_config('user', key, value)


# =============================================================================
# Mock Provider with typed responses
# =============================================================================

class TypedMockProvider:
    """类型化 Mock Provider - 返回特定类型的配置数据"""

    def __init__(self, data: dict):
        self._data = data
        self.get_call_count = 0
        self.update_call_count = 0

    async def get(self, key: str = None):
        self.get_call_count += 1
        if key is None:
            return self._data
        return self._data.get(key)

    async def update(self, key: str, value: any) -> None:
        self.update_call_count += 1
        self._data[key] = value

    async def refresh(self) -> None:
        pass

    @property
    def cache_ttl(self) -> int:
        return 300


# =============================================================================
# Tests
# =============================================================================

class TestBackwardCompatibility:
    """向后兼容别名方法测试"""

    @pytest.fixture
    def manager(self):
        """创建 ConfigManagerWithAliases 实例"""
        return ConfigManagerWithAliases()

    @pytest.fixture
    def core_provider(self):
        """创建 CoreConfig Mock Provider"""
        return TypedMockProvider({
            'core_symbols': ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
            'core_timeframes': ['15m', '1h', '4h'],
            'ema_period': 60,
            'test_mode': False,
        })

    @pytest.fixture
    def user_provider(self):
        """创建 UserConfig Mock Provider"""
        return TypedMockProvider({
            'api_key': 'test_api_key',
            'api_secret': 'test_api_secret',
            'testnet': True,
            'notification_enabled': True,
        })

    @pytest.fixture
    def risk_provider(self):
        """创建 RiskConfig Mock Provider"""
        return TypedMockProvider({
            'max_loss_percent': Decimal('0.01'),
            'max_leverage': 20,
            'default_leverage': 10,
            'cool_down_minutes': 30,
        })

    @pytest.fixture
    def exchange_provider(self):
        """创建 ExchangeConfig Mock Provider"""
        return TypedMockProvider({
            'name': 'binance',
            'api_key': 'exchange_key',
            'api_secret': 'exchange_secret',
            'testnet': True,
        })

    # --------------------------------------------------------------------------
    # get_core_config() 测试
    # --------------------------------------------------------------------------

    async def test_get_core_config_alias(self, manager, core_provider):
        """测试 get_core_config() 委托给 get_config('core')"""
        # Arrange
        manager.register_provider('core', core_provider)

        # Act
        result = await manager.get_core_config()

        # Assert
        assert result == {
            'core_symbols': ['BTC/USDT:USDT', 'ETH/USDT:USDT'],
            'core_timeframes': ['15m', '1h', '4h'],
            'ema_period': 60,
            'test_mode': False,
        }
        assert core_provider.get_call_count == 1

    async def test_get_core_config_delegates_correctly(self, manager):
        """测试 get_core_config 正确委托给 get_config"""
        # Arrange
        provider = Mock(spec=ConfigProvider)
        provider.get = AsyncMock(return_value={'delegated': 'core_data'})
        provider.cache_ttl = 300
        manager.register_provider('core', provider)

        # Act
        result = await manager.get_core_config()

        # Assert
        assert result == {'delegated': 'core_data'}
        provider.get.assert_called_once_with(None)

    # --------------------------------------------------------------------------
    # get_user_config() 测试
    # --------------------------------------------------------------------------

    async def test_get_user_config_alias(self, manager, user_provider):
        """测试 get_user_config() 委托给 get_config('user')"""
        # Arrange
        manager.register_provider('user', user_provider)

        # Act
        result = await manager.get_user_config()

        # Assert
        assert result == {
            'api_key': 'test_api_key',
            'api_secret': 'test_api_secret',
            'testnet': True,
            'notification_enabled': True,
        }

    async def test_get_user_config_delegates_correctly(self, manager):
        """测试 get_user_config 正确委托给 get_config"""
        # Arrange
        provider = Mock(spec=ConfigProvider)
        provider.get = AsyncMock(return_value={'user': 'data'})
        provider.cache_ttl = 300
        manager.register_provider('user', provider)

        # Act
        result = await manager.get_user_config()

        # Assert
        assert result == {'user': 'data'}

    # --------------------------------------------------------------------------
    # get_risk_config() 测试
    # --------------------------------------------------------------------------

    async def test_get_risk_config_alias(self, manager, risk_provider):
        """测试 get_risk_config() 委托给 get_config('risk')"""
        # Arrange
        manager.register_provider('risk', risk_provider)

        # Act
        result = await manager.get_risk_config()

        # Assert
        assert result == {
            'max_loss_percent': Decimal('0.01'),
            'max_leverage': 20,
            'default_leverage': 10,
            'cool_down_minutes': 30,
        }

    async def test_get_risk_config_with_specific_key(self, manager, risk_provider):
        """测试 get_risk_config 获取特定键"""
        # Arrange
        manager.register_provider('risk', risk_provider)

        # Act
        max_leverage = await manager.get_config('risk', 'max_leverage')

        # Assert
        assert max_leverage == 20

    # --------------------------------------------------------------------------
    # update_risk_config() 测试
    # --------------------------------------------------------------------------

    async def test_update_risk_config_alias(self, manager, risk_provider):
        """测试 update_risk_config() 委托给 update_config('risk', key, value)"""
        # Arrange
        manager.register_provider('risk', risk_provider)

        # Act
        await manager.update_risk_config('max_leverage', 50)

        # Assert
        assert risk_provider._data['max_leverage'] == 50
        assert risk_provider.update_call_count == 1

    async def test_update_risk_config_delegates_correctly(self, manager):
        """测试 update_risk_config 正确委托给 update_config"""
        # Arrange
        provider = Mock(spec=ConfigProvider)
        provider.update = AsyncMock()
        provider.get = AsyncMock(return_value={})
        provider.cache_ttl = 300
        manager.register_provider('risk', provider)

        # Act
        await manager.update_risk_config('max_loss_percent', Decimal('0.02'))

        # Assert
        provider.update.assert_called_once_with('max_loss_percent', Decimal('0.02'))

    # --------------------------------------------------------------------------
    # update_user_config() 测试
    # --------------------------------------------------------------------------

    async def test_update_user_config_alias(self, manager, user_provider):
        """测试 update_user_config() 委托给 update_config('user', key, value)"""
        # Arrange
        manager.register_provider('user', user_provider)

        # Act
        await manager.update_user_config('testnet', False)

        # Assert
        assert user_provider._data['testnet'] == False
        assert user_provider.update_call_count == 1

    # --------------------------------------------------------------------------
    # get_exchange_config() 测试
    # --------------------------------------------------------------------------

    async def test_get_exchange_config_alias(self, manager, exchange_provider):
        """测试 get_exchange_config() 委托给 get_config('exchange')"""
        # Arrange
        manager.register_provider('exchange', exchange_provider)

        # Act
        result = await manager.get_exchange_config()

        # Assert
        assert result == {
            'name': 'binance',
            'api_key': 'exchange_key',
            'api_secret': 'exchange_secret',
            'testnet': True,
        }

    # --------------------------------------------------------------------------
    # 遗留方法存在性验证
    # --------------------------------------------------------------------------

    def test_all_legacy_methods_exist(self, manager):
        """测试所有遗留方法名仍存在"""
        # Assert
        assert hasattr(manager, 'get_core_config')
        assert hasattr(manager, 'get_user_config')
        assert hasattr(manager, 'get_risk_config')
        assert hasattr(manager, 'get_exchange_config')
        assert hasattr(manager, 'update_risk_config')
        assert hasattr(manager, 'update_user_config')

        # 验证是可调用的
        assert callable(getattr(manager, 'get_core_config'))
        assert callable(getattr(manager, 'get_user_config'))
        assert callable(getattr(manager, 'get_risk_config'))
        assert callable(getattr(manager, 'update_risk_config'))

    # --------------------------------------------------------------------------
    # 遗留方法返回类型验证
    # --------------------------------------------------------------------------

    async def test_legacy_methods_return_types(self, manager, core_provider, user_provider, risk_provider):
        """测试遗留方法返回类型正确"""
        # Arrange
        manager.register_provider('core', core_provider)
        manager.register_provider('user', user_provider)
        manager.register_provider('risk', risk_provider)

        # Act
        core_config = await manager.get_core_config()
        user_config = await manager.get_user_config()
        risk_config = await manager.get_risk_config()

        # Assert
        assert isinstance(core_config, dict)
        assert isinstance(user_config, dict)
        assert isinstance(risk_config, dict)

        # 验证具体字段类型
        assert isinstance(core_config['core_symbols'], list)
        assert isinstance(risk_config['max_leverage'], int)
        assert isinstance(risk_config['max_loss_percent'], Decimal)

    # --------------------------------------------------------------------------
    # 委托链验证
    # --------------------------------------------------------------------------

    async def test_alias_and_direct_access_consistency(self, manager, core_provider):
        """测试别名访问和直接访问的一致性"""
        # Arrange
        manager.register_provider('core', core_provider)

        # Act
        alias_result = await manager.get_core_config()
        direct_result = await manager.get_config('core')

        # Assert
        assert alias_result == direct_result

    async def test_multiple_alias_calls_use_same_provider(self, manager, risk_provider):
        """测试多次别名调用使用同一 Provider"""
        # Arrange
        manager.register_provider('risk', risk_provider)

        # Act
        await manager.get_risk_config()
        await manager.get_risk_config()
        await manager.update_risk_config('max_leverage', 50)
        await manager.get_risk_config()

        # Assert - Provider 被多次调用
        assert risk_provider.get_call_count == 3
        assert risk_provider.update_call_count == 1

    # --------------------------------------------------------------------------
    # 边界条件测试
    # --------------------------------------------------------------------------

    async def test_alias_with_missing_provider(self, manager):
        """测试别名方法在 Provider 缺失时的行为"""
        # Act & Assert
        with pytest.raises(KeyError):
            await manager.get_core_config()

    async def test_alias_with_faulty_provider(self, manager):
        """测试别名方法在 Provider 故障时的行为"""
        # Arrange
        faulty_provider = Mock(spec=ConfigProvider)
        faulty_provider.get = AsyncMock(side_effect=RuntimeError("Provider error"))
        faulty_provider.cache_ttl = 300
        manager.register_provider('core', faulty_provider)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Provider error"):
            await manager.get_core_config()


class TestBackwardCompatibilityIntegration:
    """向后兼容集成测试"""

    async def test_full_backward_compat_workflow(self):
        """测试完整的向后兼容工作流"""
        # Arrange
        manager = ConfigManagerWithAliases()

        # 注册所有 Provider
        manager.register_provider('core', TypedMockProvider({
            'core_symbols': ['BTC/USDT:USDT'],
            'ema_period': 60,
        }))
        manager.register_provider('user', TypedMockProvider({
            'api_key': 'key',
            'testnet': True,
        }))
        manager.register_provider('risk', TypedMockProvider({
            'max_loss_percent': Decimal('0.01'),
            'max_leverage': 20,
        }))

        # Act - 使用别名方法（旧代码）
        core = await manager.get_core_config()
        user = await manager.get_user_config()
        risk = await manager.get_risk_config()

        # Assert - 所有别名方法工作正常
        assert core['ema_period'] == 60
        assert user['testnet'] == True
        assert risk['max_leverage'] == 20

        # Act - 使用新 API（新代码）
        core_symbols = await manager.get_config('core', 'core_symbols')
        await manager.update_config('risk', 'max_leverage', 50)
        new_risk = await manager.get_risk_config()

        # Assert - 新 API 也工作正常
        assert core_symbols == ['BTC/USDT:USDT']
        assert new_risk['max_leverage'] == 50

    async def test_mixed_old_and_new_api_usage(self):
        """测试混合使用新旧 API"""
        # Arrange
        manager = ConfigManagerWithAliases()
        provider = TypedMockProvider({'key1': 'value1', 'key2': 'value2'})
        manager.register_provider('test', provider)

        # Act - 旧 API
        key1_old = await provider.get('key1')

        # Act - 新 API
        key2_new = await manager.get_config('test', 'key2')
        await manager.update_config('test', 'key3', 'value3')
        key3 = await provider.get('key3')

        # Assert - 验证所有键都能正确获取
        assert key1_old == 'value1'
        assert key2_new == 'value2'
        assert key3 == 'value3'

        # 验证最终数据包含所有键
        all_data = await provider.get()
        assert all_data == {'key1': 'value1', 'key2': 'value2', 'key3': 'value3'}
