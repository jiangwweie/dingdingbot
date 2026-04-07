"""
Provider 注册模式 - 配置管理基础设施

本模块提供配置提供者协议、注册中心、缓存基类。

使用示例:
    from src.application.config.providers import (
        ConfigProvider,
        ProviderRegistry,
        CachedProvider,
        SystemClock,
        MockClock,
    )

    # 创建注册中心
    registry = ProviderRegistry()

    # 注册 Provider
    registry.register('core', CoreConfigProvider())

    # 获取 Provider
    provider = await registry.get_provider('core')

设计文档：docs/arch/P1-5-provider-registration-design.md
"""

from .base import ConfigProvider, ProviderType
from .registry import ProviderRegistry
from .cached_provider import (
    CachedProvider,
    ClockProtocol,
    SystemClock,
    MockClock,
)
from .core_provider import CoreConfigProvider
from .user_provider import UserConfigProvider
from .risk_provider import RiskConfigProvider

__all__ = [
    # Protocol
    "ConfigProvider",
    "ProviderType",
    # Registry
    "ProviderRegistry",
    # Cached Provider
    "CachedProvider",
    "ClockProtocol",
    "SystemClock",
    "MockClock",
    # Concrete Providers
    "CoreConfigProvider",
    "UserConfigProvider",
    "RiskConfigProvider",
]
