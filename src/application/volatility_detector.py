"""
Volatility Detector - 波动率检测器

P0-004: 订单参数合理性检查 - 极端行情检测模块

职责:
1. 实时监控价格波动
2. 检测极端行情触发条件
3. 管理极端行情状态
4. 提供有效的价格偏差限制（正常 10%, 极端 20%）

Reference: docs/designs/p0-004-order-validation.md Section 2.6
"""
import asyncio
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Deque, Dict, TYPE_CHECKING

from src.domain.models import (
    ExtremeVolatilityConfig,
    ExtremeVolatilityStatus,
)

if TYPE_CHECKING:
    from src.infrastructure.notifier import Notifier


@dataclass
class PricePoint:
    """价格点"""
    timestamp: int  # 毫秒
    price: Decimal


class VolatilityDetector:
    """
    波动率检测器

    职责:
    1. 实时监控价格波动
    2. 检测极端行情触发条件
    3. 管理极端行情状态
    4. 提供有效的价格偏差限制
    """

    def __init__(
        self,
        config: Optional[ExtremeVolatilityConfig] = None,
        notifier: Optional["Notifier"] = None,
    ):
        """
        初始化波动率检测器

        Args:
            config: 极端行情配置（使用默认配置如果未提供）
            notifier: 通知服务（用于发送告警）
        """
        self._config = config or ExtremeVolatilityConfig()
        self._notifier = notifier
        # 每个 symbol 独立追踪价格历史
        self._price_history: Dict[str, Deque[PricePoint]] = {}
        self._status: Dict[str, ExtremeVolatilityStatus] = {}
        self._lock = asyncio.Lock()

    def _get_or_create_status(self, symbol: str) -> ExtremeVolatilityStatus:
        """获取或创建 symbol 的状态"""
        if symbol not in self._status:
            self._status[symbol] = ExtremeVolatilityStatus()
        return self._status[symbol]

    def _get_or_create_history(self, symbol: str) -> Deque[PricePoint]:
        """获取或创建 symbol 的价格历史"""
        if symbol not in self._price_history:
            self._price_history[symbol] = deque()
        return self._price_history[symbol]

    async def add_price_point(self, symbol: str, price: Decimal) -> None:
        """
        添加价格点并检测波动率

        Args:
            symbol: 币种对 (如 "BTC/USDT:USDT")
            price: 价格
        """
        async with self._lock:
            current_time = int(time.time() * 1000)
            history = self._get_or_create_history(symbol)
            history.append(PricePoint(current_time, price))

            # 清理过期数据（超出时间窗口）
            cutoff = current_time - (self._config.volatility_window_seconds * 1000)
            while history and history[0].timestamp < cutoff:
                history.popleft()

            # 检测波动率
            await self._check_volatility(symbol)

            # 检查是否恢复
            await self._check_recovery(symbol)

    async def _check_volatility(self, symbol: str) -> None:
        """
        检查价格波动率

        Args:
            symbol: 币种对
        """
        if not self._config.enabled:
            return

        history = self._get_or_create_history(symbol)
        if len(history) < 2:
            return

        # 计算时间窗口内的价格波动
        min_price = min(p.price for p in history)
        max_price = max(p.price for p in history)
        avg_price = (min_price + max_price) / 2

        if avg_price == Decimal("0"):
            return

        volatility = (max_price - min_price) / avg_price * Decimal("100")

        status = self._get_or_create_status(symbol)
        status.current_volatility = volatility

        # 判断是否触发极端行情
        if volatility >= self._config.price_volatility_threshold:
            await self._trigger_extreme(
                symbol=symbol,
                reason=f"价格波动 {volatility:.2f}% 超过阈值 {self._config.price_volatility_threshold}%"
            )

    async def _trigger_extreme(self, symbol: str, reason: str) -> None:
        """
        触发极端行情状态

        Args:
            symbol: 币种对
            reason: 触发原因
        """
        status = self._get_or_create_status(symbol)
        if status.is_extreme:
            return  # 已经触发

        current_time = int(time.time() * 1000)
        status.is_extreme = True
        status.triggered_at = current_time
        status.trigger_reason = reason
        status.recovery_at = current_time + (self._config.auto_recovery_seconds * 1000)

        # 发送通知
        if self._config.notify_on_trigger and self._notifier:
            await self._send_alert(symbol, reason)

    async def _check_recovery(self, symbol: str) -> None:
        """
        检查是否恢复正常

        Args:
            symbol: 币种对
        """
        status = self._get_or_create_status(symbol)
        if not status.is_extreme:
            return

        current_time = int(time.time() * 1000)
        if status.recovery_at and current_time >= status.recovery_at:
            # 恢复时间已到，恢复正常状态
            status.is_extreme = False
            status.triggered_at = None
            status.trigger_reason = None
            status.recovery_at = None

    async def _send_alert(self, symbol: str, reason: str) -> None:
        """
        发送极端行情告警

        Args:
            symbol: 币种对
            reason: 触发原因
        """
        if self._notifier:
            await self._notifier.send_alert(
                "极端行情告警",
                f"{symbol}: {reason}"
            )

    def get_status(self, symbol: str) -> ExtremeVolatilityStatus:
        """
        获取当前状态

        Args:
            symbol: 币种对

        Returns:
            ExtremeVolatilityStatus: 当前极端行情状态
        """
        return self._get_or_create_status(symbol)

    def get_effective_price_deviation(self, symbol: str) -> Decimal:
        """
        获取有效的价格偏差限制

        Args:
            symbol: 币种对

        Returns:
            Decimal: 有效偏差限制（正常 10%, 极端 20%）
        """
        status = self._get_or_create_status(symbol)
        if status.is_extreme:
            return self._config.relaxed_price_deviation
        return Decimal("10.0")  # 默认 10%

    def should_allow_order(self, symbol: str, is_tp_sl: bool) -> bool:
        """
        判断是否允许下单

        Args:
            symbol: 币种对
            is_tp_sl: 是否为 TP/SL 订单（止盈止损单）

        Returns:
            bool: 是否允许下单
        """
        status = self._get_or_create_status(symbol)
        if not status.is_extreme:
            return True

        # 根据配置决定是否仅允许 TP/SL 订单
        if self._config.allow_only_tp_sl:
            return is_tp_sl

        # 根据行为配置决定
        if self._config.action_on_trigger == "pause_all":
            return False

        return True

    def is_extreme_volatility(self, symbol: str) -> bool:
        """
        检查是否处于极端行情

        Args:
            symbol: 币种对

        Returns:
            bool: 是否处于极端行情
        """
        status = self._get_or_create_status(symbol)
        return status.is_extreme

    def get_current_volatility(self, symbol: str) -> Decimal:
        """
        获取当前波动率

        Args:
            symbol: 币种对

        Returns:
            Decimal: 当前波动率百分比
        """
        status = self._get_or_create_status(symbol)
        return status.current_volatility

    def reset(self, symbol: Optional[str] = None) -> None:
        """
        重置状态

        Args:
            symbol: 币种对（可选，不指定则重置所有）
        """
        if symbol:
            if symbol in self._status:
                self._status[symbol] = ExtremeVolatilityStatus()
            if symbol in self._price_history:
                self._price_history[symbol].clear()
        else:
            self._status.clear()
            self._price_history.clear()
