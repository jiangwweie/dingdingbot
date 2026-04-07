"""
UserConfig Provider - 用户配置提供者

本模块实现 UserConfigProvider，负责从 ConfigRepository 加载用户配置。

设计文档：docs/arch/P1-5-provider-registration-design.md
"""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from src.application.config.config_repository import ConfigRepository
from src.application.config.models import UserConfig, RiskConfig, StrategyDefinition

from .cached_provider import CachedProvider, ClockProtocol, SystemClock


class UserConfigProvider(CachedProvider):
    """
    用户配置 Provider

    职责:
    - 从 ConfigRepository 加载用户配置
    - 提供 TTL 缓存机制 (默认 300 秒)
    - 支持配置更新操作

    使用示例:
        repo = ConfigRepository()
        await repo.initialize()

        provider = UserConfigProvider(repo)
        user_config = await provider.get()
        symbols = await provider.get('user_symbols')
    """

    CACHE_TTL_SECONDS = 300  # 5 分钟缓存

    def __init__(
        self,
        repo: ConfigRepository,
        clock: ClockProtocol = None
    ) -> None:
        """
        初始化 UserConfigProvider

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
        获取用户配置数据

        Args:
            key: 配置键，None 表示获取全部配置

        Returns:
            配置值或 UserConfig 模型

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
            # 支持嵌套键访问，如 'exchange.api_key'
            return self._get_nested_value(cached, key)

        # 从数据源加载
        config = await self._fetch_data()

        # 写入缓存
        self._set_cached('__all__', config)

        if key:
            return self._get_nested_value(config, key)
        return config

    async def update(self, key: str, value: Any) -> None:
        """
        更新用户配置

        Args:
            key: 配置键 (支持嵌套键，如 'exchange.api_key')
            value: 新值

        Raises:
            ValueError: 配置未初始化
        """
        self._ensure_repo_initialized()

        # 保存到数据源
        await self._repo.update_user_config_item(key, value)

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

    async def _fetch_data(self) -> UserConfig:
        """
        从 ConfigRepository 获取用户配置数据

        Returns:
            UserConfig 模型实例
        """
        # 从 Repository 获取用户配置字典
        data = await self._repo.get_user_config_dict()

        # 转换为 Pydantic 模型
        return self._build_user_config(data)

    def _build_user_config(self, data: Dict[str, Any]) -> UserConfig:
        """
        将字典数据转换为 UserConfig 模型

        Args:
            data: 原始配置字典

        Returns:
            UserConfig 模型实例

        Note:
            所有 Decimal 字段使用 Decimal(str(value)) 转换，避免 float 精度损失
        """
        # 构建 ExchangeConfig
        exchange_data = data.get('exchange', {})
        exchange = {
            'name': exchange_data.get('name', 'binance'),
            'api_key': exchange_data.get('api_key', ''),
            'api_secret': exchange_data.get('api_secret', ''),
            'testnet': exchange_data.get('testnet', True),
        }

        # 构建 RiskConfig
        risk_data = data.get('risk', {})
        risk = {
            'max_loss_percent': Decimal(str(risk_data.get('max_loss_percent', '0.01'))),
            'max_leverage': risk_data.get('max_leverage', 20),
            'max_total_exposure': Decimal(str(risk_data.get('max_total_exposure', '0.8'))),
            'daily_max_trades': risk_data.get('daily_max_trades'),
            'daily_max_loss': Decimal(str(risk_data['daily_max_loss'])) if risk_data.get('daily_max_loss') else None,
            'max_position_hold_time': risk_data.get('max_position_hold_time'),
        }

        # 构建 NotificationConfig
        notification_data = data.get('notification', {})
        channels_data = notification_data.get('channels', [])
        channels = []
        for ch in channels_data:
            channels.append({
                'type': ch.get('type', 'feishu'),
                'webhook_url': ch.get('webhook_url', ''),
            })
        notification = {
            'channels': channels,
        }

        # 构建 active_strategies
        strategies_data = data.get('active_strategies', [])
        active_strategies = []
        for s in strategies_data:
            if isinstance(s, dict):
                active_strategies.append(StrategyDefinition(**s))
            elif isinstance(s, StrategyDefinition):
                active_strategies.append(s)

        # 构建 MTF 映射
        mtf_mapping_data = data.get('mtf_mapping', {
            "15m": "1h",
            "1h": "4h",
            "4h": "1d",
            "1d": "1w",
        })

        # 构建 UserConfig 模型
        return UserConfig(
            exchange=exchange,
            user_symbols=data.get('user_symbols', []),
            timeframes=data.get('timeframes', ['15m', '1h', '4h']),
            active_strategies=active_strategies,
            strategy=data.get('strategy'),
            risk=risk,
            asset_polling={
                'interval_seconds': data.get('asset_polling_interval', 60),
            },
            notification=notification,
            mtf_ema_period=data.get('mtf_ema_period', 60),
            mtf_mapping=mtf_mapping_data,
        )

    def _get_nested_value(self, obj: Any, key: str) -> Any:
        """
        获取嵌套值（支持点分隔键）

        Args:
            obj: 对象或字典
            key: 键（支持 'exchange.api_key' 格式）

        Returns:
            嵌套值，如果不存在返回 None
        """
        if '.' not in key:
            if isinstance(obj, dict):
                return obj.get(key)
            elif hasattr(obj, key):
                return getattr(obj, key)
            return None

        # 嵌套键访问
        keys = key.split('.')
        current = obj
        for k in keys:
            if isinstance(current, dict):
                current = current.get(k)
            elif hasattr(current, k):
                current = getattr(current, k)
            else:
                return None
        return current

    def _ensure_repo_initialized(self) -> None:
        """确保 Repository 已初始化"""
        if not hasattr(self._repo, '_initialized') or not self._repo._initialized:
            raise ValueError(
                "ConfigRepository not initialized. "
                "Call await repo.initialize() before using UserConfigProvider."
            )
