"""
Capital Protection Manager - 资金保护管理器

Phase 5: 实盘集成 - 资金保护管理器
负责下单前检查资金限制，确保交易安全。

Reference: docs/designs/phase5-detailed-design.md Section 3.4
"""
import asyncio
import threading
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from src.domain.models import (
    OrderType,
    OrderCheckResult,
    DailyTradeStats,
    CapitalProtectionConfig,
)
from src.domain.exceptions import FatalStartupError
from src.infrastructure.logger import logger

# Avoid circular imports
if TYPE_CHECKING:
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.notifier import Notifier


class CapitalProtectionManager:
    """
    资金保护管理器

    职责:
    1. 下单前资金检查（单笔损失、仓位占比、每日亏损、交易次数、最低余额）
    2. 每日交易统计追踪
    3. 市价单价格预估（G-002 修复）

    检查项:
    | 检查项 | 公式 | 限制 |
    |--------|------|------|
    | 单笔最大损失 | amount * (price - stop_loss) | 2% of balance |
    | 单次最大仓位 | amount * price | 20% of balance |
    | 每日最大亏损 | daily_stats.realized_pnl | 5% of balance |
    | 每日交易次数 | daily_stats.trade_count | 50 次 |
    | 最低余额 | balance | 100 USDT |
    """

    def __init__(
        self,
        config: CapitalProtectionConfig,
        account_service: "AccountService",
        notifier: "Notifier",
        gateway: "ExchangeGateway",
    ):
        """
        初始化资金保护管理器

        Args:
            config: 资金保护配置
            account_service: 账户服务（用于获取余额）
            notifier: 通知服务（用于告警）
            gateway: 交易所网关（G-002 修复：用于获取盘口价）
        """
        self._config = config
        self._account = account_service
        self._notifier = notifier
        self._gateway = gateway
        self._daily_stats = DailyTradeStats()
        self._stats_lock = threading.Lock()  # 使用同步锁避免事件循环问题

    async def pre_order_check(
        self,
        symbol: str,
        order_type: OrderType,
        amount: Decimal,
        price: Optional[Decimal],       # G-002 修复：可选参数
        trigger_price: Optional[Decimal],
        stop_loss: Decimal,
    ) -> OrderCheckResult:
        """
        下单前资金检查

        G-002 修复核心:
        - 市价单价格获取逻辑
        - MARKET: 调用 fetch_ticker_price
        - STOP_MARKET: 使用 trigger_price

        Args:
            symbol: 币种对
            order_type: 订单类型
            amount: 数量
            price: 限价单价格（可选）
            trigger_price: 条件单触发价
            stop_loss: 止损价格

        Returns:
            OrderCheckResult: 检查结果
        """
        # 获取账户余额
        balance = await self._get_balance()
        if balance is None:
            return OrderCheckResult(
                allowed=False,
                reason="CANNOT_GET_BALANCE",
                reason_message="无法获取账户余额"
            )

        # ========== G-002 修复：市价单价格获取 ==========
        effective_price = price
        if effective_price is None:
            if order_type == OrderType.MARKET:
                # 获取最新盘口价作为预估执行价
                effective_price = await self._gateway.fetch_ticker_price(symbol)
                if effective_price is None:
                    return OrderCheckResult(
                        allowed=False,
                        reason="CANNOT_ESTIMATE_MARKET_PRICE",
                        reason_message="无法获取市价预估价格"
                    )
            elif order_type == OrderType.STOP_MARKET:
                # 条件单使用触发价作为预估
                effective_price = trigger_price
                if effective_price is None:
                    return OrderCheckResult(
                        allowed=False,
                        reason="MISSING_TRIGGER_PRICE",
                        reason_message="STOP_MARKET 订单缺少触发价"
                    )
            else:
                # 限价单必须有价格
                return OrderCheckResult(
                    allowed=False,
                    reason="MISSING_PRICE",
                    reason_message="LIMIT 订单必须指定价格"
                )

        # ========== 检查 1: 单笔最大损失 ==========
        single_trade_check, estimated_loss, max_allowed_loss = await self._check_single_trade_loss(
            amount=amount,
            price=effective_price,
            stop_loss=stop_loss,
            balance=balance
        )
        if not single_trade_check:
            await self._notifier.send_alert(
                "单笔交易损失超限",
                f"预计损失 {estimated_loss:.2f} > 限制 {max_allowed_loss:.2f} USDT"
            )
            return OrderCheckResult(
                allowed=False,
                reason="SINGLE_TRADE_LOSS_LIMIT",
                reason_message=f"单笔损失超限：预计 {estimated_loss:.2f} USDT > 限制 {max_allowed_loss:.2f} USDT",
                single_trade_check=False,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
            )

        # ========== 检查 2: 单次最大仓位 ==========
        position_limit_check, position_value, max_allowed_position = self._check_position_limit(
            amount=amount,
            price=effective_price,
            balance=balance
        )
        if not position_limit_check:
            return OrderCheckResult(
                allowed=False,
                reason="POSITION_LIMIT",
                reason_message=f"仓位占比超限：{position_value:.2f} USDT > 限制 {max_allowed_position:.2f} USDT",
                single_trade_check=True,
                position_limit_check=False,
                position_value=position_value,
                max_allowed_position=max_allowed_position,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
            )

        # ========== 检查 3: 每日最大亏损 ==========
        daily_loss_check, daily_pnl = await self._check_daily_loss(balance)
        if not daily_loss_check:
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_LOSS_LIMIT",
                reason_message=f"每日亏损超限：当日已亏损 {abs(daily_pnl):.2f} USDT",
                single_trade_check=True,
                position_limit_check=True,
                daily_loss_check=False,
                daily_pnl=daily_pnl,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
                position_value=position_value,
                max_allowed_position=max_allowed_position,
            )

        # ========== 检查 4: 每日交易次数 ==========
        daily_count_check, daily_trade_count = self._check_daily_trade_count()
        if not daily_count_check:
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_TRADE_COUNT_LIMIT",
                reason_message=f"每日交易次数超限：当日已交易 {daily_trade_count} 次",
                single_trade_check=True,
                position_limit_check=True,
                daily_loss_check=True,
                daily_count_check=False,
                daily_trade_count=daily_trade_count,
                daily_pnl=daily_pnl,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
                position_value=position_value,
                max_allowed_position=max_allowed_position,
            )

        # ========== 检查 5: 最低余额 ==========
        balance_check, available_balance, min_required_balance = self._check_min_balance(balance)
        if not balance_check:
            return OrderCheckResult(
                allowed=False,
                reason="INSUFFICIENT_BALANCE",
                reason_message=f"账户余额不足：{available_balance:.2f} USDT < 最低要求 {min_required_balance:.2f} USDT",
                single_trade_check=True,
                position_limit_check=True,
                daily_loss_check=True,
                daily_count_check=True,
                balance_check=False,
                available_balance=available_balance,
                min_required_balance=min_required_balance,
                daily_trade_count=daily_trade_count,
                daily_pnl=daily_pnl,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
                position_value=position_value,
                max_allowed_position=max_allowed_position,
            )

        # 所有检查通过
        return OrderCheckResult(
            allowed=True,
            reason=None,
            reason_message="所有检查通过，允许下单",
            single_trade_check=True,
            position_limit_check=True,
            daily_loss_check=True,
            daily_count_check=True,
            balance_check=True,
            estimated_loss=estimated_loss,
            max_allowed_loss=max_allowed_loss,
            position_value=position_value,
            max_allowed_position=max_allowed_position,
            daily_pnl=daily_pnl,
            daily_trade_count=daily_trade_count,
            available_balance=available_balance,
            min_required_balance=min_required_balance,
        )

    async def _check_single_trade_loss(
        self,
        amount: Decimal,
        price: Decimal,
        stop_loss: Decimal,
        balance: Decimal,
    ) -> tuple[bool, Decimal, Decimal]:
        """
        检查单笔最大损失

        公式：estimated_loss = amount * |price - stop_loss|
        限制：estimated_loss <= balance * (max_loss_percent / 100)

        Returns:
            (passed, estimated_loss, max_allowed_loss)
        """
        # 计算预计损失
        estimated_loss = abs(amount * (price - stop_loss))

        # 计算最大允许损失
        max_loss_percent = Decimal(str(self._config.single_trade["max_loss_percent"]))
        max_allowed_loss = balance * (max_loss_percent / Decimal("100"))

        passed = estimated_loss <= max_allowed_loss
        return passed, estimated_loss, max_allowed_loss

    def _check_position_limit(
        self,
        amount: Decimal,
        price: Decimal,
        balance: Decimal,
    ) -> tuple[bool, Decimal, Decimal]:
        """
        检查单次最大仓位

        公式：position_value = amount * price
        限制：position_value <= balance * (max_position_percent / 100)

        Returns:
            (passed, position_value, max_allowed_position)
        """
        # 计算仓位价值
        position_value = amount * price

        # 计算最大允许仓位
        max_position_percent = Decimal(str(self._config.single_trade["max_position_percent"]))
        max_allowed_position = balance * (max_position_percent / Decimal("100"))

        passed = position_value <= max_allowed_position
        return passed, position_value, max_allowed_position

    async def _check_daily_loss(self, balance: Decimal) -> tuple[bool, Decimal]:
        """
        检查每日最大亏损

        公式：daily_pnl = daily_stats.realized_pnl
        限制：daily_pnl >= -balance * (max_loss_percent / 100)

        Returns:
            (passed, daily_pnl)
        """
        with self._stats_lock:
            daily_pnl = self._daily_stats.realized_pnl

        # 计算每日最大允许亏损
        max_loss_percent = Decimal(str(self._config.daily["max_loss_percent"]))
        max_daily_loss = balance * (max_loss_percent / Decimal("100"))

        passed = daily_pnl >= -max_daily_loss
        return passed, daily_pnl

    def _check_daily_trade_count(self) -> tuple[bool, int]:
        """
        检查每日交易次数

        限制：trade_count < max_trade_count

        Returns:
            (passed, trade_count)
        """
        with self._stats_lock:
            trade_count = self._daily_stats.trade_count

        max_trade_count = self._config.daily["max_trade_count"]

        passed = trade_count < max_trade_count
        return passed, trade_count

    def _check_min_balance(self, balance: Decimal) -> tuple[bool, Decimal, Decimal]:
        """
        检查最低余额

        限制：balance >= min_balance

        Returns:
            (passed, available_balance, min_required_balance)
        """
        min_balance = Decimal(str(self._config.account["min_balance"]))
        passed = balance >= min_balance
        return passed, balance, min_balance

    async def _get_balance(self) -> Optional[Decimal]:
        """
        获取账户可用余额

        Returns:
            Decimal: 可用余额，None 表示获取失败
        """
        try:
            # 调用账户服务的 get_balance 方法
            if hasattr(self._account, 'get_balance'):
                balance = await self._account.get_balance()
                return balance
            elif hasattr(self._account, 'available_balance'):
                # 如果 account_service 是 Account 对象
                return self._account.available_balance
            else:
                logger.error("Account service does not have get_balance method")
                return None
        except Exception as e:
            logger.error(f"获取账户余额失败：{e}")
            return None

    def record_trade(self, realized_pnl: Decimal) -> None:
        """
        记录交易，更新每日统计

        Args:
            realized_pnl: 已实现盈亏（正数为盈利，负数为亏损）
        """
        with self._stats_lock:
            self._daily_stats.trade_count += 1
            self._daily_stats.realized_pnl += realized_pnl
            logger.info(f"交易记录更新：次数={self._daily_stats.trade_count}, 盈亏={self._daily_stats.realized_pnl:.2f} USDT")

    def reset_if_new_day(self) -> None:
        """
        如果是新的一天，重置统计

        每日重置逻辑：
        - trade_count = 0
        - realized_pnl = 0
        - last_reset_date = today
        """
        today = datetime.now(timezone.utc).date().isoformat()

        with self._stats_lock:
            if today != self._daily_stats.last_reset_date:
                old_date = self._daily_stats.last_reset_date
                self._daily_stats.trade_count = 0
                self._daily_stats.realized_pnl = Decimal("0")
                self._daily_stats.last_reset_date = today
                logger.info(f"每日统计已重置：{old_date} -> {today}")

    def get_daily_stats(self) -> DailyTradeStats:
        """
        获取每日统计

        Returns:
            DailyTradeStats: 当前统计信息
        """
        with self._stats_lock:
            return self._daily_stats.model_copy()


class AccountService:
    """
    账户服务接口（用于解耦）

    实际使用时，应该注入真实的账户服务实现
    """

    async def get_balance(self) -> Decimal:
        """
        获取可用余额

        Returns:
            Decimal: 可用余额 (USDT)
        """
        raise NotImplementedError("Subclasses must implement get_balance")


class BinanceAccountService(AccountService):
    """
    基于 ExchangeGateway 的真实账户服务实现

    用于全链路集成测试和生产环境
    """

    def __init__(self, gateway: "ExchangeGateway"):
        """
        初始化账户服务

        Args:
            gateway: ExchangeGateway 实例
        """
        self._gateway = gateway

    async def get_balance(self) -> Decimal:
        """
        获取 USDT 可用余额

        Returns:
            Decimal: USDT 可用余额
        """
        balance = await self._gateway.rest_exchange.fetch_balance()
        usdt_balance = balance.get("USDT", {})
        # 返回可用余额（free），而非总余额（total）
        return Decimal(str(usdt_balance.get("free", 0)))
