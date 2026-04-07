"""
Provider 注册中心

本模块实现 Provider 注册机制，支持动态注册/注销、懒加载、并发安全访问。

设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查：docs/reviews/p1_5_provider_design_qa_review.md

关键修复 (QA P0):
- 使用 asyncio.Lock + 双重检查锁定模式防止懒加载竞态条件
"""

import asyncio
from typing import Callable, Dict

from .base import ConfigProvider


class ProviderRegistry:
    """
    Provider 注册中心 - 管理所有配置提供者

    特性:
    - 动态注册/注销 Provider
    - 按需懒加载 Provider
    - 支持 Provider 装饰器
    - 并发安全（双重检查锁定）

    使用示例:
        registry = ProviderRegistry()

        # 注册 Provider 实例
        registry.register('core', CoreConfigProvider())

        # 注册工厂函数（懒加载）
        registry.register_factory('user', lambda: UserConfigProvider())

        # 获取 Provider（自动懒加载）
        provider = await registry.get_provider('core')

        # 注销 Provider
        registry.unregister('user')
    """

    def __init__(self) -> None:
        """初始化注册中心"""
        self._providers: Dict[str, ConfigProvider] = {}
        self._factory_funcs: Dict[str, Callable[[], ConfigProvider]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, name: str) -> asyncio.Lock:
        """
        获取或创建指定 Provider 的锁（懒加载）

        Args:
            name: Provider 名称

        Returns:
            asyncio.Lock 实例
        """
        if name not in self._locks:
            self._locks[name] = asyncio.Lock()
        return self._locks[name]

    def register(self, name: str, provider: ConfigProvider) -> None:
        """
        注册 Provider 实例

        Args:
            name: Provider 名称
            provider: ConfigProvider 实例

        注意:
            - 如果名称已存在，会覆盖原有 Provider
            - 不会注销工厂函数，如果需要同时注销请调用 unregister()
        """
        self._providers[name] = provider

    def register_factory(self, name: str, factory: Callable[[], ConfigProvider]) -> None:
        """
        注册 Provider 工厂函数（懒加载）

        Args:
            name: Provider 名称
            factory: 无参数工厂函数，返回 ConfigProvider 实例

        注意:
            - 工厂函数仅在首次调用 get_provider() 时执行
            - 如果名称已存在，会覆盖原有工厂函数
        """
        self._factory_funcs[name] = factory

    async def get_provider(self, name: str) -> ConfigProvider:
        """
        获取 Provider 实例（并发安全 - 双重检查锁定）

        Args:
            name: Provider 名称

        Returns:
            ConfigProvider 实例

        Raises:
            KeyError: Provider 不存在且未注册工厂函数

        并发安全说明:
            使用双重检查锁定模式防止懒加载竞态条件：
            1. 第一次检查（无锁，快速路径）：如果已存在直接返回
            2. 获取锁进行懒加载
            3. 第二次检查（有锁）：防止多个协程同时创建多个实例
        """
        # 第一次检查（无锁，快速路径）
        if name not in self._providers:
            if name in self._factory_funcs:
                # 获取锁进行懒加载
                async with self._get_lock(name):
                    # 第二次检查（有锁，防止竞态条件）
                    if name not in self._providers:
                        # 懒加载：首次访问时创建
                        provider = self._factory_funcs[name]()
                        self.register(name, provider)
            else:
                raise KeyError(f"Provider '{name}' not registered")
        return self._providers[name]

    def unregister(self, name: str) -> None:
        """
        注销 Provider

        Args:
            name: Provider 名称

        注意:
            - 如果 Provider 不存在，静默成功
            - 同时注销 Provider 实例和工厂函数
        """
        self._providers.pop(name, None)
        self._factory_funcs.pop(name, None)

    @property
    def registered_names(self) -> list[str]:
        """
        返回所有已注册的 Provider 名称

        Returns:
            Provider 名称列表（包括已注册实例和工厂函数）
        """
        return list(self._providers.keys()) + list(self._factory_funcs.keys())
