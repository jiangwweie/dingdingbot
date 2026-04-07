"""
缓存 Provider 基类

本模块实现带 TTL 缓存的 Provider 基类，子类继承后自动获得缓存能力。

设计文档：docs/arch/P1-5-provider-registration-design.md
QA 审查：docs/reviews/p1_5_provider_design_qa_review.md

关键修复 (QA P1):
- 注入时钟依赖 (ClockProtocol)，解决测试时无法验证 TTL 过期逻辑的问题
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Protocol

from .base import ConfigProvider


class ClockProtocol(Protocol):
    """
    时钟协议接口 - 用于依赖注入，使 TTL 测试可控制

    使用示例:
        # 生产环境使用系统时钟
        provider = CachedProvider(clock=SystemClock())

        # 测试环境使用模拟时钟
        mock_clock = MockClock(fixed_time=datetime(2026, 4, 7, 10, 0, 0))
        provider = CachedProvider(clock=mock_clock)

        # 推进时间验证 TTL 过期
        mock_clock.advance(300)  # 推进 5 分钟
    """

    def now(self) -> datetime:
        """返回当前时间"""
        ...


class SystemClock:
    """系统时钟实现 - 返回真实时间"""

    def now(self) -> datetime:
        """返回当前系统时间"""
        return datetime.now()


class MockClock:
    """
    模拟时钟 - 用于测试时控制时间

    使用示例:
        mock_clock = MockClock(datetime(2026, 4, 7, 10, 0, 0))
        provider = TestProvider(clock=mock_clock)

        # 推进时间验证 TTL 过期
        mock_clock.advance(300)  # 推进 5 分钟
    """

    def __init__(self, fixed_time: datetime = None) -> None:
        """
        Args:
            fixed_time: 固定的模拟时间，None 表示使用当前时间
        """
        self._fixed_time = fixed_time or datetime.now()

    def now(self) -> datetime:
        """返回当前模拟时间"""
        return self._fixed_time

    def advance(self, seconds: int) -> None:
        """
        推进时间（用于测试 TTL 过期）

        Args:
            seconds: 推进的秒数
        """
        self._fixed_time += timedelta(seconds=seconds)


class CachedProvider:
    """
    带缓存的 Provider 基类

    提供 TTL 缓存机制，子类继承后自动获得缓存能力。

    特性:
    - TTL 缓存，支持自定义过期时间
    - 时钟抽象注入，测试时可模拟时间
    - 手动缓存失效机制

    使用示例:
        class CoreConfigProvider(CachedProvider):
            async def get(self, key: Optional[str] = None) -> Any:
                # 尝试从缓存获取
                cache_key = key or '__all__'
                cached = self._get_cached(cache_key)
                if cached is not None:
                    return cached

                # 从数据源加载
                data = await self._load_from_source()

                # 写入缓存
                self._set_cached(cache_key, data)
                return data

            async def update(self, key: str, value: Any) -> None:
                await self._save_to_source(key, value)
                self._invalidate_cache(key)

            async def refresh(self) -> None:
                self._invalidate_cache()
    """

    CACHE_TTL_SECONDS = 300  # 5 分钟默认 TTL

    def __init__(self, clock: ClockProtocol = None) -> None:
        """
        Args:
            clock: 时钟实现，默认使用 SystemClock
                   测试时可注入 MockClock 控制时间
        """
        self._clock = clock or SystemClock()
        self._cache: Dict[str, tuple[Any, datetime]] = {}

    @property
    def cache_ttl(self) -> int:
        """缓存 TTL（秒），0 表示不缓存"""
        return self.CACHE_TTL_SECONDS

    def _get_cached(self, key: str) -> Optional[Any]:
        """
        获取缓存值，过期则返回 None

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]

        # 使用注入的时钟检查是否过期
        if self._clock.now() > expires_at:
            del self._cache[key]
            return None

        return value

    def _set_cached(self, key: str, value: Any) -> None:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
        """
        # 使用注入的时钟计算过期时间
        expires_at = self._clock.now() + timedelta(seconds=self.cache_ttl)
        self._cache[key] = (value, expires_at)

    def _invalidate_cache(self, key: Optional[str] = None) -> None:
        """
        使缓存失效

        Args:
            key: 指定键，None 表示清空全部缓存
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)
