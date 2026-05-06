"""
Capital Protection Manager - 资金保护管理器

Phase 5: 实盘集成 - 资金保护管理器
负责下单前检查资金限制，确保交易安全。

Reference: docs/designs/phase5-detailed-design.md Section 3.4

P0-004: 订单参数合理性检查
- 最小订单金额检查（防止粉尘订单）
- 价格合理性检查（防止异常价格订单）
- 极端行情检测与放宽逻辑（波动率检测）
"""
import asyncio
import time
from datetime import datetime, timezone, date
from decimal import Decimal, localcontext
from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from src.application.decision_trace import TraceService
from src.domain.models import (
    OrderType,
    OrderCheckResult,
    DailyTradeStats,
    CapitalProtectionConfig,
    ExtremeVolatilityConfig,
    ExtremeVolatilityStatus,
)
from src.domain.exceptions import FatalStartupError
from src.infrastructure.logger import logger
from src.infrastructure.repository_ports import (
    DailyRiskStatsEvent,
    DailyRiskStatsRepositoryPort,
    DailyRiskStatsSnapshot,
)
from src.application.volatility_detector import VolatilityDetector
from src.application.account_service import AccountService, BinanceAccountService

# Avoid circular imports
if TYPE_CHECKING:
    from src.infrastructure.exchange_gateway import ExchangeGateway
    from src.infrastructure.notifier import Notifier


DAILY_RISK_STATS_SCOPE_KEY = "runtime:default"
DAILY_RISK_STATS_UNAVAILABLE_REASON = "DAILY_RISK_STATS_UNAVAILABLE"
DAILY_RISK_STATS_UNAVAILABLE_MESSAGE = (
    "daily risk stats persistence is unavailable; new entries are blocked"
)
DAILY_RISK_STATS_DECIMAL_QUANT = Decimal("0.000000000000000001")


def normalize_daily_risk_decimal(value: Decimal) -> str:
    """Return a stable Decimal string for daily risk idempotency keys."""
    with localcontext() as context:
        context.prec = 50
        quantized = value.quantize(DAILY_RISK_STATS_DECIMAL_QUANT)
    if quantized == Decimal("0"):
        return "0"
    return format(quantized.normalize(), "f")


class CapitalProtectionManager:
    """
    资金保护管理器

    职责:
    1. 下单前资金检查（单笔损失、仓位占比、每日亏损、交易次数、最低余额）
    2. 每日交易统计追踪
    3. 市价单价格预估（G-002 修复）
    4. 订单参数合理性检查（P0-004：最小名义价值、价格偏差）
    5. 极端行情检测与放宽逻辑（波动率检测）

    检查项:
    | 检查项 | 公式 | 限制 |
    |--------|------|------|
    | 最小名义价值 | quantity * price | ≥ 5 USDT (Binance) |
    | 价格偏差 | |price - ticker| / ticker | ≤ 10% (极端行情≤20%) |
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
        volatility_detector: Optional[VolatilityDetector] = None,
        trace_service: Optional[TraceService] = None,
        config_hash: Optional[str] = None,
        daily_stats_repository: Optional[DailyRiskStatsRepositoryPort] = None,
        daily_stats_scope_key: str = DAILY_RISK_STATS_SCOPE_KEY,
        restored_daily_stats: Optional[DailyRiskStatsSnapshot] = None,
        daily_stats_persistence_required: bool = False,
        daily_stats_persistence_available: bool = True,
    ):
        """
        初始化资金保护管理器

        Args:
            config: 资金保护配置
            account_service: 账户服务（用于获取余额）
            notifier: 通知服务（用于告警）
            gateway: 交易所网关（G-002 修复：用于获取盘口价）
            volatility_detector: 波动率检测器（可选，用于极端行情检测）
        """
        self._config = config
        self._account = account_service
        self._notifier = notifier
        self._gateway = gateway
        self._volatility_detector = volatility_detector
        self._trace_service = trace_service
        self._config_hash = config_hash
        self._daily_stats_repository = daily_stats_repository
        self._daily_stats_scope_key = daily_stats_scope_key
        self._daily_stats_persistence_required = daily_stats_persistence_required
        self._daily_stats_persistence_available = (
            daily_stats_persistence_available
            and (
                daily_stats_repository is not None
                or not daily_stats_persistence_required
            )
        )
        # LS-002b: runtime may restore daily stats from PG aggregate. The
        # in-memory copy remains the hot-path read model used by pre-order
        # checks, with PG write-through on exit projection accounting.
        self._daily_stats = self._stats_from_snapshot(restored_daily_stats)
        self._stats_lock = asyncio.Lock()  # P0 修复：使用异步锁避免阻塞事件循环

    @staticmethod
    def _stats_from_snapshot(
        snapshot: Optional[DailyRiskStatsSnapshot],
    ) -> DailyTradeStats:
        if snapshot is None:
            return DailyTradeStats()
        return DailyTradeStats(
            trade_count=snapshot.trade_count,
            realized_pnl=snapshot.realized_pnl,
            last_reset_date=snapshot.stats_date.isoformat(),
        )

    def mark_daily_stats_persistence_unavailable(self) -> None:
        """Fail closed for future new-entry checks when persistence is unhealthy."""
        self._daily_stats_persistence_available = False

    def is_daily_stats_persistence_available(self) -> bool:
        return self._daily_stats_persistence_available

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

        P0-004 新增:
        - 最小名义价值检查（防止粉尘订单）
        - 价格合理性检查（防止异常价格订单）

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
        lifecycle_id = (
            f"capital_protection:{symbol}:{order_type.value}:{int(time.time() * 1000)}"
        )

        def finalize(result: OrderCheckResult, current_price: Optional[Decimal]) -> OrderCheckResult:
            if self._trace_service is None:
                return result

            self._trace_service.emit_risk_decision(
                lifecycle_id=lifecycle_id,
                decision="allow" if result.allowed else "deny",
                reason=result.reason,
                config_hash=self._config_hash,
                metadata={
                    "symbol": symbol,
                    "order_type": order_type.value,
                    "amount": str(amount),
                    "price": str(price) if price is not None else None,
                    "effective_price": str(current_price) if current_price is not None else None,
                    "trigger_price": str(trigger_price) if trigger_price is not None else None,
                    "stop_loss": str(stop_loss),
                    "reason_message": result.reason_message,
                    "checks": {
                        "single_trade_check": result.single_trade_check,
                        "position_limit_check": result.position_limit_check,
                        "daily_loss_check": result.daily_loss_check,
                        "daily_count_check": result.daily_count_check,
                        "balance_check": result.balance_check,
                    },
                },
            )
            return result

        await self.reset_if_new_day()

        if not self._daily_stats_persistence_available:
            logger.warning(
                "Daily risk stats persistence unavailable; denying new entry "
                "symbol=%s order_type=%s",
                symbol,
                order_type.value,
            )
            return finalize(OrderCheckResult(
                allowed=False,
                reason=DAILY_RISK_STATS_UNAVAILABLE_REASON,
                reason_message=DAILY_RISK_STATS_UNAVAILABLE_MESSAGE,
                daily_loss_check=False,
                daily_count_check=False,
            ), None)

        balance = await self._get_balance()
        if balance is None:
            return finalize(OrderCheckResult(
                allowed=False,
                reason="CANNOT_GET_BALANCE",
                reason_message="无法获取账户余额"
            ), None)

        effective_price = price
        if effective_price is None:
            if order_type == OrderType.MARKET:
                effective_price = await self._gateway.fetch_ticker_price(symbol)
                if effective_price is None:
                    return finalize(OrderCheckResult(
                        allowed=False,
                        reason="CANNOT_ESTIMATE_MARKET_PRICE",
                        reason_message="无法获取市价预估价格"
                    ), None)
            elif order_type == OrderType.STOP_MARKET:
                effective_price = trigger_price
                if effective_price is None:
                    return finalize(OrderCheckResult(
                        allowed=False,
                        reason="MISSING_TRIGGER_PRICE",
                        reason_message="STOP_MARKET 订单缺少触发价"
                    ), None)
            else:
                return finalize(OrderCheckResult(
                    allowed=False,
                    reason="MISSING_PRICE",
                    reason_message="LIMIT 订单必须指定价格"
                ), None)

        notional_check, notional_value = self._check_min_notional(
            quantity=amount,
            price=effective_price,
        )
        if not notional_check:
            logger.warning(
                f"订单名义价值过低：{notional_value:.2f} USDT < {self._config.min_notional} USDT "
                f"(symbol={symbol}, amount={amount}, price={effective_price})"
            )
            return finalize(OrderCheckResult(
                allowed=False,
                reason="BELOW_MIN_NOTIONAL",
                reason_message=f"订单名义价值 {notional_value:.2f} USDT 低于最小要求 {self._config.min_notional} USDT",
                notional_value=notional_value,
                min_notional=self._config.min_notional,
            ), effective_price)

        qty_passed, qty_reason, qty_message = await self._check_quantity_precision(
            symbol=symbol,
            quantity=amount,
        )
        if not qty_passed:
            logger.warning(
                f"订单数量精度检查失败：{qty_message} (symbol={symbol}, quantity={amount})"
            )
            return finalize(OrderCheckResult(
                allowed=False,
                reason=qty_reason,
                reason_message=qty_message,
                notional_value=notional_value,
                min_notional=self._config.min_notional,
            ), effective_price)

        if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and price is not None:
            price_check, ticker_price, deviation = await self._check_price_reasonability(
                symbol=symbol,
                order_price=price,
            )
            if not price_check:
                if ticker_price is None:
                    logger.warning(
                        f"订单价格合理性检查失败：内部依赖异常 (symbol={symbol}, order_price={price})"
                    )
                    return finalize(OrderCheckResult(
                        allowed=False,
                        reason="PRICE_REASONABILITY_CHECK_ERROR",
                        reason_message="价格合理性检查失败：内部依赖异常，live-safe 模式下拒绝下单",
                        order_price=price,
                        ticker_price=ticker_price,
                        price_deviation=deviation,
                    ), effective_price)

                logger.warning(
                    f"订单价格偏差过大：{deviation*100:.2f}% > {self._config.price_deviation_threshold*100:.0f}% "
                    f"(symbol={symbol}, order_price={price}, ticker_price={ticker_price})"
                )
                return finalize(OrderCheckResult(
                    allowed=False,
                    reason="PRICE_DEVIATION_TOO_HIGH",
                    reason_message=f"订单价格偏差 {deviation*100:.2f}% 超过阈值 {self._config.price_deviation_threshold*100:.0f}%",
                    order_price=price,
                    ticker_price=ticker_price,
                    price_deviation=deviation,
                ), effective_price)

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
            return finalize(OrderCheckResult(
                allowed=False,
                reason="SINGLE_TRADE_LOSS_LIMIT",
                reason_message=f"单笔损失超限：预计 {estimated_loss:.2f} USDT > 限制 {max_allowed_loss:.2f} USDT",
                single_trade_check=False,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
            ), effective_price)

        position_limit_check, position_value, max_allowed_position = self._check_position_limit(
            amount=amount,
            price=effective_price,
            balance=balance
        )
        if not position_limit_check:
            return finalize(OrderCheckResult(
                allowed=False,
                reason="POSITION_LIMIT",
                reason_message=f"仓位占比超限：{position_value:.2f} USDT > 限制 {max_allowed_position:.2f} USDT",
                single_trade_check=True,
                position_limit_check=False,
                position_value=position_value,
                max_allowed_position=max_allowed_position,
                estimated_loss=estimated_loss,
                max_allowed_loss=max_allowed_loss,
            ), effective_price)

        daily_loss_check, daily_pnl = await self._check_daily_loss(balance)
        if not daily_loss_check:
            return finalize(OrderCheckResult(
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
            ), effective_price)

        daily_count_check, daily_trade_count = await self._check_daily_trade_count()
        if not daily_count_check:
            return finalize(OrderCheckResult(
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
            ), effective_price)

        balance_check, available_balance, min_required_balance = self._check_min_balance(balance)
        if not balance_check:
            return finalize(OrderCheckResult(
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
            ), effective_price)

        return finalize(OrderCheckResult(
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
            notional_value=notional_value,
            min_notional=self._config.min_notional,
        ), effective_price)

    def _check_min_notional(
        self,
        quantity: Decimal,
        price: Decimal,
    ) -> tuple[bool, Decimal]:
        """
        检查最小名义价值（P0-004）

        公式：notional_value = quantity * price
        限制：notional_value >= MIN_NOTIONAL (5 USDT)

        Binance 规则:
        - NOTIONAL: 名义价值 ≥ 5 USDT (部分币种 100 USDT)
        - LOT_SIZE: 数量精度限制
        - PRICE_FILTER: 价格精度限制

        Args:
            quantity: 订单数量
            price: 订单价格

        Returns:
            (passed, notional_value)
        """
        notional_value = quantity * price
        passed = notional_value >= self._config.min_notional
        return passed, notional_value

    async def _check_quantity_precision(
        self,
        symbol: str,
        quantity: Decimal,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """
        检查数量精度（P0-004）

        规则:
        - 数量不能小于最小交易量
        - 数量精度不能超过交易所允许的小数位数
        - 数量必须是 step_size 的整数倍

        Args:
            symbol: 币种对
            quantity: 订单数量

        Returns:
            (passed, reason_code, reason_message)
            - passed: 是否通过检查
            - reason_code: 拒绝原因代码（如果失败）
            - reason_message: 拒绝原因描述（如果失败）
        """
        try:
            # 获取交易对精度信息
            market_info = await self._gateway.get_market_info(symbol)

            min_quantity = market_info.get('min_quantity', Decimal("0"))
            quantity_precision = market_info.get('quantity_precision', 6)
            step_size = market_info.get('step_size', Decimal("0"))

            # 检查 1: 最小交易量
            if quantity < min_quantity:
                logger.warning(
                    f"订单数量过小：{quantity} < {min_quantity} (symbol={symbol})"
                )
                return (
                    False,
                    "BELOW_MIN_QUANTITY",
                    f"订单数量 {quantity} 小于最小限制 {min_quantity}"
                )

            # 检查 2: 数量精度
            # quantity_precision 可能是小数位数（int）或 step_size（Decimal），需要区分处理
            if isinstance(quantity_precision, Decimal):
                # 如果 quantity_precision 是 Decimal（如 0.0001），则是 step_size，使用 step_size 检查
                if step_size and step_size > Decimal("0"):
                    remainder = quantity % step_size
                    if remainder != Decimal("0") and remainder > Decimal("1e-10"):
                        logger.warning(
                            f"订单数量不是 step_size 的整数倍：quantity={quantity}, step_size={step_size}, remainder={remainder}"
                        )
                        return (
                            False,
                            "QUANTITY_NOT_MULTIPLE_OF_STEP",
                            f"订单数量 {quantity} 不是 step_size {step_size} 的整数倍"
                        )
            elif isinstance(quantity_precision, int):
                # 如果 quantity_precision 是整数（如 4），则是小数位数
                quantity_str = str(quantity)
                if '.' in quantity_str:
                    decimals = len(quantity_str.split('.')[1])
                    if decimals > quantity_precision:
                        logger.warning(
                            f"订单数量精度超限：{decimals} > {quantity_precision} (symbol={symbol}, quantity={quantity})"
                        )
                        return (
                            False,
                            "QUANTITY_PRECISION_EXCEEDED",
                            f"订单数量精度 {decimals} 超过最大允许 {quantity_precision}"
                        )

            # 检查 3: step_size 整除性（如果 step_size > 0 且未在上述检查）
            if step_size and step_size > Decimal("0") and not isinstance(quantity_precision, Decimal):
                remainder = quantity % step_size
                # 使用一个小的容差值来处理浮点数精度问题
                if remainder != Decimal("0") and remainder > Decimal("1e-10"):
                    # 调整为 step_size 的整数倍
                    adjusted_qty = (quantity // step_size) * step_size
                    logger.warning(
                        f"订单数量不是 step_size 的整数倍：{quantity} % {step_size} = {remainder} "
                        f"(symbol={symbol}, adjusted={adjusted_qty})"
                    )
                    return (
                        False,
                        "QUANTITY_NOT_MULTIPLE_OF_STEP",
                        f"订单数量 {quantity} 不是步长 {step_size} 的整数倍，建议调整为 {adjusted_qty}"
                    )

            # 所有检查通过
            return True, None, None

        except Exception as e:
            logger.error(f"数量精度检查失败：{e} (symbol={symbol}, quantity={quantity})")
            return (
                False,
                "QUANTITY_PRECISION_CHECK_ERROR",
                "数量精度检查失败：内部依赖异常，live-safe 模式下拒绝下单"
            )

    async def _check_price_reasonability(
        self,
        symbol: str,
        order_price: Decimal,
        is_tp_sl: bool = False,
    ) -> tuple[bool, Optional[Decimal], Decimal]:
        """
        检查价格合理性（P0-004）

        公式：deviation = |order_price - ticker_price| / ticker_price
        限制：
        - 正常行情：deviation <= 10%
        - 极端行情：deviation <= 20%（放宽）

        参考价格:
        - 最新 ticker 价格
        - 盘口中间价 (bid + ask) / 2

        Args:
            symbol: 币种对
            order_price: 订单价格
            is_tp_sl: 是否为 TP/SL 订单（极端行情下可能允许）

        Returns:
            (passed, ticker_price, deviation)
        """
        try:
            # 获取 ticker 价格
            ticker_price = await self._gateway.fetch_ticker_price(symbol)
            if ticker_price is None or ticker_price == Decimal("0"):
                # 无法获取 ticker 价格，跳过检查（记录警告但不拒绝订单）
                logger.warning(f"无法获取 ticker 价格，跳过价格合理性检查 (symbol={symbol})")
                return True, None, Decimal("0")

            # 计算偏差
            deviation = abs(order_price - ticker_price) / ticker_price

            # 获取有效的偏差阈值（考虑极端行情）
            if self._volatility_detector:
                # 添加价格点到波动率检测器
                await self._volatility_detector.add_price_point(symbol, ticker_price)
                # 获取有效阈值（10% 或 20%）
                effective_threshold = self._volatility_detector.get_effective_price_deviation(symbol) / Decimal("100")

                # 检查是否允许下单（极端行情下可能暂停非 TP/SL 订单）
                if not self._volatility_detector.should_allow_order(symbol, is_tp_sl):
                    logger.warning(f"极端行情下暂停下单：{symbol}")
                    return False, ticker_price, deviation
            else:
                effective_threshold = self._config.price_deviation_threshold

            # 检查是否超过阈值
            passed = deviation <= effective_threshold
            return passed, ticker_price, deviation

        except Exception as e:
            logger.error(f"价格合理性检查失败：{e} (symbol={symbol}, order_price={order_price})")
            return False, None, Decimal("0")

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
        限制：
        - 优先使用 max_loss_amount: daily_pnl >= -max_loss_amount
        - 否则使用百分比: daily_pnl >= -balance * (max_loss_percent / 100)

        Returns:
            (passed, daily_pnl)
        """
        async with self._stats_lock:
            daily_pnl = self._daily_stats.realized_pnl

        # 优先使用显式金额上限；否则回退到百分比口径
        max_loss_amount = self._config.daily.get("max_loss_amount")
        if max_loss_amount is not None:
            max_daily_loss = Decimal(str(max_loss_amount))
        else:
            max_loss_percent = Decimal(str(self._config.daily["max_loss_percent"]))
            max_daily_loss = balance * (max_loss_percent / Decimal("100"))

        passed = daily_pnl >= -max_daily_loss
        return passed, daily_pnl

    async def _check_daily_trade_count(self) -> tuple[bool, int]:
        """
        检查每日交易次数

        限制：trade_count < max_trade_count

        Returns:
            (passed, trade_count)
        """
        async with self._stats_lock:
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

    async def record_projected_realized_pnl_delta(self, realized_pnl_delta: Decimal) -> None:
        """
        记录 projected realized PnL 增量。

        LS-002 v0:
        - 使用 runtime position projection 口径
        - 不是完整账户真实日亏
        - 使用 UTC 日切
        - runtime 重启后会归零（内存态已知限制）

        Args:
            realized_pnl_delta: 本次 exit delta 的 projected realized PnL
        """
        if realized_pnl_delta == Decimal("0"):
            return

        await self.reset_if_new_day()
        async with self._stats_lock:
            self._daily_stats.realized_pnl += realized_pnl_delta
            logger.info(
                "每日 projected realized PnL 更新：delta=%s, cumulative=%s USDT",
                realized_pnl_delta,
                self._daily_stats.realized_pnl,
            )

    async def record_closed_trade(self) -> None:
        """
        记录一次完整关闭的 position lifecycle。

        LS-002 v0:
        - 只有 position 首次 full close 时才增加 trade_count
        - partial TP / partial SL 不计为新的 daily trade
        - 使用 UTC 日切
        """
        await self.reset_if_new_day()
        async with self._stats_lock:
            self._daily_stats.trade_count += 1
            logger.info("每日完整平仓计数更新：trade_count=%s", self._daily_stats.trade_count)

    async def record_exit_projection(
        self,
        *,
        position_id: str,
        signal_id: str,
        exit_order_id: str,
        delta_exit_qty: Decimal,
        projected_exit_qty_after: Decimal,
        delta_realized_pnl: Decimal,
        just_closed: bool,
        occurred_at: Optional[datetime] = None,
    ) -> None:
        """Record one LS-002 exit projection delta through the daily stats boundary."""
        if delta_realized_pnl == Decimal("0") and not just_closed:
            return

        stats_date = datetime.now(timezone.utc).date()
        await self._ensure_stats_date(stats_date)
        if not self._daily_stats_persistence_available:
            return
        trade_count_delta = 1 if just_closed else 0

        if self._daily_stats_repository is None:
            if self._daily_stats_persistence_required:
                self.mark_daily_stats_persistence_unavailable()
                logger.error(
                    "Daily risk stats repository unavailable during exit projection; "
                    "future new entries will be blocked position_id=%s exit_order_id=%s",
                    position_id,
                    exit_order_id,
                )
                return
            await self.record_projected_realized_pnl_delta(delta_realized_pnl)
            if just_closed:
                await self.record_closed_trade()
            return

        event_key = self.build_daily_risk_event_key(
            scope_key=self._daily_stats_scope_key,
            stats_date=stats_date,
            position_id=position_id,
            exit_order_id=exit_order_id,
            projected_exit_qty_after=projected_exit_qty_after,
        )
        event = DailyRiskStatsEvent(
            event_key=event_key,
            scope_key=self._daily_stats_scope_key,
            stats_date=stats_date,
            position_id=position_id,
            signal_id=signal_id,
            exit_order_id=exit_order_id,
            delta_exit_qty=delta_exit_qty,
            delta_realized_pnl=delta_realized_pnl,
            trade_count_delta=trade_count_delta,
            occurred_at=occurred_at or datetime.now(timezone.utc),
        )
        try:
            result = await self._daily_stats_repository.record_event(event)
        except Exception as exc:
            self.mark_daily_stats_persistence_unavailable()
            logger.error(
                "Daily risk stats write-through failed; future new entries will be blocked "
                "position_id=%s exit_order_id=%s event_key=%s error=%s",
                position_id,
                exit_order_id,
                event_key,
                exc,
                exc_info=True,
            )
            return

        async with self._stats_lock:
            self._daily_stats = self._stats_from_snapshot(result.snapshot)

        if result.inserted:
            logger.info(
                "每日风险统计持久化更新：event_key=%s, delta_pnl=%s, trade_count_delta=%s, "
                "cumulative_pnl=%s, trade_count=%s",
                event_key,
                delta_realized_pnl,
                trade_count_delta,
                result.snapshot.realized_pnl,
                result.snapshot.trade_count,
            )

    @staticmethod
    def build_daily_risk_event_key(
        *,
        scope_key: str,
        stats_date: date,
        position_id: str,
        exit_order_id: str,
        projected_exit_qty_after: Decimal,
    ) -> str:
        normalized_qty = normalize_daily_risk_decimal(projected_exit_qty_after)
        return (
            f"daily-risk:v1:{scope_key}:{stats_date.isoformat()}:"
            f"{position_id}:{exit_order_id}:{normalized_qty}"
        )

    async def record_trade(
        self,
        realized_pnl: Decimal,
        *,
        increment_trade_count: bool = True,
    ) -> None:
        """兼容包装接口，避免旧调用点语义漂移。"""
        await self.record_projected_realized_pnl_delta(realized_pnl)
        if increment_trade_count:
            await self.record_closed_trade()

    async def reset_if_new_day(self) -> None:
        """
        如果是新的一天，重置统计

        每日重置逻辑：
        - trade_count = 0
        - realized_pnl = 0
        - last_reset_date = today
        """
        today_date = datetime.now(timezone.utc).date()
        await self._ensure_stats_date(today_date)

    async def _ensure_stats_date(self, stats_date: date) -> None:
        today = stats_date.isoformat()

        async with self._stats_lock:
            if today == self._daily_stats.last_reset_date:
                return

        if self._daily_stats_repository is not None and self._daily_stats_persistence_available:
            try:
                snapshot = await self._daily_stats_repository.restore_or_create(
                    self._daily_stats_scope_key,
                    stats_date,
                )
            except Exception as exc:
                self.mark_daily_stats_persistence_unavailable()
                logger.error(
                    "Daily risk stats restore failed during UTC day reset; "
                    "future new entries will be blocked scope_key=%s stats_date=%s error=%s",
                    self._daily_stats_scope_key,
                    today,
                    exc,
                    exc_info=True,
                )
                return
            async with self._stats_lock:
                old_date = self._daily_stats.last_reset_date
                self._daily_stats = self._stats_from_snapshot(snapshot)
                logger.info(f"每日统计已从持久化聚合恢复/重置：{old_date} -> {today}")
                return

        async with self._stats_lock:
            if today != self._daily_stats.last_reset_date:
                old_date = self._daily_stats.last_reset_date
                self._daily_stats.trade_count = 0
                self._daily_stats.realized_pnl = Decimal("0")
                self._daily_stats.last_reset_date = today
                logger.info(f"每日统计已重置：{old_date} -> {today}")

    async def get_daily_stats(self) -> DailyTradeStats:
        """
        获取每日统计

        Returns:
            DailyTradeStats: 当前统计信息
        """
        async with self._stats_lock:
            return self._daily_stats.model_copy()
