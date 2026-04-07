"""
Provider Protocol 接口定义

本模块定义配置提供者协议 (ConfigProvider Protocol)，所有配置 Provider 必须实现此接口。

设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查：docs/reviews/p1_5_provider_design_qa_review.md
"""

from typing import Protocol, Any, Optional, runtime_checkable


@runtime_checkable
class ConfigProvider(Protocol):
    """
    配置提供者协议 - 所有 Provider 必须实现的接口

    职责:
    - 提供配置数据访问方法
    - 管理 Provider 级缓存
    - 支持配置更新通知

    示例:
        class CoreConfigProvider:
            async def get(self, key: Optional[str] = None) -> Any:
                ...

            async def update(self, key: str, value: Any) -> None:
                ...

            async def refresh(self) -> None:
                ...

            @property
            def cache_ttl(self) -> int:
                ...
    """

    async def get(self, key: Optional[str] = None) -> Any:
        """
        获取配置数据

        Args:
            key: 配置键，None 表示获取全部配置

        Returns:
            配置值或配置字典
        """
        ...

    async def update(self, key: str, value: Any) -> None:
        """
        更新配置数据

        Args:
            key: 配置键
            value: 新值
        """
        ...

    async def refresh(self) -> None:
        """刷新缓存（从数据源重新加载）"""
        ...

    @property
    def cache_ttl(self) -> int:
        """缓存 TTL（秒），0 表示不缓存"""
        ...


# 类型别名，便于使用
ProviderType = ConfigProvider
