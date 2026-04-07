"""
CoreConfig Provider - 核心配置提供者

本模块实现 CoreConfigProvider，负责从 ConfigRepository 加载核心配置。

设计文档：docs/arch/P1-5-provider-registration-design.md
"""

from decimal import Decimal
from typing import Any, Dict, Optional

from src.application.config.config_repository import ConfigRepository
from src.application.config.models import CoreConfig

from .cached_provider import CachedProvider, ClockProtocol, SystemClock


class CoreConfigProvider(CachedProvider):
    """
    核心配置 Provider

    职责:
    - 从 ConfigRepository 加载核心配置 (system_configs 表)
    - 提供 TTL 缓存机制 (默认 300 秒)
    - 支持配置更新操作

    使用示例:
        repo = ConfigRepository()
        await repo.initialize()

        provider = CoreConfigProvider(repo)
        core_config = await provider.get()
        symbols = await provider.get('core_symbols')
    """

    CACHE_TTL_SECONDS = 300  # 5 分钟缓存

    def __init__(
        self,
        repo: ConfigRepository,
        clock: ClockProtocol = None
    ) -> None:
        """
        初始化 CoreConfigProvider

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
        获取核心配置数据

        Args:
            key: 配置键，None 表示获取全部配置

        Returns:
            配置值或 CoreConfig 模型

        Raises:
            ValueError: 配置未初始化
        """
        # 确保 Repository 已初始化
        self._ensure_repo_initialized()

        # 尝试从缓存获取
        cache_key = key or '__all__'
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached if key is None else getattr(cached, key, None)

        # 从数据源加载
        config = await self._fetch_data()

        # 写入缓存
        self._set_cached('__all__', config)

        if key:
            return getattr(config, key, None)
        return config

    async def update(self, key: str, value: Any) -> None:
        """
        更新核心配置

        Args:
            key: 配置键
            value: 新值

        Note:
            核心配置通常为只读，此方法主要用于系统级配置更新
        """
        self._ensure_repo_initialized()

        # 保存到数据源
        await self._repo.update_system_config({key: value})

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

    async def _fetch_data(self) -> CoreConfig:
        """
        从 ConfigRepository 获取核心配置数据

        Returns:
            CoreConfig 模型实例
        """
        # 从 Repository 获取原始字典数据
        data = await self._repo.get_system_config()

        # 转换为 Pydantic 模型
        return self._build_core_config(data)

    def _build_core_config(self, data: Dict[str, Any]) -> CoreConfig:
        """
        将字典数据转换为 CoreConfig 模型

        Args:
            data: 原始配置字典

        Returns:
            CoreConfig 模型实例

        Note:
            所有 Decimal 字段使用 Decimal(str(value)) 转换，避免 float 精度损失
        """
        # 构建嵌套对象
        pinbar_defaults = {
            'min_wick_ratio': Decimal(str(data.get('pinbar_min_wick_ratio', '0.6'))),
            'max_body_ratio': Decimal(str(data.get('pinbar_max_body_ratio', '0.3'))),
            'body_position_tolerance': Decimal(str(data.get('pinbar_body_position_tolerance', '0.1'))),
        }

        ema = {
            'period': data.get('ema_period', 60),
        }

        mtf_mapping_data = data.get('mtf_mapping', {})
        if isinstance(mtf_mapping_data, str):
            import json
            mtf_mapping_data = json.loads(mtf_mapping_data)

        warmup = {
            'history_bars': data.get('warmup_history_bars', 100),
        }

        signal_pipeline = {
            'cooldown_seconds': data.get('signal_cooldown_seconds', 14400),
        }

        atr = {
            'enabled': data.get('atr_filter_enabled', True),
            'period': data.get('atr_period', 14),
            'min_ratio': Decimal(str(data.get('atr_min_ratio', '0.5'))),
        }

        # 构建 CoreConfig 模型
        return CoreConfig(
            core_symbols=data.get('core_symbols', ['BTC/USDT:USDT', 'ETH/USDT:USDT']),
            pinbar_defaults=pinbar_defaults,
            ema=ema,
            mtf_mapping=mtf_mapping_data,
            mtf_ema_period=data.get('mtf_ema_period', 60),
            warmup=warmup,
            signal_pipeline=signal_pipeline,
            atr=atr,
        )

    def _ensure_repo_initialized(self) -> None:
        """确保 Repository 已初始化"""
        if not hasattr(self._repo, '_initialized') or not self._repo._initialized:
            raise ValueError(
                "ConfigRepository not initialized. "
                "Call await repo.initialize() before using CoreConfigProvider."
            )
