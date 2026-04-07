"""
RiskConfig Provider - 风控配置提供者

本模块实现 RiskConfigProvider，负责从 ConfigRepository 加载风控配置。

设计文档：docs/arch/P1-5-provider-registration-design.md
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from src.domain.models import RiskConfig
from src.application.config.config_repository import ConfigRepository

from .cached_provider import CachedProvider, ClockProtocol, SystemClock


class RiskConfigProvider(CachedProvider):
    """
    风控配置 Provider

    职责:
    - 从 ConfigRepository 加载风控配置 (risk_configs 表)
    - 提供 TTL 缓存机制 (默认 300 秒)
    - 支持配置更新操作

    使用示例:
        repo = ConfigRepository()
        await repo.initialize()

        provider = RiskConfigProvider(repo)
        risk_config = await provider.get()
        max_leverage = await provider.get('max_leverage')
    """

    CACHE_TTL_SECONDS = 300  # 5 分钟缓存

    def __init__(
        self,
        repo: ConfigRepository,
        clock: ClockProtocol = None
    ) -> None:
        """
        初始化 RiskConfigProvider

        Args:
            repo: ConfigRepository 实例，用于数据访问
            clock: 时钟实现，默认使用 SystemClock
        """
        super().__init__(clock=clock or SystemClock())
        self._repo = repo

    @property
    def cache_ttl(self) -> int:
        """缓存 TTL（秒）"""
        return self.CACHE_TTL_SECONDS

    async def get(self, key: Optional[str] = None) -> Any:
        """
        获取风控配置数据

        Args:
            key: 配置键，None 表示获取全部配置

        Returns:
            配置值或 RiskConfig 模型

        Raises:
            ValueError: 配置未初始化
        """
        # 确保 Repository 已初始化
        self._ensure_repo_initialized()

        # 尝试从缓存获取
        cache_key = key or '__all__'
        cached = self._get_cached(cache_key)
        if cached is not None:
            if key is None:
                return cached
            return getattr(cached, key, None)

        # 从数据源加载
        config = await self._fetch_data()

        # 写入缓存
        self._set_cached('__all__', config)

        if key:
            return getattr(config, key, None)
        return config

    async def update(self, key: str, value: Any) -> None:
        """
        更新风控配置

        Args:
            key: 配置键
            value: 新值

        Raises:
            ValueError: 配置未初始化
        """
        self._ensure_repo_initialized()

        # 保存到数据源
        await self._repo.update_risk_config_item(key, value)

        # 刷新缓存
        await self.refresh()

    async def refresh(self) -> None:
        """
        刷新缓存（从数据源重新加载）

        调用场景:
        - 配置热重载
        - 手动刷新缓存
        """
        self._invalidate_cache()
        # 预加载缓存
        await self.get()

    async def _fetch_data(self) -> RiskConfig:
        """
        从 ConfigRepository 获取风控配置数据

        Returns:
            RiskConfig 模型实例
        """
        # 从 Repository 获取 RiskConfig 模型（Repository 已经做了转换）
        return await self._repo.get_risk_config()

    def _ensure_repo_initialized(self) -> None:
        """确保 Repository 已初始化"""
        if not hasattr(self._repo, '_initialized') or not self._repo._initialized:
            raise ValueError(
                "ConfigRepository not initialized. "
                "Call await repo.initialize() before using RiskConfigProvider."
            )
