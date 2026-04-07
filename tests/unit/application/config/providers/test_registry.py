"""
ProviderRegistry 单元测试 - 注册/注销机制验证

测试范围:
- 注册 Provider 实例
- 注册工厂函数（懒加载）
- 获取 Provider（正常/异常）
- 注销 Provider
- Provider 类型验证

对应设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查报告：docs/reviews/p1_5_provider_design_qa_review.md
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.application.config.providers.registry import ProviderRegistry
from src.application.config.providers.base import ConfigProvider


class TestProviderRegistry:
    """ProviderRegistry 注册/注销测试"""

    # --------------------------------------------------------------------------
    # 基础注册测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_register_provider_success(self):
        """测试成功注册 Provider"""
        # Arrange
        registry = ProviderRegistry()
        provider = Mock(spec=ConfigProvider)

        # Act
        registry.register('test', provider)

        # Assert
        result = await registry.get_provider('test')
        assert result is provider

    @pytest.mark.asyncio
    async def test_register_provider_overwrite(self):
        """测试注册覆盖已存在的 Provider"""
        # Arrange
        registry = ProviderRegistry()
        provider1 = Mock(spec=ConfigProvider)
        provider2 = Mock(spec=ConfigProvider)

        # Act
        registry.register('test', provider1)
        registry.register('test', provider2)

        # Assert
        result = await registry.get_provider('test')
        assert result is provider2
        assert result is not provider1

    @pytest.mark.asyncio
    async def test_get_provider_not_found(self):
        """测试获取不存在的 Provider 抛出 KeyError"""
        # Arrange
        registry = ProviderRegistry()

        # Act & Assert
        with pytest.raises(KeyError, match="Provider 'nonexistent' not registered"):
            await registry.get_provider('nonexistent')

    # --------------------------------------------------------------------------
    # 懒加载测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_register_factory_lazy_loading(self):
        """测试工厂函数懒加载"""
        # Arrange
        registry = ProviderRegistry()
        factory_called = False

        def factory():
            nonlocal factory_called
            factory_called = True
            return Mock(spec=ConfigProvider)

        # Act
        registry.register_factory('lazy', factory)

        # Assert - 注册时不触发
        assert not factory_called

        # Act - 首次访问触发
        provider = await registry.get_provider('lazy')

        # Assert
        assert factory_called
        assert provider is not None

    @pytest.mark.asyncio
    async def test_factory_lazy_loading_multiple_accesses(self):
        """测试懒加载多次访问只创建一次"""
        # Arrange
        registry = ProviderRegistry()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return Mock(spec=ConfigProvider)

        registry.register_factory('lazy', factory)

        # Act - 多次访问
        provider1 = await registry.get_provider('lazy')
        provider2 = await registry.get_provider('lazy')
        provider3 = await registry.get_provider('lazy')

        # Assert - 工厂只调用一次
        assert call_count == 1
        assert provider1 is provider2 is provider3

    # --------------------------------------------------------------------------
    # 注销测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unregister_existing_provider(self):
        """测试注销已存在的 Provider"""
        # Arrange
        registry = ProviderRegistry()
        provider = Mock(spec=ConfigProvider)
        registry.register('test', provider)

        # Act
        registry.unregister('test')

        # Assert
        with pytest.raises(KeyError):
            await registry.get_provider('test')

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_provider(self):
        """测试注销不存在的 Provider（应静默成功）"""
        # Arrange
        registry = ProviderRegistry()

        # Act
        registry.unregister('nonexistent')

        # Assert - 不应该抛出异常
        assert 'nonexistent' not in registry.registered_names

    @pytest.mark.asyncio
    async def test_unregister_removes_factory_too(self):
        """测试注销同时移除 Provider 实例和工厂函数"""
        # Arrange
        registry = ProviderRegistry()
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return Mock(spec=ConfigProvider)

        registry.register_factory('test', factory)

        # Act - 先获取（触发懒加载）
        await registry.get_provider('test')
        assert call_count == 1

        # Act - 注销
        registry.unregister('test')

        # Assert - Provider 和工厂都被移除
        assert 'test' not in registry.registered_names

        # 再次获取会失败
        with pytest.raises(KeyError):
            await registry.get_provider('test')

    # --------------------------------------------------------------------------
    # registered_names 属性测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_registered_names_property_with_instances(self):
        """测试 registered_names 属性返回正确列表（实例注册）"""
        # Arrange
        registry = ProviderRegistry()
        provider1 = Mock(spec=ConfigProvider)
        provider2 = Mock(spec=ConfigProvider)

        # Act
        registry.register('core', provider1)
        registry.register('user', provider2)

        # Assert
        names = registry.registered_names
        assert 'core' in names
        assert 'user' in names
        assert len(names) == 2

    @pytest.mark.asyncio
    async def test_registered_names_property_with_factories(self):
        """测试 registered_names 属性返回正确列表（工厂注册）"""
        # Arrange
        registry = ProviderRegistry()

        # Act
        registry.register_factory('core', lambda: Mock(spec=ConfigProvider))
        registry.register_factory('user', lambda: Mock(spec=ConfigProvider))

        # Assert
        names = registry.registered_names
        assert 'core' in names
        assert 'user' in names
        assert len(names) == 2

    @pytest.mark.asyncio
    async def test_registered_names_property_mixed(self):
        """测试 registered_names 属性返回正确列表（混合注册）"""
        # Arrange
        registry = ProviderRegistry()

        # Act
        registry.register('core', Mock(spec=ConfigProvider))
        registry.register_factory('user', lambda: Mock(spec=ConfigProvider))

        # Assert
        names = registry.registered_names
        assert 'core' in names
        assert 'user' in names
        assert len(names) == 2

    # --------------------------------------------------------------------------
    # Provider 类型验证测试
    # --------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_provider_returns_correct_type(self):
        """测试获取的 Provider 类型正确"""
        # Arrange
        registry = ProviderRegistry()
        provider = Mock(spec=ConfigProvider)
        registry.register('test', provider)

        # Act
        result = await registry.get_provider('test')

        # Assert
        assert isinstance(result, ConfigProvider)

    @pytest.mark.asyncio
    async def test_register_non_config_provider(self):
        """测试注册非 ConfigProvider 对象（应允许，运行时验证）"""
        # Arrange
        registry = ProviderRegistry()

        # Act - 注册一个没有实现 Protocol 的对象
        # 注意：Python 是鸭子类型，注册时不验证，使用时才验证
        registry.register('invalid', {'not': 'a provider'})

        # Assert - 获取时会尝试使用，但可能失败
        result = await registry.get_provider('invalid')
        assert result == {'not': 'a provider'}


class TestProviderRegistryWithMockProvider:
    """使用真实 Mock Provider 的集成测试"""

    @pytest.fixture
    def mock_provider(self):
        """创建 Mock Provider"""
        from tests.unit.application.config.providers.conftest import MockConfigProvider
        return MockConfigProvider({'key': 'value'})

    @pytest.mark.asyncio
    async def test_register_and_get_with_mock_provider(self, mock_provider):
        """测试注册和获取 Mock Provider"""
        # Arrange
        registry = ProviderRegistry()

        # Act
        registry.register('test', mock_provider)
        result = await registry.get_provider('test')

        # Assert
        assert result is mock_provider

    @pytest.mark.asyncio
    async def test_get_provider_and_call_methods(self, mock_provider):
        """测试获取 Provider 后调用其方法"""
        # Arrange
        registry = ProviderRegistry()
        registry.register('test', mock_provider)

        # Act
        provider = await registry.get_provider('test')
        data = await provider.get('key')

        # Assert
        assert data == 'value'
        assert mock_provider.get_call_count == 1
